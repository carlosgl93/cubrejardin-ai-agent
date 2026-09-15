"""Shared Facebook / Meta OAuth code-exchange logic.

Single source of truth for the OAuth flow used by both the FastAPI route in
``api.facebook_auth`` and the ``WhatsAppAdapter.exchange_oauth`` channel
adapter. Returns a plain dict so callers can wrap it in whatever shape they
need (Pydantic model, adapter response, etc.).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import httpx

from config.settings import get_settings
from config.supabase import get_supabase_client

META_GRAPH_URL = "https://graph.facebook.com/v21.0"


async def _exchange_code_for_token(
    auth_code: str, client: httpx.AsyncClient
) -> Tuple[str, Optional[int]]:
    """Exchange a short-lived auth code for a user access token.

    Returns (access_token, expires_in_seconds). expires_in is None for
    non-expiring system user tokens.
    """
    from fastapi import HTTPException, status as http_status

    settings = get_settings()
    resp = await client.get(
        f"{META_GRAPH_URL}/oauth/access_token",
        params={
            "client_id": settings.facebook_target_app_id,
            "client_secret": settings.facebook_app_secret,
            "code": auth_code,
        },
    )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail=f"Meta token exchange failed: {resp.text}",
        )
    data = resp.json()
    if "access_token" not in data:
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail=f"No access_token in Meta response: {data}",
        )
    expires_in: Optional[int] = data.get("expires_in")
    if expires_in == 0:
        expires_in = None
    return data["access_token"], expires_in


async def _get_waba_info(
    token: str, client: httpx.AsyncClient
) -> Dict[str, Any]:
    """Discover the WABA and phone number ID from the user's token."""
    from fastapi import HTTPException, status as http_status

    settings = get_settings()
    app_token = f"{settings.facebook_target_app_id}|{settings.facebook_app_secret}"

    resp = await client.get(
        f"{META_GRAPH_URL}/debug_token",
        params={"input_token": token, "access_token": app_token},
    )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to debug token: {resp.text}",
        )

    debug_data = resp.json().get("data", {})
    granular_scopes = debug_data.get("granular_scopes", [])

    waba_id: Optional[str] = None
    for scope in granular_scopes:
        if scope.get("scope") == "whatsapp_business_management":
            target_ids = scope.get("target_ids", [])
            if target_ids:
                waba_id = target_ids[0]
                break

    if not waba_id:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No WhatsApp Business Account found in token scopes. "
            f"Scopes: {granular_scopes}",
        )

    resp2 = await client.get(
        f"{META_GRAPH_URL}/{waba_id}/phone_numbers",
        params={
            "access_token": token,
            "fields": "id,display_phone_number,verified_name",
        },
    )
    if resp2.status_code != 200:
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch phone numbers: {resp2.text}",
        )
    phone_numbers = resp2.json().get("data", [])
    if not phone_numbers:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No phone numbers found in the WhatsApp Business Account.",
        )

    return {
        "waba_id": waba_id,
        "phone_number_id": phone_numbers[0]["id"],
        "display_phone_number": phone_numbers[0].get("display_phone_number", ""),
    }


async def _discover_ig_account(
    token: str,
    client: httpx.AsyncClient,
    hinted_page_id: str = "",
    hinted_ig_user_id: str = "",
) -> Dict[str, Any]:
    """Find the IG business account linked to the user's page.

    Strategy:
      1. If sessionInfoListener surfaced page_id + ig_user_id, trust them.
      2. Else query /me/accounts with `fields=id,name,access_token,
         instagram_business_account{id,username}`. Pick first page that has
         an IG business account attached.

    Returns dict with page_id, page_access_token, ig_user_id, or empty
    values if IG scoping wasn't granted / no IG account found.
    """
    if hinted_page_id and hinted_ig_user_id:
        # Reuse the same long-lived user token as a page-scoped token if it
        # has `pages_show_list`; otherwise we need to ask Meta to surface one.
        return {
            "page_id": hinted_page_id,
            "ig_user_id": hinted_ig_user_id,
            "page_access_token": "",  # backend caller can choose to use token
            "source": "sessionInfoListener",
        }

    try:
        resp = await client.get(
            f"{META_GRAPH_URL}/me/accounts",
            params={
                "access_token": token,
                "fields": "id,name,access_token,instagram_business_account{id,username}",
            },
        )
        if resp.status_code != 200:
            return {"page_id": "", "ig_user_id": "", "page_access_token": "", "source": "error"}
        data = resp.json().get("data", [])
        for page in data:
            ig_obj = page.get("instagram_business_account")
            if ig_obj and ig_obj.get("id"):
                return {
                    "page_id": page["id"],
                    "ig_user_id": ig_obj["id"],
                    "page_access_token": page.get("access_token", ""),
                    "source": "me_accounts",
                }
    except Exception:
        pass
    return {"page_id": "", "ig_user_id": "", "page_access_token": "", "source": "not_found"}


