"""Tests for DeduplicationService and webhook idempotency."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from services.deduplication_service import DeduplicationService
from main import app
import api.webhooks as webhooks_module

client = TestClient(app)


@pytest.mark.asyncio
async def test_deduplication_claim_and_duplicate():
    dedup = DeduplicationService(redis_url=None)
    dedup._redis_available = False

    # First claim should succeed
    assert await dedup.claim_message("msg_123", tenant_id="tenant_a") is True

    # Immediate second claim with same message_id should be rejected
    assert await dedup.claim_message("msg_123", tenant_id="tenant_a") is False

    # Different message_id should succeed
    assert await dedup.claim_message("msg_456", tenant_id="tenant_a") is True

    # Different tenant_id with same message_id should succeed
    assert await dedup.claim_message("msg_123", tenant_id="tenant_b") is True


@pytest.mark.asyncio
async def test_deduplication_is_processed():
    dedup = DeduplicationService(redis_url=None)
    dedup._redis_available = False

    assert await dedup.is_processed("msg_999") is False
    await dedup.claim_message("msg_999")
    assert await dedup.is_processed("msg_999") is True
    await dedup.mark_done("msg_999")
    assert await dedup.is_processed("msg_999") is True


def test_unified_webhook_discards_duplicate_instagram_mid(monkeypatch):
    payload = {
        "object": "instagram",
        "entry": [{
            "id": "PAGE_ID_999",
            "messaging": [{
                "sender": {"id": "IGSID_USER_42"},
                "recipient": {"id": "PAGE_ID_999"},
                "message": {"mid": "mid_dup_test_1", "text": "hola!"},
            }],
        }],
    }

    monkeypatch.setattr(webhooks_module.settings, "skip_webhook_signature_validation", True, raising=False)

    with patch("api.webhooks._resolve_tenant_for_instagram", return_value="TENANT_UUID"), \
         patch("api.webhooks._persist_conversation_message") as persist, \
         patch("api.webhooks._run_bot_pipeline", new_callable=AsyncMock) as run_bot:

        # First request: should process
        resp1 = client.post("/webhook", json=payload, headers={"X-Hub-Signature-256": "sha256=FAKE"})
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["results"][0]["status"] == "delivered"
        assert persist.call_count == 1
        assert run_bot.call_count == 1

        # Second request with SAME payload and mid: must be discarded as duplicate
        resp2 = client.post("/webhook", json=payload, headers={"X-Hub-Signature-256": "sha256=FAKE"})
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["results"][0]["status"] == "ignored_duplicate"
        # Persist and run_bot count must remain 1 (not called again)
        assert persist.call_count == 1
        assert run_bot.call_count == 1
