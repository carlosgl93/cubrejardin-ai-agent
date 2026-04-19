"""Telegram webhook endpoint — receives agent replies and forwards to WhatsApp."""

from __future__ import annotations

from fastapi import APIRouter, Request

from config import get_settings
from config.supabase import get_supabase_client
from services.telegram_service import TelegramService
from services.whatsapp_service import WhatsAppService
from utils import logger

router = APIRouter()
settings = get_settings()


def _resolve_handoff_by_reply(reply_to_id: int) -> dict | None:
    sb = get_supabase_client()
    result = (
        sb.table("active_handoffs")
        .select("*")
        .eq("telegram_message_id", reply_to_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _resolve_latest_handoff(chat_id: str) -> dict | None:
    sb = get_supabase_client()
    result = (
        sb.table("active_handoffs")
        .select("*")
        .eq("telegram_chat_id", chat_id)
        .eq("status", "active")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


@router.post("/telegram")
async def telegram_webhook(request: Request) -> dict:
    """Receive Telegram update from agent and forward reply to WhatsApp user."""

    data = await request.json()
    message = data.get("message")
    if not message:
        return {"status": "ignored"}

    chat_id = str(message.get("chat", {}).get("id", ""))
    text = message.get("text", "").strip()
    reply_to = message.get("reply_to_message")

    if not text or not chat_id:
        return {"status": "ignored"}

    # Commands
    if text.startswith("/"):
        if text == "/handoffs":
            await _list_active_handoffs(chat_id)
        return {"status": "command"}

    # Find active handoff: prefer reply-to match, fall back to latest
    handoff = None
    if reply_to:
        handoff = _resolve_handoff_by_reply(reply_to["message_id"])
    if not handoff:
        handoff = _resolve_latest_handoff(chat_id)

    if not handoff:
        tg = TelegramService()
        try:
            await tg.send_message(chat_id, "⚠️ No hay handoffs activos a quién responder.")
        finally:
            await tg.close()
        return {"status": "no_handoff"}

    wa_service = WhatsAppService(
        phone_id=handoff["wa_service_phone_id"],
        token=_get_tenant_token(handoff["tenant_id"]),
    )
    try:
        await wa_service.send_text_message(handoff["whatsapp_number"], text, skip_window_check=True)
        logger.info(
            "telegram_handoff_reply_forwarded",
            extra={"to": handoff["whatsapp_number"], "handoff_id": handoff["id"]},
        )
    finally:
        await wa_service.close()

    return {"status": "ok"}


async def _list_active_handoffs(chat_id: str) -> None:
    sb = get_supabase_client()
    result = sb.table("active_handoffs").select("whatsapp_number, created_at").eq("status", "active").execute()
    tg = TelegramService()
    try:
        if not result.data:
            await tg.send_message(chat_id, "✅ No hay handoffs activos.")
        else:
            lines = [f"• <code>{h['whatsapp_number']}</code> desde {h['created_at'][:16]}" for h in result.data]
            await tg.send_message(chat_id, "📋 <b>Handoffs activos:</b>\n" + "\n".join(lines))
    finally:
        await tg.close()


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
