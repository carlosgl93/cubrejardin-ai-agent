"""Custom exception hierarchy for the WhatsApp agent."""

from __future__ import annotations


class AgentWhatsAppError(Exception):
    """Base exception for WhatsApp agent specific errors."""


class OutsideMessagingWindowError(AgentWhatsAppError):
    """Raised when attempting to send a free-form message outside the 24h window."""

    def __init__(self, user_id: str) -> None:
        super().__init__(
            f"Cannot send free-form message to {user_id}: outside 24-hour customer service window. "
            "Use an approved template via send_template_message()."
        )
        self.user_id = user_id
