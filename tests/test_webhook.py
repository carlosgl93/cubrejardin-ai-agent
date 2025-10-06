"""Tests for the WhatsApp webhook endpoint."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from api.webhooks import whatsapp_webhook


@pytest.fixture
def anyio_backend():
    return "asyncio"


class DummyRequest:
    """Simple ASGI request stub."""

    def __init__(self, url: str, data: dict[str, str]) -> None:
        self._url = url
        self._data = data

    @property
    def url(self) -> str:
        return self._url

    async def form(self) -> dict[str, str]:
        return dict(self._data)


class DummyOrchestrator:
    """Ensure the orchestrator is not called for invalid signatures."""

    def process_message(self, *_args, **_kwargs):  # type: ignore[unused-arg]
        raise AssertionError("process_message should not be called")


class DummyWhatsAppService:
    """Capture signature validation calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str], str]] = []

    def validate_signature(self, url: str, params: dict[str, str], signature: str) -> bool:
        self.calls.append((url, dict(params), signature))
        return False


@pytest.mark.anyio
async def test_webhook_rejects_invalid_signature() -> None:
    """Requests with invalid Twilio signatures must be rejected."""

    request = DummyRequest("https://example.com/webhook/twilio", {"From": "+123456789", "Body": "Hola"})
    orchestrator = DummyOrchestrator()
    whatsapp_service = DummyWhatsAppService()

    with pytest.raises(HTTPException) as exc:
        await whatsapp_webhook(
            request=request,
            x_twilio_signature="invalid",
            orchestrator=orchestrator,
            whatsapp_service=whatsapp_service,
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == "Invalid Twilio signature"
    assert whatsapp_service.calls
