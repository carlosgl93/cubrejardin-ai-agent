"""Handoff agent implementation."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from models.database import Conversation, Escalation, InMemorySession
from services.learning_service import LearningService
from services.openai_service import OpenAIService
from services.whatsapp_service import WhatsAppService
from utils import logger


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
                recipient_id=conversation.user_number,
                metadata=metadata or {},
            )
        except Exception as exc:  # pragma: no cover
            logger.error(
                "handoff_pass_control_error",
                extra={"conversation_id": conversation.id, "error": str(exc)},
            )
            raise
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
                recipient_id=conversation.user_number,
                metadata=metadata or {},
            )
        except Exception as exc:  # pragma: no cover
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
        logger.info(
            "handoff_take_control_success",
            extra={"conversation_id": conversation.id},
        )

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

    async def escalate(
        self,
        conversation: Conversation,
        user_number: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Escalate conversation and notify user."""

        details = metadata or {"reason": "low_confidence"}
        message = (
            "Gracias por tu paciencia. Un especialista humano revisará tu caso y te contactará en menos de 2 horas."
        )
        await self.whatsapp_service.send_text_message(user_number, message)
        await self.pass_control_to_human(conversation=conversation, metadata=details)
        return message
