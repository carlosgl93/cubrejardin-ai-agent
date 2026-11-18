"""Behavioral tests for email subject formatting, conversion alerts, and tenant notification config."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from agents import orchestrator as orchestrator_module
from agents.orchestrator import AgentOrchestrator
from api.tenant_context import TenantContext, get_tenant_context
from main import app
from models.database import SessionLocal
from services.email_service import EmailService
from services.template_service import TemplateService
from services.tenant_config_service import TenantBotConfig, invalidate_tenant_bot_config
from services.vector_store import VectorStoreService


FAKE_TENANT_ID = "33333333-3333-3333-3333-333333333333"
client = TestClient(app)


class _StubOpenAIService:
    """Stub OpenAI service returning configurable Guardian, FAQ, and RAG payloads."""

    def __init__(self, *, guardian_intent: str, faq_category: str, faq_confidence: float) -> None:
        self.guardian_intent = guardian_intent
        self.faq_category = faq_category
        self.faq_confidence = faq_confidence

    def chat_completion(self, *, messages, response_format=None):  # type: ignore[override]
        system_prompt = messages[0]["content"] if messages else ""
        if response_format:
            if "preguntas frecuentes" in system_prompt.lower():
                payload = {
                    "category": self.faq_category,
                    "confidence": self.faq_confidence,
                    "extracted_info": {},
                }
            else:
                payload = {
                    "category": "VALID_QUERY",
                    "confidence": 0.92,
                    "intent": self.guardian_intent,
                    "entities": {},
                    "sentiment": "neutral",
                    "reason": "consulta comercial",
                }
            return {"choices": [{"message": {"content": json.dumps(payload)}}]}
        return {"choices": [{"message": {"content": "Nuestros planes comienzan en $29.990 mensuales."}}]}

    def embed(self, *, input_texts):  # type: ignore[override]
        return {"data": [{"embedding": [1.0, 0.0]}]}


class _StubWhatsAppService:
    def __init__(self) -> None:
        self.phone_id = "1234567890"


def _build_orchestrator(
    tmp_path,
    *,
    guardian_intent: str,
    faq_category: str,
    faq_confidence: float,
) -> tuple[AgentOrchestrator, object]:
    session = SessionLocal()
    vector_store = VectorStoreService(
        index_path=str(tmp_path / "index.json"),
        tenant_id=FAKE_TENANT_ID,
        backend="local",
    )
    vector_store.add_embeddings(
        embeddings=[[1.0, 0.0]],
        metadatas=[{"title": "Precios", "content": "Nuestros planes comienzan en $29.990 mensuales."}],
    )
    wa = _StubWhatsAppService()
    openai_svc = _StubOpenAIService(
        guardian_intent=guardian_intent,
        faq_category=faq_category,
        faq_confidence=faq_confidence,
    )
    bot_cfg = TenantBotConfig(
        tenant_name="Tienda Demo",
        notify_email_enabled=True,
        notify_email_recipient="ventas@demo.cl",
        notify_conversion_alerts=True,
    )
    with patch("agents.orchestrator.get_tenant_bot_config", return_value=bot_cfg):
        orch = AgentOrchestrator(
            session=session,
            openai_service=openai_svc,  # type: ignore[arg-type]
            vector_store=vector_store,
            whatsapp_service=wa,  # type: ignore[arg-type]
            template_service=TemplateService(whatsapp_service=wa),  # type: ignore[arg-type]
            tenant_id=FAKE_TENANT_ID,
        )
    return orch, session


@pytest.fixture(autouse=True)
def _reset_conversion_state():
    orchestrator_module._conversion_alert_sent.clear()
    invalidate_tenant_bot_config(FAKE_TENANT_ID)
    yield
    orchestrator_module._conversion_alert_sent.clear()
    invalidate_tenant_bot_config(FAKE_TENANT_ID)


@pytest.mark.asyncio
async def test_email_service_send_alert_uses_unicode_bullet_in_subject():
    service = EmailService(api_key="re_test_key", from_email="alertas@sgcloud.cl")
    mock_response = MagicMock()
    mock_response.json.return_value = {"id": "email_bullet"}
    mock_response.raise_for_status.return_value = None

    with patch.object(service._client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        await service.send_alert(
            to="ventas@negocio.cl",
            alert_type="conversion",
            tenant_name="Tienda Demo",
            channel="whatsapp",
            customer_id="56912345678",
            reason="Consulta de precios",
        )
        subject = mock_post.call_args[1]["json"]["subject"]
        assert "•" in subject
        assert "&bull;" not in subject
        assert subject == "[LEAD CALIENTE] Tienda Demo • Cliente 56912345678 (whatsapp)"
    await service.close()


@pytest.mark.asyncio
async def test_orchestrator_triggers_conversion_alert_on_pricing_faq_and_deduplicates(tmp_path):
    orch, session = _build_orchestrator(
        tmp_path,
        guardian_intent="consulta",
        faq_category="PRICING",
        faq_confidence=0.9,
    )
    try:
        with patch("agents.orchestrator.alert_notification_service.dispatch_alert", new_callable=AsyncMock) as mock_dispatch:
            mock_dispatch.return_value = {"email": {"id": "e1"}}

            first_reply = await orch.process_message("56911112222", "Cuanto cuesta el servicio?")
            second_reply = await orch.process_message("56911112222", "Y cuanto sale el plan anual?")

            assert first_reply.message == "Nuestros planes comienzan en $29.990 mensuales."
            assert second_reply.message == "Nuestros planes comienzan en $29.990 mensuales."
            mock_dispatch.assert_awaited_once()
            call_kwargs = mock_dispatch.await_args.kwargs
            assert call_kwargs["tenant_id"] == FAKE_TENANT_ID
            assert call_kwargs["alert_type"] == "conversion"
            assert call_kwargs["channel"] == "whatsapp"
            assert call_kwargs["customer_id"] == "56911112222"
            assert "PRICING" in call_kwargs["reason"]
    finally:
        session.close()


@pytest.mark.asyncio
async def test_orchestrator_triggers_conversion_alert_on_guardian_purchase_intent_and_survives_error(tmp_path):
    orch, session = _build_orchestrator(
        tmp_path,
        guardian_intent="cotizar_servicio",
        faq_category="NOT_FAQ",
        faq_confidence=0.1,
    )
    try:
        with patch(
            "agents.orchestrator.alert_notification_service.dispatch_alert",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Resend timeout"),
        ) as mock_dispatch:
            reply = await orch.process_message("56933334444", "Quiero cotizar 50 unidades")

            assert reply.message
            mock_dispatch.assert_awaited_once()
            call_kwargs = mock_dispatch.await_args.kwargs
            assert call_kwargs["alert_type"] == "conversion"
            assert call_kwargs["customer_id"] == "56933334444"
            assert "cotizar_servicio" in call_kwargs["reason"]
    finally:
        session.close()


@pytest.mark.asyncio
async def test_orchestrator_skips_conversion_alert_for_non_commercial_query(tmp_path):
    orch, session = _build_orchestrator(
        tmp_path,
        guardian_intent="horario",
        faq_category="HOURS",
        faq_confidence=0.95,
    )
    try:
        with patch("agents.orchestrator.alert_notification_service.dispatch_alert", new_callable=AsyncMock) as mock_dispatch:
            reply = await orch.process_message("56955556666", "A que hora abren?")

            assert reply.message
            mock_dispatch.assert_not_awaited()
    finally:
        session.close()


def test_bot_config_notification_fields_round_trip():
    stored_rows: list[dict] = []

    class _FakeTable:
        def select(self, *_args):
            return self

        def eq(self, *_args):
            return self

        def limit(self, *_args):
            return self

        def upsert(self, payload, **_kwargs):
            row = {
                "id": "cfg-notif-1",
                "system_prompt": None,
                "greeting": None,
                "handoff_trigger": None,
                "business_hours": {},
                **payload,
            }
            stored_rows[:] = [row]
            return SimpleNamespace(execute=lambda: SimpleNamespace(data=[row]))

        def execute(self):
            return SimpleNamespace(data=list(stored_rows))

    fake_sb = MagicMock()
    fake_sb.table.return_value = _FakeTable()

    app.dependency_overrides[get_tenant_context] = lambda: TenantContext(
        tenant_id=FAKE_TENANT_ID,
        user_id="USER_OWNER",
        role="owner",
        tenant_name="Tienda Demo",
    )
    try:
        with patch("api.tenants.get_supabase_client", return_value=fake_sb):
            empty_resp = client.get("/api/tenants/config")
            assert empty_resp.status_code == 200
            defaults = empty_resp.json()
            assert defaults["notify_email_enabled"] is False
            assert defaults["notify_email_recipient"] is None
            assert defaults["notify_whatsapp_enabled"] is False
            assert defaults["notify_whatsapp_recipient"] is None
            assert defaults["notify_conversion_alerts"] is True
            assert defaults["notify_handoff_alerts"] is True

            put_payload = {
                "notify_email_enabled": True,
                "notify_email_recipient": "admin@tiendademo.cl",
                "notify_whatsapp_enabled": True,
                "notify_whatsapp_recipient": "+56987654321",
                "notify_conversion_alerts": False,
                "notify_handoff_alerts": True,
            }
            put_resp = client.put("/api/tenants/config", json=put_payload)
            assert put_resp.status_code == 200
            saved = put_resp.json()
            for key, value in put_payload.items():
                assert saved[key] == value

            get_resp = client.get("/api/tenants/config")
            assert get_resp.status_code == 200
            fetched = get_resp.json()
            for key, value in put_payload.items():
                assert fetched[key] == value
    finally:
        app.dependency_overrides.pop(get_tenant_context, None)
