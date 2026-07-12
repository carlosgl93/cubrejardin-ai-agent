"""Tests for GET /api/conversations channel filter."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from api.tenant_context import TenantContext, get_tenant_context
from main import app

client = TestClient(app)


def _override_ctx():
    return TenantContext(
        tenant_id="11111111-1111-1111-1111-111111111111",
        user_id="USER_UUID",
        role="owner",
        tenant_name="Test Tenant",
    )


def test_conversations_filter_by_channel_instagram():
    """`/api/conversations?channel=instagram` returns only IG contacts."""
    fake_rows = [
        {
            "channel": "instagram",
            "channel_user_id": "IGSID_1",
            "last_message": "hi",
            "last_at": "2026-07-12T00:00:00Z",
            "count": 1,
        },
    ]
    app.dependency_overrides[get_tenant_context] = _override_ctx
    try:
        with patch("api.conversations._list_contacts", return_value=fake_rows):
            resp = client.get(
                "/api/conversations?channel=instagram",
                headers={"Authorization": "Bearer FAKE"},
            )
    finally:
        app.dependency_overrides.pop(get_tenant_context, None)

    assert resp.status_code == 200
    assert resp.json()["contacts"][0]["channel"] == "instagram"


def test_conversations_no_filter_returns_all():
    """No channel query param returns all channels (no filter applied)."""
    fake_rows = [
        {"channel": "whatsapp", "channel_user_id": "WA_1",
         "last_message": "yo", "last_at": "2026-07-12T00:00:00Z", "count": 1},
        {"channel": "instagram", "channel_user_id": "IG_1",
         "last_message": "hi", "last_at": "2026-07-12T00:00:00Z", "count": 1},
    ]
    app.dependency_overrides[get_tenant_context] = _override_ctx
    try:
        with patch("api.conversations._list_contacts", return_value=fake_rows):
            resp = client.get(
                "/api/conversations",
                headers={"Authorization": "Bearer FAKE"},
            )
    finally:
        app.dependency_overrides.pop(get_tenant_context, None)

    assert resp.status_code == 200
    contacts = resp.json()["contacts"]
    assert len(contacts) == 2
    channels = {c["channel"] for c in contacts}
    assert channels == {"whatsapp", "instagram"}