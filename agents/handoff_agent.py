"""Handoff agent implementation."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from config import get_settings
from config.supabase import get_supabase_client
from models.database import Conversation, Escalation, InMemorySession
from services.learning_service import LearningService
from services.openai_service import OpenAIService
from services.telegram_service import TelegramService
from services.whatsapp_service import WhatsAppService
from utils import logger

settings = get_settings()


class HandoffAgent:
    """Agent handling escalations to humans."""

    def __init__(
        self,
        *,
        openai_service: OpenAIService,
        whatsapp_service: WhatsAppService,
        session: InMemorySession,
        learning_service: Optional[LearningService] = None,
    ) -> None:
        self.openai_service = openai_service
        self.whatsapp_service = whatsapp_service
        self.session = session
        self.learning_service = learning_service or LearningService(session)

    async def pass_control_to_human(
        self,
        *,
        conversation: Conversation,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Escalation:
        """Trigger WhatsApp handover protocol to a human agent."""

        def _persist() -> Escalation:
            escalation = Escalation(
                conversation_id=conversation.id,
                status="pending",
                handoff_type="to_human",
                metadata=metadata or {},
            )
            self.session.add(escalation)
            self.session.commit()
            return escalation

        escalation = await asyncio.to_thread(_persist)
        try:
            await self.whatsapp_service.pass_thread_control(
                recipient_id=conversation.channel_user_id,
                metadata=metadata or {},
            )
        except Exception as exc:
            logger.warning(
                "handoff_pass_control_error",
                extra={"conversation_id": conversation.id, "error": str(exc)},
            )
        logger.info(
            "handoff_pass_control_success",
            extra={"conversation_id": conversation.id, "escalation_id": escalation.id},
        )
        return escalation

    async def take_control_back(
        self,
        *,
        conversation: Conversation,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Recover WhatsApp thread control for the bot."""

        try:
            await self.whatsapp_service.take_thread_control(
                recipient_id=conversation.channel_user_id,
                metadata=metadata or {},
            )
        except Exception as exc:
            logger.error(
                "handoff_take_control_error",
                extra={"conversation_id": conversation.id, "error": str(exc)},
            )
            raise

        def _resolve() -> None:
            for escalation in reversed(self.session.query(Escalation)):
                if escalation.conversation_id == conversation.id and escalation.status != "resolved":
                    escalation.status = "resolved"
                    escalation.handoff_type = "to_bot"
                    escalation.metadata.update(metadata or {})
                    break
            self.session.commit()

        await asyncio.to_thread(_resolve)
        logger.info("handoff_take_control_success", extra={"conversation_id": conversation.id})

    async def record_human_response(
        self,
        *,
        conversation: Conversation,
        user_message: str,
        human_answer: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Persist a human response into the learning queue."""

        def _queue() -> Any:
            return self.learning_service.queue_human_response(
                conversation_id=conversation.id,
                user_message=user_message,
                human_answer=human_answer,
                metadata=metadata,
            )

        entry = await asyncio.to_thread(_queue)
        logger.info(
            "handoff_human_response_recorded",
            extra={"conversation_id": conversation.id, "entry_id": entry.id},
        )

    async def _notify_telegram(
        self,
        *,
        user_number: str,
        last_message: str,
        reason: str,
        tenant_id: str,
        phone_id: str,
    ) -> Optional[int]:
        """Send handoff notification to Telegram agent and persist active handoff."""

        chat_id = settings.telegram_agent_chat_id
        if not chat_id or not settings.telegram_bot_token:
            logger.warning("telegram_not_configured")
            return None

        # Fetch last messages for context
        history_text = ""
        try:
            from config.supabase import get_supabase_client as _get_sb
            _sb = _get_sb()
            _hist = (
                _sb.table("conversations")
                .select("role, message")
                .eq("tenant_id", tenant_id)
                .eq("channel_user_id", user_number)
                .eq("channel", "whatsapp")
                .order("created_at", desc=True)
                .limit(6)
                .execute()
            )
            if _hist.data:
                rows = list(reversed(_hist.data))
                lines_hist = []
                for r in rows:
                    prefix = "🧑" if r["role"] == "user" else "🤖"
                    lines_hist.append(f"{prefix} {r['message'][:120]}")
                history_text = "\n".join(lines_hist)
        except Exception:
            pass
        site_url = getattr(settings, "site_url", "https://sgcloud.cl")
        conversation_link = f"{site_url}/conversations?number={user_number}"
        text = (
            f"🔔 <b>Nuevo handoff</b>\n\n"
            f"👤 Usuario: <code>{user_number}</code>\n"
            f"📌 Razón: {reason}\n"
            + (f"\n📜 <b>Conversación previa:</b>\n{history_text}\n" if history_text else "")
            + f"\n👉 <a href='{conversation_link}'>Abrir conversación</a>\n"
            + f"↩️ O responde a este mensaje desde Telegram."
        )
        tg = TelegramService()
        try:
            result = await tg.send_message(chat_id, text)
            message_id = result.get("message_id")
        finally:
            await tg.close()

        # Persist active handoff in Supabase
        try:
            sb = get_supabase_client()
            sb.table("handoffs").insert({
                "tenant_id": tenant_id,
                "whatsapp_number": user_number,
                "telegram_chat_id": chat_id,
                "telegram_message_id": message_id,
                "wa_service_phone_id": phone_id,
                "status": "active",
            }).execute()
        except Exception as exc:
            logger.error("handoff_supabase_persist_error", extra={"error": str(exc)})

        logger.info("telegram_handoff_notified", extra={"user": user_number, "message_id": message_id})
        return message_id

    async def escalate(
        self,
        conversation: Conversation,
        user_number: str,
        metadata: Optional[Dict[str, Any]] = None,
        *,
        tenant_id: str = "",
        phone_id: str = "",
        last_message: str = "",
    ) -> str:
        """Escalate conversation and notify user + Telegram agent."""

        details = metadata or {"reason": "low_confidence"}
        reason = details.get("reason", "low_confidence")
        message = (
            "Gracias por tu paciencia. Un especialista humano revisará tu caso y te contactará en menos de 2 horas."
        )
        await self.whatsapp_service.send_text_message(user_number, message)
        await self.pass_control_to_human(conversation=conversation, metadata=details)
        await self._notify_telegram(
            user_number=user_number,
            last_message=last_message or "(sin mensaje)",
            reason=reason,
            tenant_id=tenant_id,
            phone_id=phone_id,
        )
        return message
