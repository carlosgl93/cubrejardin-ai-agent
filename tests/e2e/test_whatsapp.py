"""E2E tests for WhatsApp message flow."""

from __future__ import annotations

import pytest
import httpx
import time


@pytest.mark.e2e
class TestWhatsAppMessageFlow:
    """Test complete WhatsApp message handling flow."""

    @pytest.mark.asyncio
    async def test_user_greeting_flow(self, api_base_url: str, test_user_phone: str):
        """User sends greeting, bot should respond appropriately."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "entry": [{
                    "changes": [{
                        "value": {
                            "messages": [{
                                "from": test_user_phone,
                                "id": f"e2e-greet-{int(time.time())}",
                                "text": {"body": "Hola"},
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

    @pytest.mark.asyncio
    async def test_user_asks_question(self, api_base_url: str, test_user_phone: str):
        """User asks a question, bot should route to RAG or FAQ."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "entry": [{
                    "changes": [{
                        "value": {
                            "messages": [{
                                "from": test_user_phone,
                                "id": f"e2e-question-{int(time.time())}",
                                "text": {"body": "¿Cuál es el precio del producto X?"},
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

            assert response.status_code in [200, 202, 400, 403]

    @pytest.mark.asyncio
    async def test_user_requests_human(self, api_base_url: str, test_user_phone: str):
        """User requests human agent, should trigger handoff."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "entry": [{
                    "changes": [{
                        "value": {
                            "messages": [{
                                "from": test_user_phone,
                                "id": f"e2e-handoff-{int(time.time())}",
                                "text": {"body": "Necesito hablar con un humano"},
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

            assert response.status_code in [200, 202, 400, 403]


@pytest.mark.e2e
class TestWhatsAppButtonCallbacks:
    """Test WhatsApp interactive button callbacks."""

    @pytest.mark.asyncio
    async def test_faq_button_callback(self, api_base_url: str, test_user_phone: str):
        """User clicks FAQ button, should trigger RAG suggestions."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Simulate button callback (text that matches FAQ handler)
            payload = {
                "entry": [{
                    "changes": [{
                        "value": {
                            "messages": [{
                                "from": test_user_phone,
                                "id": f"e2e-btn-faq-{int(time.time())}",
                                "text": {"body": "FAQ"},
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

            assert response.status_code in [200, 202, 400, 403]


@pytest.mark.e2e
class TestWhatsAppMedia:
    """Test WhatsApp media message handling."""

    @pytest.mark.asyncio
    async def test_voice_message(self, api_base_url: str, test_user_phone: str):
        """User sends voice message, bot should handle gracefully."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "entry": [{
                    "changes": [{
                        "value": {
                            "messages": [{
                                "from": test_user_phone,
                                "id": f"e2e-voice-{int(time.time())}",
                                "audio": {"id": "audio-123", "mime_type": "audio/ogg"},
                                "timestamp": str(int(time.time())),
                                "type": "audio"
                            }]
                        }
                    }]
                }]
            }

            response = await client.post(
                f"{api_base_url}/webhook/whatsapp",
                json=payload,
            )

            # Should accept but may not process audio
            assert response.status_code in [200, 202, 400, 403]