async def _persist_ig_credentials(
    tenant_id: str,
    page_id: str,
    ig_user_id: str,
    page_access_token: str,
    long_token: str,
    expires_at_iso: Optional[str],
) -> bool:
    """Upsert row in tenant_instagram_credentials. Returns True on success."""
    if not (page_id and ig_user_id):
        return False
    sb = get_supabase_client()
    # Prefer the page-scoped token from /me/accounts; fall back to the
    # long-lived user token (page-scoped tokens inherit page-level scopes
    # granted through /me/accounts and don't inherit user scopes otherwise).
    effective_token = page_access_token or long_token
    row: Dict[str, Any] = {
        "tenant_id": tenant_id,
        "page_id": page_id,
        "ig_user_id": ig_user_id,
        "page_access_token": effective_token,
        "status": "active",
        "raw_oauth_response": {
            "source": "facebook_auth.exchange",
            "ig_granted_via": "wa_fbl_popup_scopes",
        },
    }
    if expires_at_iso:
        row["token_expires_at"] = expires_at_iso
    try:
        sb.table("tenant_instagram_credentials").upsert(
            row, on_conflict="tenant_id"
        ).execute()
        return True
    except Exception:
        return False


async def exchange_facebook_code_to_credentials(
    code: str,
    tenant_id: str,
    waba_id: str = "",
    phone_number_id: str = "",
    page_id: str = "",
    ig_user_id: str = "",
) -> Dict[str, Any]:
    """Exchange Meta OAuth code, resolve WABA + phone, persist WA + IG credentials.

    Returns dict with keys:
        access_token, waba_id, phone_number_id, token_expires_at, status,
        instagram_connected, page_id, ig_user_id
    """
    async with httpx.AsyncClient(timeout=30.0) as http:
        access_token, expires_in = await _exchange_code_for_token(code, http)

        if waba_id and phone_number_id:
            waba_info: Dict[str, Any] = {
                "waba_id": waba_id,
                "phone_number_id": phone_number_id,
                "display_phone_number": "",
            }
        else:
            waba_info = await _get_waba_info(access_token, http)

    token_expires_at: Optional[str] = None
    if expires_in:
        token_expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        ).isoformat()

    sb = get_supabase_client()
    existing = (
        sb.table("tenant_whatsapp_credentials")
        .select("status, whatsapp_business_account_id, phone_number_id")
        .eq("tenant_id", tenant_id)
        .limit(1)
        .execute()
    )

    already_active = (
        existing.data
        and existing.data[0].get("status") == "active"
        and existing.data[0].get("phone_number_id")
    )

    if already_active:
        update_payload: Dict[str, Any] = {"access_token": access_token}
        if token_expires_at is not None:
            update_payload["token_expires_at"] = token_expires_at
        sb.table("tenant_whatsapp_credentials").update(update_payload).eq(
            "tenant_id", tenant_id
        ).execute()
        saved_waba_id = existing.data[0]["whatsapp_business_account_id"]
        saved_phone_id = existing.data[0]["phone_number_id"]
    else:
        upsert_payload: Dict[str, Any] = {
            "tenant_id": tenant_id,
            "access_token": access_token,
            "whatsapp_business_account_id": waba_info["waba_id"],
            "phone_number_id": waba_info["phone_number_id"],
            "status": "active",
            "raw_oauth_response": {
                "waba_id": waba_info["waba_id"],
                "phone_number_id": waba_info["phone_number_id"],
                "display_phone_number": waba_info.get("display_phone_number", ""),
            },
        }
        if token_expires_at is not None:
            upsert_payload["token_expires_at"] = token_expires_at
        sb.table("tenant_whatsapp_credentials").upsert(
            upsert_payload, on_conflict="tenant_id"
        ).execute()
        saved_waba_id = waba_info["waba_id"]
        saved_phone_id = waba_info["phone_number_id"]

    # IG credentials: piggyback on the same OAuth. The dialog already grants
    # instagram_basic + instagram_manage_engagement + pages_messaging; this
    # call discovers the IG business account linked to the user's page.
    ig_info = await _discover_ig_simple(access_token, page_id, ig_user_id)

    ig_persisted = False
    if ig_info["page_id"] and ig_info["ig_user_id"]:
        ig_persisted = await _persist_ig_credentials(
            tenant_id=tenant_id,
            page_id=ig_info["page_id"],
            ig_user_id=ig_info["ig_user_id"],
            page_access_token=ig_info.get("page_access_token", ""),
            long_token=access_token,
            expires_at_iso=token_expires_at,
        )

    return {
        "access_token": access_token,
        "waba_id": saved_waba_id,
        "phone_number_id": saved_phone_id,
        "token_expires_at": token_expires_at,
        "status": "active",
        "instagram_connected": ig_persisted,
        "page_id": ig_info.get("page_id", ""),
        "ig_user_id": ig_info.get("ig_user_id", ""),
    }


async def _discover_ig_simple(
    token: str, hinted_page_id: str = "", hinted_ig_user_id: str = ""
) -> Dict[str, Any]:
    """Stand-alone IG discoverer. Re-opens its own httpx client."""
    async with httpx.AsyncClient(timeout=30.0) as http:
        return await _discover_ig_account(
            token, http, hinted_page_id, hinted_ig_user_id
        )