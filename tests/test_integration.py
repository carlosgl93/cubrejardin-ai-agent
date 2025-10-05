"""Integration test for orchestrator flow."""

from __future__ import annotations

from agents.orchestrator import AgentOrchestrator
from models.database import SessionLocal
from services.whatsapp_service import WhatsAppService


class DummyOpenAIService:
    """Stub OpenAI returning classification and answers."""

    def chat_completion(self, *, messages, response_format=None):  # type: ignore[override]
        if response_format:
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"category": "VALID_QUERY", "confidence": 0.8, "intent": "info", '
                                '"entities": {}, "sentiment": "neutral", "reason": "ok"}'
                            )
                        }
                    }
                ]
            }
        return {"choices": [{"message": {"content": "Respuesta base"}}]}

    def embed(self, *, input_texts):  # type: ignore[override]
        return {"data": [{"embedding": [0.1, 0.2, 0.3]}]}


class DummyVectorStore:
    """Stub vector store for integration test."""

    def search(self, embedding, top_k=5):  # type: ignore[override]
        return [(0.8, {"title": "Politica", "content": "Texto"})]


class DummyWhatsAppService(WhatsAppService):
    """Avoid real Twilio calls."""

    def __init__(self) -> None:
        pass

    def send_message(self, to: str, body: str) -> None:  # type: ignore[override]
        self.last_message = body


def test_orchestrator_flow() -> None:
    """Ensure orchestrator returns assistant message."""

    session = SessionLocal()
    orchestrator = AgentOrchestrator(
        session=session,
        openai_service=DummyOpenAIService(),
        vector_store=DummyVectorStore(),
        whatsapp_service=DummyWhatsAppService(),
    )
    response = orchestrator.process_message("+1", "Hola")
    assert "Respuesta" in response
    session.close()
