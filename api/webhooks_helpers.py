"""Webhook helper functions: tenant resolution, persistence, bot pipeline dispatch.

These are extracted from ``api.webhooks`` so they can be imported and patched
in isolation by tests, and reused across handlers.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from config.supabase import get_supabase_client
from utils import logger


def resolve_tenant_for_whatsapp(payload: dict) -> str:
    """Resolve tenant_id from a WhatsApp Business webhook payload.

    Looks up ``phone_number_id`` (from ``entry[0].changes[0].value.metadata``)
    against the active rows of ``tenant_whatsapp_credentials``.
    """

    phone_number_id = (
        payload["entry"][0]["changes"][0]["value"]
        ["metadata"]["phone_number_id"]
    )
    supabase = get_supabase_client()
    res = (
        supabase.table("tenant_whatsapp_credentials")
        .select("tenant_id")
        .eq("phone_number_id", phone_number_id)
        .eq("status", "active")
        .limit(1)
        .maybe_single()
        .execute()
    )
    if not res.data:
        logger.warning(
            "webhook_unknown_phone_id",
            extra={"phone_number_id": phone_number_id},
        )
        raise ValueError(f"No tenant for phone_number_id {phone_number_id}")
    return res.data["tenant_id"]


def resolve_tenant_for_instagram(payload: dict) -> str:
    """Resolve tenant_id from an Instagram webhook payload.

    Looks up the ID (from ``entry[0].id``) against active rows of
    ``tenant_instagram_credentials``, checking both ``ig_user_id`` and ``page_id``.
    """

    entry_id = str(payload["entry"][0]["id"])
    supabase = get_supabase_client()
    # Check ig_user_id first
    res = (
        supabase.table("tenant_instagram_credentials")
        .select("tenant_id")
        .eq("ig_user_id", entry_id)
        .eq("status", "active")
        .limit(1)
        .maybe_single()
        .execute()
    )
    if res and res.data:
        return res.data["tenant_id"]

    # Fall back to page_id
    res_page = (
        supabase.table("tenant_instagram_credentials")
        .select("tenant_id")
        .eq("page_id", entry_id)
        .eq("status", "active")
        .limit(1)
        .maybe_single()
        .execute()
    )
    if res_page and res_page.data:
        return res_page.data["tenant_id"]

    raise ValueError(f"No tenant for IG account/page {entry_id}")


def resolve_tenant_for_messenger(payload: dict) -> str:
    """Resolve tenant_id from a Facebook Messenger (Page) webhook payload.

    Looks up ``page_id`` (from ``entry[0].id``) against active rows of
    ``tenant_messenger_credentials``, and falls back to ``tenant_instagram_credentials``.
    """

    page_id = payload["entry"][0]["id"]
    supabase = get_supabase_client()
    res = (
        supabase.table("tenant_messenger_credentials")
        .select("tenant_id")
        .eq("page_id", page_id)
        .eq("status", "active")
        .limit(1)
        .maybe_single()
        .execute()
    )
    if res and res.data:
        return res.data["tenant_id"]

    res_ig = (
        supabase.table("tenant_instagram_credentials")
        .select("tenant_id")
        .eq("page_id", page_id)
        .eq("status", "active")
        .limit(1)
        .maybe_single()
        .execute()
    )
    if res_ig and res_ig.data:
        return res_ig.data["tenant_id"]

    raise ValueError(f"No tenant for Messenger page {page_id}")


def persist_conversation_message(
    *,
    tenant_id: str,
    channel: str,
    channel_user_id: str,
    role: str,
    message: str,
    metadata: Optional[dict] = None,
    message_id: Optional[str] = None,
) -> None:
    """Insert a single conversation row tagged by channel."""

    supabase = get_supabase_client()
    row = {
        "tenant_id": tenant_id,
        "channel": channel,
        "channel_user_id": channel_user_id,
        "role": role,
        "message": message,
        "metadata": metadata or {},
    }
    if message_id:
        row["message_id"] = message_id
    supabase.table("conversations").insert(row).execute()


async def run_bot_pipeline(
    *,
    tenant_id: str,
    channel: str,
    channel_user_id: str,
    user_message: str,
    message_id: Optional[str] = None,
) -> None:
    """Run the inbound agent flow and route the outbound reply via the channel adapter.

    Inbound processing still goes through ``AgentOrchestrator.process_message``
    (existing single-tenant-aware pipeline). The outbound reply is sent via the
    channel adapter so the same handle serves WhatsApp and Instagram.
    """

    # Check if an active handoff exists — if so, check if auto-return has expired or pause bot
    try:
        supabase = get_supabase_client()
        handoff_check = (
            supabase.table("handoffs")
            .select("id, message_count, updated_at")
            .eq("tenant_id", tenant_id)
            .eq("channel", channel)
            .eq("whatsapp_number", channel_user_id)
            .eq("status", "active")
            .limit(1)
            .execute()
        )
        if handoff_check.data:
            h = handoff_check.data[0]
            h_id = h["id"]
            updated_at_raw = h.get("updated_at")

            from services.tenant_config_service import get_tenant_bot_config
            t_cfg = get_tenant_bot_config(tenant_id)

            should_expire = False
            if t_cfg.handoff_auto_return_enabled and updated_at_raw:
                try:
                    updated_at = datetime.fromisoformat(str(updated_at_raw).replace("Z", "+00:00"))
                    timeout_delta = timedelta(minutes=t_cfg.handoff_timeout_minutes)
                    if datetime.now(timezone.utc) - updated_at > timeout_delta:
                        should_expire = True
                except Exception as parse_err:
                    logger.warning("handoff_updated_at_parse_failed", extra={"error": str(parse_err)})

            if should_expire:
                now_iso = datetime.now(timezone.utc).isoformat()
                supabase.table("handoffs").update({
                    "status": "expired",
                    "closed_at": now_iso,
                    "closed_by": "auto_timeout",
                }).eq("id", h_id).execute()
                logger.info(
                    "handoff_auto_expired_timeout",
                    extra={
                        "tenant_id": tenant_id,
                        "channel": channel,
                        "user": channel_user_id,
                        "handoff_id": h_id,
                        "timeout_minutes": t_cfg.handoff_timeout_minutes,
                    },
                )
                # Auto-expired: fall through so bot answers immediately
            else:
                count = (h.get("message_count") or 0) + 1
                supabase.table("handoffs").update({
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "message_count": count,
                }).eq("id", h_id).execute()
                logger.info(
                    "bot_pipeline_paused_during_active_handoff",
                    extra={"tenant_id": tenant_id, "channel": channel, "user": channel_user_id, "handoff_id": h_id},
                )
                return
    except Exception as exc:
        logger.warning("handoff_check_failed_proceeding", extra={"error": str(exc)})

    from agents.orchestrator import AgentOrchestrator
    from channels.registry import get_adapter
    from models.database import SessionLocal
    from services.openai_service import OpenAIService
    from services.template_service import TemplateService
    from services.vector_store import VectorStoreService
    from services.whatsapp_service import WhatsAppService

    # WhatsApp service is still needed by the orchestrator (handoff + template
    # paths reference ``whatsapp_service.phone_id``); for Instagram we still
    # hand a placeholder — the orchestrator's WhatsApp-bound code paths are
    # only entered when an active handoff exists.
    wa_service = WhatsAppService()
    db = SessionLocal()
    orchestrator = AgentOrchestrator(
        session=db,
        openai_service=OpenAIService(),
        vector_store=VectorStoreService(tenant_id=tenant_id),
        whatsapp_service=wa_service,
        template_service=TemplateService(whatsapp_service=wa_service),
        tenant_id=tenant_id,
    )
    try:
        agent_response = await orchestrator.process_message(
            channel_user_id, user_message, message_id=message_id
        )
        text = getattr(agent_response, "message", None)
        if text:
            adapter = get_adapter(channel)
            await adapter.send_message(
                recipient_id=channel_user_id,
                text=text,
                tenant_id=tenant_id,
            )
            persist_conversation_message(
                tenant_id=tenant_id,
                channel=channel,
                channel_user_id=channel_user_id,
                role="assistant",
                message=text,
                message_id=f"reply_to_{message_id}" if message_id else None,
            )
    except Exception as exc:
        logger.error(
            "bot_pipeline_execution_failed: tenant=%s channel=%s user=%s error=%s",
            tenant_id,
            channel,
            channel_user_id,
            exc,
            exc_info=True,
        )
    finally:
        try:
            db.close()
        except Exception:
            pass
        try:
            await wa_service.close()
        except Exception:
            pass
