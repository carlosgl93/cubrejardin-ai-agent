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
from services.mercadofiel_service import MercadoFielService
from utils import logger
from utils.helpers import sanitize_text

from .guardian_agent import GuardianAgent
from .handoff_agent import HandoffAgent
from .rag_agent import RAGAgent
from .faq_agent import FAQAgent


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
        mercadofiel_service: Optional[MercadoFielService] = None,
        tenant_id: Optional[str] = None,
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.openai_service = openai_service
        self.vector_store = vector_store
        self.whatsapp_service = whatsapp_service
        self.template_service = template_service
        self.mercadofiel_service = mercadofiel_service or MercadoFielService()
        self.guardian = GuardianAgent(openai_service)
        self.rag = RAGAgent(openai_service, vector_store)
        self.faq = FAQAgent(openai_service)
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
        """Persist conversation message.

        When tenant_id is set, writes to Supabase for durability across
        Cloud Run instances. Falls back to the in-memory session otherwise.
        """

        if self.tenant_id:
            def _supabase_persist() -> Conversation:
                from config.supabase import get_supabase_client
                sb = get_supabase_client()
                now = utc_now().isoformat()
                row = {
                    "tenant_id": self.tenant_id,
                    "user_number": user_number,
                    "role": role,
                    "message": message,
                    "metadata": metadata or {},
                }
                if role == "user":
                    row["last_interaction_at"] = now
                sb.table("conversations").insert(row).execute()
                entry = Conversation(user_number=user_number, role=role, message=message, metadata=metadata or {})
                return entry

            return await asyncio.to_thread(_supabase_persist)

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
        logger.info("guardian result", extra={"result": guardian_result})

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

        # First, try to identify if it's an FAQ question
        faq_intent = await asyncio.to_thread(self.faq.identify_faq_intent, cleaned)
        logger.info(
            "faq_intent_check",
            extra={
                "user": user_number,
                "category": faq_intent.get("category"),
                "confidence": faq_intent.get("confidence"),
            },
        )

        # If FAQ agent has high confidence (>=0.7) and it's a known FAQ category, use FAQ agent
        if faq_intent.get("confidence", 0) >= 0.7 and faq_intent.get("category") != "NOT_FAQ":
            # Get vector store context directly (without RAG's low confidence check)
            embedding_response = self.openai_service.embed(input_texts=[cleaned])
            embedding = embedding_response["data"][0]["embedding"]
            search_results = self.vector_store.search(embedding, top_k=3)
            
            # Build context from search results
            context_text = ""
            sources = []
            for score, metadata in search_results:
                context_text += f"\n\n{metadata.get('content', '')}"
                sources.append({
                    "title": metadata.get("title", "unknown"),
                    "score": f"{score:.2f}"
                })
            
            logger.info(
                "faq_vector_context",
                extra={
                    "user": user_number,
                    "category": faq_intent.get("category"),
                    "sources": sources,
                    "context_length": len(context_text)
                }
            )
            
            # Generate FAQ response using vector store context
            faq_answer = await asyncio.to_thread(
                self.faq.generate_faq_response,
                cleaned,
                faq_intent,
                context_text
            )
            
            # Use FAQ confidence (which is higher)
            final_confidence = faq_intent.get("confidence", 0.8)
            
            logger.info(
                "faq_response_used",
                extra={
                    "user": user_number,
                    "category": faq_intent.get("category"),
                    "confidence": final_confidence,
                },
            )
            
            await self._store_message(
                user_number,
                "assistant",
                faq_answer,
                {
                    "confidence": final_confidence,
                    "faq_category": faq_intent.get("category"),
                    "method": "faq_agent"
                },
            )

            return AgentResponse(
                message=faq_answer,
                intent=guardian_result.intent,
                category=guardian_result.category,
                data={
                    "guardian": guardian_result.model_dump(),
                    "faq": faq_intent,
                    "confidence": final_confidence,
                },
            )

        # Fall back to standard RAG if not a clear FAQ or low FAQ confidence
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

        # Try to escalate on low confidence, but don't fail the request if escalation fails
        if rag_response.confidence < 0.5 and guardian_result.category == "VALID_QUERY":
            conv = await self._store_message(user_number, "system", "Confianza baja, escalando")
            try:
                await self.handoff.escalate(conv, user_number, metadata={"reason": "low_confidence"})
            except Exception as exc:
                logger.warning(
                    "escalation_failed_gracefully",
                    extra={
                        "user": user_number,
                        "error": str(exc),
                        "confidence": rag_response.confidence,
                    }
                )

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

        if self.tenant_id:
            def _check_supabase() -> bool:
                from config.supabase import get_supabase_client
                sb = get_supabase_client()
                result = (
                    sb.table("conversations")
                    .select("id")
                    .eq("tenant_id", self.tenant_id)
                    .eq("role", "user")
                    .contains("metadata", {"message_id": message_id})
                    .limit(1)
                    .execute()
                )
                return bool(result.data)

            return await asyncio.to_thread(_check_supabase)

        def _check() -> bool:
            for convo in self.session.query(Conversation):
                if convo.role != "user":
                    continue
                metadata = convo.metadata or {}
                if metadata.get("message_id") == message_id:
                    return True
            return False

        return await asyncio.to_thread(_check)
