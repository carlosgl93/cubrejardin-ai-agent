"""Tests for handoff auto-return configuration and timeout expiration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from api.tenant_context import TenantContext, get_tenant_context
from api.webhooks_helpers import run_bot_pipeline
from api.webhooks import _get_active_handoff
from main import app
from services.tenant_config_service import (
    TenantBotConfig,
    get_tenant_bot_config,
    invalidate_tenant_bot_config,
)

client = TestClient(app)
FAKE_TENANT_ID = "22222222-2222-2222-2222-222222222222"


def _override_ctx():
    return TenantContext(
        tenant_id=FAKE_TENANT_ID,
        user_id="USER_TEST",
        role="owner",
        tenant_name="Test Business",
    )


@pytest.fixture(autouse=True)
def apply_ctx():
    app.dependency_overrides[get_tenant_context] = _override_ctx
    invalidate_tenant_bot_config(FAKE_TENANT_ID)
    yield
    app.dependency_overrides.pop(get_tenant_context, None)
    invalidate_tenant_bot_config(FAKE_TENANT_ID)


def test_get_bot_config_returns_defaults_when_empty():
    fake_sb = MagicMock()
    fake_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []

    with patch("api.tenants.get_supabase_client", return_value=fake_sb):
        resp = client.get("/api/tenants/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["handoff_auto_return_enabled"] is True
        assert data["handoff_timeout_minutes"] == 10


def test_upsert_bot_config_saves_and_validates():
    fake_sb = MagicMock()
    fake_sb.table.return_value.upsert.return_value.execute.return_value.data = [{
        "id": "cfg-1",
        "tenant_id": FAKE_TENANT_ID,
        "system_prompt": "Prompt",
        "greeting": "Hola",
        "handoff_trigger": "humano",
        "business_hours": {},
        "handoff_auto_return_enabled": False,
        "handoff_timeout_minutes": 25,
    }]

    with patch("api.tenants.get_supabase_client", return_value=fake_sb):
        # Valid update
        resp = client.put(
            "/api/tenants/config",
            json={
                "handoff_auto_return_enabled": False,
                "handoff_timeout_minutes": 25,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["handoff_auto_return_enabled"] is False
        assert data["handoff_timeout_minutes"] == 25

        # Invalid timeout (< 1)
        resp_invalid = client.put(
            "/api/tenants/config",
            json={"handoff_timeout_minutes": 0},
        )
        assert resp_invalid.status_code == 400


def test_tenant_bot_config_loader_and_cache_invalidation():
    fake_sb = MagicMock()
    mock_bot_cfg = MagicMock()
    mock_bot_cfg.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{
        "system_prompt": "Custom prompt",
        "greeting": "Custom greeting",
        "handoff_trigger": "ayuda",
        "handoff_auto_return_enabled": False,
        "handoff_timeout_minutes": 15,
    }]
    mock_tenants = MagicMock()
    mock_tenants.select.return_value.eq.return_value.limit.return_value.maybe_single.return_value.execute.return_value.data = {
        "name": "Custom Business"
    }

    def fake_table(name: str):
        if name == "tenant_bot_config":
            return mock_bot_cfg
        return mock_tenants

    fake_sb.table.side_effect = fake_table

    with patch("services.tenant_config_service.get_supabase_client", return_value=fake_sb):
        cfg = get_tenant_bot_config(FAKE_TENANT_ID)
        assert cfg.handoff_auto_return_enabled is False
        assert cfg.handoff_timeout_minutes == 15
        assert cfg.tenant_name == "Custom Business"
        assert mock_bot_cfg.select.call_count == 1

        # Second call uses cache
        cfg_cached = get_tenant_bot_config(FAKE_TENANT_ID)
        assert cfg_cached is cfg
        assert mock_bot_cfg.select.call_count == 1

        # Invalidate cache
        invalidate_tenant_bot_config(FAKE_TENANT_ID)
        cfg_reloaded = get_tenant_bot_config(FAKE_TENANT_ID)
        assert mock_bot_cfg.select.call_count == 2


@pytest.mark.asyncio
async def test_run_bot_pipeline_expires_handoff_when_stale():
    """If timeout has elapsed, handoff is marked expired and bot answers."""
    stale_time = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()

    fake_sb = MagicMock()
    mock_handoff_query = MagicMock()
    mock_handoff_query.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{
        "id": "h-123",
        "message_count": 2,
        "updated_at": stale_time,
    }]
    mock_update = MagicMock()
    mock_handoff_query.update.return_value.eq.return_value.execute = MagicMock()

    def fake_table(name: str):
        if name == "handoffs":
            return mock_handoff_query
        return MagicMock()

    fake_sb.table.side_effect = fake_table

    mock_t_cfg = TenantBotConfig(
        handoff_auto_return_enabled=True,
        handoff_timeout_minutes=10,
    )

    mock_orchestrator = MagicMock()
    mock_orchestrator.process_message = AsyncMock(return_value=MagicMock(message="Respuesta del bot"))
    mock_adapter = MagicMock()
    mock_adapter.send_message = AsyncMock(return_value={"id": "msg-1"})

    with patch("api.webhooks_helpers.get_supabase_client", return_value=fake_sb), \
         patch("services.tenant_config_service.get_tenant_bot_config", return_value=mock_t_cfg), \
         patch("agents.orchestrator.AgentOrchestrator", return_value=mock_orchestrator), \
         patch("channels.registry.get_adapter", return_value=mock_adapter), \
         patch("models.database.SessionLocal", return_value=MagicMock()), \
         patch("services.whatsapp_service.WhatsAppService", return_value=MagicMock()), \
         patch("services.openai_service.OpenAIService", return_value=MagicMock()), \
         patch("services.vector_store.VectorStoreService", return_value=MagicMock()):

        await run_bot_pipeline(
            tenant_id=FAKE_TENANT_ID,
            channel="whatsapp",
            channel_user_id="+56999999999",
            user_message="Hola necesito ayuda",
        )

        # Verified that handoff was updated to expired
        mock_handoff_query.update.assert_called_once()
        update_args = mock_handoff_query.update.call_args[0][0]
        assert update_args["status"] == "expired"
        assert update_args["closed_by"] == "auto_timeout"

        # Verified that orchestrator was called to reply
        mock_orchestrator.process_message.assert_awaited_once()
        mock_adapter.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_bot_pipeline_pauses_bot_when_handoff_is_active():
    """If timeout has not elapsed, handoff is touched and bot does NOT answer."""
    fresh_time = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()

    fake_sb = MagicMock()
    mock_handoff_query = MagicMock()
    mock_handoff_query.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{
        "id": "h-456",
        "message_count": 2,
        "updated_at": fresh_time,
    }]
    mock_handoff_query.update.return_value.eq.return_value.execute = MagicMock()

    fake_sb.table.return_value = mock_handoff_query

    mock_t_cfg = TenantBotConfig(
        handoff_auto_return_enabled=True,
        handoff_timeout_minutes=10,
    )

    mock_orchestrator = MagicMock()

    with patch("api.webhooks_helpers.get_supabase_client", return_value=fake_sb), \
         patch("services.tenant_config_service.get_tenant_bot_config", return_value=mock_t_cfg), \
         patch("agents.orchestrator.AgentOrchestrator", return_value=mock_orchestrator):

        await run_bot_pipeline(
            tenant_id=FAKE_TENANT_ID,
            channel="whatsapp",
            channel_user_id="+56999999999",
            user_message="Sigo esperando al humano",
        )

        # Hand off touched, NOT expired
        update_args = mock_handoff_query.update.call_args[0][0]
        assert "status" not in update_args
        assert update_args["message_count"] == 3

        # Bot orchestrator not called
        mock_orchestrator.process_message.assert_not_called()


@pytest.mark.asyncio
async def test_run_bot_pipeline_respects_disabled_auto_return():
    """When auto-return is disabled, handoff never expires automatically even if stale."""
    very_old_time = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()

    fake_sb = MagicMock()
    mock_handoff_query = MagicMock()
    mock_handoff_query.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{
        "id": "h-789",
        "message_count": 1,
        "updated_at": very_old_time,
    }]
    mock_handoff_query.update.return_value.eq.return_value.execute = MagicMock()

    fake_sb.table.return_value = mock_handoff_query

    mock_t_cfg = TenantBotConfig(
        handoff_auto_return_enabled=False,
        handoff_timeout_minutes=10,
    )

    mock_orchestrator = MagicMock()

    with patch("api.webhooks_helpers.get_supabase_client", return_value=fake_sb), \
         patch("services.tenant_config_service.get_tenant_bot_config", return_value=mock_t_cfg), \
         patch("agents.orchestrator.AgentOrchestrator", return_value=mock_orchestrator):

        await run_bot_pipeline(
            tenant_id=FAKE_TENANT_ID,
            channel="whatsapp",
            channel_user_id="+56999999999",
            user_message="Mensaje con auto-return desactivado",
        )

        update_args = mock_handoff_query.update.call_args[0][0]
        assert "status" not in update_args
        mock_orchestrator.process_message.assert_not_called()


def test_get_active_handoff_auto_expires_when_timeout_exceeded():
    stale_time = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()

    fake_sb = MagicMock()
    mock_query = MagicMock()
    mock_query.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [{
        "id": "h-stale",
        "whatsapp_number": "+56911111111",
        "updated_at": stale_time,
    }]
    fake_sb.table.return_value = mock_query

    mock_t_cfg = TenantBotConfig(
        handoff_auto_return_enabled=True,
        handoff_timeout_minutes=10,
    )

    with patch("api.webhooks.get_supabase_client", return_value=fake_sb), \
         patch("services.tenant_config_service.get_tenant_bot_config", return_value=mock_t_cfg):

        result = _get_active_handoff("+56911111111", FAKE_TENANT_ID)
        assert result is None
        mock_query.update.assert_called_once()
        update_args = mock_query.update.call_args[0][0]
        assert update_args["status"] == "expired"
        assert update_args["closed_by"] == "auto_timeout"
