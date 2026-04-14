"""Tests for webhook multi-tenant resolution and duplicate handling."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from agents.orchestrator import DuplicateInboundMessageError
from api import webhooks
from models.schemas import AgentResponse


class DummyRequest:
    """Simple ASGI request stub."""

    def __init__(self, body: Dict[str, Any]) -> None:
        self._body = body

    async def body(self) -> bytes:
        return json.dumps(self._body).encode("utf-8")

    async def json(self) -> Dict[str, Any]:
        return self._body


class FakeWhatsAppService:
    """Capture WhatsApp send attempts."""

    def __init__(self) -> None:
        self.sent_messages: List[str] = []

    async def send_text_message(self, _to: str, body: str, *, preview_url: bool = True):
        self.sent_messages.append(body)
        return {"messages": [{"id": "out"}]}

    async def send_template_message(self, to: str, template_name: str, *, language: str = "es", components=None):
        return {"to": to, "template": template_name, "components": components or []}

    async def mark_as_read(self, *_args, **_kwargs):
        return {"status": "read"}

    def record_incoming_interaction(self, *_args, **_kwargs):
        return None

    def validate_webhook_signature(self, *_args, **_kwargs) -> bool:
        return True

    async def close(self) -> None:
        return None


class FakeMessengerService:
    """Capture Messenger lifecycle calls."""

    def __init__(self, token: str | None = None, **_kwargs) -> None:
        self.token = token
        self.sent_messages: List[str] = []
        self.typing_calls: List[str] = []
        self.closed = False

    async def send_text_message(self, _recipient_id: str, text: str):
        self.sent_messages.append(text)
        return {"message_id": "fb-out"}

    async def send_typing_action(self, recipient_id: str, action: str = "typing_on"):
        self.typing_calls.append(f"{recipient_id}:{action}")
        return {"status": "ok"}

    def record_incoming_interaction(self, *_args, **_kwargs):
        return None

    async def close(self) -> None:
        self.closed = True


@pytest.mark.anyio("asyncio")
async def test_whatsapp_webhook_marks_duplicate_without_sending(monkeypatch: pytest.MonkeyPatch) -> None:
    """A duplicate inbound message must be ignored without sending a second reply."""

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "test",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "phone-id"},
                            "messages": [
                                {
                                    "from": "5210000000",
                                    "id": "wamid.dup",
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

    class DummyOrchestrator:
        async def has_processed_message(self, _message_id: str) -> bool:
            return False

        async def process_message(self, *_args, **_kwargs):
            raise DuplicateInboundMessageError("wamid.dup", "tenant-a")

    monkeypatch.setattr(webhooks, "_validate_whatsapp_signature", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        webhooks,
        "_resolve_tenant_credentials",
        lambda *_args, **_kwargs: {
            "tenant_id": "tenant-a",
            "phone_number_id": "phone-id",
            "access_token": "wa-token",
        },
    )
    monkeypatch.setattr(webhooks, "WhatsAppService", lambda *args, **kwargs: fake_client)
    monkeypatch.setattr(webhooks, "build_orchestrator", lambda *args, **kwargs: DummyOrchestrator())

    response = await webhooks.whatsapp_webhook(
        request=DummyRequest(payload),
        x_hub_signature_256="sha256=dummy",
    )

    assert response["results"][-1]["status"] == "duplicate"
    assert fake_client.sent_messages == []


@pytest.mark.anyio("asyncio")
async def test_facebook_webhook_resolves_tenant_from_page_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Messenger should resolve tenant and token per page id, not from a global tenant env."""

    payload = {
        "object": "page",
        "entry": [
            {
                "id": "page-123",
                "time": 1700000000,
                "messaging": [
                    {
                        "sender": {"id": "user-123"},
                        "recipient": {"id": "page-123"},
                        "timestamp": 1700000000,
                        "message": {"mid": "mid-1", "text": "Hola desde Messenger"},
                    }
                ],
            }
        ],
    }

    captured: dict[str, Any] = {}

    class DummyOrchestrator:
        async def has_processed_message(self, _message_id: str) -> bool:
            return False

        async def process_message(self, *_args, **_kwargs) -> AgentResponse:
            return AgentResponse(message="Respuesta Messenger", intent="consulta", category="VALID_QUERY")

    def fake_build_orchestrator(*, db, openai_service, vector_store, messaging_service, template_service, tenant_id):
        captured["tenant_id"] = tenant_id
        captured["vector_store_tenant_id"] = vector_store.tenant_id
        captured["messenger_token"] = messaging_service.token
        return DummyOrchestrator()

    monkeypatch.setattr(webhooks, "_validate_facebook_messenger_signature", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        webhooks,
        "_resolve_facebook_messenger_credentials",
        lambda *_args, **_kwargs: {
            "tenant_id": "tenant-fb",
            "page_id": "page-123",
            "page_access_token": "fb-page-token",
        },
    )
    monkeypatch.setattr(webhooks, "FacebookMessengerService", FakeMessengerService)
    monkeypatch.setattr(webhooks, "build_orchestrator", fake_build_orchestrator)

    response = await webhooks.facebook_messenger_webhook(
        request=DummyRequest(payload),
        x_hub_signature_256="sha256=dummy",
        openai_service=SimpleNamespace(),
    )

    assert captured["tenant_id"] == "tenant-fb"
    assert captured["vector_store_tenant_id"] == "tenant-fb"
    assert captured["messenger_token"] == "fb-page-token"
    assert response["results"][0]["status"] == "delivered"
    assert response["results"][0]["tenant_id"] == "tenant-fb"
    assert response["results"][0]["page_id"] == "page-123"
