"""Tests for /api/instagram/exchange endpoint."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from api.tenant_context import TenantContext, get_tenant_context
from main import app

client = TestClient(app)


def test_exchange_endpoint_persists_credentials():
    """Exchanges code, resolves IG account, persists creds."""
    fake_ctx = TenantContext(
        tenant_id="TENANT_UUID",
        user_id="USER_UUID",
        role="owner",
        tenant_name="Test Tenant",
    )

    # The endpoint calls _graph_get multiple times during the IG flow:
    #  1. code -> short-lived user token
    #  2. short -> long-lived user token (with expires_in)
    #  3. /me/accounts to list pages
    #  4. /{page_id}?fields=instagram_business_account
    # Return the correct shape per call.
    graph_responses = [
        {"access_token": "SHORT_LIVED_TOKEN"},
        {"access_token": "PAGE_TOKEN_LONG", "expires_in": 5184000},
        {"data": [{"id": "1234567890", "access_token": "PAGE_ACCESS_TOKEN"}]},
        {"instagram_business_account": {"id": "17841401234567890"}},
    ]

    def override_get_tenant_context():
        return fake_ctx

    app.dependency_overrides[get_tenant_context] = override_get_tenant_context
    try:
        with patch("api.instagram._graph_get", side_effect=graph_responses), \
             patch("api.instagram._supabase_upsert_ig_creds") as upsert, \
             patch("api.instagram._supabase_fetch_ig_creds", return_value=None):
            resp = client.post(
                "/api/instagram/exchange",
                json={"auth_code": "AUTH_CODE_XYZ", "redirect_uri": "https://app/cb"},
                headers={"Authorization": "Bearer FAKE_JWT"},
            )
    finally:
        app.dependency_overrides.pop(get_tenant_context, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["ig_user_id"] == "17841401234567890"
    assert body["page_id"] == "1234567890"
    assert body["status"] == "active"
    assert body["token_expires_at"]
    upsert.assert_called_once()


def test_status_endpoint_returns_state():
    fake_ctx = TenantContext(
        tenant_id="TENANT_UUID",
        user_id="USER_UUID",
        role="owner",
        tenant_name="Test Tenant",
    )

    def override_get_tenant_context():
        return fake_ctx

    app.dependency_overrides[get_tenant_context] = override_get_tenant_context
    try:
        with patch("api.instagram._supabase_fetch_ig_creds", return_value={
            "status": "active",
            "ig_user_id": "17841401234567890",
            "page_id": "1234567890",
            "token_expires_at": "2026-09-10T00:00:00+00:00",
        }):
            resp = client.get("/api/instagram/status",
                              headers={"Authorization": "Bearer FAKE_JWT"})
    finally:
        app.dependency_overrides.pop(get_tenant_context, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["instagram_connected"] is True
    assert body["status"] == "active"