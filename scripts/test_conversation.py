"""Simulate conversation with orchestrator."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.orchestrator import AgentOrchestrator
from models.database import SessionLocal
from services.openai_service import OpenAIService
from services.vector_store import VectorStoreService
from services.template_service import TemplateService


class DummyWhatsAppService:
    """Override network interactions for local testing."""

    async def send_text_message(self, to: str, body: str, *, preview_url: bool = True) -> Dict[str, Any]:
        print(f"[MetaStub] -> {to}: {body}")
        return {"messages": [{"id": "local"}]}

    async def pass_thread_control(self, recipient_id: str, metadata=None):  # type: ignore[override]
        print(f"[MetaStub] pass control to human: {recipient_id} ({metadata})")
        return {"status": "ok"}

    async def take_thread_control(self, recipient_id: str, metadata=None):  # type: ignore[override]
        print(f"[MetaStub] take control back: {recipient_id} ({metadata})")
        return {"status": "ok"}

    async def mark_as_read(self, message_id: str) -> Dict[str, Any]:
        return {"status": "read", "message_id": message_id}

    def validate_webhook_signature(self, payload: bytes, signature: str) -> bool:
        return True

    async def close(self) -> None:
        return None

    def record_incoming_interaction(self, user_id: str, *, timestamp=None) -> None:  # type: ignore[override]
        pass

    def is_within_24h_window(self, user_id: str) -> bool:  # type: ignore[override]
        return True

    async def send_template_message(self, to: str, template_name: str, *, language: str = "es", components=None):
        print(f"[MetaStub][Template:{template_name}] -> {to} components={components}")
        return {"messages": [{"id": "template"}]}


async def main() -> None:
    """Run interactive simulation."""

    session = SessionLocal()
    whatsapp_stub = DummyWhatsAppService()
    orchestrator = AgentOrchestrator(
        session=session,
        openai_service=OpenAIService(),
        vector_store=VectorStoreService(),
        whatsapp_service=whatsapp_stub,  # type: ignore[arg-type]
        template_service=TemplateService(whatsapp_service=whatsapp_stub),  # type: ignore[arg-type]
    )
    print("Enter 'exit' to quit.")
    user_number = "+123456789"
    try:
        while True:
            text = input("You: ")
            if text.lower() == "exit":
                break
            response = await orchestrator.process_message(user_number, text)
            print(f"Bot: {response.message}")
    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())
