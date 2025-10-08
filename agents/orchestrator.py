"""Agent orchestrator module."""

from __future__ import annotations

import asyncio
from typing import Optional

from models.database import Conversation, InMemorySession, utc_now
from models.schemas import AgentResponse, GuardianResult, RAGResponse
from services.openai_service import OpenAIService
from services.vector_store import VectorStoreService
from services.whatsapp_service import WhatsAppService
from services.template_service import TemplateService
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
        template_service: TemplateService,
    ) -> None:
        self.session = session
        self.openai_service = openai_service
        self.vector_store = vector_store
        self.whatsapp_service = whatsapp_service
        self.template_service = template_service
        self.guardian = GuardianAgent(openai_service)
        self.rag = RAGAgent(openai_service, vector_store)
        self.handoff = HandoffAgent(
            openai_service=openai_service,
            whatsapp_service=whatsapp_service,
            session=session,
        )

    async def _store_message(
        self,
        user_number: str,
        role: str,
        message: str,
        metadata: Optional[dict] = None,
    ) -> Conversation:
        """Persist conversation message in a background thread."""

        def _persist() -> Conversation:
            timestamp = utc_now()
            entry = Conversation(user_number=user_number, role=role, message=message, metadata=metadata or {})
            entry.created_at = timestamp
            if role == "user":
                entry.last_interaction_at = timestamp
            entry.updated_at = timestamp
            self.session.add(entry)
            self.session.commit()
            return entry

        return await asyncio.to_thread(_persist)

    async def process_message(
        self,
        user_number: str,
        message: str,
        *,
        message_id: Optional[str] = None,
    ) -> AgentResponse:
        """Process inbound message and return response."""

        cleaned = sanitize_text(message)
        guardian_result: GuardianResult = await asyncio.to_thread(self.guardian.classify, cleaned)
        user_metadata = guardian_result.model_dump()
        if message_id:
            user_metadata["message_id"] = message_id
        await self._store_message(user_number, "user", cleaned, user_metadata)
        logger.info("guardian_classification", extra=guardian_result.model_dump())

        if guardian_result.category in {"SPAM", "SENSITIVE", "OFF_TOPIC"}:
            response = (
                "Gracias por contactarnos. Actualmente no podemos procesar este mensaje."
            )
            await self._store_message(user_number, "system", response)
            return AgentResponse(
                message=response,
                intent=guardian_result.intent,
                category=guardian_result.category,
                data={"guardian": guardian_result.model_dump()},
            )

        if guardian_result.category == "ESCALATION_REQUEST":
            conv = await self._store_message(user_number, "system", "Escalación solicitada")
            message_text = await self.handoff.escalate(conv, user_number, metadata={"reason": "user_request"})
            return AgentResponse(
                message=message_text,
                intent="handoff",
                category=guardian_result.category,
                data={"guardian": guardian_result.model_dump()},
            )

        if guardian_result.category == "GREETING":
            response = "¡Hola! ¿En qué puedo ayudarte hoy?"
            await self._store_message(user_number, "assistant", response)
            return AgentResponse(
                message=response,
                intent=guardian_result.intent,
                category=guardian_result.category,
                data={"guardian": guardian_result.model_dump()},
            )

        rag_response: RAGResponse = await asyncio.to_thread(self.rag.answer, cleaned)
        logger.info(
            "rag_answer",
            extra={
                "user": user_number,
                "confidence": rag_response.confidence,
                "sources": rag_response.sources,
            },
        )
        await self._store_message(
            user_number,
            "assistant",
            rag_response.answer,
            {"confidence": rag_response.confidence, "sources": rag_response.sources},
        )

        if rag_response.confidence < 0.5 and guardian_result.category == "VALID_QUERY":
            conv = await self._store_message(user_number, "system", "Confianza baja, escalando")
            await self.handoff.escalate(conv, user_number, metadata={"reason": "low_confidence"})

        return AgentResponse(
            message=rag_response.answer,
            intent=guardian_result.intent,
            category=guardian_result.category,
            data={
                "guardian": guardian_result.model_dump(),
                "rag": rag_response.model_dump(),
            },
        )

    async def handle_outside_window(self, user_number: str, response: AgentResponse) -> str:
        """Fallback to an approved template when outside the 24h window."""

        result = await self.template_service.send_fallback_template(user_number, response)
        logger.info(
            "template_fallback_sent",
            extra={
                "user": user_number,
                "template": result.template_name,
                "intent": response.intent,
            },
        )
        return result.template_name

    async def has_processed_message(self, message_id: str) -> bool:
        """Return True if the inbound message id has already been processed."""

        def _check() -> bool:
            for convo in self.session.query(Conversation):
                if convo.role != "user":
                    continue
                metadata = convo.metadata or {}
                if metadata.get("message_id") == message_id:
                    return True
            return False

        return await asyncio.to_thread(_check)
