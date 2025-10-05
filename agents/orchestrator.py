"""Agent orchestrator module."""

from __future__ import annotations

from typing import Optional

from models.database import Conversation, InMemorySession
from models.schemas import GuardianResult
from services.openai_service import OpenAIService
from services.vector_store import VectorStoreService
from services.whatsapp_service import WhatsAppService
from utils import logger
from utils.helpers import sanitize_text

from .guardian_agent import GuardianAgent
from .handoff_agent import HandoffAgent
from .rag_agent import RAGAgent


class AgentOrchestrator:
    """Coordinate multi-agent workflow."""

    def __init__(
        self,
        *,
        session: InMemorySession,
        openai_service: OpenAIService,
        vector_store: VectorStoreService,
        whatsapp_service: WhatsAppService,
    ) -> None:
        self.session = session
        self.openai_service = openai_service
        self.vector_store = vector_store
        self.whatsapp_service = whatsapp_service
        self.guardian = GuardianAgent(openai_service)
        self.rag = RAGAgent(openai_service, vector_store)
        self.handoff = HandoffAgent(
            openai_service=openai_service,
            whatsapp_service=whatsapp_service,
            session=session,
        )

    def _store_message(self, user_number: str, role: str, message: str, metadata: Optional[dict] = None) -> Conversation:
        """Persist conversation message."""

        entry = Conversation(user_number=user_number, role=role, message=message, metadata=metadata or {})
        self.session.add(entry)
        self.session.commit()
        return entry

    def process_message(self, user_number: str, message: str) -> str:
        """Process inbound message and return response."""

        cleaned = sanitize_text(message)
        guardian_result: GuardianResult = self.guardian.classify(cleaned)
        self._store_message(user_number, "user", cleaned, guardian_result.dict())
        logger.info("guardian_classification", extra=guardian_result.dict())

        if guardian_result.category in {"SPAM", "SENSITIVE", "OFF_TOPIC"}:
            response = "Gracias por contactarnos. Actualmente no podemos procesar este mensaje."
            self._store_message(user_number, "system", response)
            return response
        if guardian_result.category == "ESCALATION_REQUEST":
            conv = self._store_message(user_number, "system", "Escalación solicitada")
            return self.handoff.escalate(conv, user_number)
        if guardian_result.category == "GREETING":
            response = "¡Hola! ¿En qué puedo ayudarte hoy?"
            self._store_message(user_number, "assistant", response)
            return response

        rag_response = self.rag.answer(cleaned)
        self._store_message(
            user_number,
            "assistant",
            rag_response.answer,
            {"confidence": rag_response.confidence, "sources": rag_response.sources},
        )
        if rag_response.confidence < 0.5:
            conv = self._store_message(user_number, "system", "Confianza baja, escalando")
            self.handoff.escalate(conv, user_number)
        return rag_response.answer
