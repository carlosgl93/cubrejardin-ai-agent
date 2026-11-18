"""Behavioral tests for the Phase 4 ReAct-lite tool loop in AgentOrchestrator."""

from __future__ import annotations

import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import pytest

from agents.orchestrator import AgentOrchestrator, _conversion_alert_sent
from models.database import SessionLocal
from services.template_service import TemplateService
from services.tenant_config_service import TenantBotConfig
from services.vector_store import VectorStoreService


FAKE_TENANT_ID = "44444444-4444-4444-4444-444444444444"


class _StubWhatsAppService:
    def __init__(self) -> None:
        self.phone_id = "1234567890"


class _ToolLoopOpenAIService:
    """Stub OpenAI supporting tool_calls in the orchestrator loop."""

    def __init__(self, *, infinite_loop: bool = False) -> None:
        self.infinite_loop = infinite_loop
        self.tool_loop_turns = 0

    def embed(self, *, input_texts):  # type: ignore[override]
        return {"data": [{"embedding": [1.0, 0.0]}]}

    def chat_completion(
        self,
        *,
        messages: List[Dict[str, Any]],
        response_format: Dict[str, Any] | None = None,
        tools: List[Dict[str, Any]] | None = None,
        tool_choice: Any = None,
    ) -> Dict[str, Any]:
        system_msg = messages[0]["content"] if messages else ""
        if response_format:
            if "preguntas frecuentes" in system_msg.lower():
                return {"choices": [{"message": {"content": json.dumps({"category": "NOT_FAQ", "confidence": 0.1, "extracted_info": {}})}}]}
            if "Guardian" in system_msg or "clasifica" in system_msg.lower():
                return {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "category": "VALID_QUERY",
                                        "confidence": 0.95,
                                        "intent": "consulta_precio",
                                        "entities": {},
                                        "sentiment": "neutral",
                                        "reason": "consulta producto",
                                    }
                                )
                            }
                        }
                    ]
                }
            return {"choices": [{"message": {"content": json.dumps({"answer": "Fallback RAG", "answerable": True, "confidence": 0.85})}}]}

        if tools is not None:
            self.tool_loop_turns += 1
            if self.infinite_loop or self.tool_loop_turns == 1:
                return {
                    "choices": [
                        {
                            "message": {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": f"call_{self.tool_loop_turns}_1",
                                        "type": "function",
                                        "function": {
                                            "name": "search_knowledge_base",
                                            "arguments": json.dumps({"query": "precio piso vinyl"}),
                                        },
                                    },
                                    {
                                        "id": f"call_{self.tool_loop_turns}_2",
                                        "type": "function",
                                        "function": {
                                            "name": "emit_conversion_alert",
                                            "arguments": json.dumps({"intent_summary": "Quiere cotizar piso vinyl"}),
                                        },
                                    },
                                ],
                            }
                        }
                    ]
                }
            return {
                "choices": [
                    {
                        "message": {
                            "content": "El piso vinyl cuesta $19.990 por m2.",
                            "tool_calls": [],
                        }
                    }
                ]
            }

        return {"choices": [{"message": {"content": "Fallback RAG"}}]}


def _build_orchestrator(tmp_path, *, infinite_loop: bool = False) -> tuple[AgentOrchestrator, _ToolLoopOpenAIService]:
    session = SessionLocal()
    vector_store = VectorStoreService(
        index_path=str(tmp_path / "index.json"),
        tenant_id=FAKE_TENANT_ID,
        backend="local",
    )
    vector_store.add_embeddings(
        embeddings=[[1.0, 0.0]],
        metadatas=[{"title": "Catalogo", "content": "Piso vinyl click $19.990 por m2"}],
    )
    wa = _StubWhatsAppService()
    openai_svc = _ToolLoopOpenAIService(infinite_loop=infinite_loop)
    bot_cfg = TenantBotConfig(
        tenant_name="Pisos Demo",
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
    return orch, openai_svc


@pytest.mark.asyncio
async def test_orchestrator_tool_loop_executes_search_and_conversion_alert(tmp_path) -> None:
    """ReAct-lite loop should invoke search_knowledge_base and emit_conversion_alert then reply."""

    _conversion_alert_sent.clear()
    orch, openai_svc = _build_orchestrator(tmp_path)

    with patch("agents.orchestrator.alert_notification_service.dispatch_alert", new_callable=AsyncMock) as mock_alert:
        response = await orch.process_message("ig-user-1", "Cuánto cuesta el piso vinyl?", channel="instagram")

    assert response.message == "El piso vinyl cuesta $19.990 por m2."
    assert response.data["method"] == "react_tool_loop"
    assert openai_svc.tool_loop_turns == 2
    assert mock_alert.await_count == 1
    assert mock_alert.await_args.kwargs["alert_type"] == "conversion"
    assert mock_alert.await_args.kwargs["channel"] == "instagram"


@pytest.mark.asyncio
async def test_orchestrator_tool_loop_bounds_iterations_and_falls_back(tmp_path) -> None:
    """Loop should stop after 3 iterations and fall back cleanly to standard RAG."""

    _conversion_alert_sent.clear()
    orch, openai_svc = _build_orchestrator(tmp_path, infinite_loop=True)

    with patch("agents.orchestrator.alert_notification_service.dispatch_alert", new_callable=AsyncMock):
        response = await orch.process_message("wa-user-1", "Cuánto cuesta el piso vinyl?", channel="whatsapp")

    assert openai_svc.tool_loop_turns == 3
    assert response.message == "Fallback RAG"
