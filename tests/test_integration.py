"""Integration test for orchestrator flow."""

from __future__ import annotations

import json

from agents.orchestrator import AgentOrchestrator
from models.database import Conversation, LearningQueueEntry, SessionLocal
from services.learning_service import LearningService
from services.vector_store import VectorStoreService
from services.whatsapp_service import WhatsAppService


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
        if context:
            answer = context.splitlines()[-1]
        else:
            answer = "Sin contexto disponible"
        return {"choices": [{"message": {"content": answer}}]}

    def embed(self, *, input_texts):  # type: ignore[override]
        value = float(len(input_texts[0])) if input_texts else 0.0
        return {"data": [{"embedding": [value]}]}


class DummyWhatsAppService(WhatsAppService):
    """Avoid real network calls for WhatsApp interactions."""

    def __init__(self) -> None:
        self.sent_messages: list[str] = []
        self.pass_calls: list[tuple[str, dict]] = []
        self.take_calls: list[tuple[str, dict]] = []

    def send_message(self, to: str, body: str) -> None:  # type: ignore[override]
        self.sent_messages.append(body)

    def pass_thread_control(self, recipient_id: str, metadata=None):  # type: ignore[override]
        self.pass_calls.append((recipient_id, metadata or {}))
        return {"status": "ok"}

    def take_thread_control(self, recipient_id: str, metadata=None):  # type: ignore[override]
        self.take_calls.append((recipient_id, metadata or {}))
        return {"status": "ok"}


def test_incremental_learning_flow(tmp_path) -> None:
    """Validate handoff, learning ingestion, and retrieval."""

    index_path = tmp_path / "index.json"
    vector_store = VectorStoreService(index_path=str(index_path))
    session = SessionLocal()
    whatsapp_service = DummyWhatsAppService()
    orchestrator = AgentOrchestrator(
        session=session,
        openai_service=DummyOpenAIService(),
        vector_store=vector_store,
        whatsapp_service=whatsapp_service,
    )

    response = orchestrator.process_message("+123", "Necesito ayuda con mi pedido")
    assert "Sin contexto" in response
    assert whatsapp_service.pass_calls, "Expected pass_thread_control call"

    user_conversation = next(
        conv for conv in session.query(Conversation) if conv.role == "user"
    )
    orchestrator.handoff.record_human_response(
        conversation=user_conversation,
        user_message=user_conversation.message,
        human_answer="Esta es la respuesta humana validada",
    )

    queue_entries = session.query(LearningQueueEntry)
    assert queue_entries and queue_entries[0].validated is False

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

    follow_up = orchestrator.process_message("+123", "Necesito ayuda con mi pedido")
    assert "respuesta humana validada" in follow_up.lower()
    assert len(whatsapp_service.pass_calls) == 1
    session.close()
