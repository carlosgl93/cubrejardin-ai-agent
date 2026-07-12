from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class InboundMessage:
    channel: str           # 'whatsapp' | 'instagram'
    external_user_id: str  # phone number or IGSID
    text: str
    raw: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


@runtime_checkable
class ChannelAdapter(Protocol):
    name: str

    def exchange_oauth(self, code: str, **context: Any) -> dict:
        """Exchange OAuth `code` (from Meta) into channel credentials."""
        ...

    def refresh_token(self, credentials: dict, **context: Any) -> dict:
        """Refresh an expiring access token. Returns updated credentials."""
        ...

    def send_message(self, recipient_id: str, text: str, **context: Any) -> dict:
        """Send a text reply. Returns provider message id."""
        ...

    def parse_webhook(self, payload: dict) -> list[InboundMessage]:
        """Parse a webhook payload into a list of inbound messages."""
        ...