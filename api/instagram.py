"""Instagram OAuth code exchange endpoint.

Mirrors ``api.facebook_auth`` but resolves the IG Professional account linked
to one of the user's Facebook Pages instead of WABA + phone. Flow:
  1. code -> short-lived user token
  2. short token -> long-lived user token (~60d)
  3. /me/accounts to list Pages the user manages
  4. For each Page, fetch instagram_business_account
  5. Upsert tenant_instagram_credentials
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.tenant_context import TenantContext, get_tenant_context
from channels.instagram import GRAPH_BASE
from config.settings import get_settings
from services.facebook_auth import subscribe_page_to_app

router = APIRouter(prefix="/api/instagram", tags=["instagram"])


class ExchangeInstagramCodeRequest(BaseModel):
    auth_code: str
    redirect_uri: str = ""
    config_id: str = ""
    # Captured from sessionInfoListener on the FBL popup. When present, the
    # backend skips page/IG discovery (which fails for system-user tokens
    # issued by FBL) and writes the connection directly.
    page_id: str = ""
    ig_user_id: str = ""


class ExchangeInstagramCodeResponse(BaseModel):
    ig_user_id: str
    page_id: str
    status: str
    token_expires_at: str


class InstagramStatusResponse(BaseModel):
    instagram_connected: bool
    status: str
    ig_user_id: str | None = None
    page_id: str | None = None
    token_expires_at: str | None = None


async def _graph_get(path: str, params: dict) -> dict[str, Any]:
    """Async GET helper against Graph API. Wrapped for tests.

    Meta's auth/code-exchange endpoints are GET with query params.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{GRAPH_BASE}{path}", params=params)
    if resp.status_code >= 400:
        # raise_for_status would discard Meta's actual error body; log it first
        # so we see WHY Meta rejected the request (redirect_uri mismatch,
        # invalid code, missing config_id, etc.).
        import logging

        logging.getLogger(__name__).error(
            "Meta %s %s -> %s body=%s",
            "GET",
            path,
            resp.status_code,
            resp.text[:1000],
        )
    resp.raise_for_status()
    return resp.json()


def _scrub_tokens(resp: dict) -> dict:
    """Remove secrets from a token response before persistence."""
    scrubbed = dict(resp)
    scrubbed.pop("access_token", None)
    return scrubbed


def _supabase_client():
    """Service-role Supabase client (bypasses RLS).

    ``get_supabase_client`` already uses the service role key — appropriate
    for server-to-server writes.
    """
    from config.supabase import get_supabase_client

    return get_supabase_client()


def _supabase_fetch_ig_creds(tenant_id: str) -> Optional[dict]:
    supabase = _supabase_client()
    try:
        res = (
            supabase.table("tenant_instagram_credentials")
            .select("*")
            .eq("tenant_id", tenant_id)
            .limit(1)
            .maybe_single()
            .execute()
        )
        if not res or not getattr(res, "data", None):
            return None
        return res.data
    except Exception:
        return None


def _supabase_update_ig_creds(tenant_id: str, updates: dict) -> None:
    supabase = _supabase_client()
    supabase.table("tenant_instagram_credentials").update(updates).eq(
        "tenant_id", tenant_id
    ).execute()


def _supabase_upsert_ig_creds(tenant_id: str, row: dict) -> None:
    """Mockable indirection — real impl writes via supabase client."""
    supabase = _supabase_client()
    supabase.table("tenant_instagram_credentials").upsert(
        {"tenant_id": tenant_id, **row},
        on_conflict="tenant_id",
    ).execute()


