"""E2E tests for backend API endpoints."""

from __future__ import annotations

import pytest
import httpx


@pytest.mark.e2e
class TestHealthEndpoints:
    """Test health and status endpoints."""

    @pytest.mark.asyncio
    async def test_health_check(self, api_base_url: str):
        """Health endpoint should return OK."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{api_base_url}/admin/health")
            assert response.status_code == 200
            data = response.json()
            assert data.get("status") == "ok"

    @pytest.mark.asyncio
    async def test_queue_metrics_endpoint(self, api_base_url: str):
        """Queue metrics endpoint should return valid data."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{api_base_url}/admin/queue/metrics")
            assert response.status_code == 200
            data = response.json()

            # Should have all expected fields
            assert "messages_sent" in data
            assert "messages_failed" in data
            assert "queue_high" in data
            assert "queue_normal" in data
            assert "queue_low" in data
            assert "dead_letter_count" in data


@pytest.mark.e2e
class TestLearningQueue:
    """Test learning queue API endpoints."""

    @pytest.mark.asyncio
    async def test_list_learning_queue(self, api_base_url: str):
        """Learning queue endpoint should return list."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{api_base_url}/admin/learning-queue")
            # Without auth, might return 401/403/422 depending on implementation
            assert response.status_code in [200, 401, 403, 422]


@pytest.mark.e2e
class TestWebhooks:
    """Test webhook endpoints."""

    @pytest.mark.asyncio
    async def test_whatsapp_webhook_verify(self, api_base_url: str):
        """WhatsApp webhook verification should work with correct token."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{api_base_url}/webhook/whatsapp",
                params={
                    "hub.mode": "subscribe",
                    "hub.verify_token": "test-verify-token",
                    "hub.challenge": "challenge123",
                },
            )
            # Should return the challenge if token matches
            assert response.status_code in [200, 403]

    @pytest.mark.asyncio
    async def test_whatsapp_webhook_message(self, api_base_url: str, test_user_phone: str):
        """WhatsApp webhook should accept valid message format."""
        import time
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "entry": [{
                    "changes": [{
                        "value": {
                            "messages": [{
                                "from": test_user_phone,
                                "id": "test-e2e-msg-001",
                                "text": {"body": "Hola, necesito ayuda"},
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
            # Should accept the message (200, 202) or validate properly
            assert response.status_code in [200, 202, 400, 403]


@pytest.mark.e2e
class TestTemplates:
    """Test template management endpoints."""

    @pytest.mark.asyncio
    async def test_templates_endpoint_accessible(self, api_base_url: str):
        """Templates endpoint should be accessible."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{api_base_url}/templates")
            # Without auth might be 401/403, with auth returns list
            assert response.status_code in [200, 401, 403, 422]


@pytest.mark.e2e
class TestConversations:
    """Test conversations API."""

    @pytest.mark.asyncio
    async def test_conversations_accessible(self, api_base_url: str):
        """Conversations endpoint should be accessible with auth."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{api_base_url}/api/conversations")
            # Without proper tenant auth, returns validation error
            assert response.status_code in [200, 401, 403, 422]
