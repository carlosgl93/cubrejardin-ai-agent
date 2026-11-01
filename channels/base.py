from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable


@dataclass
class InboundMessage:
    channel: str           # 'whatsapp' | 'instagram' | 'messenger'
    external_user_id: str  # phone number or IGSID/PSID
    text: str
    raw: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    message_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.message_id:
            self.message_id = (
                self.metadata.get("ig_mid")
                or self.metadata.get("wamid")
                or self.metadata.get("mid")
                or self.raw.get("id")
                or self.raw.get("mid")
            )



@runtime_checkable
class ChannelAdapter(Protocol):
    name: str

    async def exchange_oauth(self, code: str, **context: Any) -> dict:
        """Exchange OAuth `code` (from Meta) into channel credentials."""
        ...

    def refresh_token(self, credentials: dict, **context: Any) -> dict:
        """Refresh an expiring access token. Returns updated credentials."""
        ...

    async def send_message(self, recipient_id: str, text: str, **context: Any) -> dict:
        """Send a text reply. Returns provider message id."""
        ...

    def parse_webhook(self, payload: dict) -> list[InboundMessage]:
        """Parse a webhook payload into a list of inbound messages."""
        ...