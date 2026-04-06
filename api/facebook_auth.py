"""Facebook / Meta OAuth code exchange endpoint.

Flow:
  1. Frontend completes FB Embedded Signup and receives a short-lived auth code.
  2. Frontend POSTs the code here with its Supabase JWT.
  3. This endpoint exchanges the code for a user access token via Meta Graph API.
  4. Discovers the WABA ID and phone number ID for the tenant.
  5. Upserts tenant_whatsapp_credentials with status='active'.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.tenant_context import TenantContext, get_tenant_context
from config.settings import get_settings
from config.supabase import get_supabase_client

router = APIRouter()

META_GRAPH_URL = "https://graph.facebook.com/v21.0"


# ── Models ────────────────────────────────────────────────────────────────


class ExchangeCodeRequest(BaseModel):
    auth_code: str
    waba_id: str = ""  # from Embedded Signup sessionInfoListener
    phone_number_id: str = ""  # from Embedded Signup sessionInfoListener


class ExchangeCodeResponse(BaseModel):
    tenant_id: str
    waba_id: str
    phone_number_id: str
    status: str


# ── Helpers ───────────────────────────────────────────────────────────────


async def _exchange_code_for_token(auth_code: str, client: httpx.AsyncClient) -> tuple[str, Optional[int]]:
    """Exchange a short-lived auth code for a user access token.

    Returns (access_token, expires_in_seconds). expires_in is None for
    non-expiring system user tokens.
    """
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
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Meta token exchange failed: {resp.text}",
        )
    data = resp.json()
    if "access_token" not in data:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No access_token in Meta response: {data}",
        )
    expires_in: Optional[int] = data.get("expires_in")
    # Meta returns 0 for system user tokens (non-expiring)
    if expires_in == 0:
        expires_in = None
    return data["access_token"], expires_in


async def _get_waba_info(
    token: str, client: httpx.AsyncClient
) -> Dict[str, Any]:
    """Discover the WABA and phone number ID from the user's token.

    Uses debug_token to inspect granular_scopes — this works with the
    limited permissions granted by Embedded Signup (whatsapp_business_management
    + whatsapp_business_messaging) without needing business_management.
    """
    settings = get_settings()
    app_token = f"{settings.facebook_target_app_id}|{settings.facebook_app_secret}"

    # Step 1: Inspect the user token via debug_token
    resp = await client.get(
        f"{META_GRAPH_URL}/debug_token",
        params={
            "input_token": token,
            "access_token": app_token,
        },
    )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to debug token: {resp.text}",
        )

    debug_data = resp.json().get("data", {})
    granular_scopes = debug_data.get("granular_scopes", [])

    # Extract WABA ID from granular_scopes
    waba_id: Optional[str] = None
    for scope in granular_scopes:
        if scope.get("scope") == "whatsapp_business_management":
            target_ids = scope.get("target_ids", [])
            if target_ids:
                waba_id = target_ids[0]
                break

    if not waba_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No WhatsApp Business Account found in token scopes. "
            f"Scopes: {granular_scopes}",
        )

    # Step 2: Get phone numbers for the WABA using the user token
    resp2 = await client.get(
        f"{META_GRAPH_URL}/{waba_id}/phone_numbers",
        params={
            "access_token": token,
            "fields": "id,display_phone_number,verified_name",
        },
    )
    if resp2.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch phone numbers: {resp2.text}",
        )
    phone_numbers = resp2.json().get("data", [])
    if not phone_numbers:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No phone numbers found in the WhatsApp Business Account.",
        )

    return {
        "waba_id": waba_id,
        "phone_number_id": phone_numbers[0]["id"],
        "display_phone_number": phone_numbers[0].get("display_phone_number", ""),
    }


# ── Endpoint ──────────────────────────────────────────────────────────────


@router.post("/exchange", response_model=ExchangeCodeResponse)
async def exchange_facebook_code(
    body: ExchangeCodeRequest,
    ctx: TenantContext = Depends(get_tenant_context),
) -> ExchangeCodeResponse:
    """Exchange a Facebook auth code for a WhatsApp Business access token.

    Saves the resulting credentials to tenant_whatsapp_credentials with
    status='active' and returns the resolved WABA / phone number IDs.
    """
    async with httpx.AsyncClient(timeout=30.0) as http:
        # 1. Exchange code → token
        access_token, expires_in = await _exchange_code_for_token(body.auth_code, http)

        # 2. Use WABA info from Embedded Signup callback, or discover via API
        if body.waba_id and body.phone_number_id:
            waba_info = {
                "waba_id": body.waba_id,
                "phone_number_id": body.phone_number_id,
                "display_phone_number": "",
            }
        else:
            waba_info = await _get_waba_info(access_token, http)

    # Compute expiry timestamp (None → non-expiring system user token)
    token_expires_at: Optional[str] = None
    if expires_in:
        token_expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        ).isoformat()

    # 3. Save credentials — if already active, only refresh the token
    sb = get_supabase_client()
    existing = (
        sb.table("tenant_whatsapp_credentials")
        .select("status, whatsapp_business_account_id, phone_number_id")
        .eq("tenant_id", ctx.tenant_id)
        .limit(1)
        .execute()
    )

    already_active = (
        existing.data
        and existing.data[0].get("status") == "active"
        and existing.data[0].get("phone_number_id")
    )

    if already_active:
        # Token refresh only — keep existing WABA and phone number
        update_payload: Dict[str, Any] = {"access_token": access_token}
        if token_expires_at is not None:
            update_payload["token_expires_at"] = token_expires_at
        sb.table("tenant_whatsapp_credentials").update(update_payload).eq(
            "tenant_id", ctx.tenant_id
        ).execute()

        saved_waba_id = existing.data[0]["whatsapp_business_account_id"]
        saved_phone_id = existing.data[0]["phone_number_id"]
    else:
        # First-time setup — save everything
        upsert_payload: Dict[str, Any] = {
            "tenant_id": ctx.tenant_id,
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

    return ExchangeCodeResponse(
        tenant_id=ctx.tenant_id,
        waba_id=saved_waba_id,
        phone_number_id=saved_phone_id,
        status="active",
    )
