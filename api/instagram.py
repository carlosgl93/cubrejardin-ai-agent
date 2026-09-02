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

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.tenant_context import TenantContext, get_tenant_context
from channels.instagram import GRAPH_BASE
from config.settings import get_settings

router = APIRouter(prefix="/api/instagram", tags=["instagram"])


class ExchangeInstagramCodeRequest(BaseModel):
    auth_code: str
    redirect_uri: str = ""
    config_id: str = ""


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

    log = logging.getLogger(__name__)
    code = payload.auth_code
    redirect_uri = payload.redirect_uri
    config_id = payload.config_id
    log.info(
        "ig.exchange.start tenant=%s has_code=%s config_id=%s redirect_uri=%s",
        ctx.tenant_id, bool(code), bool(config_id), redirect_uri,
    )
    if not code:
        raise HTTPException(status_code=400, detail="auth_code required")

    settings = get_settings()
    app_id = settings.facebook_target_app_id
    app_secret = settings.facebook_app_secret

    # 1. Exchange code -> short-lived user token (FBL v4 infers redirect_uri
    # from the config_id used during the OAuth dialog, so we omit it here to
    # avoid the "redirect_uri is identical" mismatch error).
    token_resp = await _graph_get("/oauth/access_token", {
        "client_id": app_id,
        "client_secret": app_secret,
        "code": code,
        **({"config_id": config_id} if config_id else {}),
    })
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

    # 3. Resolve pages user manages
    me_resp = await _graph_get("/me/accounts", {"access_token": long_token})
    pages = me_resp.get("data") or []
    log.info("ig.exchange.pages tenant=%s count=%d", ctx.tenant_id, len(pages))
    if not pages:
        raise HTTPException(
            status_code=400,
            detail="No Facebook Pages found for this account",
        )

    # 4. Find a Page with a linked Instagram Professional account
    ig_user_id: Optional[str] = None
    page_id: Optional[str] = None
    page_access_token: Optional[str] = None
    for p in pages:
        try:
            r = await _graph_get(
                f"/{p['id']}",
                {
                    "fields": "instagram_business_account",
                    "access_token": p.get("access_token", long_token),
                },
            )
        except httpx.HTTPError:
            continue
        igba = r.get("instagram_business_account")
        if igba:
            ig_user_id = igba["id"]
            page_id = p["id"]
            page_access_token = p.get("access_token", long_token)
            break

    if not ig_user_id:
        log.info(
            "ig.exchange.no_ig tenant=%s page_ids=%s",
            ctx.tenant_id, [p.get("id") for p in pages],
        )
        raise HTTPException(
            status_code=400,
            detail="No Instagram Professional account linked to your Pages",
        )

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    row = {
        "ig_user_id": ig_user_id,
        "page_id": page_id,
        "page_access_token": page_access_token,
        "status": "active",
        "token_expires_at": expires_at.isoformat(),
        "raw_oauth_response": {
            "short_token_resp": _scrub_tokens(token_resp),
            "long_token_resp": _scrub_tokens(long_resp),
            "page_id": page_id,
        },
    }

    # Idempotency: if active row exists, narrow update preserves operator edits.
    existing = _supabase_fetch_ig_creds(ctx.tenant_id)
    if existing and existing.get("status") == "active":
        _supabase_update_ig_creds(ctx.tenant_id, {
            "page_access_token": page_access_token,
            "token_expires_at": expires_at.isoformat(),
            "page_id": page_id,
        })
    else:
        _supabase_upsert_ig_creds(ctx.tenant_id, row)

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