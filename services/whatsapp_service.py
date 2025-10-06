"""WhatsApp service integration via Twilio and Meta handover protocol."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any, Dict, Optional

import httpx
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from config import settings
from utils import logger


class WhatsAppService:
    """Handle WhatsApp message sending, validation, and handover."""

    def __init__(self) -> None:
        self.client = Client(settings.whatsapp_account_sid, settings.whatsapp_auth_token)
        self._graph_base = f"https://graph.facebook.com/v17.0/{settings.whatsapp_phone_number_id}"
        self._http_client = httpx.Client(timeout=10.0)

    def _graph_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.facebook_page_access_token}",
            "Content-Type": "application/json",
        }

    def validate_signature(self, url: str, params: Dict[str, str], signature: str) -> bool:
        """Validate Twilio webhook signature."""

        if not signature:
            logger.warning("whatsapp_signature_missing")
            return False
        data = url
        for key in sorted(params):
            data += key + params[key]
        computed_signature = hmac.new(
            settings.whatsapp_auth_token.encode("utf-8"),
            data.encode("utf-8"),
            hashlib.sha1,
        ).digest()
        encoded = base64.b64encode(computed_signature).decode("utf-8")
        is_valid = hmac.compare_digest(encoded, signature)
        logger.info("signature_validation", extra={"valid": is_valid})
        return is_valid

    def send_message(self, to: str, body: str) -> None:
        """Send WhatsApp message via Twilio."""

        try:
            message = self.client.messages.create(
                body=body,
                from_=f"whatsapp:{settings.whatsapp_from_number}",
                to=f"whatsapp:{to}",
            )
            logger.info("whatsapp_message_sent", extra={"sid": message.sid})
        except TwilioRestException as exc:
            logger.error("whatsapp_send_error", extra={"error": str(exc)})
            raise

    def pass_thread_control(self, recipient_id: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, object]:
        """Invoke Meta's pass_thread_control endpoint."""

        payload = {
            "recipient": {"id": recipient_id},
            "target_app_id": settings.facebook_target_app_id,
            "metadata": json.dumps(metadata or {}),
        }
        try:
            response = self._http_client.post(
                f"{self._graph_base}/pass_thread_control",
                headers=self._graph_headers(),
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "whatsapp_pass_thread_control_error",
                extra={"status_code": exc.response.status_code, "body": exc.response.text},
            )
            raise
        except httpx.HTTPError as exc:
            logger.error("whatsapp_pass_thread_control_http_error", extra={"error": str(exc)})
            raise
        logger.info("whatsapp_pass_thread_control_success", extra={"recipient": recipient_id})
        return response.json()

    def take_thread_control(self, recipient_id: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, object]:
        """Invoke Meta's take_thread_control endpoint."""

        payload = {
            "recipient": {"id": recipient_id},
            "target_app_id": settings.facebook_target_app_id,
            "metadata": json.dumps(metadata or {}),
        }
        try:
            response = self._http_client.post(
                f"{self._graph_base}/take_thread_control",
                headers=self._graph_headers(),
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "whatsapp_take_thread_control_error",
                extra={"status_code": exc.response.status_code, "body": exc.response.text},
            )
            raise
        except httpx.HTTPError as exc:
            logger.error("whatsapp_take_thread_control_http_error", extra={"error": str(exc)})
            raise
        logger.info("whatsapp_take_thread_control_success", extra={"recipient": recipient_id})
        return response.json()
