"""Tests for manual reply and bot resuming from /conversations."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from api.tenant_context import TenantContext, get_tenant_context
from main import app

client = TestClient(app)

FAKE_TENANT_ID = "11111111-1111-1111-1111-111111111111"


def _override_ctx():
    return TenantContext(
        tenant_id=FAKE_TENANT_ID,
        user_id="USER_123",
        role="owner",
        tenant_name="Test Tenant",
    )


@pytest.fixture(autouse=True)
def apply_ctx():
    app.dependency_overrides[get_tenant_context] = _override_ctx
    yield
    app.dependency_overrides.pop(get_tenant_context, None)


def test_reply_conversation_creates_handoff_and_sends():
    fake_sb = MagicMock()

    # Query for existing handoff -> empty
    mock_handoff_query = MagicMock()
    mock_handoff_query.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    
    # Insert new handoff
    mock_handoff_insert = MagicMock()
    mock_handoff_insert.data = [{"id": "new-handoff-uuid"}]
    mock_handoff_query.insert.return_value.execute.return_value = mock_handoff_insert

    # Insert conversation message
    mock_conv_query = MagicMock()
    mock_conv_query.insert.return_value.execute.return_value.data = [{
        "id": 99,
        "message": "Hola cliente",
        "role": "assistant",
    }]

    def fake_table(name: str):
        if name == "handoffs":
            return mock_handoff_query
        elif name == "conversations":
            return mock_conv_query
        return MagicMock()

    fake_sb.table.side_effect = fake_table

    mock_adapter = MagicMock()
    mock_adapter.send_message = AsyncMock(return_value={"id": "msg-meta-1"})

    with patch("api.conversations.get_supabase_client", return_value=fake_sb), \
         patch("api.conversations.get_adapter", return_value=mock_adapter):

        resp = client.post(
            "/api/conversations/reply",
            json={
                "channel": "whatsapp",
                "channel_user_id": "+56912345678",
                "message": "Hola cliente",
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "sent"
        assert data["handoff_id"] == "new-handoff-uuid"
        mock_adapter.send_message.assert_awaited_once_with(
            recipient_id="+56912345678",
            text="Hola cliente",
            tenant_id=FAKE_TENANT_ID,
        )


def test_reply_conversation_rejects_invalid_channel():
    resp = client.post(
        "/api/conversations/reply",
        json={
            "channel": "telegram",
            "channel_user_id": "12345",
            "message": "test",
        },
    )
    assert resp.status_code == 400


def test_resume_bot_closes_active_handoff():
    fake_sb = MagicMock()
    mock_update = MagicMock()
    mock_update.data = [{"id": "handoff-1", "status": "closed"}]
    fake_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = mock_update

    with patch("api.conversations.get_supabase_client", return_value=fake_sb):
        resp = client.post(
            "/api/conversations/resume-bot",
            json={
                "channel": "whatsapp",
                "channel_user_id": "+56912345678",
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "bot_resumed"
        assert data["closed_count"] == 1
