"""Handoff management endpoints — used by the conversations UI."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.auth import AuthenticatedUser, get_current_user
from api.tenant_context import TenantContext, get_tenant_context
from config.supabase import get_supabase_client
from utils import logger
from services.whatsapp_service import WhatsAppService

router = APIRouter()


class ReplyRequest(BaseModel):
    message: str


def _get_tenant_token(tenant_id: str) -> str:
    sb = get_supabase_client()
    result = (
        sb.table("tenant_whatsapp_credentials")
        .select("access_token")
        .eq("tenant_id", tenant_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    return result.data[0]["access_token"] if result.data else ""


@router.get("/")
async def list_handoffs(
    ctx: TenantContext = Depends(get_tenant_context),
):
    """List all active handoffs for the authenticated tenant."""
    sb = get_supabase_client()
    result = (
        sb.table("active_handoffs")
        .select("*")
        .eq("tenant_id", ctx.tenant_id)
        .eq("status", "active")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


@router.post("/{handoff_id}/reply")
async def reply_to_handoff(
    handoff_id: str,
    body: ReplyRequest,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Send a reply from the human agent to the WhatsApp user."""
    sb = get_supabase_client()
    result = (
        sb.table("active_handoffs")
        .select("*")
        .eq("id", handoff_id)
        .eq("tenant_id", ctx.tenant_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Handoff not found or already closed")

    handoff = result.data[0]
    wa = WhatsAppService(
        phone_id=handoff["wa_service_phone_id"],
        token=_get_tenant_token(ctx.tenant_id),
    )
    try:
        await wa.send_text_message(handoff["whatsapp_number"], body.message, skip_window_check=True)
    finally:
        await wa.close()

    # Persist as assistant message in conversations
    sb.table("conversations").insert({
        "tenant_id": ctx.tenant_id,
        "user_number": handoff["whatsapp_number"],
        "role": "assistant",
        "message": body.message,
        "metadata": {"source": "human_agent"},
    }).execute()

    # Touch updated_at
    sb.table("active_handoffs").update(
        {"updated_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", handoff_id).execute()

    logger.info("handoff_replied_via_ui", extra={"handoff_id": handoff_id, "to": handoff["whatsapp_number"]})
    return {"status": "sent"}


@router.post("/{handoff_id}/close")
async def close_handoff(
    handoff_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Close an active handoff, returning control to the bot."""
    sb = get_supabase_client()
    result = (
        sb.table("active_handoffs")
        .select("id, whatsapp_number")
        .eq("id", handoff_id)
        .eq("tenant_id", ctx.tenant_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Handoff not found")

    sb.table("active_handoffs").update({"status": "closed"}).eq("id", handoff_id).execute()
    logger.info("handoff_closed_via_ui", extra={"handoff_id": handoff_id})
    return {"status": "closed"}