@router.post(
    "/exchange",
    response_model=ExchangeInstagramCodeResponse,
)
async def exchange(
    payload: ExchangeInstagramCodeRequest,
    ctx: TenantContext = Depends(get_tenant_context),
):
    import logging

    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger(__name__)
    code = payload.auth_code
    redirect_uri = payload.redirect_uri
    config_id = payload.config_id
    print(
        f"[ig.exchange] start tenant={ctx.tenant_id} has_code={bool(code)} "
        f"config_id={config_id!r} redirect_uri={redirect_uri!r} "
        f"page_id={payload.page_id!r} ig_user_id={payload.ig_user_id!r} "
        f"INSTAGRAM_PAGE_ID={os.getenv('INSTAGRAM_PAGE_ID', '<unset>')!r}",
        flush=True,
    )
    if not code:
        raise HTTPException(status_code=400, detail="auth_code required")

    settings = get_settings()
    app_id = settings.facebook_target_app_id
    app_secret = settings.facebook_app_secret

    # 1. Exchange code -> short-lived user token.
    # For standard OAuth (no FBL), FB.login locks redirect_uri to the page
    # origin at popup time. Frontend MUST mirror the same URL here or Meta
    # rejects with 191. For FBL configs with User access token type, Meta
    # ALSO requires redirect_uri (rejects with 36008 "redirect_uri is
    # identical" if omitted). System-user configs tolerate omission, but
    # sending redirect_uri is harmless.
    token_params = {
        "client_id": app_id,
        "client_secret": app_secret,
        "code": code,
    }
    if config_id:
        token_params["config_id"] = config_id
        # Frontend sends the page-origin URL that FB.login captured.
        token_params["redirect_uri"] = (
            redirect_uri
            or "https://www.facebook.com/connect/login_success.html"
        )
    else:
        token_params["redirect_uri"] = (
            redirect_uri
            or "https://www.facebook.com/connect/login_success.html"
        )
    token_resp = await _graph_get("/oauth/access_token", token_params)
    if "access_token" not in token_resp:
        raise HTTPException(
            status_code=502,
            detail="Meta token exchange failed",
        )
    short_token = token_resp["access_token"]

    # 2. Exchange short -> long-lived (~60 days)
    long_resp = await _graph_get("/oauth/access_token", {
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": short_token,
    })
    if "access_token" not in long_resp:
        raise HTTPException(
            status_code=502,
            detail="Meta long-lived token exchange failed",
        )
    long_token = long_resp["access_token"]
    expires_in = long_resp.get("expires_in", 5184000)

    # 3. Resolve page_id and ig_user_id
    page_id = payload.page_id.strip() if payload.page_id else ""
    ig_user_id = payload.ig_user_id.strip() if payload.ig_user_id else ""

    # 3a. Inspect token via /debug_token to read granular_scopes
    app_token = f"{app_id}|{app_secret}"
    debug_data: dict[str, Any] = {}
    try:
        debug_resp = await _graph_get(
            "/debug_token",
            {"input_token": long_token, "access_token": app_token},
        )
        debug_data = debug_resp.get("data", {})
        granular_scopes = debug_data.get("granular_scopes", [])
        print(f"[ig.exchange] debug_token granular_scopes: {granular_scopes}", flush=True)

        for item in granular_scopes:
            scope = item.get("scope", "")
            target_ids = item.get("target_ids", [])
            if not target_ids:
                continue
            if not ig_user_id and scope in (
                "instagram_manage_engagement",
                "instagram_manage_messages",
                "instagram_basic",
            ):
                ig_user_id = str(target_ids[0])
            elif not page_id and scope in (
                "pages_messaging",
                "pages_show_list",
                "pages_read_engagement",
                "pages_manage_metadata",
            ):
                page_id = str(target_ids[0])
    except Exception as e:
        print(f"[ig.exchange] debug_token inspect failed: {e}", flush=True)

    # 3b. If page_id is known, query it with long_token to get page_access_token & linked IG account
    page_access_token = ""
    if page_id:
        try:
            page_query = await _graph_get(
                f"/{page_id}",
                {"fields": "access_token,instagram_business_account", "access_token": long_token},
            )
            page_access_token = page_query.get("access_token", "")
            if not ig_user_id and page_query.get("instagram_business_account"):
                ig_user_id = str(page_query["instagram_business_account"].get("id", ""))
        except Exception as e:
            print(f"[ig.exchange] direct page query with long_token failed: {e}", flush=True)

    # 3c. If ig_user_id is known but not page_id, query IG user for linked page
    if ig_user_id and not page_id:
        try:
            ig_resp = await _graph_get(
                f"/{ig_user_id}",
                {"fields": "id,username,name,page{id,name}", "access_token": long_token},
            )
            page_obj = ig_resp.get("page")
            if page_obj:
                page_id = str(page_obj["id"])
                try:
                    pq = await _graph_get(
                        f"/{page_id}",
                        {"fields": "access_token", "access_token": long_token},
                    )
                    page_access_token = pq.get("access_token", "")
                except Exception:
                    pass
        except Exception as e:
            print(f"[ig.exchange] ig_user query failed: {e}", flush=True)

    # 3d. Resolve page_access_token and linked IG via /me/accounts with user long_token
    if not page_id or not ig_user_id or not page_access_token:
        try:
            me_resp = await _graph_get(
                "/me/accounts",
                {"access_token": long_token, "fields": "id,name,access_token,instagram_business_account"},
            )
            for p in me_resp.get("data", []):
                p_id = str(p["id"])
                p_token = p.get("access_token", "")
                p_ig = p.get("instagram_business_account", {}).get("id") if p.get("instagram_business_account") else None

                if page_id and p_id == page_id:
                    if p_token:
                        page_access_token = p_token
                    if p_ig:
                        ig_user_id = str(p_ig)
                    break
                elif not page_id:
                    page_id = p_id
                    if p_token:
                        page_access_token = p_token
                    if p_ig:
                        ig_user_id = str(p_ig)
                    break
        except Exception as e:
            print(f"[ig.exchange] /me/accounts failed: {e}", flush=True)

    # 3e. Env var fallbacks for single-tenant / local development
    if not ig_user_id:
        ig_user_id = os.getenv("INSTAGRAM_IG_USER_ID", "")
    if not page_id:
        page_id = os.getenv("INSTAGRAM_PAGE_ID", "")

    if not ig_user_id:
        print(
            f"[ig.exchange] failed to resolve ig_user_id tenant={ctx.tenant_id} page_id={page_id} debug_data={debug_data}",
            flush=True,
        )
        raise HTTPException(
            status_code=400,
            detail="No Instagram Professional account linked to your Pages",
        )

    # Fall back to long_token if page_access_token wasn't separately returned
    effective_token = page_access_token or long_token

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    row = {
        "ig_user_id": ig_user_id,
        "page_id": page_id,
        "page_access_token": effective_token,
        "status": "active",
        "token_expires_at": expires_at.isoformat(),
        "raw_oauth_response": {
            "short_token_resp": _scrub_tokens(token_resp),
            "long_token_resp": _scrub_tokens(long_resp),
            "debug_token": debug_data,
            "page_id": page_id,
            "ig_user_id": ig_user_id,
        },
    }

    # Upsert Instagram credentials
    existing = _supabase_fetch_ig_creds(ctx.tenant_id)
    if existing and existing.get("status") == "active":
        _supabase_update_ig_creds(ctx.tenant_id, {
            "page_access_token": effective_token,
            "token_expires_at": expires_at.isoformat(),
            "page_id": page_id,
            "ig_user_id": ig_user_id,
        })
    else:
        _supabase_upsert_ig_creds(ctx.tenant_id, row)

    # Also upsert Facebook Messenger credentials if page_id is known
    if page_id:
        try:
            from api.messenger import (
                _supabase_fetch_messenger_creds,
                _supabase_update_messenger_creds,
                _supabase_upsert_messenger_creds,
            )
            msg_existing = _supabase_fetch_messenger_creds(ctx.tenant_id)
            if msg_existing and msg_existing.get("status") == "active":
                _supabase_update_messenger_creds(ctx.tenant_id, {
                    "page_access_token": effective_token,
                    "token_expires_at": expires_at.isoformat(),
                    "page_id": page_id,
                })
            else:
                _supabase_upsert_messenger_creds(ctx.tenant_id, {
                    "page_id": page_id,
                    "page_access_token": effective_token,
                    "status": "active",
                    "token_expires_at": expires_at.isoformat(),
                    "raw_oauth_response": {
                        "source": "api.instagram.exchange",
                        "page_id": page_id,
                    },
                })
        except Exception as e:
            print(f"[ig.exchange] messenger creds upsert failed: {e}", flush=True)

    # Subscribe page to webhooks for inbound DMs
    if page_id and effective_token:
        await subscribe_page_to_app(page_id, effective_token)

    print(
        f"[ig.exchange] success tenant={ctx.tenant_id} page_id={page_id} ig_user_id={ig_user_id}",
        flush=True,
    )

    return ExchangeInstagramCodeResponse(
        ig_user_id=ig_user_id,
        page_id=page_id,
        status="active",
        token_expires_at=expires_at.isoformat(),
    )


@router.get("/status", response_model=InstagramStatusResponse)
async def status(ctx: TenantContext = Depends(get_tenant_context)):
    row = _supabase_fetch_ig_creds(ctx.tenant_id)
    if not row:
        return {
            "instagram_connected": False,
            "status": "absent",
        }
    return {
        "instagram_connected": row.get("status") == "active",
        "status": row.get("status"),
        "ig_user_id": row.get("ig_user_id"),
        "page_id": row.get("page_id"),
        "token_expires_at": row.get("token_expires_at"),
    }