"""WhatsApp service integration via Twilio."""

from __future__ import annotations

import hashlib
import hmac
from typing import Dict

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from config import settings
from utils import logger


class WhatsAppService:
    """Handle WhatsApp message sending and validation."""

    def __init__(self) -> None:
        self.client = Client(settings.whatsapp_account_sid, settings.whatsapp_auth_token)

    def validate_signature(self, url: str, params: Dict[str, str], signature: str) -> bool:
        """Validate Twilio webhook signature."""

        data = url
        for key in sorted(params):
            data += key + params[key]
        computed_signature = hmac.new(
            settings.whatsapp_auth_token.encode("utf-8"),
            data.encode("utf-8"),
            hashlib.sha1,
        ).digest()
        encoded = computed_signature.hex()
        is_valid = hmac.compare_digest(encoded, signature.lower())
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
