"""Tests for inbound message idempotency."""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

from agents.orchestrator import AgentOrchestrator, DuplicateInboundMessageError
from services.template_service import TemplateService
from services.vector_store import VectorStoreService
from models.database import SessionLocal


class DummyOpenAIService:
    """Minimal OpenAI stub for orchestrator tests."""

    def chat_completion(self, *, messages, response_format=None):  # type: ignore[override]
        if response_format:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "category": "VALID_QUERY",
                                    "confidence": 0.9,
                                    "intent": "consulta",
                                    "entities": {},
                                    "sentiment": "neutral",
                                    "reason": "ok",
                                }
                            )
                        }
                    }
                ]
            }
        return {"choices": [{"message": {"content": "Respuesta"}}]}

    def embed(self, *, input_texts):  # type: ignore[override]
        return {"data": [{"embedding": [float(len(input_texts[0]))]}]}


class DummyTransport:
    """Transport stub for orchestrator tests."""

    def __init__(self) -> None:
        self.sent_messages: List[str] = []

    async def send_text_message(self, _to: str, body: str, *, preview_url: bool = True) -> Dict[str, Any]:
        self.sent_messages.append(body)
        return {"messages": [{"id": "dummy"}]}

    async def send_template_message(self, to: str, template_name: str, *, language: str = "es", components=None):
        return {"to": to, "template": template_name, "components": components or []}

    async def pass_thread_control(self, recipient_id: str, metadata=None):  # type: ignore[override]
        return {"recipient": recipient_id, "metadata": metadata or {}}

    async def take_thread_control(self, recipient_id: str, metadata=None):  # type: ignore[override]
        return {"recipient": recipient_id, "metadata": metadata or {}}


@pytest.mark.anyio("asyncio")
async def test_process_message_raises_on_duplicate_message_id(tmp_path) -> None:
    """The orchestrator must reject duplicate inbound message ids at the DB layer."""

    session = SessionLocal()
    try:
        transport = DummyTransport()
        orchestrator = AgentOrchestrator(
            session=session,
            openai_service=DummyOpenAIService(),
            vector_store=VectorStoreService(
                index_path=str(tmp_path / "index.json"),
                backend="local",
                tenant_id="tenant-a",
            ),
            whatsapp_service=transport,  # type: ignore[arg-type]
            template_service=TemplateService(whatsapp_service=transport),  # type: ignore[arg-type]
            tenant_id="tenant-a",
        )

        await orchestrator.process_message("+56911111111", "Hola", message_id="wamid.dup")

        with pytest.raises(DuplicateInboundMessageError):
            await orchestrator.process_message("+56911111111", "Hola otra vez", message_id="wamid.dup")
    finally:
        session.close()
