"""Integration test for orchestrator flow."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

import pytest

from agents.orchestrator import AgentOrchestrator
from models.database import Conversation, LearningQueueEntry, SessionLocal
from services.learning_service import LearningService
from services.vector_store import VectorStoreService
from services.template_service import TemplateService


class DummyOpenAIService:
    """Stub OpenAI returning classification, embeddings, and answers."""

    def chat_completion(self, *, messages, response_format=None):  # type: ignore[override]
        if response_format:
            payload = {
                "category": "VALID_QUERY",
                "confidence": 0.9,
                "intent": "informacion",
                "entities": {},
                "sentiment": "neutral",
                "reason": "ok",
            }
            return {"choices": [{"message": {"content": json.dumps(payload)}}]}
        context = "\n".join(msg["content"] for msg in messages if "Fuente:" in msg["content"])
        answer = context.splitlines()[-1] if context else "Sin contexto disponible"
        return {"choices": [{"message": {"content": answer}}]}

    def embed(self, *, input_texts):  # type: ignore[override]
        value = float(len(input_texts[0])) if input_texts else 0.0
        return {"data": [{"embedding": [value]}]}


class DummyWhatsAppService:
    """Avoid real network calls for WhatsApp interactions."""

    def __init__(self) -> None:
        self.sent_messages: List[str] = []
        self.pass_calls: List[Tuple[str, Dict[str, Any]]] = []
        self.take_calls: List[Tuple[str, Dict[str, Any]]] = []
        self._interactions: Dict[str, int] = {}
        self.template_calls: List[Tuple[str, str, List[Dict[str, Any]]]] = []

    async def send_text_message(self, to: str, body: str, *, preview_url: bool = True) -> Dict[str, Any]:
        self.sent_messages.append(body)
        return {"messages": [{"id": "dummy"}]}

    async def pass_thread_control(self, recipient_id: str, metadata=None):  # type: ignore[override]
        self.pass_calls.append((recipient_id, metadata or {}))
        return {"status": "ok"}

    async def take_thread_control(self, recipient_id: str, metadata=None):  # type: ignore[override]
        self.take_calls.append((recipient_id, metadata or {}))
        return {"status": "ok"}

    async def mark_as_read(self, message_id: str) -> Dict[str, Any]:
        return {"status": "read", "message_id": message_id}

    def validate_webhook_signature(self, payload: bytes, signature: str) -> bool:
        return True

    async def close(self) -> None:
        return None

    def record_incoming_interaction(self, user_id: str, *, timestamp=None) -> None:  # type: ignore[override]
        self._interactions[user_id] = 1

    def is_within_24h_window(self, user_id: str) -> bool:  # type: ignore[override]
        return True

    async def send_template_message(self, to: str, template_name: str, *, language: str = "es", components=None):
        self.template_calls.append((to, template_name, components or []))
        return {"messages": [{"id": "template"}]}


@pytest.mark.anyio("asyncio")
async def test_incremental_learning_flow(tmp_path) -> None:
    """Validate handoff, learning ingestion, and retrieval."""

    index_path = tmp_path / "index.json"
    vector_store = VectorStoreService(index_path=str(index_path))
    session = SessionLocal()
    whatsapp_service = DummyWhatsAppService()
    orchestrator = AgentOrchestrator(
        session=session,
        openai_service=DummyOpenAIService(),
        vector_store=vector_store,
        whatsapp_service=whatsapp_service,  # type: ignore[arg-type]
        template_service=TemplateService(whatsapp_service=whatsapp_service),  # type: ignore[arg-type]
    )

    response = await orchestrator.process_message("+123", "Necesito ayuda con mi pedido")
    assert "Sin contexto" in response.message
    assert whatsapp_service.pass_calls, "Expected pass_thread_control call"

    user_conversation = next(
        conv for conv in session.query(Conversation) if conv.role == "user"
    )
    await orchestrator.handoff.record_human_response(
        conversation=user_conversation,
        user_message=user_conversation.message,
        human_answer="Esta es la respuesta humana validada",
    )

    queue_entries = session.query(LearningQueueEntry)
    assert queue_entries and getattr(queue_entries[0], "validated", False) is False

    learning_service = LearningService(session)
    entry_id = queue_entries[0].id
    learning_service.validate_entry(entry_id)
    ingested = learning_service.ingest_validated_learning(
        openai_service=DummyOpenAIService(),
        vector_store=vector_store,
        entry_ids=[entry_id],
    )
    assert ingested == 1
    assert not session.query(LearningQueueEntry)

    follow_up = await orchestrator.process_message("+123", "Necesito ayuda con mi pedido")
    assert "respuesta humana validada" in follow_up.message.lower()
    assert len(whatsapp_service.pass_calls) == 1

    session.close()
