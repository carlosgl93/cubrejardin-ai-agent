"""Tests for the unified /webhook router (Instagram branch)."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app
import api.webhooks as webhooks_module

client = TestClient(app)


def test_ig_webhook_persists_message_and_dispatches_bot(monkeypatch):
    payload = {
        "object": "instagram",
        "entry": [{
            "id": "PAGE_ID_999",
            "messaging": [{
                "sender": {"id": "IGSID_USER_42"},
                "recipient": {"id": "IGSID_PAGE"},
                "message": {"mid": "m_z", "text": "precio?"},
            }],
        }],
    }

    # Bypass HMAC check for unit test — focus is dispatch/persist logic.
    monkeypatch.setattr(webhooks_module.settings, "skip_webhook_signature_validation", True, raising=False)

    with patch("api.webhooks._resolve_tenant_for_instagram", return_value="TENANT_UUID"), \
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
    assert call_kwargs["channel"] == "instagram"
    assert call_kwargs["channel_user_id"] == "IGSID_USER_42"
    assert call_kwargs["message"] == "precio?"
