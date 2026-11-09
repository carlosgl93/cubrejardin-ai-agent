"""Unit tests for EmailService (Resend) and alert dispatching."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from services.email_service import EmailService
from services.alert_notification_service import dispatch_alert
from services.tenant_config_service import TenantBotConfig


@pytest.mark.asyncio
async def test_email_service_send_email_mocked():
    service = EmailService(api_key="re_test_key", from_email="alertas@sgcloud.cl")
    
    mock_response = MagicMock()
    mock_response.json.return_value = {"id": "email_123"}
    mock_response.raise_for_status.return_value = None

    with patch.object(service._client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        result = await service.send_email(
            to="admin@example.com",
            subject="Test Subject",
            html="<p>Hello</p>",
            text="Hello",
        )
        assert result.get("id") == "email_123"
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs["json"]["to"] == ["admin@example.com"]
        assert kwargs["json"]["from"] == "alertas@sgcloud.cl"
    await service.close()


@pytest.mark.asyncio
async def test_email_service_send_alert():
    service = EmailService(api_key="re_test_key", from_email="alertas@sgcloud.cl")

    mock_response = MagicMock()
    mock_response.json.return_value = {"id": "alert_456"}
    mock_response.raise_for_status.return_value = None

    with patch.object(service._client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        result = await service.send_alert(
            to="ventas@negocio.cl",
            alert_type="conversion",
            tenant_name="Tienda Demo",
            channel="instagram",
            customer_id="1534732795083535",
            reason="Intento de compra",
            recent_messages="Cliente: Tienen stock del producto azul?",
            action_url="https://sgcloud.cl/conversations?number=1534732795083535",
        )
        assert result.get("id") == "alert_456"
        kwargs = mock_post.call_args[1]
        assert "[LEAD CALIENTE]" in kwargs["json"]["subject"]
        assert "Oportunidad de Venta" in kwargs["json"]["html"]
    await service.close()


@pytest.mark.asyncio
async def test_dispatch_alert_routes_to_email():
    cfg = TenantBotConfig(
        tenant_name="Demo",
        notify_email_enabled=True,
        notify_email_recipient="guardia@demo.cl",
        notify_conversion_alerts=True,
        notify_handoff_alerts=True,
    )

    with patch("services.alert_notification_service.EmailService.send_alert", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = {"id": "resend_789"}
        res = await dispatch_alert(
            tenant_id="tenant_123",
            alert_type="handoff",
            channel="whatsapp",
            customer_id="56911223344",
            reason="Usuario solicito asesor",
            bot_config=cfg,
        )
        assert "email" in res
        assert res["email"]["id"] == "resend_789"
        mock_send.assert_called_once()
