"""Tests for the WhatsApp webhook endpoint."""

from __future__ import annotations

import json
from typing import Any, Dict

import pytest
from fastapi import HTTPException

from api.webhooks import whatsapp_webhook


class DummyRequest:
    """Simple ASGI request stub."""

    def __init__(self, payload: Dict[str, Any]) -> None:
        self._payload = payload

    async def body(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    async def json(self) -> Dict[str, Any]:
        return self._payload


@pytest.mark.anyio("asyncio")
async def test_webhook_rejects_invalid_signature(monkeypatch) -> None:
    """Requests with invalid Meta signatures must be rejected."""

    monkeypatch.setattr("api.webhooks.settings.debug", False, raising=False)
    request = DummyRequest({"object": "whatsapp_business_account"})

    with pytest.raises(HTTPException) as exc:
        await whatsapp_webhook(
            request=request,
            x_hub_signature_256="sha256=invalid",
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == "Invalid signature"


class FakeWhatsAppService:
    """Stub WhatsApp client."""

    def __init__(self) -> None:
        self.sent_messages: list[dict] = []
        self.marked_read: list[str] = []

    async def send_text_message(self, to: str, body: str, **kwargs):
        self.sent_messages.append({"to": to, "body": body, **kwargs})
        return {"messages": [{"id": "wamid.out"}]}

    async def mark_as_read(self, message_id: str):
        self.marked_read.append(message_id)
        return {"status": "read"}

    def record_incoming_interaction(self, *_args, **_kwargs):
        return None

    async def close(self) -> None:
        return None


class FakeOrchestrator:
    """Stub Orchestrator."""

    def __init__(self) -> None:
        self.processed_messages: list[tuple[str, str]] = []

    async def has_processed_message(self, _id: str) -> bool:
        return False

    async def process_message(self, user_number: str, body_text: str, **kwargs):
        from models.schemas import AgentResponse
        self.processed_messages.append((user_number, body_text))
        return AgentResponse(message=f"Echo: {body_text}", intent="general")


@pytest.mark.anyio("asyncio")
async def test_webhook_unsupported_media_replies_polite_message(monkeypatch: pytest.MonkeyPatch) -> None:
    """Audio, images, etc. should receive polite text reply."""

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "test",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "test-phone"},
                            "messages": [
                                {
                                    "from": "56911112222",
                                    "id": "wamid.audio123",
                                    "timestamp": "1700000000",
                                    "type": "audio",
                                    "audio": {"id": "media-xyz"},
                                }
                            ],
                        }
                    }
                ],
            }
        ],
    }

    fake_client = FakeWhatsAppService()
    fake_orch = FakeOrchestrator()

    monkeypatch.setattr("api.webhooks._validate_whatsapp_signature", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("api.webhooks._get_active_handoff", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "api.webhooks._resolve_tenant_credentials",
        lambda *_args, **_kwargs: {
            "tenant_id": "tenant-media",
            "phone_number_id": "test-phone",
            "access_token": "token",
        },
    )
    monkeypatch.setattr("api.webhooks.WhatsAppService", lambda *args, **kwargs: fake_client)
    monkeypatch.setattr("api.webhooks.AgentOrchestrator", lambda *args, **kwargs: fake_orch)

    response = await whatsapp_webhook(
        request=DummyRequest(payload),
        x_hub_signature_256="sha256=dummy",
    )

    assert len(fake_client.marked_read) == 1
    assert fake_client.marked_read[0] == "wamid.audio123"
    assert len(fake_client.sent_messages) == 1
    assert "solo puedo procesar mensajes de texto" in fake_client.sent_messages[0]["body"]
    assert len(fake_orch.processed_messages) == 0
    assert response["results"][0]["status"] == "unsupported_media_handled"


@pytest.mark.anyio("asyncio")
async def test_webhook_interactive_button_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    """Button clicks should be routed as text to the orchestrator."""

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "test",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "test-phone"},
                            "messages": [
                                {
                                    "from": "56911112222",
                                    "id": "wamid.btn123",
                                    "timestamp": "1700000000",
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "button_reply",
                                        "button_reply": {
                                            "id": "btn_catalog",
                                            "title": "Ver catalogo",
                                        },
                                    },
                                }
                            ],
                        }
                    }
                ],
            }
        ],
    }

    fake_client = FakeWhatsAppService()
    fake_orch = FakeOrchestrator()

    monkeypatch.setattr("api.webhooks._validate_whatsapp_signature", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("api.webhooks._get_active_handoff", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "api.webhooks._resolve_tenant_credentials",
        lambda *_args, **_kwargs: {
            "tenant_id": "tenant-interactive",
            "phone_number_id": "test-phone",
            "access_token": "token",
        },
    )
    monkeypatch.setattr("api.webhooks.WhatsAppService", lambda *args, **kwargs: fake_client)
    monkeypatch.setattr("api.webhooks.AgentOrchestrator", lambda *args, **kwargs: fake_orch)

    response = await whatsapp_webhook(
        request=DummyRequest(payload),
        x_hub_signature_256="sha256=dummy",
    )

    assert len(fake_orch.processed_messages) == 1
    assert fake_orch.processed_messages[0] == ("56911112222", "Ver catalogo")
    assert len(fake_client.sent_messages) == 1
    assert fake_client.sent_messages[0]["body"] == "Echo: Ver catalogo"
    assert response["results"][0]["status"] == "delivered"
