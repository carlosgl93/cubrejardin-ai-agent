"""Template management endpoints for Meta Graph API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from httpx import HTTPStatusError
from pydantic import BaseModel

from api.dependencies import get_whatsapp_service
from config import settings
from services.whatsapp_service import WhatsAppService

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


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.facebook_page_access_token}",
        "Content-Type": "application/json",
    }


def _waba_url(path: str = "") -> str:
    return f"{META_GRAPH_URL}/{settings.whatsapp_business_account_id}/message_templates{path}"


# ── Endpoints ────────────────────────────────────────────────────────────


@router.get("")
async def list_templates() -> Dict[str, Any]:
    """List all message templates for the WABA."""
    print(_waba_url())

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(_waba_url(), headers=_headers())
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.json())
        return resp.json()


@router.post("")
async def create_template(body: CreateTemplateRequest) -> Dict[str, Any]:
    """Create a new message template."""

    payload = {
        "name": body.name,
        "language": body.language,
        "category": body.category,
        "components": body.components,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(_waba_url(), headers=_headers(), json=payload)
        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=resp.status_code, detail=resp.json())
        return resp.json()


@router.delete("/{template_name}")
async def delete_template(template_name: str) -> Dict[str, Any]:
    """Delete a message template by name."""

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.delete(
            _waba_url(),
            headers=_headers(),
            params={"name": template_name},
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.json())
        return resp.json()


@router.post("/send")
async def send_template(
    body: SendTemplateRequest,
    whatsapp_service: WhatsAppService = Depends(get_whatsapp_service),
) -> Dict[str, Any]:
    """Send a template message to a phone number."""

    try:
        result = await whatsapp_service.send_template_message(
            to=body.to,
            template_name=body.template_name,
            language=body.language,
            components=body.components,
        )
    except HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.json())
    return result
