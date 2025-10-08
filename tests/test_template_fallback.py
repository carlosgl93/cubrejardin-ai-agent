"""Tests for template fallback logic."""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

from api.webhooks import whatsapp_webhook
from models.schemas import AgentResponse
from services.template_service import TemplateService
from utils import OutsideMessagingWindowError


class FakeWhatsAppService:
    """Stub WhatsApp client that captures template sends."""

    def __init__(self) -> None:
        self.template_calls: List[Dict[str, Any]] = []

    async def send_template_message(self, to: str, template_name: str, *, language: str = "es", components=None):
        self.template_calls.append(
            {"to": to, "template": template_name, "components": components or []}
        )
        return {"messages": [{"id": "tpl"}]}

    async def send_text_message(self, *_args, **_kwargs):
        raise OutsideMessagingWindowError("5210000000")

    def record_incoming_interaction(self, *_args, **_kwargs):
        return None

    async def mark_as_read(self, *_args, **_kwargs):
        return {"status": "read"}

    def validate_webhook_signature(self, *_args, **_kwargs) -> bool:
        return True

    async def close(self) -> None:
        return None


class DummyRequest:
    """Simple ASGI request stub."""

    def __init__(self, body: Dict[str, Any]) -> None:
        self._body = body

    async def body(self) -> bytes:
        return json.dumps(self._body).encode("utf-8")

    async def json(self) -> Dict[str, Any]:
        return self._body


class DummyOrchestrator:
    """Return a static agent response and capture fallback usage."""

    def __init__(self, template_service: TemplateService) -> None:
        self.template_service = template_service
        self.fallback_calls: List[Dict[str, Any]] = []

    async def has_processed_message(self, _message_id: str) -> bool:
        return False

    async def process_message(self, *_args, **_kwargs) -> AgentResponse:
        return AgentResponse(
            message="Respuesta fuera de ventana",
            intent="session_expired",
            data={"guardian": {"entities": {"name": "Benja"}}},
        )

    async def handle_outside_window(self, user_number: str, response: AgentResponse) -> str:
        result = await self.template_service.send_fallback_template(user_number, response)
        self.fallback_calls.append({"user": user_number, "template": result.template_name})
        return result.template_name


@pytest.mark.anyio("asyncio")
async def test_template_service_uses_mapping() -> None:
    """Template service should resolve template names using mappings."""

    fake_client = FakeWhatsAppService()
    template_service = TemplateService(
        whatsapp_service=fake_client,
        default_template="session_expired",
        template_mapping={"handoff": "handoff_notification", "session_expired": "session_expired"},
    )
    response = AgentResponse(
        message="Hola",
        intent="handoff",
        data={"guardian": {"entities": {"name": "Ana"}}, "rag": {"answer": "Te conectamos"}},
    )

    result = await template_service.send_fallback_template("521111222333", response)

    assert result.template_name == "handoff_notification"
    assert fake_client.template_calls
    first_call = fake_client.template_calls[0]
    assert first_call["template"] == "handoff_notification"
    assert first_call["components"][0]["parameters"][0]["text"] == "Ana"


@pytest.mark.anyio("asyncio")
async def test_webhook_fallback_sends_template() -> None:
    """Webhook should fallback to templates when outside window."""

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "test",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {},
                            "messages": [
                                {
                                    "from": "5210000000",
                                    "id": "wamid.test",
                                    "timestamp": "1700000000",
                                    "type": "text",
                                    "text": {"body": "Hola"},
                                }
                            ],
                        }
                    }
                ],
            }
        ],
    }

    fake_client = FakeWhatsAppService()
    template_service = TemplateService(
        whatsapp_service=fake_client,
        default_template="session_expired",
        template_mapping={"session_expired": "session_expired"},
    )
    orchestrator = DummyOrchestrator(template_service=template_service)

    response = await whatsapp_webhook(
        request=DummyRequest(payload),
        x_hub_signature_256="sha256=dummy",
        orchestrator=orchestrator,  # type: ignore[arg-type]
        whatsapp_service=fake_client,  # type: ignore[arg-type]
    )

    assert orchestrator.fallback_calls
    assert fake_client.template_calls
    assert response["results"][-1]["status"] == "template_sent"
