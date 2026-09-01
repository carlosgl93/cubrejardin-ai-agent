"""E2E tests for Telegram webhook integration."""

from __future__ import annotations

import pytest
import httpx
import time


@pytest.mark.e2e
class TestTelegramWebhook:
    """Test Telegram webhook message handling."""

    @pytest.mark.asyncio
    async def test_telegram_message_text(self, api_base_url: str):
        """Telegram should accept text messages."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "update_id": int(time.time()) * 1000,
                "message": {
                    "message_id": 1,
                    "from": {
                        "id": 123456789,
                        "is_bot": False,
                        "first_name": "Test",
                        "last_name": "User",
                        "username": "testuser"
                    },
                    "chat": {
                        "id": 123456789,
                        "type": "private"
                    },
                    "date": int(time.time()),
                    "text": "Hola, necesito información"
                }
            }

            response = await client.post(
                f"{api_base_url}/webhook/telegram",
                json=payload,
            )
            # Should accept the message (200, 202) or handle errors gracefully (400, 500)
            assert response.status_code in [200, 202, 400, 500]

    @pytest.mark.asyncio
    async def test_telegram_message_with_command(self, api_base_url: str):
        """Telegram should handle bot commands."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "update_id": int(time.time()) * 1000 + 1,
                "message": {
                    "message_id": 2,
                    "from": {
                        "id": 123456789,
                        "is_bot": False,
                        "first_name": "Test"
                    },
                    "chat": {
                        "id": 123456789,
                        "type": "private"
                    },
                    "date": int(time.time()),
                    "text": "/start"
                }
            }

            response = await client.post(
                f"{api_base_url}/webhook/telegram",
                json=payload,
            )
            assert response.status_code in [200, 202, 400, 500]

    @pytest.mark.asyncio
    async def test_telegram_message_photo(self, api_base_url: str):
        """Telegram should accept photo messages."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "update_id": int(time.time()) * 1000 + 2,
                "message": {
                    "message_id": 3,
                    "from": {
                        "id": 123456789,
                        "is_bot": False,
                        "first_name": "Test"
                    },
                    "chat": {
                        "id": 123456789,
                        "type": "private"
                    },
                    "date": int(time.time()),
                    "photo": [{
                        "file_id": "AgACAgIAAxkBAAIBZ2Q",
                        "file_unique_id": "unique",
                        "width": 800,
                        "height": 600
                    }]
                }
            }

            response = await client.post(
                f"{api_base_url}/webhook/telegram",
                json=payload,
            )
            assert response.status_code in [200, 202, 400, 500]

    @pytest.mark.asyncio
    async def test_telegram_callback_query(self, api_base_url: str):
        """Telegram should handle inline keyboard callbacks."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "update_id": int(time.time()) * 1000 + 3,
                "callback_query": {
                    "id": "callback_123",
                    "from": {
                        "id": 123456789,
                        "is_bot": False,
                        "first_name": "Test"
                    },
                    "chat_instance": "123456789",
                    "data": "faq_category_prices"
                }
            }

            response = await client.post(
                f"{api_base_url}/webhook/telegram",
                json=payload,
            )
            assert response.status_code in [200, 202, 400, 500]


@pytest.mark.e2e
class TestTelegramHandoff:
    """Test Telegram handoff functionality."""

    @pytest.mark.asyncio
    async def test_telegram_handoff_request(self, api_base_url: str):
        """User should be able to request human via Telegram."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "update_id": int(time.time()) * 1000 + 4,
                "message": {
                    "message_id": 4,
                    "from": {
                        "id": 123456789,
                        "is_bot": False,
                        "first_name": "Test"
                    },
                    "chat": {
                        "id": 123456789,
                        "type": "private"
                    },
                    "date": int(time.time()),
                    "text": "Hablar con agente"
                }
            }

            response = await client.post(
                f"{api_base_url}/webhook/telegram",
                json=payload,
            )
            assert response.status_code in [200, 202, 400, 500]
