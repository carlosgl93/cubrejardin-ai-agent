from __future__ import annotations

import os

from channels.base import ChannelAdapter, InboundMessage


GRAPH_API_VERSION = os.getenv("META_GRAPH_VERSION", "v21.0")
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


class InstagramAdapter(ChannelAdapter):
    name = "instagram"

    async def exchange_oauth(self, code: str, **context) -> dict:
        """Exchange Meta OAuth code for IG credentials. Implemented in Task C.1."""
        raise NotImplementedError("Implemented in C.1")

    def refresh_token(self, credentials: dict, **context) -> dict:
        """Refresh long-lived Page token. Implemented in Task C.3."""
        raise NotImplementedError("Implemented in C.3")

    async def send_message(self, recipient_id: str, text: str, **context) -> dict:
        """POST to /me/messages. Implemented in Task F.1."""
        raise NotImplementedError("Implemented in F.1")

    def parse_webhook(self, payload: dict) -> list[InboundMessage]:
        out: list[InboundMessage] = []
        for entry in payload.get("entry", []):
            page_id = entry.get("id")
            for event in entry.get("messaging", []):
                msg = event.get("message") or {}
                text = msg.get("text")
                if not text:
                    continue
                sender = event.get("sender", {}).get("id")
                if not sender:
                    continue
                out.append(InboundMessage(
                    channel="instagram",
                    external_user_id=sender,
                    text=text,
                    raw=msg,
                    metadata={
                        "page_id": page_id,
                        "ig_mid": msg.get("mid"),
                    },
                ))
        return out
