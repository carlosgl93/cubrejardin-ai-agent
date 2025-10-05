"""Handoff agent implementation."""

from __future__ import annotations

from models.database import Conversation, Escalation, InMemorySession
from services.openai_service import OpenAIService
from services.whatsapp_service import WhatsAppService


class HandoffAgent:
    """Agent handling escalations to humans."""

    def __init__(
        self,
        *,
        openai_service: OpenAIService,
        whatsapp_service: WhatsAppService,
        session: InMemorySession,
    ) -> None:
        self.openai_service = openai_service
        self.whatsapp_service = whatsapp_service
        self.session = session

    def escalate(self, conversation: Conversation, user_number: str) -> str:
        """Escalate conversation and notify user."""

        escalation = Escalation(conversation_id=conversation.id, status="pending")
        self.session.add(escalation)
        self.session.commit()
        message = (
            "Gracias por tu paciencia. Un especialista humano revisará tu caso y te contactará en menos de 2 horas."
        )
        self.whatsapp_service.send_message(user_number, message)
        return message
