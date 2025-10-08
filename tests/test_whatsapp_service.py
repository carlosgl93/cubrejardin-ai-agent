"""Tests for WhatsAppService Meta implementation."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import List

import httpx
import pytest

from models.database import Conversation, InMemorySession, SessionLocal, utc_now
from services.whatsapp_service import WhatsAppService
from utils import OutsideMessagingWindowError


class DummySettings:
    """Minimal settings stub for WhatsAppService."""

    whatsapp_phone_number_id = "1234567890"
    facebook_page_access_token = "test-token"
    facebook_app_secret = "app-secret"


@pytest.mark.anyio("asyncio")
async def test_send_text_message_uses_meta_endpoint(monkeypatch) -> None:
    """Sending a message hits the Meta messages endpoint and strips prefixes."""

    records: List[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        records.append(request)
        return httpx.Response(200, json={"messages": [{"id": "fake-id"}]})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("services.whatsapp_service.settings", DummySettings, raising=False)
    service = WhatsAppService(client=httpx.AsyncClient(transport=transport, base_url=WhatsAppService.BASE_URL))

    service.record_incoming_interaction("whatsapp:+521234567890")
    response = await service.send_text_message("whatsapp:+521234567890", "Hola Meta")
    assert response["messages"][0]["id"] == "fake-id"
    request = records[0]
    assert request.url.path == "/v21.0/1234567890/messages"
    payload = json.loads(request.content.decode())
    assert payload["to"] == "521234567890"
    assert payload["text"]["body"] == "Hola Meta"
    await service.close()


@pytest.mark.anyio("asyncio")
async def test_pass_thread_control_calls_expected_endpoint(monkeypatch) -> None:
    """Thread handover should call the correct Meta endpoint."""

    records: List[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        records.append(request)
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("services.whatsapp_service.settings", DummySettings, raising=False)
    service = WhatsAppService(client=httpx.AsyncClient(transport=transport, base_url=WhatsAppService.BASE_URL))

    await service.pass_thread_control(recipient_id="521234567890", metadata={"reason": "test"})
    request = records[-1]
    assert request.url.path.endswith("/pass_thread_control")
    body = json.loads(request.content.decode())
    assert body["recipient"]["id"] == "521234567890"
    assert body["metadata"]["reason"] == "test"
    await service.close()


@pytest.mark.anyio("asyncio")
async def test_validate_webhook_signature_success(monkeypatch) -> None:
    """The signature validator should accept correct hashes."""

    monkeypatch.setattr("services.whatsapp_service.settings", DummySettings, raising=False)
    svc = WhatsAppService(client=httpx.AsyncClient(base_url=WhatsAppService.BASE_URL))
    payload = b'{"object":"whatsapp_business_account"}'
    digest = hmac.new(DummySettings.facebook_app_secret.encode(), payload, hashlib.sha256).hexdigest()
    signature = f"sha256={digest}"
    assert svc.validate_webhook_signature(payload, signature) is True
    await svc.close()


@pytest.mark.anyio("asyncio")
async def test_send_text_message_raises_outside_window(monkeypatch) -> None:
    """Sending outside the 24h window should raise a custom exception."""

    monkeypatch.setattr("services.whatsapp_service.settings", DummySettings, raising=False)
    service = WhatsAppService(client=httpx.AsyncClient(base_url=WhatsAppService.BASE_URL))
    with pytest.raises(OutsideMessagingWindowError):
        await service.send_text_message("+5210000000", "Hola fuera de ventana")
    await service.close()


@pytest.mark.anyio("asyncio")
async def test_is_within_window_loads_from_persistence(monkeypatch) -> None:
    """The service should consult the persistence layer when cache is cold."""

    InMemorySession.storage.clear()
    InMemorySession.counters.clear()
    monkeypatch.setattr("services.whatsapp_service.settings", DummySettings, raising=False)

    session = SessionLocal()
    recent_ts = utc_now()
    conversation = Conversation(
        user_number="521999888777",
        role="user",
        message="Hola",
        last_interaction_at=recent_ts,
    )
    session.add(conversation)
    session.commit()

    service = WhatsAppService(
        client=httpx.AsyncClient(base_url=WhatsAppService.BASE_URL),
        session_factory=lambda: session,
    )

    assert service.is_within_24h_window("+521999888777") is True
    await service.close()
    session.close()
