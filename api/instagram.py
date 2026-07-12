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
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException

from api.tenant_context import TenantContext, get_tenant_context
from channels.instagram import GRAPH_BASE

router = APIRouter(prefix="/api/instagram", tags=["instagram"])


def _graph_post(path: str, params: dict) -> dict[str, Any]:
    """GET helper against Graph API. Wrapped for tests.

    Meta's auth/code-exchange endpoints are GET with query params; using GET
    here for parity with the /oauth/access_token endpoint shape.
    """
    resp = httpx.get(f"{GRAPH_BASE}{path}", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _supabase_upsert_ig_creds(tenant_id: str, row: dict) -> None:
    """Mockable indirection — real impl writes via supabase client."""
    from config.supabase import get_supabase_client

    supabase = get_supabase_client()
    supabase.table("tenant_instagram_credentials").upsert(
        {"tenant_id": tenant_id, **row},
        on_conflict="tenant_id",
    ).execute()


@router.post("/exchange")
async def exchange(
    payload: dict,
    ctx: TenantContext = Depends(get_tenant_context),
):
    code = payload.get("auth_code")
    redirect_uri = payload.get("redirect_uri", "")
    if not code:
        raise HTTPException(status_code=400, detail="auth_code required")

    from config.settings import get_settings

    settings = get_settings()
    app_id = settings.facebook_target_app_id
    app_secret = settings.facebook_app_secret

    # 1. Exchange code -> short-lived user token
    token_resp = _graph_post("/oauth/access_token", {
        "client_id": app_id,
        "client_secret": app_secret,
        "redirect_uri": redirect_uri,
        "code": code,
    })
    short_token = token_resp["access_token"]

    # 2. Exchange short -> long-lived (~60 days)
    long_resp = _graph_post("/oauth/access_token", {
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": short_token,
    })
    long_token = long_resp["access_token"]
    expires_in = long_resp.get("expires_in", 5184000)

    # 3. Resolve pages user manages
    me_resp = _graph_post("/me/accounts", {"access_token": long_token})
    pages = me_resp.get("data") or []
    if not pages:
        raise HTTPException(
            status_code=400,
            detail="No Facebook Pages found for this account",
        )

    page_id = pages[0]["id"]
    page_access_token = pages[0].get("access_token", long_token)

    # 4. Find a Page with a linked Instagram Professional account
    ig_user_id = None
    for p in pages:
        try:
            r = _graph_post(
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
        raise HTTPException(
            status_code=400,
            detail="No Instagram Professional account linked to your Pages",
        )

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    row = {
        "ig_user_id": ig_user_id,
        "page_id": page_id,
        "page_access_token": page_access_token,
        "app_secret": app_secret,
        "status": "active",
        "token_expires_at": expires_at.isoformat(),
        "raw_oauth_response": {
            "short_token_resp": token_resp,
            "long_token_resp": long_resp,
            "page_id": page_id,
        },
    }
    _supabase_upsert_ig_creds(ctx.tenant_id, row)

    return {
        "ig_user_id": ig_user_id,
        "page_id": page_id,
        "status": "active",
        "token_expires_at": row["token_expires_at"],
    }
