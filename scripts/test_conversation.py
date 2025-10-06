"""Simulate conversation with orchestrator."""

from __future__ import annotations

from agents.orchestrator import AgentOrchestrator
from models.database import SessionLocal
from services.openai_service import OpenAIService
from services.vector_store import VectorStoreService
from services.whatsapp_service import WhatsAppService


class DummyWhatsAppService(WhatsAppService):
    """Override send message for testing."""

    def send_message(self, to: str, body: str) -> None:  # type: ignore[override]
        print(f"[TwilioStub] -> {to}: {body}")


def main() -> None:
    """Run interactive simulation."""

    session = SessionLocal()
    orchestrator = AgentOrchestrator(
        session=session,
        openai_service=OpenAIService(),
        vector_store=VectorStoreService(),
        whatsapp_service=DummyWhatsAppService(),
    )
    print("Enter 'exit' to quit.")
    user_number = "+123456789"
    while True:
        text = input("You: ")
        if text.lower() == "exit":
            break
        response = orchestrator.process_message(user_number, text)
        print(f"Bot: {response}")
    session.close()


if __name__ == "__main__":
    main()
