"""Template management endpoints for Meta Graph API (multi-tenant)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.tenant_context import TenantContext, get_tenant_context
from config.supabase import get_supabase_client

router = APIRouter()

META_GRAPH_URL = "https://graph.facebook.com/v21.0"


# ── Request / Response models ───────────────────────────────────────────


class CreateTemplateRequest(BaseModel):
    name: str
    language: str = "es"
    category: str  # MARKETING | UTILITY | AUTHENTICATION
    components: List[Dict[str, Any]]


class SendTemplateRequest(BaseModel):
    to: str
    template_name: str
    language: str = "es"
    components: Optional[List[Dict[str, Any]]] = None


# ── Helpers ──────────────────────────────────────────────────────────────


def _get_tenant_credentials(tenant_id: str) -> Dict[str, str]:
    """Fetch WhatsApp credentials for a tenant from Supabase."""
    client = get_supabase_client()
    result = (
        client.table("tenant_whatsapp_credentials")
        .select("access_token, whatsapp_business_account_id, phone_number_id, status")
        .eq("tenant_id", tenant_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=403,
            detail="WhatsApp Business not connected. Please go to /auth-fb to connect your account.",
        )
    creds = result.data[0]
    if creds.get("status") != "active":
        raise HTTPException(
            status_code=403,
            detail="WhatsApp credentials are pending or invalid. Please reconnect at /auth-fb.",
        )
    return creds


def _headers(access_token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }


def _waba_url(waba_id: str, path: str = "") -> str:
    return f"{META_GRAPH_URL}/{waba_id}/message_templates{path}"


# ── Endpoints ────────────────────────────────────────────────────────────


@router.get("")
async def list_templates(
    ctx: TenantContext = Depends(get_tenant_context),
) -> Dict[str, Any]:
    """List all message templates for the tenant's WABA."""
    creds = _get_tenant_credentials(ctx.tenant_id)
    waba_id = creds["whatsapp_business_account_id"]
    token = creds["access_token"]

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(_waba_url(waba_id), headers=_headers(token))
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.json())
        return resp.json()


@router.post("")
async def create_template(
    body: CreateTemplateRequest,
    ctx: TenantContext = Depends(get_tenant_context),
) -> Dict[str, Any]:
    """Create a new message template."""
    creds = _get_tenant_credentials(ctx.tenant_id)
    waba_id = creds["whatsapp_business_account_id"]
    token = creds["access_token"]

    payload = {
        "name": body.name,
        "language": body.language,
        "category": body.category,
        "components": body.components,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(_waba_url(waba_id), headers=_headers(token), json=payload)
        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=resp.status_code, detail=resp.json())
        return resp.json()


@router.delete("/{template_name}")
async def delete_template(
    template_name: str,
    ctx: TenantContext = Depends(get_tenant_context),
) -> Dict[str, Any]:
    """Delete a message template by name."""
    creds = _get_tenant_credentials(ctx.tenant_id)
    waba_id = creds["whatsapp_business_account_id"]
    token = creds["access_token"]

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.delete(
            _waba_url(waba_id),
            headers=_headers(token),
            params={"name": template_name},
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.json())
        return resp.json()


@router.post("/send")
async def send_template(
    body: SendTemplateRequest,
    ctx: TenantContext = Depends(get_tenant_context),
) -> Dict[str, Any]:
    """Send a template message using the tenant's stored WhatsApp credentials."""
    creds = _get_tenant_credentials(ctx.tenant_id)
    phone_number_id = creds["phone_number_id"]
    token = creds["access_token"]

    to = body.to.replace("whatsapp:", "").replace("+", "").strip()
    to = "".join(filter(str.isdigit, to))

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": body.template_name,
            "language": {"code": body.language},
            "components": body.components or [],
        },
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{META_GRAPH_URL}/{phone_number_id}/messages",
            headers=_headers(token),
            json=payload,
        )
        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=resp.status_code, detail=resp.json())
        return resp.json()
