"""Conversations list endpoint — used by the inbox UI.

Returns one row per (channel, channel_user_id) pair, grouped from raw
``conversations`` rows. Supports optional ``?channel=`` filter so the
inbox tab (WhatsApp | Instagram | All) can scope the response.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.tenant_context import TenantContext, get_tenant_context
from channels.registry import get_adapter
from config.supabase import get_supabase_client
from utils import logger

router = APIRouter(prefix="/api", tags=["conversations"])


class ConversationReplyRequest(BaseModel):
    channel: str = Field(..., description="'whatsapp' | 'instagram' | 'messenger'")
    channel_user_id: str = Field(..., description="Recipient user/phone ID")
    message: str = Field(..., min_length=1, description="Message text to send")


class ResumeBotRequest(BaseModel):
    channel: str = Field(..., description="'whatsapp' | 'instagram' | 'messenger'")
    channel_user_id: str = Field(..., description="Recipient user/phone ID")



def _list_contacts(tenant_id: str, channel: Optional[str]) -> list[dict]:
    """Return one grouped contact per (channel, channel_user_id) pair.

    Channel column comes from migration 006_instagram_channel.sql. Empty /
    ``None`` channel param returns contacts from all channels.
    """
    supabase = get_supabase_client()
    q = (
        supabase.table("conversations")
        .select("channel, channel_user_id, message, created_at")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .limit(1000)
    )
    if channel:
        q = q.eq("channel", channel)
    rows = q.execute().data or []

    grouped: dict[tuple[str, str], dict] = {}
    for r in rows:
        key = (r["channel"], r["channel_user_id"])
        if key not in grouped:
            grouped[key] = {
                "channel": r["channel"],
                "channel_user_id": r["channel_user_id"],
                "last_message": r["message"],
                "last_at": r["created_at"],
                "count": 1,
            }
        else:
            grouped[key]["count"] += 1
    return list(grouped.values())


@router.get("/conversations")
async def list_conversations(
    channel: Optional[str] = Query(default=None, description="Filter by channel: 'whatsapp' | 'instagram'. Omit for all."),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """List recent conversation contacts for the current tenant."""
    contacts = _list_contacts(tenant_id=ctx.tenant_id, channel=channel)
    return {"contacts": contacts}


@router.post("/conversations/reply")
async def reply_conversation(
    body: ConversationReplyRequest,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Send an outbound reply as a human agent across any supported channel.

    Automatically creates or touches an active handoff to pause the bot,
    routes the outbound text through the matching channel adapter, and persists
    the conversation row.
    """
    channel = body.channel.strip().lower()
    if channel not in ("whatsapp", "instagram", "messenger"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported channel '{body.channel}'. Must be whatsapp, instagram, or messenger.",
        )

    supabase = get_supabase_client()
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Check or activate handoff to pause the bot
    existing_handoff = (
        supabase.table("handoffs")
        .select("id, message_count, first_response_at")
        .eq("tenant_id", ctx.tenant_id)
        .eq("channel", channel)
        .eq("whatsapp_number", body.channel_user_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    )

    handoff_id = None
    if existing_handoff.data:
        h = existing_handoff.data[0]
        handoff_id = h["id"]
        update_data = {
            "updated_at": now_iso,
            "message_count": (h.get("message_count") or 0) + 1,
        }
        if not h.get("first_response_at"):
            update_data["first_response_at"] = now_iso
        supabase.table("handoffs").update(update_data).eq("id", handoff_id).execute()
    else:
        new_handoff = (
            supabase.table("handoffs")
            .insert({
                "tenant_id": ctx.tenant_id,
                "channel": channel,
                "whatsapp_number": body.channel_user_id,
                "status": "active",
                "created_at": now_iso,
                "updated_at": now_iso,
                "first_response_at": now_iso,
                "message_count": 1,
            })
            .execute()
        )
        if new_handoff.data:
            handoff_id = new_handoff.data[0].get("id")

    # 2. Dispatch outbound message via channel adapter
    adapter = get_adapter(channel)
    try:
        await adapter.send_message(
            recipient_id=body.channel_user_id,
            text=body.message,
            tenant_id=ctx.tenant_id,
        )
    except Exception as exc:
        logger.error(
            "manual_reply_send_failed",
            extra={
                "tenant_id": ctx.tenant_id,
                "channel": channel,
                "recipient": body.channel_user_id,
                "error": str(exc),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed sending outbound message to {channel}: {str(exc)}",
        )

    # 3. Persist conversation message
    conv_res = (
        supabase.table("conversations")
        .insert({
            "tenant_id": ctx.tenant_id,
            "channel": channel,
            "channel_user_id": body.channel_user_id,
            "role": "assistant",
            "message": body.message,
            "metadata": {
                "source": "human_agent",
                "user_id": ctx.user_id,
                "sent_from": "conversations_module",
            },
            "created_at": now_iso,
            "updated_at": now_iso,
        })
        .execute()
    )

    logger.info(
        "manual_reply_sent",
        extra={
            "tenant_id": ctx.tenant_id,
            "channel": channel,
            "recipient": body.channel_user_id,
            "handoff_id": handoff_id,
        },
    )

    return {
        "status": "sent",
        "handoff_id": handoff_id,
        "channel": channel,
        "channel_user_id": body.channel_user_id,
        "message": conv_res.data[0] if conv_res.data else None,
    }


@router.post("/conversations/resume-bot")
async def resume_bot(
    body: ResumeBotRequest,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Close active handoff for a contact and return conversational control to the bot."""
    channel = body.channel.strip().lower()
    supabase = get_supabase_client()
    now_iso = datetime.now(timezone.utc).isoformat()

    res = (
        supabase.table("handoffs")
        .update({
            "status": "closed",
            "closed_at": now_iso,
            "closed_by": "agent_ui",
            "updated_at": now_iso,
        })
        .eq("tenant_id", ctx.tenant_id)
        .eq("channel", channel)
        .eq("whatsapp_number", body.channel_user_id)
        .eq("status", "active")
        .execute()
    )

    closed_count = len(res.data or [])
    logger.info(
        "bot_resumed_from_ui",
        extra={
            "tenant_id": ctx.tenant_id,
            "channel": channel,
            "recipient": body.channel_user_id,
            "closed_count": closed_count,
        },
    )

    return {"status": "bot_resumed", "closed_count": closed_count}
