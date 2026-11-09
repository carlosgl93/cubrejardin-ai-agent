"""Alert notification dispatcher for human handoffs and conversion opportunities."""

from __future__ import annotations

from typing import Any, Dict, Optional

from config import get_settings
from services.email_service import EmailService
from services.tenant_config_service import TenantBotConfig, get_tenant_bot_config
from utils import logger


async def dispatch_alert(
    *,
    tenant_id: str,
    alert_type: str,  # 'handoff' | 'conversion'
    channel: str,
    customer_id: str,
    reason: str,
    recent_messages: str = "",
    bot_config: Optional[TenantBotConfig] = None,
) -> Dict[str, Any]:
    """Dispatch notifications across configured channels (Email via Resend, WhatsApp, etc.)."""
    settings = get_settings()
    cfg = bot_config or get_tenant_bot_config(tenant_id)
    site_url = getattr(settings, "site_url", "https://sgcloud.cl")
    action_url = f"{site_url}/conversations?number={customer_id}"

    results: Dict[str, Any] = {}

    # Check alert type filters
    if alert_type == "conversion" and not cfg.notify_conversion_alerts:
        return {"status": "skipped", "reason": "conversion_alerts_disabled"}
    if alert_type == "handoff" and not cfg.notify_handoff_alerts:
        return {"status": "skipped", "reason": "handoff_alerts_disabled"}

    # 1. Dispatch Email via Resend
    if cfg.notify_email_enabled and cfg.notify_email_recipient:
        email_svc = EmailService()
        try:
            res = await email_svc.send_alert(
                to=cfg.notify_email_recipient,
                alert_type=alert_type,
                tenant_name=cfg.tenant_name,
                channel=channel,
                customer_id=customer_id,
                reason=reason,
                recent_messages=recent_messages,
                action_url=action_url,
            )
            results["email"] = res
        except Exception as exc:
            logger.error("dispatch_email_alert_failed", extra={"tenant_id": tenant_id, "error": str(exc)})
            results["email"] = {"status": "error", "error": str(exc)}
        finally:
            await email_svc.close()

    # 2. Dispatch WhatsApp to admin
    if cfg.notify_whatsapp_enabled and cfg.notify_whatsapp_recipient:
        try:
            from services.whatsapp_service import WhatsAppService
            from config.supabase import get_supabase_client

            sb = get_supabase_client()
            cred_res = (
                sb.table("tenant_whatsapp_credentials")
                .select("access_token, phone_number_id")
                .eq("tenant_id", tenant_id)
                .eq("status", "active")
                .limit(1)
                .execute()
            )
            if cred_res.data:
                phone_id = cred_res.data[0].get("phone_number_id") or settings.whatsapp_phone_number_id
                token = cred_res.data[0].get("access_token")
                wa = WhatsAppService(phone_id=phone_id, token=token)
                try:
                    alert_tag = "[VENTA]" if alert_type == "conversion" else "[ALERTA]"
                    msg_text = (
                        f"{alert_tag} {cfg.tenant_name}\n"
                        f"Canal: {channel.capitalize()}\n"
                        f"Cliente: {customer_id}\n"
                        f"Motivo: {reason}\n"
                        f"Link: {action_url}"
                    )
                    await wa.send_text_message(cfg.notify_whatsapp_recipient, msg_text, skip_window_check=True)
                    results["whatsapp"] = {"status": "sent"}
                finally:
                    await wa.close()
        except Exception as exc:
            logger.warning("dispatch_whatsapp_alert_failed", extra={"tenant_id": tenant_id, "error": str(exc)})
            results["whatsapp"] = {"status": "error", "error": str(exc)}

    return results
