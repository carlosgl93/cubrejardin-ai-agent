"""Facebook Messenger service implementation using Graph API."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import httpx

from config import settings
from models.database import Conversation, InMemorySession, SessionLocal
from utils import logger


class FacebookMessengerService:
    """Interact with Facebook Messenger Platform API."""

    BASE_URL = "https://graph.facebook.com/v21.0"
    MAX_RETRIES = 3
    RETRY_BASE_SECONDS = 1.5

    def __init__(
        self,
        *,
        client: Optional[httpx.AsyncClient] = None,
        session_factory: Optional[Callable[[], InMemorySession]] = None,
    ) -> None:
        self.token = settings.facebook_messenger_page_token
        self.app_secret = settings.facebook_app_secret
        if not self.token:
            raise ValueError("Facebook Messenger page token is required")
        self._client = client or httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=30.0,
        )
        self._session_factory: Callable[[], InMemorySession] = session_factory or SessionLocal
        self._last_interactions: Dict[str, datetime] = {}

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def send_text_message(self, recipient_id: str, text: str) -> Dict[str, Any]:
        """Send a text message to a Facebook Messenger user."""
        payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": text},
            "messaging_type": "RESPONSE",
        }
        logger.info(
            "messenger_send_text",
            extra={"to": recipient_id, "length": len(text)},
        )
        return await self._request("POST", "/me/messages", json=payload)

    async def send_typing_action(self, recipient_id: str, action: str = "typing_on") -> Dict[str, Any]:
        """Send typing indicator (typing_on, typing_off, mark_seen)."""
        payload = {
            "recipient": {"id": recipient_id},
            "sender_action": action,
        }
        logger.debug("messenger_typing_action", extra={"to": recipient_id, "action": action})
        return await self._request("POST", "/me/messages", json=payload)

    async def send_quick_replies(
        self,
        recipient_id: str,
        text: str,
        quick_replies: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Send a message with quick reply buttons."""
        payload = {
            "recipient": {"id": recipient_id},
            "message": {
                "text": text,
                "quick_replies": quick_replies,
            },
        }
        logger.info(
            "messenger_send_quick_replies",
            extra={"to": recipient_id, "replies": len(quick_replies)},
        )
        return await self._request("POST", "/me/messages", json=payload)

    async def send_button_template(
        self,
        recipient_id: str,
        text: str,
        buttons: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Send a message with button template."""
        payload = {
            "recipient": {"id": recipient_id},
            "message": {
                "attachment": {
                    "type": "template",
                    "payload": {
                        "template_type": "button",
                        "text": text,
                        "buttons": buttons,
                    },
                },
            },
        }
        logger.info(
            "messenger_send_buttons",
            extra={"to": recipient_id, "buttons": len(buttons)},
        )
        return await self._request("POST", "/me/messages", json=payload)

    def validate_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Validate X-Hub-Signature-256 header from Facebook."""
        if not signature:
            logger.warning("messenger_signature_missing")
            return False
        expected = hmac.new(
            self.app_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        provided = signature.split("=", 1)[1] if "=" in signature else signature
        is_valid = hmac.compare_digest(expected, provided)
        logger.debug("messenger_signature_validated", extra={"valid": is_valid})
        return is_valid

    def record_incoming_interaction(self, user_id: str, *, timestamp: Optional[datetime] = None) -> None:
        """Register the most recent user interaction timestamp."""
        self._last_interactions[user_id] = (timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc)

    async def _request(self, method: str, endpoint: str, **kwargs: Any) -> Dict[str, Any]:
        """Wrapper around httpx request with retry and logging."""
        headers = kwargs.pop("headers", {})
        headers.setdefault("Content-Type", "application/json")
        
        # Add access token as query parameter
        params = kwargs.pop("params", {})
        params["access_token"] = self.token
        
        attempt = 0
        while True:
            try:
                response = await self._client.request(
                    method, endpoint, headers=headers, params=params, **kwargs
                )
            except httpx.HTTPError as exc:
                if attempt >= self.MAX_RETRIES:
                    logger.error("messenger_http_error", extra={"error": str(exc), "endpoint": endpoint})
                    raise
                await asyncio.sleep(self._backoff(attempt))
                attempt += 1
                continue

            if response.status_code == 429 and attempt < self.MAX_RETRIES:
                retry_after = float(response.headers.get("Retry-After", self._backoff(attempt)))
                logger.warning(
                    "messenger_rate_limited",
                    extra={"endpoint": endpoint, "retry_after": retry_after, "attempt": attempt + 1},
                )
                await asyncio.sleep(retry_after)
                attempt += 1
                continue

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "messenger_request_failed",
                    extra={
                        "endpoint": endpoint,
                        "status_code": exc.response.status_code,
                        "response": exc.response.text,
                    },
                )
                raise

            data = response.json() if response.content else {}
            logger.debug(
                "messenger_request_success",
                extra={"endpoint": endpoint, "status_code": response.status_code},
            )
            return data

    def _backoff(self, attempt: int) -> float:
        """Return exponential backoff time in seconds."""
        return self.RETRY_BASE_SECONDS * (2**attempt)

    def _fetch_last_interaction_from_store(self, user_id: str) -> Optional[datetime]:
        """Inspect the persistence layer for the most recent user interaction."""
        session = self._session_factory()
        try:
            conversations = session.query(Conversation)
            latest: Optional[datetime] = None
            for entry in conversations:
                if entry.user_number == user_id and entry.role == "user":
                    candidate = entry.last_interaction_at or entry.created_at
                    if latest is None or candidate > latest:
                        latest = candidate
            return latest
        finally:
            session.close()


__all__ = ["FacebookMessengerService"]
