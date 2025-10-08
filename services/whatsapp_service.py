"""WhatsApp service implementation for Meta WhatsApp Cloud API v21.0."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import httpx

from config import settings
from models.database import Conversation, InMemorySession, SessionLocal
from utils import OutsideMessagingWindowError, logger


class WhatsAppService:
    """Interact with Meta's WhatsApp Cloud API in an async fashion."""

    BASE_URL = "https://graph.facebook.com/v21.0"
    MAX_RETRIES = 3
    RETRY_BASE_SECONDS = 1.5

    def __init__(
        self,
        *,
        client: Optional[httpx.AsyncClient] = None,
        session_factory: Optional[Callable[[], InMemorySession]] = None,
    ) -> None:
        self.phone_id = settings.whatsapp_phone_number_id
        self.token = settings.facebook_page_access_token
        self.app_secret = settings.facebook_app_secret
        if not self.phone_id or not self.token:
            raise ValueError("WhatsApp phone number ID and access token are required")
        self._client = client or httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=30.0,
        )
        self._session_factory: Callable[[], InMemorySession] = session_factory or SessionLocal
        self._last_interactions: Dict[str, datetime] = {}

    async def close(self) -> None:
        """Close the underlying HTTP client."""

        await self._client.aclose()

    async def send_text_message(self, to: str, body: str, *, preview_url: bool = True) -> Dict[str, Any]:
        """Send a text message within the 24-hour session window."""

        sanitized = self._sanitize_number(to)
        if not self.is_within_24h_window(sanitized):
            raise OutsideMessagingWindowError(sanitized)
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": sanitized,
            "type": "text",
            "text": {"preview_url": preview_url, "body": body},
        }
        logger.info(
            "whatsapp_send_text",
            extra={"to": payload["to"], "preview_url": preview_url, "length": len(body)},
        )
        return await self._request("POST", f"/{self.phone_id}/messages", json=payload)

    async def send_message(self, to: str, body: str, *, preview_url: bool = True) -> Dict[str, Any]:
        """Backward-compatible alias for Twilio-style naming."""

        return await self.send_text_message(to=to, body=body, preview_url=preview_url)

    async def send_template_message(
        self,
        to: str,
        template_name: str,
        *,
        language: str = "es",
        components: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Send an approved template message (outside 24-hour window)."""

        payload = {
            "messaging_product": "whatsapp",
            "to": self._sanitize_number(to),
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
                "components": components or [],
            },
        }
        logger.info(
            "whatsapp_send_template",
            extra={"to": payload["to"], "template": template_name},
        )
        return await self._request("POST", f"/{self.phone_id}/messages", json=payload)

    async def send_interactive_buttons(
        self,
        to: str,
        body_text: str,
        buttons: List[Dict[str, Any]],
        *,
        header: Optional[Dict[str, Any]] = None,
        footer: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send an interactive buttons message."""

        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": self._sanitize_number(to),
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body_text},
                "action": {"buttons": buttons},
            },
        }
        if header:
            payload["interactive"]["header"] = header
        if footer:
            payload["interactive"]["footer"] = footer
        logger.info("whatsapp_send_interactive", extra={"to": payload["to"], "buttons": len(buttons)})
        return await self._request("POST", f"/{self.phone_id}/messages", json=payload)

    async def mark_as_read(self, message_id: str) -> Dict[str, Any]:
        """Mark a message as read."""

        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        logger.info("whatsapp_mark_read", extra={"message_id": message_id})
        return await self._request("POST", f"/{self.phone_id}/messages", json=payload)

    def validate_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Validate X-Hub-Signature-256 header from Meta."""

        if not signature:
            logger.warning("whatsapp_signature_missing")
            return False
        expected = hmac.new(
            self.app_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        provided = signature.split("=", 1)[1] if "=" in signature else signature
        is_valid = hmac.compare_digest(expected, provided)
        logger.debug("whatsapp_signature_validated", extra={"valid": is_valid})
        return is_valid

    async def pass_thread_control(
        self,
        recipient_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Pass thread control to a human agent inbox."""

        payload = {
            "recipient": {"id": recipient_id},
            "metadata": metadata or {},
        }
        logger.info("whatsapp_pass_thread_control", extra={"recipient": recipient_id})
        return await self._request(
            "POST",
            f"/{self.phone_id}/pass_thread_control",
            json=payload,
        )

    async def take_thread_control(
        self,
        recipient_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Take back thread control for the bot."""

        payload = {
            "recipient": {"id": recipient_id},
            "metadata": metadata or {},
        }
        logger.info("whatsapp_take_thread_control", extra={"recipient": recipient_id})
        return await self._request(
            "POST",
            f"/{self.phone_id}/take_thread_control",
            json=payload,
        )

    def record_incoming_interaction(self, user_id: str, *, timestamp: Optional[datetime] = None) -> None:
        """Register the most recent user interaction timestamp."""

        sanitized = self._sanitize_number(user_id)
        self._last_interactions[sanitized] = (timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc)

    def is_within_24h_window(self, user_id: str) -> bool:
        """Return True if we are still inside the 24h customer service window for a user."""

        sanitized = self._sanitize_number(user_id)
        last = self._last_interactions.get(sanitized)
        if last is None:
            last = self._fetch_last_interaction_from_store(sanitized)
            if last:
                self._last_interactions[sanitized] = last
        if last is None:
            return False
        return self._within_window(last)

    @staticmethod
    def _within_window(last_user_message_time: datetime) -> bool:
        """Return True if we are still inside the 24h customer service window."""

        now = datetime.now(timezone.utc)
        delta_seconds = (now - last_user_message_time.astimezone(timezone.utc)).total_seconds()
        return delta_seconds < 86_400

    async def _request(self, method: str, endpoint: str, **kwargs: Any) -> Dict[str, Any]:
        """Wrapper around httpx request with retry and logging."""

        headers = kwargs.pop("headers", {})
        headers.setdefault("Authorization", f"Bearer {self.token}")
        headers.setdefault("Content-Type", "application/json")
        attempt = 0
        while True:
            try:
                response = await self._client.request(method, endpoint, headers=headers, **kwargs)
            except httpx.HTTPError as exc:
                if attempt >= self.MAX_RETRIES:
                    logger.error("whatsapp_http_error", extra={"error": str(exc), "endpoint": endpoint})
                    raise
                await asyncio.sleep(self._backoff(attempt))
                attempt += 1
                continue

            if response.status_code == 429 and attempt < self.MAX_RETRIES:
                retry_after = float(response.headers.get("Retry-After", self._backoff(attempt)))
                logger.warning(
                    "whatsapp_rate_limited",
                    extra={"endpoint": endpoint, "retry_after": retry_after, "attempt": attempt + 1},
                )
                await asyncio.sleep(retry_after)
                attempt += 1
                continue

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "whatsapp_request_failed",
                    extra={
                        "endpoint": endpoint,
                        "status_code": exc.response.status_code,
                        "response": exc.response.text,
                    },
                )
                raise

            data = response.json() if response.content else {}
            logger.debug(
                "whatsapp_request_success",
                extra={"endpoint": endpoint, "status_code": response.status_code},
            )
            return data

    def _backoff(self, attempt: int) -> float:
        """Return exponential backoff time in seconds."""

        return self.RETRY_BASE_SECONDS * (2**attempt)

    @staticmethod
    def _sanitize_number(raw: str) -> str:
        """Strip prefixes and leave only digits."""

        if not raw:
            return raw
        sanitized = raw.replace("whatsapp:", "").replace("+", "").strip()
        return "".join(filter(str.isdigit, sanitized))

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
