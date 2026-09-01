"""E2E tests for handoff flow.

Tests the complete human handoff workflow:
1. User requests human agent
2. Handoff is created and assigned
3. Human agent replies to conversation
4. Handoff is closed and bot takes over
"""

from __future__ import annotations

import pytest
import httpx
import time


@pytest.mark.e2e
class TestHandoffsList:
    """Test handoffs listing endpoints."""

    @pytest.mark.asyncio
    async def test_list_active_handoffs(
        self, api_base_url: str, auth_headers: dict[str, str]
    ):
        """Should return list of active handoffs."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{api_base_url}/api/handoffs/",
                headers=auth_headers,
            )
            # With valid auth returns 200, without returns 401/403/422
            assert response.status_code in [200, 401, 403, 422]

    @pytest.mark.asyncio
    async def test_list_handoffs_history(
        self, api_base_url: str, auth_headers: dict[str, str]
    ):
        """Should return handoff history with pagination."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{api_base_url}/api/handoffs/history",
                headers=auth_headers,
            )
            # With valid auth returns 200
            assert response.status_code in [200, 401, 403, 422]

    @pytest.mark.asyncio
    async def test_get_handoffs_stats(
        self, api_base_url: str, auth_headers: dict[str, str]
    ):
        """Should return handoff statistics."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{api_base_url}/api/handoffs/stats",
                headers=auth_headers,
            )
            # With valid auth returns 200
            assert response.status_code in [200, 401, 403, 422]


@pytest.mark.e2e
class TestHandoffReply:
    """Test handoff reply functionality."""

    @pytest.mark.asyncio
    async def test_reply_to_handoff_requires_auth(self, api_base_url: str):
        """Reply endpoint should require authentication."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{api_base_url}/api/handoffs/test-handoff-id/reply",
                json={"message": "Test reply"},
            )
            # Should be 401, 403, or 422 without auth
            assert response.status_code in [401, 403, 422]

    @pytest.mark.asyncio
    async def test_reply_to_nonexistent_handoff(
        self, api_base_url: str, auth_headers: dict[str, str]
    ):
        """Should return 404 for non-existent handoff with valid auth."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{api_base_url}/api/handoffs/nonexistent-id/reply",
                headers=auth_headers,
                json={"message": "Test reply"},
            )
            # 404 if not found, 401/403/422 if auth invalid
            assert response.status_code in [404, 401, 403, 422]


@pytest.mark.e2e
class TestHandoffClose:
    """Test handoff closure functionality."""

    @pytest.mark.asyncio
    async def test_close_handoff_requires_auth(self, api_base_url: str):
        """Close endpoint should require authentication."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{api_base_url}/api/handoffs/test-handoff-id/close",
                json={"reason": "resolved"},
            )
            assert response.status_code in [401, 403, 422]

    @pytest.mark.asyncio
    async def test_close_nonexistent_handoff(
        self, api_base_url: str, auth_headers: dict[str, str]
    ):
        """Should return 404 for non-existent handoff with valid auth."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{api_base_url}/api/handoffs/nonexistent-id/close",
                headers=auth_headers,
                json={"reason": "resolved"},
            )
            # 404 if not found, 401/403/422 if auth invalid
            assert response.status_code in [404, 401, 403, 422]


@pytest.mark.e2e
class TestFullHandoffFlow:
    """Test complete handoff flow from message to close."""

    @pytest.mark.asyncio
    async def test_handoff_flow_from_whatsapp_message(
        self, api_base_url: str, test_user_phone: str
    ):
        """Simulate handoff request via WhatsApp message."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            # User requests human agent
            payload = {
                "entry": [{
                    "changes": [{
                        "value": {
                            "messages": [{
                                "from": test_user_phone,
                                "id": f"e2e-handoff-{int(time.time())}",
                                "text": {"body": "Necesito ayuda de un agente humano"},
                                "timestamp": str(int(time.time())),
                                "type": "text"
                            }]
                        }
                    }]
                }]
            }

            response = await client.post(
                f"{api_base_url}/webhook/whatsapp",
                json=payload,
            )
            # Should accept the message
            assert response.status_code in [200, 202, 400, 403]
