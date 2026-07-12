"""Webhook helper functions: tenant resolution, persistence, bot pipeline dispatch.

These are extracted from ``api.webhooks`` so they can be imported and patched
in isolation by tests, and reused across handlers.
"""

from __future__ import annotations

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
        .eq("active", True)
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

    Looks up the ``page_id`` (from ``entry[0].id``) against active rows of
    ``tenant_instagram_credentials``.
    """

    page_id = payload["entry"][0]["id"]
    supabase = get_supabase_client()
    res = (
        supabase.table("tenant_instagram_credentials")
        .select("tenant_id")
        .eq("page_id", page_id)
        .eq("status", "active")
        .limit(1)
        .maybe_single()
        .execute()
    )
    if not res.data:
        raise ValueError(f"No tenant for IG page {page_id}")
    return res.data["tenant_id"]


def persist_conversation_message(
    *,
    tenant_id: str,
    channel: str,
    channel_user_id: str,
    role: str,
    message: str,
    metadata: Optional[dict] = None,
) -> None:
    """Insert a single conversation row tagged by channel."""

    supabase = get_supabase_client()
    supabase.table("conversations").insert({
        "tenant_id": tenant_id,
        "channel": channel,
        "channel_user_id": channel_user_id,
        "role": role,
        "message": message,
        "metadata": metadata or {},
    }).execute()


async def run_bot_pipeline(
    *,
    tenant_id: str,
    channel: str,
    channel_user_id: str,
    user_message: str,
) -> None:
    """Run the inbound agent flow and route the outbound reply via the channel adapter.

    Inbound processing still goes through ``AgentOrchestrator.process_message``
    (existing single-tenant-aware pipeline). The outbound reply is sent via the
    channel adapter so the same handle serves WhatsApp and Instagram.
    """

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
            channel_user_id, user_message
        )
        text = getattr(agent_response, "message", None)
        if text:
            adapter = get_adapter(channel)
            await adapter.send_message(
                recipient_id=channel_user_id,
                text=text,
                tenant_id=tenant_id,
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
