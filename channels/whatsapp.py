"""WhatsApp ChannelAdapter.

Thin shim that wraps the existing ``services.whatsapp_service.WhatsAppService``
and the token-exchange helpers from ``services.facebook_auth`` so callers can
interact with the WhatsApp channel through the unified ``ChannelAdapter``
Protocol.

Tenant credentials (phone_number_id + access_token) are resolved per call from
the ``tenant_whatsapp_credentials`` Supabase table — same lookup used by the
webhook layer — so the adapter works for multi-tenant setups without holding
state.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from channels.base import ChannelAdapter, InboundMessage
from config.settings import get_settings


def _load_tenant_credentials(tenant_id: str) -> Optional[dict]:
    """Return ``{phone_number_id, access_token}`` for an active tenant, or None."""

    # Imported lazily to keep the adapter import-light for tests / CLI tools.
    from config.supabase import get_supabase_client

    sb = get_supabase_client()
    if sb is None:
        return None
    result = (
        sb.table("tenant_whatsapp_credentials")
        .select("phone_number_id, access_token")
        .eq("tenant_id", tenant_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


class WhatsAppAdapter(ChannelAdapter):
    name = "whatsapp"

    async def exchange_oauth(self, code: str, **context: Any) -> dict:
        """Exchange a Meta OAuth code for WhatsApp Business credentials.

        ``context`` must include ``tenant_id``. Optional ``waba_id`` and
        ``phone_number_id`` come from the Embedded Signup callback; when
        omitted the adapter discovers them via the Meta Graph API.

        Delegates to ``services.facebook_auth.exchange_facebook_code_to_credentials``
        so the FastAPI route and the adapter share the same implementation.
        """
        from services.facebook_auth import exchange_facebook_code_to_credentials

        tenant_id = context.get("tenant_id")
        if not tenant_id:
            raise ValueError("`tenant_id` required in context")

        return await exchange_facebook_code_to_credentials(
            code=code,
            tenant_id=tenant_id,
            waba_id=context.get("waba_id", ""),
            phone_number_id=context.get("phone_number_id", ""),
        )

    def refresh_token(self, credentials: dict, **context: Any) -> dict:
        """Refresh a long-lived WhatsApp access token.

        Uses Meta's ``fb_exchange_token`` grant to extend the existing
        long-lived token — no fresh OAuth code required.

        https://developers.facebook.com/docs/facebook-login/access-tokens/refreshing
        """

        settings = get_settings()
        app_id = settings.facebook_target_app_id
        app_secret = settings.facebook_app_secret
        if not app_id or not app_secret:
            raise RuntimeError("FACEBOOK_APP_ID/SECRET not configured")

        current_token = credentials.get("access_token")
        if not current_token:
            raise ValueError("credentials.access_token required")

        resp = httpx.get(
            "https://graph.facebook.com/v21.0/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": current_token,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        new_creds = dict(credentials)
        new_creds["access_token"] = data["access_token"]
        new_creds["expires_in"] = data.get("expires_in", 5184000)
        return new_creds

    async def send_message(
        self,
        recipient_id: str,
        text: str,
        **context: Any,
    ) -> dict:
        """Send a text message to a WhatsApp recipient.

        ``context`` must include ``tenant_id``. Phone id and access token are
        loaded from ``tenant_whatsapp_credentials``.
        """

        from services.whatsapp_service import WhatsAppService

        tenant_id = context.get("tenant_id")
        if not tenant_id:
            raise ValueError("`tenant_id` required in context")
        creds = _load_tenant_credentials(tenant_id)
        if not creds:
            raise ValueError(
                f"No active WhatsApp credentials for tenant '{tenant_id}'"
            )

        service = WhatsAppService(
            phone_id=creds["phone_number_id"],
            token=creds["access_token"],
        )
        try:
            return await service.send_text_message(
                to=recipient_id,
                body=text,
                skip_window_check=context.get("skip_window_check", False),
            )
        finally:
            await service.close()

    def parse_webhook(self, payload: dict) -> list[InboundMessage]:
        """Parse a Meta WhatsApp webhook payload into InboundMessages.

        Defensive: skips entries/changes/messages with missing fields rather
        than raising. Non-text messages are ignored.
        """

        out: list[InboundMessage] = []
        for entry in payload.get("entry", []) or []:
            for change in entry.get("changes", []) or []:
                if change.get("field") != "messages":
                    continue
                value = change.get("value") or {}
                metadata = value.get("metadata") or {}
                for msg in value.get("messages", []) or []:
                    # Default to "text" when type is missing — some test
                    # fixtures omit it, and messages with a `text` body are
                    # always text in practice.
                    msg_type = msg.get("type") or ("text" if msg.get("text") else None)
                    if msg_type != "text":
                        continue
                    text_obj = msg.get("text") or {}
                    out.append(
                        InboundMessage(
                            channel="whatsapp",
                            external_user_id=msg.get("from", ""),
                            text=text_obj.get("body", ""),
                            raw=msg,
                            metadata={
                                "phone_number_id": metadata.get("phone_number_id"),
                                "waba_id": metadata.get("waba_id"),
                                "wamid": msg.get("id"),
                            },
                        )
                    )
        return out
