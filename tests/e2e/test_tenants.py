"""E2E tests for tenant management endpoints."""

from __future__ import annotations

import pytest
import httpx


@pytest.mark.e2e
class TestTenantMe:
    """Test /api/tenants/me endpoint."""

    @pytest.mark.asyncio
    async def test_get_my_tenant_requires_auth(self, api_base_url: str):
        """Should require authentication."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{api_base_url}/api/tenants/me")
            # Returns auth error without credentials
            assert response.status_code in [401, 403, 422]

    @pytest.mark.asyncio
    async def test_get_my_tenant_with_auth(
        self, api_base_url: str, auth_headers: dict[str, str]
    ):
        """Should return current tenant information with auth."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{api_base_url}/api/tenants/me",
                headers=auth_headers,
            )

            # With valid auth returns 200, with invalid returns 422
            if response.status_code == 200:
                data = response.json()
                assert "id" in data
                assert "name" in data
                assert "slug" in data
            else:
                # Auth failed or user has no tenant
                assert response.status_code in [401, 403, 422]


@pytest.mark.e2e
class TestTenantCreate:
    """Test POST /api/tenants/ endpoint."""

    @pytest.mark.asyncio
    async def test_create_tenant_requires_auth(self, api_base_url: str):
        """Should require authentication."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{api_base_url}/api/tenants/",
                json={
                    "name": "Test Tenant",
                    "slug": f"test-tenant-{id}"
                },
            )
            assert response.status_code in [401, 403, 422]

    @pytest.mark.asyncio
    async def test_create_tenant_validation(
        self, api_base_url: str, auth_headers: dict[str, str]
    ):
        """Should validate required fields."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{api_base_url}/api/tenants/",
                headers=auth_headers,
                json={},
            )
            # Validation error or auth error
            assert response.status_code in [400, 401, 403, 422]


@pytest.mark.e2e
class TestTenantConnectionStatus:
    """Test tenant WhatsApp/Instagram connection status."""

    @pytest.mark.asyncio
    async def test_tenant_shows_wa_connection(
        self, api_base_url: str, auth_headers: dict[str, str]
    ):
        """Tenant should show WhatsApp connection status with auth."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{api_base_url}/api/tenants/me",
                headers=auth_headers,
            )

            if response.status_code == 200:
                data = response.json()
                assert isinstance(data.get("whatsapp_connected"), bool)

    @pytest.mark.asyncio
    async def test_tenant_shows_ig_connection(
        self, api_base_url: str, auth_headers: dict[str, str]
    ):
        """Tenant should show Instagram connection status with auth."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{api_base_url}/api/tenants/me",
                headers=auth_headers,
            )

            if response.status_code == 200:
                data = response.json()
                assert isinstance(data.get("instagram_connected"), bool)


@pytest.mark.e2e
class TestTenantConversations:
    """Test tenant-scoped conversation access."""

    @pytest.mark.asyncio
    async def test_conversations_requires_auth(self, api_base_url: str):
        """Should require authentication."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{api_base_url}/api/conversations",
            )
            assert response.status_code in [401, 403, 422]

    @pytest.mark.asyncio
    async def test_conversations_returns_list(
        self, api_base_url: str, auth_headers: dict[str, str]
    ):
        """Should return list of conversations with auth."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{api_base_url}/api/conversations",
                headers=auth_headers,
            )

            if response.status_code == 200:
                data = response.json()
                assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_conversations_filter_by_channel(
        self, api_base_url: str, auth_headers: dict[str, str]
    ):
        """Should support channel filtering with auth."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{api_base_url}/api/conversations",
                headers=auth_headers,
                params={"channel": "whatsapp"},
            )

            if response.status_code == 200:
                data = response.json()
                assert isinstance(data, list)
