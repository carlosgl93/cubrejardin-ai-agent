"""Tests for the unified /webhook router (Facebook Page / Messenger branch + GET verification)."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app
import api.webhooks as webhooks_module

client = TestClient(app)


def test_unified_webhook_get_challenge_success(monkeypatch):
    monkeypatch.setattr(webhooks_module.settings, "whatsapp_webhook_verify_token", "secret123", raising=False)
    monkeypatch.setattr(webhooks_module.settings, "facebook_messenger_verify_token", "secret456", raising=False)

    resp = client.get("/webhook?hub.mode=subscribe&hub.challenge=998877&hub.verify_token=secret123")
    assert resp.status_code == 200
    assert resp.text == "998877"

    resp2 = client.get("/webhook?hub.mode=subscribe&hub.challenge=554433&hub.verify_token=secret456")
    assert resp2.status_code == 200
    assert resp2.text == "554433"


def test_unified_webhook_get_challenge_invalid_token(monkeypatch):
    monkeypatch.setattr(webhooks_module.settings, "whatsapp_webhook_verify_token", "secret123", raising=False)
    monkeypatch.setattr(webhooks_module.settings, "facebook_messenger_verify_token", "secret456", raising=False)

    resp = client.get("/webhook?hub.mode=subscribe&hub.challenge=998877&hub.verify_token=wrong_token")
    assert resp.status_code == 403


def test_page_webhook_persists_message_and_dispatches_bot(monkeypatch):
    payload = {
        "object": "page",
        "entry": [{
            "id": "PAGE_ID_999",
            "messaging": [{
                "sender": {"id": "PSID_USER_42"},
                "recipient": {"id": "PAGE_ID_999"},
                "message": {"mid": "m_mid_1", "text": "Hola Facebook Messenger!"},
            }],
        }],
    }

    monkeypatch.setattr(webhooks_module.settings, "skip_webhook_signature_validation", True, raising=False)

    with patch("api.webhooks._resolve_tenant_for_messenger", return_value="TENANT_UUID"), \
         patch("api.webhooks._persist_conversation_message") as persist, \
         patch("api.webhooks._run_bot_pipeline") as run_bot:
        resp = client.post(
            "/webhook",
            json=payload,
            headers={"X-Hub-Signature-256": "sha256=FAKE"},
        )
    assert resp.status_code == 200
    persist.assert_called_once()
    call_kwargs = persist.call_args.kwargs
    assert call_kwargs["channel"] == "messenger"
    assert call_kwargs["channel_user_id"] == "PSID_USER_42"
    assert call_kwargs["message"] == "Hola Facebook Messenger!"
