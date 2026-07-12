from __future__ import annotations

import os
from typing import Any, Optional

import httpx

from channels.base import ChannelAdapter, InboundMessage


GRAPH_API_VERSION = os.getenv("META_GRAPH_VERSION", "v21.0")
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


def _load_tenant_credentials(tenant_id: str) -> Optional[dict]:
    """Return ``{page_id, page_access_token}`` for an active tenant, or None."""

    # Imported lazily to keep the adapter import-light for tests / CLI tools.
    from config.supabase import get_supabase_client

    sb = get_supabase_client()
    if sb is None:
        return None
    result = (
        sb.table("tenant_instagram_credentials")
        .select("page_id, page_access_token")
        .eq("tenant_id", tenant_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


class InstagramAdapter(ChannelAdapter):
    name = "instagram"

    async def exchange_oauth(self, code: str, **context) -> dict:
        """Exchange Meta OAuth code for IG credentials. Implemented in Task C.1."""
        raise NotImplementedError("Implemented in C.1")

    def refresh_token(self, credentials: dict, **context) -> dict:
        """Refresh long-lived Page token. Implemented in Task C.3."""
        raise NotImplementedError("Implemented in C.3")

    async def send_message(
        self,
        recipient_id: str,
        text: str,
        **context: Any,
    ) -> dict:
        """Send a text message to an Instagram recipient.

        IG send via Meta Graph API /me/messages. ``context`` must include
        ``tenant_id``. Page access token is loaded from
        ``tenant_instagram_credentials``.
        """

        tenant_id = context.get("tenant_id")
        if not tenant_id:
            raise ValueError("`tenant_id` required in context")
        creds = _load_tenant_credentials(tenant_id)
        if not creds:
            raise ValueError(
                f"No active Instagram credentials for tenant '{tenant_id}'"
            )

        url = f"{GRAPH_BASE}/me/messages"
        headers = {
            "Authorization": f"Bearer {creds['page_access_token']}",
            "Content-Type": "application/json",
        }
        payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": text},
        }

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        return {
            "message_id": data.get("message_id"),
            "channel": "instagram",
        }

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
