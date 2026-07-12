"""WhatsApp ChannelAdapter.

Thin shim that wraps the existing ``services.whatsapp_service.WhatsAppService``
and the token-exchange helpers from ``api.facebook_auth`` so callers can
interact with the WhatsApp channel through the unified ``ChannelAdapter``
Protocol.

Tenant credentials (phone_number_id + access_token) are resolved per call from
the ``tenant_whatsapp_credentials`` Supabase table — same lookup used by the
webhook layer — so the adapter works for multi-tenant setups without holding
state.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import httpx

from channels.base import ChannelAdapter, InboundMessage


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
        """

        from api.facebook_auth import _exchange_code_for_token, _get_waba_info
        from config.supabase import get_supabase_client

        tenant_id = context["tenant_id"]

        async with httpx.AsyncClient(timeout=30.0) as http:
            access_token, expires_in = await _exchange_code_for_token(code, http)

            if context.get("waba_id") and context.get("phone_number_id"):
                waba_info: Dict[str, Any] = {
                    "waba_id": context["waba_id"],
                    "phone_number_id": context["phone_number_id"],
                    "display_phone_number": "",
                }
            else:
                waba_info = await _get_waba_info(access_token, http)

        token_expires_at: Optional[str] = None
        if expires_in:
            token_expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            ).isoformat()

        sb = get_supabase_client()
        existing = (
            sb.table("tenant_whatsapp_credentials")
            .select("status, whatsapp_business_account_id, phone_number_id")
            .eq("tenant_id", tenant_id)
            .limit(1)
            .execute()
        )

        already_active = (
            existing.data
            and existing.data[0].get("status") == "active"
            and existing.data[0].get("phone_number_id")
        )

        if already_active:
            update_payload: Dict[str, Any] = {"access_token": access_token}
            if token_expires_at is not None:
                update_payload["token_expires_at"] = token_expires_at
            sb.table("tenant_whatsapp_credentials").update(update_payload).eq(
                "tenant_id", tenant_id
            ).execute()
            saved_waba_id = existing.data[0]["whatsapp_business_account_id"]
            saved_phone_id = existing.data[0]["phone_number_id"]
        else:
            upsert_payload: Dict[str, Any] = {
                "tenant_id": tenant_id,
                "access_token": access_token,
                "whatsapp_business_account_id": waba_info["waba_id"],
                "phone_number_id": waba_info["phone_number_id"],
                "status": "active",
                "raw_oauth_response": {
                    "waba_id": waba_info["waba_id"],
                    "phone_number_id": waba_info["phone_number_id"],
                    "display_phone_number": waba_info.get("display_phone_number", ""),
                },
            }
            if token_expires_at is not None:
                upsert_payload["token_expires_at"] = token_expires_at
            sb.table("tenant_whatsapp_credentials").upsert(
                upsert_payload, on_conflict="tenant_id"
            ).execute()
            saved_waba_id = waba_info["waba_id"]
            saved_phone_id = waba_info["phone_number_id"]

        return {
            "access_token": access_token,
            "waba_id": saved_waba_id,
            "phone_number_id": saved_phone_id,
            "token_expires_at": token_expires_at,
        }

    async def refresh_token(self, credentials: dict, **context: Any) -> dict:
        """Refresh a WhatsApp access token.

        Meta's Embedded Signup flow refreshes the stored token when the tenant
        re-runs it. The caller passes the new ``auth_code`` via
        ``context["auth_code"]`` plus ``tenant_id``.
        """

        if "auth_code" not in context:
            raise ValueError(
                "refresh_token requires 'auth_code' in context for WhatsApp"
            )
        return await self.exchange_oauth(context["auth_code"], **context)

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

        tenant_id = context["tenant_id"]
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