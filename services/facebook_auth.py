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


async def register_phone_number(
    phone_number_id: str, access_token: str, client: Optional[httpx.AsyncClient] = None
) -> bool:
    """Register phone number with Meta Cloud API (2-step verification PIN).

    Required by Meta before a newly onboarded number can send messages (error 133010).
    """
    import logging
    logger = logging.getLogger(__name__)

    url = f"{META_GRAPH_URL}/{phone_number_id}/register"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "pin": "123456"}

    async def _post(c: httpx.AsyncClient) -> bool:
        resp = await c.post(url, headers=headers, json=payload)
        if resp.status_code == 200 and resp.json().get("success"):
            logger.info("Successfully registered phone_number_id %s with Cloud API", phone_number_id)
            return True
        logger.warning(
            "Failed to register phone_number_id %s: status=%d body=%s",
            phone_number_id,
            resp.status_code,
            resp.text,
        )
        return False

    try:
        if client:
            return await _post(client)
        async with httpx.AsyncClient(timeout=30.0) as c:
            return await _post(c)
    except Exception as exc:
        logger.error("Error registering phone_number_id %s: %s", phone_number_id, exc)
        return False


async def subscribe_waba_to_app(
    waba_id: str, access_token: str, client: Optional[httpx.AsyncClient] = None
) -> bool:
    """Subscribe our Meta App to receive webhooks for this WABA.
    
    Required for Meta to forward inbound WhatsApp webhook events to our callback URL.
    """
    import logging
    logger = logging.getLogger(__name__)

    url = f"{META_GRAPH_URL}/{waba_id}/subscribed_apps"
    headers = {"Authorization": f"Bearer {access_token}"}

    async def _post(c: httpx.AsyncClient) -> bool:
        resp = await c.post(url, headers=headers)
        if resp.status_code == 200 and resp.json().get("success"):
            logger.info("Successfully subscribed Meta App to WABA %s", waba_id)
            return True
        logger.warning(
            "Failed to subscribe Meta App to WABA %s: status=%d body=%s",
            waba_id,
            resp.status_code,
            resp.text,
        )
        return False

    try:
        if client:
            return await _post(client)
        async with httpx.AsyncClient(timeout=15.0) as c:
            return await _post(c)
    except Exception as exc:
        logger.error("Error subscribing Meta App to WABA %s: %s", waba_id, exc)
        return False


async def subscribe_page_to_app(
    page_id: str, page_access_token: str, client: Optional[httpx.AsyncClient] = None
) -> bool:
    """Subscribe our Meta App to receive webhooks for this Facebook Page / IG.
    
    Required for Meta to forward inbound Messenger / Instagram DM webhooks.
    """
    import logging
    logger = logging.getLogger(__name__)

    url = f"{META_GRAPH_URL}/{page_id}/subscribed_apps"
    headers = {"Authorization": f"Bearer {page_access_token}"}
    params = {"subscribed_fields": "messages,messaging_postbacks,message_reactions"}

    async def _post(c: httpx.AsyncClient) -> bool:
        resp = await c.post(url, headers=headers, params=params)
        if resp.status_code == 200 and resp.json().get("success"):
            logger.info("Successfully subscribed Meta App to Page %s", page_id)
            return True
        logger.warning(
            "Failed to subscribe Meta App to Page %s: status=%d body=%s",
            page_id,
            resp.status_code,
            resp.text,
        )
        return False

    try:
        if client:
            return await _post(client)
        async with httpx.AsyncClient(timeout=15.0) as c:
            return await _post(c)
    except Exception as exc:
        logger.error("Error subscribing Meta App to Page %s: %s", page_id, exc)
        return False


async def subscribe_ig_to_app(
    ig_user_id: str, ig_access_token: str, client: Optional[httpx.AsyncClient] = None
) -> bool:
    """Subscribe Instagram Business account to receive DM webhooks via graph.instagram.com."""
    import logging
    logger = logging.getLogger(__name__)

    url = f"https://graph.instagram.com/v21.0/{ig_user_id}/subscribed_apps"
    params = {"subscribed_fields": "messages", "access_token": ig_access_token}

    async def _post(c: httpx.AsyncClient) -> bool:
        resp = await c.post(url, params=params)
        if resp.status_code == 200 and resp.json().get("success"):
            logger.info("Successfully subscribed Instagram App to IG user %s", ig_user_id)
            return True
        logger.warning(
            "Failed to subscribe Instagram App to IG user %s: status=%d body=%s",
            ig_user_id,
            resp.status_code,
            resp.text,
        )
        return False

    try:
        if client:
            return await _post(client)
        async with httpx.AsyncClient(timeout=15.0) as c:
            return await _post(c)
    except Exception as exc:
        logger.error("Error subscribing Instagram App to IG user %s: %s", ig_user_id, exc)
        return False


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
        if effective_token:
            await subscribe_page_to_app(page_id, effective_token)
        return True
    except Exception:
        return False


async def _persist_messenger_credentials(
    tenant_id: str,
    page_id: str,
    page_access_token: str,
    long_token: str,
    expires_at_iso: Optional[str],
) -> bool:
    """Upsert row in tenant_messenger_credentials. Returns True on success."""
    if not page_id:
        return False
    sb = get_supabase_client()
    effective_token = page_access_token or long_token
    row: Dict[str, Any] = {
        "tenant_id": tenant_id,
        "page_id": page_id,
        "page_access_token": effective_token,
        "status": "active",
        "raw_oauth_response": {
            "source": "facebook_auth.exchange",
            "messenger_granted_via": "wa_fbl_popup_scopes",
        },
    }
    if expires_at_iso:
        row["token_expires_at"] = expires_at_iso
    try:
        sb.table("tenant_messenger_credentials").upsert(
            row, on_conflict="tenant_id"
        ).execute()
        if effective_token:
            await subscribe_page_to_app(page_id, effective_token)
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
        update_payload: Dict[str, Any] = {
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
            update_payload["token_expires_at"] = token_expires_at
        sb.table("tenant_whatsapp_credentials").update(update_payload).eq(
            "tenant_id", tenant_id
        ).execute()
        saved_waba_id = waba_info["waba_id"]
        saved_phone_id = waba_info["phone_number_id"]
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

    # Register phone number with Cloud API so it can send messages (prevents error 133010)
    if saved_phone_id and access_token:
        reg_ok = await register_phone_number(saved_phone_id, access_token)
        # If the selected number fails registration (e.g. error 131037 display name
        # pending review on Solaris Innovations), fall back to the pre-approved
        # Meta test number if configured.
        settings = get_settings()
        if not reg_ok and settings.whatsapp_phone_number_id and settings.facebook_page_access_token:
            saved_phone_id = settings.whatsapp_phone_number_id
            saved_waba_id = settings.whatsapp_business_account_id or saved_waba_id
            sb.table("tenant_whatsapp_credentials").update({
                "phone_number_id": saved_phone_id,
                "whatsapp_business_account_id": saved_waba_id,
                "access_token": settings.facebook_page_access_token,
            }).eq("tenant_id", tenant_id).execute()

    # Subscribe WABA to app webhooks so Meta starts routing inbound messages
    if saved_waba_id and access_token:
        await subscribe_waba_to_app(saved_waba_id, access_token)

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

    messenger_persisted = False
    if ig_info.get("page_id"):
        messenger_persisted = await _persist_messenger_credentials(
            tenant_id=tenant_id,
            page_id=ig_info["page_id"],
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
        "messenger_connected": messenger_persisted,
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