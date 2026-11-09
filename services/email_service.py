"""Resend email service for alert and handoff notifications."""

from __future__ import annotations

from typing import Any, Dict, Optional
import httpx

from config import get_settings
from utils import logger


class EmailService:
    BASE_URL = "https://api.resend.com/emails"

    def __init__(self, api_key: Optional[str] = None, from_email: Optional[str] = None) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.resend_api_key
        self.from_email = from_email or settings.resend_from_email or "alertas@sgcloud.cl"
        self._client = httpx.AsyncClient(timeout=10.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def send_email(
        self,
        to: str,
        subject: str,
        html: str,
        text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send an email using Resend REST API."""
        if not self.api_key:
            logger.warning("resend_api_key_not_configured_skipping_email", extra={"to": to})
            return {"status": "skipped", "reason": "missing_api_key"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "from": self.from_email,
            "to": [to],
            "subject": subject,
            "html": html,
        }
        if text:
            payload["text"] = text

        response = await self._client.post(self.BASE_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        logger.info("resend_email_sent", extra={"to": to, "id": data.get("id"), "subject": subject})
        return data

    async def send_alert(
        self,
        to: str,
        *,
        alert_type: str,
        tenant_name: str,
        channel: str,
        customer_id: str,
        reason: str,
        recent_messages: str = "",
        action_url: str = "",
    ) -> Dict[str, Any]:
        """Send formatted HTML alert for hot lead or human handoff."""
        is_conversion = alert_type == "conversion"
        title = "Oportunidad de Venta / Lead Caliente" if is_conversion else "Solicitud de Atencion / Handoff"
        badge_color = "#16a34a" if is_conversion else "#dc2626"
        badge_text = "LEAD CALIENTE" if is_conversion else "AYUDA REQUERIDA"

        html = f"""<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f3f4f6; padding: 24px; margin: 0;">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; border: 1px solid #e5e7eb;">
    <tr>
      <td style="padding: 24px; background-color: #111827; color: #ffffff;">
        <span style="background-color: {badge_color}; color: #ffffff; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;">{badge_text}</span>
        <h2 style="margin: 12px 0 0 0; font-size: 20px; color: #ffffff;">{title}</h2>
        <p style="margin: 4px 0 0 0; font-size: 13px; color: #9ca3af;">{tenant_name}</p>
      </td>
    </tr>
    <tr>
      <td style="padding: 24px;">
        <table width="100%" cellpadding="6" cellspacing="0" style="font-size: 14px; color: #374151; margin-bottom: 20px;">
          <tr>
            <td width="30%" style="color: #6b7280; font-weight: bold;">Canal:</td>
            <td><strong>{channel.capitalize()}</strong></td>
          </tr>
          <tr>
            <td style="color: #6b7280; font-weight: bold;">Cliente:</td>
            <td><code>{customer_id}</code></td>
          </tr>
          <tr>
            <td style="color: #6b7280; font-weight: bold;">Motivo:</td>
            <td>{reason}</td>
          </tr>
        </table>
        {f'<div style="background-color: #f9fafb; border-left: 4px solid #d1d5db; padding: 12px; margin-bottom: 24px; font-size: 13px; color: #4b5563; white-space: pre-wrap;"><strong>Historial reciente:</strong><br>{recent_messages}</div>' if recent_messages else ''}
        {f'<div style="text-align: center; margin-top: 24px;"><a href="{action_url}" style="background-color: #2563eb; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-size: 14px; font-weight: bold; display: inline-block;">Abrir Conversacion</a></div>' if action_url else ''}
      </td>
    </tr>
    <tr>
      <td style="padding: 16px 24px; background-color: #f9fafb; text-align: center; font-size: 12px; color: #9ca3af; border-top: 1px solid #e5e7eb;">
        SG Cloud &bull; Sistema de Notificaciones Automaticas
      </td>
    </tr>
  </table>
</body>
</html>"""

        subject = f"[{badge_text}] {tenant_name} &bull; Cliente {customer_id} ({channel})"
        text = f"{title}\nTenant: {tenant_name}\nCanal: {channel}\nCliente: {customer_id}\nMotivo: {reason}\n\nHistorial:\n{recent_messages}\n\nLink: {action_url}"
        return await self.send_email(to=to, subject=subject, html=html, text=text)
