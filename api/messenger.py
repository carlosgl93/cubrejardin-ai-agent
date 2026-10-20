"""Facebook Messenger OAuth code exchange and status endpoints.

Mirrors ``api.instagram`` for the Facebook Page Messenger channel.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.tenant_context import TenantContext, get_tenant_context
from channels.messenger import GRAPH_BASE
from config.settings import get_settings
from services.facebook_auth import subscribe_page_to_app

router = APIRouter(prefix="/api/messenger", tags=["messenger"])


class ExchangeMessengerCodeRequest(BaseModel):
    auth_code: str
    redirect_uri: str = ""
    config_id: str = ""
    page_id: str = ""


class ExchangeMessengerCodeResponse(BaseModel):
    page_id: str
    status: str
    token_expires_at: str


class MessengerStatusResponse(BaseModel):
    messenger_connected: bool
    status: str
    page_id: str | None = None
    token_expires_at: str | None = None


async def _graph_get(path: str, params: dict) -> dict[str, Any]:
    """Async GET helper against Graph API."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{GRAPH_BASE}{path}", params=params)
    if resp.status_code >= 400:
        import logging
        logging.getLogger(__name__).error(
            "Meta %s %s -> %s body=%s", "GET", path, resp.status_code, resp.text[:1000]
        )
    resp.raise_for_status()
    return resp.json()


def _scrub_tokens(resp: dict) -> dict:
    """Remove secrets from a token response before persistence."""
    scrubbed = dict(resp)
    scrubbed.pop("access_token", None)
    return scrubbed


def _supabase_client():
    from config.supabase import get_supabase_client
    return get_supabase_client()


def _supabase_fetch_messenger_creds(tenant_id: str) -> Optional[dict]:
    supabase = _supabase_client()
    try:
        res = (
            supabase.table("tenant_messenger_credentials")
            .select("*")
            .eq("tenant_id", tenant_id)
            .limit(1)
            .maybe_single()
            .execute()
        )
        if res and res.data:
            return res.data
        # Fall back to checking tenant_instagram_credentials
        res_ig = (
            supabase.table("tenant_instagram_credentials")
            .select("*")
            .eq("tenant_id", tenant_id)
            .limit(1)
            .maybe_single()
            .execute()
        )
        return res_ig.data if res_ig else None
    except Exception:
        return None


def _supabase_upsert_messenger_creds(tenant_id: str, row: dict) -> None:
    supabase = _supabase_client()
    supabase.table("tenant_messenger_credentials").upsert(
        {"tenant_id": tenant_id, **row}, on_conflict="tenant_id"
    ).execute()


def _supabase_update_messenger_creds(tenant_id: str, updates: dict) -> None:
    supabase = _supabase_client()
    supabase.table("tenant_messenger_credentials").update(updates).eq(
        "tenant_id", tenant_id
    ).execute()


@router.post("/exchange", response_model=ExchangeMessengerCodeResponse)
async def exchange(
    payload: ExchangeMessengerCodeRequest,
    ctx: TenantContext = Depends(get_tenant_context),
):
    code = payload.auth_code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="auth_code required")

    settings = get_settings()
    app_id = settings.facebook_target_app_id
    app_secret = settings.facebook_app_secret

    token_params = {
        "client_id": app_id,
        "client_secret": app_secret,
        "code": code,
        "redirect_uri": payload.redirect_uri or "https://www.facebook.com/connect/login_success.html",
    }
    if payload.config_id:
        token_params["config_id"] = payload.config_id

    token_resp = await _graph_get("/oauth/access_token", token_params)
    if "access_token" not in token_resp:
        raise HTTPException(status_code=502, detail="Meta token exchange failed")
    short_token = token_resp["access_token"]

    long_resp = await _graph_get("/oauth/access_token", {
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": short_token,
    })
    if "access_token" not in long_resp:
        raise HTTPException(status_code=502, detail="Meta long-lived token exchange failed")
    long_token = long_resp["access_token"]
    expires_in = long_resp.get("expires_in", 5184000)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    page_id = payload.page_id
    page_access_token = ""

    if page_id:
        try:
            page_query = await _graph_get(
                f"/{page_id}",
                {"fields": "access_token", "access_token": long_token},
            )
            page_access_token = page_query.get("access_token", "")
        except Exception:
            pass

    if not page_id:
        # Discover first Page
        try:
            accounts_resp = await _graph_get(
                "/me/accounts",
                {"access_token": long_token, "fields": "id,name,access_token"},
            )
            data = accounts_resp.get("data", [])
            if data:
                page_id = data[0]["id"]
                page_access_token = data[0].get("access_token", "")
        except Exception:
            pass

    if not page_id:
        raise HTTPException(status_code=422, detail="No Facebook Page found")

    effective_token = page_access_token or long_token

    row = {
        "page_id": page_id,
        "page_access_token": effective_token,
        "status": "active",
        "token_expires_at": expires_at.isoformat(),
        "raw_oauth_response": {
            "source": "api.messenger.exchange",
            "short_token_resp": _scrub_tokens(token_resp),
            "long_token_resp": _scrub_tokens(long_resp),
            "page_id": page_id,
        },
    }

    existing = _supabase_fetch_messenger_creds(ctx.tenant_id)
    if existing and existing.get("status") == "active":
        _supabase_update_messenger_creds(ctx.tenant_id, {
            "page_access_token": effective_token,
            "token_expires_at": expires_at.isoformat(),
            "page_id": page_id,
        })
    else:
        _supabase_upsert_messenger_creds(ctx.tenant_id, row)

    if effective_token:
        await subscribe_page_to_app(page_id, effective_token)

    return ExchangeMessengerCodeResponse(
        page_id=page_id,
        status="active",
        token_expires_at=expires_at.isoformat(),
    )


@router.get("/status", response_model=MessengerStatusResponse)
async def status(ctx: TenantContext = Depends(get_tenant_context)):
    row = _supabase_fetch_messenger_creds(ctx.tenant_id)
    if not row:
        return {
            "messenger_connected": False,
            "status": "absent",
        }
    return {
        "messenger_connected": row.get("status") == "active",
        "status": row.get("status", "absent"),
        "page_id": row.get("page_id"),
        "token_expires_at": row.get("token_expires_at"),
    }
