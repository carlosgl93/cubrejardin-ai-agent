"""Tests for GET /api/tenants/me."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.tenant_context import TenantContext, get_tenant_context
from main import app

client = TestClient(app)


def _fake_tenant_row():
    return MagicMock(
        data={
            "id": "11111111-1111-1111-1111-111111111111",
            "name": "Test Tenant",
            "slug": "test-tenant",
            "plan": "free",
        }
    )


def _fake_supabase_client():
    """Mock supabase client that returns the tenant row for any tenants-table query."""
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = _fake_tenant_row()
    return sb


def _override_ctx():
    return TenantContext(
        tenant_id="11111111-1111-1111-1111-111111111111",
        user_id="USER_UUID",
        role="owner",
        tenant_name="Test Tenant",
    )


def test_me_returns_instagram_connected_flag():
    """`/tenants/me` exposes `instagram_connected` from the IG credentials table."""
    app.dependency_overrides[get_tenant_context] = _override_ctx
    try:
        with patch("api.tenants.get_supabase_client", return_value=_fake_supabase_client()), \
             patch("api.tenants._fetch_instagram_state", return_value={"instagram_connected": False}):
            resp = client.get(
                "/api/tenants/me",
                headers={"Authorization": "Bearer FAKE"},
            )
    finally:
        app.dependency_overrides.pop(get_tenant_context, None)

    assert resp.status_code == 200
    assert resp.json()["instagram_connected"] is False


def test_me_instagram_connected_true_when_active_credential():
    """Active IG credentials flip `instagram_connected` to True."""
    app.dependency_overrides[get_tenant_context] = _override_ctx
    try:
        with patch("api.tenants.get_supabase_client", return_value=_fake_supabase_client()), \
             patch("api.tenants._fetch_instagram_state", return_value={"instagram_connected": True}):
            resp = client.get(
                "/api/tenants/me",
                headers={"Authorization": "Bearer FAKE"},
            )
    finally:
        app.dependency_overrides.pop(get_tenant_context, None)

    assert resp.status_code == 200
    assert resp.json()["instagram_connected"] is True


def test_me_returns_whatsapp_connected_flag():
    """`/tenants/me` also exposes `whatsapp_connected` for parity."""
    app.dependency_overrides[get_tenant_context] = _override_ctx
    try:
        with patch("api.tenants.get_supabase_client", return_value=_fake_supabase_client()), \
             patch("api.tenants._fetch_whatsapp_state", return_value={"whatsapp_connected": True}):
            resp = client.get(
                "/api/tenants/me",
                headers={"Authorization": "Bearer FAKE"},
            )
    finally:
        app.dependency_overrides.pop(get_tenant_context, None)

    assert resp.status_code == 200
    assert resp.json()["whatsapp_connected"] is True
