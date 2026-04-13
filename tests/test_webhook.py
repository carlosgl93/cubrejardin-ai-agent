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
