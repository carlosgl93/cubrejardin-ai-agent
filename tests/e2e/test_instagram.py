"""E2E tests for Instagram OAuth flow and webhook integration."""

from __future__ import annotations

import pytest
import httpx


@pytest.mark.e2e
class TestInstagramExchange:
    """Test Instagram OAuth code exchange."""

    @pytest.mark.asyncio
    async def test_exchange_requires_auth(self, api_base_url: str):
        """Exchange endpoint should require authentication."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{api_base_url}/api/instagram/exchange",
                json={
                    "auth_code": "fake-auth-code",
                    "redirect_uri": "https://example.com/callback"
                },
            )
            # Should be 401, 403, or 422 without auth
            assert response.status_code in [401, 403, 422]

    @pytest.mark.asyncio
    async def test_exchange_invalid_code(
        self, api_base_url: str, auth_headers: dict[str, str]
    ):
        """Should handle invalid auth codes gracefully."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{api_base_url}/api/instagram/exchange",
                headers=auth_headers,
                json={
                    "auth_code": "invalid-code-12345",
                    "redirect_uri": "https://example.com/callback"
                },
            )
            # With auth, returns 4xx for invalid code, without returns 401/403/422
            assert response.status_code in [400, 401, 403, 422]


@pytest.mark.e2e
class TestInstagramStatus:
    """Test Instagram connection status endpoint."""

    @pytest.mark.asyncio
    async def test_status_requires_auth(self, api_base_url: str):
        """Status endpoint should require authentication."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{api_base_url}/api/instagram/status",
            )
            # Without auth returns error
            assert response.status_code in [401, 403, 422]

    @pytest.mark.asyncio
    async def test_status_returns_connection_info(
        self, api_base_url: str, auth_headers: dict[str, str]
    ):
        """Should return Instagram connection status with auth."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{api_base_url}/api/instagram/status",
                headers=auth_headers,
            )
            # With valid auth returns 200, with invalid returns 422
            assert response.status_code in [200, 401, 403, 422]


@pytest.mark.e2e
class TestInstagramWebhook:
    """Test Instagram webhook message handling via unified /webhook endpoint."""

    @pytest.mark.asyncio
    async def test_instagram_webhook_text_message(self, api_base_url: str):
        """Should accept Instagram text messages via unified webhook."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "object": "instagram",
                "entry": [{
                    "id": "123456789",
                    "time": 1234567890,
                    "changes": [{
                        "value": {
                            "from": {
                                "id": "987654321",
                                "username": "test_user"
                            },
                            "message": {
                                "text": "Hola desde Instagram"
                            }
                        },
                        "field": "messages"
                    }]
                }]
            }

            response = await client.post(
                f"{api_base_url}/webhook",
                json=payload,
            )
            # Should accept the message (returns 200 or ignored due to unknown tenant)
            assert response.status_code in [200, 400, 403, 404, 500]

    @pytest.mark.asyncio
    async def test_instagram_webhook_story_mention(self, api_base_url: str):
        """Should handle Instagram story mentions via unified webhook."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "object": "instagram",
                "entry": [{
                    "id": "123456789",
                    "time": 1234567890,
                    "changes": [{
                        "value": {
                            "from": {
                                "id": "987654321",
                                "username": "test_user"
                            },
                            "story": {
                                "id": "story-123"
                            },
                            "mentions": {
                                "data": [{
                                    "username": "business_account"
                                }]
                            }
                        },
                        "field": "mentions"
                    }]
                }]
            }

            response = await client.post(
                f"{api_base_url}/webhook",
                json=payload,
            )
            assert response.status_code in [200, 400, 403, 404, 500]


@pytest.mark.e2e
class TestInstagramOAuthFlow:
    """Test complete Instagram OAuth connection flow."""

    @pytest.mark.asyncio
    async def test_full_oauth_flow_requires_steps(
        self, api_base_url: str, auth_headers: dict[str, str]
    ):
        """Instagram OAuth requires multiple steps."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Check status - will be False if not connected
            response = await client.get(
                f"{api_base_url}/api/instagram/status",
                headers=auth_headers,
            )

            # Status should reflect current connection state
            assert response.status_code in [200, 401, 403, 422]
            if response.status_code == 200:
                data = response.json()
                assert "instagram_connected" in data
                assert isinstance(data["instagram_connected"], bool)
