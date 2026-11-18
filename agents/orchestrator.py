"""Agent orchestrator module."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import time
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, select

from models.database import Conversation, DatabaseSession, utc_now
from models.schemas import AgentResponse, GuardianResult, RAGResponse
from services import alert_notification_service
from services.openai_service import OpenAIService
from services.vector_store import VectorStoreService
from services.whatsapp_service import WhatsAppService
from services.template_service import TemplateService
from utils import logger
from utils.helpers import sanitize_text

from .guardian_agent import GuardianAgent
from .handoff_agent import HandoffAgent
from .rag_agent import RAGAgent
from .faq_agent import FAQAgent
from .stock_agent import StockAgent
from services.tenant_config_service import get_tenant_bot_config, TenantBotConfig

_MAX_TOOL_ITERATIONS = 3
_ORCHESTRATOR_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "Busca información del negocio, productos, precios, envíos o políticas en la base documental.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Consulta de búsqueda en español."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_product_stock",
            "description": "Analiza consultas o comandos de stock e inventario de productos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Mensaje o consulta sobre stock."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": "Escala la conversación a un agente humano cuando no hay información suficiente o el cliente lo necesita.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Motivo breve de la escalación."},
                },
                "required": ["reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "emit_conversion_alert",
            "description": "Envía alerta interna de lead caliente cuando el cliente muestra intención clara de compra o cotización.",
            "parameters": {
                "type": "object",
                "properties": {
                    "intent_summary": {"type": "string", "description": "Resumen breve del interés comercial."},
                },
                "required": ["intent_summary"],
            },
        },
    },
]

_CONVERSION_FAQ_CATEGORIES = frozenset({"PRICING", "ORDER_PROCESS"})
_CONVERSION_FAQ_MIN_CONFIDENCE = 0.7
_CONVERSION_INTENT_KEYWORDS = (
    "cotizar",
    "comprar",
    "precio",
    "pedido",
    "purchase",
    "pricing",
    "order",
)
_CONVERSION_ALERT_TTL_SECONDS = 1800.0
_conversion_alert_sent: dict[tuple[str, str], float] = {}


@dataclass(frozen=True)
class ConversionSignal:
    """Detected commercial conversion intent for a customer turn."""

    reason: str


def _detect_conversion_signal(
    guardian_result: GuardianResult,
    faq_intent: Optional[Dict[str, Any]],
) -> Optional[ConversionSignal]:
    """Return a ConversionSignal when FAQ or Guardian indicates purchase/pricing intent."""
    if faq_intent:
        category = str(faq_intent.get("category") or "").upper()
        try:
            confidence = float(faq_intent.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if category in _CONVERSION_FAQ_CATEGORIES and confidence >= _CONVERSION_FAQ_MIN_CONFIDENCE:
            return ConversionSignal(
                reason=f"Consulta comercial ({category}, confianza {confidence:.0%})"
            )

    intent_text = (guardian_result.intent or "").lower()
    if any(keyword in intent_text for keyword in _CONVERSION_INTENT_KEYWORDS):
        return ConversionSignal(
            reason=f"Intencion comercial detectada: {guardian_result.intent}"
        )

    return None


class AgentOrchestrator:
    """Coordinate multi-agent workflow."""

    def __init__(
        self,
        *,
        session: DatabaseSession,
        openai_service: OpenAIService,
        vector_store: VectorStoreService,
        whatsapp_service: WhatsAppService,
        template_service: TemplateService,
        tenant_id: Optional[str] = None,
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.openai_service = openai_service
        if tenant_id and getattr(vector_store, "tenant_id", None) != tenant_id:
            self.vector_store = VectorStoreService(
                tenant_id=tenant_id,
                backend=getattr(vector_store, "backend", None),
            )
        else:
            self.vector_store = vector_store
        self.whatsapp_service = whatsapp_service
        self.template_service = template_service
        self._bot_config: TenantBotConfig = (
            get_tenant_bot_config(tenant_id) if tenant_id else TenantBotConfig()
        )
        tenant_display_name = getattr(self._bot_config, "tenant_name", None) or "el negocio"
        self.guardian = GuardianAgent(openai_service, handoff_trigger=self._bot_config.handoff_trigger)
        self.rag = RAGAgent(
            openai_service,
            self.vector_store,
            system_prompt=self._bot_config.system_prompt,
            business_name=tenant_display_name,
        )
        self.faq = FAQAgent(openai_service, business_name=tenant_display_name)
        self.stock = StockAgent(openai_service)
        self.handoff = HandoffAgent(
            openai_service=openai_service,
            whatsapp_service=whatsapp_service,
            session=session,
        )

    async def _store_message(
        self,
        user_number: str,
        role: str,
        message: str,
        payload: Optional[dict] = None,
        message_id: Optional[str] = None,
    ) -> Conversation:
        """Persist conversation message.

        All operational messages are persisted in Postgres/Supabase through
        the shared SQLAlchemy session.
        """

        timestamp = utc_now()
        entry = Conversation(
            tenant_id=self.tenant_id,
            channel_user_id=user_number,
            role=role,
            message=message,
            message_id=message_id,
            payload=payload or {},
            last_interaction_at=timestamp if role == "user" else None,
        )
        entry.created_at = timestamp
        entry.updated_at = timestamp
        self.session.add(entry)
        self.session.commit()
        self.session.refresh(entry)
        return entry

    def _get_recent_history(
        self,
        user_number: str,
        limit: int = 6,
        current_message: str = "",
    ) -> List[Dict[str, str]]:
        """Fetch chronological prior conversation turns for prompt context."""
        history: List[Dict[str, str]] = []
        try:
            from config.supabase import get_supabase_client
            sb = get_supabase_client()
            if sb:
                query = (
                    sb.table("conversations")
                    .select("role, message, created_at")
                    .eq("channel_user_id", user_number)
                )
                if self.tenant_id:
                    query = query.eq("tenant_id", self.tenant_id)
                res = query.order("created_at", desc=True).limit(limit + 2).execute()
                rows = res.data or []
                if rows and current_message and rows[0]["role"] == "user" and rows[0].get("message", "").strip() == current_message.strip():
                    rows = rows[1:]
                for r in reversed(rows[:limit]):
                    role = "assistant" if r.get("role") in ("assistant", "system") else "user"
                    msg = (r.get("message") or "").strip()
                    if msg:
                        history.append({"role": role, "content": msg})
        except Exception as exc:
            logger.warning("history_fetch_from_supabase_failed", extra={"error": str(exc)})

        if not history and hasattr(self, "session") and self.session:
            try:
                from models.database import Conversation
                q = self.session.query(Conversation).filter(Conversation.channel_user_id == user_number)
                if self.tenant_id:
                    q = q.filter(Conversation.tenant_id == self.tenant_id)
                all_mem = q.all()
                if all_mem:
                    if current_message and all_mem[-1].role == "user" and all_mem[-1].message.strip() == current_message.strip():
                        all_mem = all_mem[:-1]
                    for c in all_mem[-limit:]:
                        role = "assistant" if c.role in ("assistant", "system") else "user"
                        if c.message.strip():
                            history.append({"role": role, "content": c.message.strip()})
            except Exception:
                pass

        return history

    async def _dispatch_conversion_alert_with_reason(
        self,
        *,
        user_number: str,
        channel: str,
        cleaned_message: str,
        reply_message: str,
        reason: str,
    ) -> bool:
        """Send a deduplicated conversion alert without risking the customer reply."""

        now = time.monotonic()
        cache_key = (self.tenant_id or "", user_number)
        last_sent = _conversion_alert_sent.get(cache_key)
        if last_sent is not None and (now - last_sent) < _CONVERSION_ALERT_TTL_SECONDS:
            return False

        recent_messages = f"Cliente: {cleaned_message[:300]}\nBot: {reply_message[:300]}"
        try:
            await alert_notification_service.dispatch_alert(
                tenant_id=self.tenant_id or "",
                alert_type="conversion",
                channel=channel,
                customer_id=user_number,
                reason=reason,
                recent_messages=recent_messages,
                bot_config=self._bot_config,
            )
            if len(_conversion_alert_sent) >= 1000:
                expired = [
                    k for k, ts in _conversion_alert_sent.items()
                    if (now - ts) >= _CONVERSION_ALERT_TTL_SECONDS
                ]
                for k in expired:
                    _conversion_alert_sent.pop(k, None)
            _conversion_alert_sent[cache_key] = now
            return True
        except Exception as exc:
            logger.warning(
                "conversion_alert_dispatch_failed",
                extra={
                    "tenant_id": self.tenant_id or "",
                    "user": user_number,
                    "error": str(exc),
                },
            )
            return False

    async def _maybe_dispatch_conversion_alert(
        self,
        *,
        user_number: str,
        channel: str,
        cleaned_message: str,
        reply_message: str,
        guardian_result: GuardianResult,
        faq_intent: Optional[Dict[str, Any]],
    ) -> None:
        """Detect and dispatch a conversion alert when commercial intent is present."""
        signal = _detect_conversion_signal(guardian_result, faq_intent)
        if not signal:
            return
        await self._dispatch_conversion_alert_with_reason(
            user_number=user_number,
            channel=channel,
            cleaned_message=cleaned_message,
            reply_message=reply_message,
            reason=signal.reason,
        )

    async def _run_tool_loop(
        self,
        *,
        user_number: str,
        channel: str,
        cleaned: str,
        raw_message: str,
        history: List[Dict[str, str]],
        guardian_result: GuardianResult,
    ) -> Optional[AgentResponse]:
        """Run a bounded ReAct-lite tool loop; return None if tools are unsupported."""

        tenant_name = getattr(self._bot_config, "tenant_name", None) or "el negocio"
        system_content = (
            f"Eres el asistente virtual de {tenant_name}. "
            "Usa search_knowledge_base antes de responder preguntas sobre productos, precios, "
            "envíos o políticas. Usa check_product_stock si preguntan por stock o inventario. "
            "Usa emit_conversion_alert si el cliente muestra clara intención de compra o cotización. "
            "Usa escalate_to_human si no encuentras información suficiente o el cliente requiere atención humana."
        )
        if self._bot_config.system_prompt:
            system_content = f"{self._bot_config.system_prompt}\n\n{system_content}"

        loop_messages: List[Dict[str, Any]] = [{"role": "system", "content": system_content}]
        loop_messages.extend(history)
        loop_messages.append({"role": "user", "content": cleaned})

        sources: List[Dict[str, str]] = []
        best_score = 0.0
        escalated = False

        for _ in range(_MAX_TOOL_ITERATIONS):
            try:
                response = await asyncio.to_thread(
                    self.openai_service.chat_completion,
                    messages=loop_messages,
                    tools=_ORCHESTRATOR_TOOLS,
                )
            except TypeError:
                return None
            except Exception as exc:
                logger.warning("orchestrator_tool_loop_failed", extra={"error": str(exc)})
                return None

            choice_msg = (response.get("choices") or [{}])[0].get("message") or {}
            tool_calls = choice_msg.get("tool_calls") or []
            if not tool_calls:
                final_text = str(choice_msg.get("content") or "").strip()
                if not final_text:
                    return None
                await self._store_message(
                    user_number,
                    "assistant",
                    final_text,
                    {"method": "react_tool_loop", "sources": sources, "confidence": best_score},
                )
                return AgentResponse(
                    message=final_text,
                    intent=guardian_result.intent,
                    category=guardian_result.category,
                    data={
                        "guardian": guardian_result.model_dump(),
                        "method": "react_tool_loop",
                        "sources": sources,
                        "escalated": escalated,
                    },
                )

            loop_messages.append(
                {
                    "role": "assistant",
                    "content": choice_msg.get("content"),
                    "tool_calls": tool_calls,
                }
            )
            for tc in tool_calls:
                fn = tc.get("function") or {}
                fn_name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except (ValueError, TypeError):
                    args = {}

                if fn_name == "search_knowledge_base":
                    q = str(args.get("query") or cleaned)
                    ctx, step_sources, step_score = await asyncio.to_thread(
                        self.rag.retrieve_context, q, history, top_k=4
                    )
                    sources.extend(step_sources)
                    best_score = max(best_score, step_score)
                    tool_output = json.dumps(
                        {"context": ctx, "sources": step_sources, "best_score": step_score},
                        ensure_ascii=False,
                    )
                elif fn_name == "check_product_stock":
                    q = str(args.get("query") or cleaned)
                    stock_op = await asyncio.to_thread(self.stock.parse_stock_command, q)
                    tool_output = stock_op.model_dump_json()
                elif fn_name == "escalate_to_human":
                    reason = str(args.get("reason") or "agent_escalation")
                    conv = await self._store_message(user_number, "system", f"Escalación: {reason}")
                    try:
                        await self.handoff.escalate(
                            conv,
                            user_number,
                            metadata={"reason": reason},
                            tenant_id=self.tenant_id or "",
                            phone_id=self.whatsapp_service.phone_id or "",
                            last_message=raw_message,
                            channel=channel,
                        )
                        escalated = True
                        tool_output = json.dumps({"escalated": True, "reason": reason})
                    except Exception as exc:
                        tool_output = json.dumps({"escalated": False, "error": str(exc)})
                elif fn_name == "emit_conversion_alert":
                    intent_summary = str(args.get("intent_summary") or guardian_result.intent or "Lead caliente")
                    sent = await self._dispatch_conversion_alert_with_reason(
                        user_number=user_number,
                        channel=channel,
                        cleaned_message=cleaned,
                        reply_message="",
                        reason=intent_summary,
                    )
                    tool_output = json.dumps({"alert_sent": sent})
                else:
                    tool_output = json.dumps({"error": f"Unknown tool: {fn_name}"})

                loop_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": tool_output,
                    }
                )

        return None

    async def process_message(
        self,
        user_number: str,
        message: str,
        *,
        message_id: Optional[str] = None,
        channel: str = "whatsapp",
    ) -> AgentResponse:
        """Process inbound message and return response."""

        cleaned = sanitize_text(message)
        history = self._get_recent_history(user_number, limit=6, current_message=cleaned)
        guardian_result: GuardianResult = await asyncio.to_thread(self.guardian.classify, cleaned, history)
        user_metadata = guardian_result.model_dump()
        if message_id:
            user_metadata["message_id"] = message_id
        await self._store_message(
            user_number,
            "user",
            cleaned,
            user_metadata,
            message_id=message_id,
        )
        logger.info("guardian_classification", extra=guardian_result.model_dump())
        logger.info("guardian result", extra={"result": guardian_result})

        if guardian_result.category in {"SPAM", "SENSITIVE", "OFF_TOPIC"}:
            response = (
                "Gracias por contactarnos. Actualmente no podemos procesar este mensaje."
            )
            await self._store_message(user_number, "system", response)
            return AgentResponse(
                message=response,
                intent=guardian_result.intent,
                category=guardian_result.category,
                data={"guardian": guardian_result.model_dump()},
            )

        if guardian_result.category == "ESCALATION_REQUEST":
            conv = await self._store_message(user_number, "system", "Escalación solicitada")
            message_text = await self.handoff.escalate(conv, user_number, metadata={"reason": "user_request"}, tenant_id=self.tenant_id or "", phone_id=self.whatsapp_service.phone_id or "", last_message=message, channel=channel)
            return AgentResponse(
                message=message_text,
                intent="handoff",
                category=guardian_result.category,
                data={"guardian": guardian_result.model_dump()},
            )

        if guardian_result.category == "GREETING":
            response = self._bot_config.greeting or "¡Hola! ¿En qué puedo ayudarte hoy?"
            await self._store_message(user_number, "assistant", response)
            return AgentResponse(
                message=response,
                intent=guardian_result.intent,
                category=guardian_result.category,
                data={"guardian": guardian_result.model_dump()},
            )

        tool_loop_response = await self._run_tool_loop(
            user_number=user_number,
            channel=channel,
            cleaned=cleaned,
            raw_message=message,
            history=history,
            guardian_result=guardian_result,
        )
        if tool_loop_response is not None:
            await self._maybe_dispatch_conversion_alert(
                user_number=user_number,
                channel=channel,
                cleaned_message=cleaned,
                reply_message=tool_loop_response.message,
                guardian_result=guardian_result,
                faq_intent=None,
            )
            return tool_loop_response

        # First, try to identify if it's an FAQ question
        faq_intent = await asyncio.to_thread(self.faq.identify_faq_intent, cleaned)
        logger.info(
            "faq_intent_check",
            extra={
                "user": user_number,
                "category": faq_intent.get("category"),
                "confidence": faq_intent.get("confidence"),
            },
        )

        # If FAQ agent has high confidence (>=0.7) and it's a known FAQ category, use FAQ agent
        if faq_intent.get("confidence", 0) >= 0.7 and faq_intent.get("category") != "NOT_FAQ":
            context_text, sources, _ = await asyncio.to_thread(
                self.rag.retrieve_context,
                cleaned,
                history,
                top_k=3,
            )
            
            logger.info(
                "faq_vector_context",
                extra={
                    "user": user_number,
                    "category": faq_intent.get("category"),
                    "sources": sources,
                    "context_length": len(context_text)
                }
            )
            
            # Generate FAQ response using vector store context
            faq_answer = await asyncio.to_thread(
                self.faq.generate_faq_response,
                cleaned,
                faq_intent,
                context_text,
                self._bot_config.system_prompt,
                history,
            )
            
            # Use FAQ confidence (which is higher)
            final_confidence = faq_intent.get("confidence", 0.8)
            
            logger.info(
                "faq_response_used",
                extra={
                    "user": user_number,
                    "category": faq_intent.get("category"),
                    "confidence": final_confidence,
                },
            )
            
            await self._store_message(
                user_number,
                "assistant",
                faq_answer,
                {
                    "confidence": final_confidence,
                    "faq_category": faq_intent.get("category"),
                    "method": "faq_agent"
                },
            )

            agent_response = AgentResponse(
                message=faq_answer,
                intent=guardian_result.intent,
                category=guardian_result.category,
                data={
                    "guardian": guardian_result.model_dump(),
                    "faq": faq_intent,
                    "confidence": final_confidence,
                },
            )
        else:
            # Fall back to standard RAG if not a clear FAQ or low FAQ confidence
            rag_response: RAGResponse = await asyncio.to_thread(self.rag.answer, cleaned, history)
            logger.info(
                "rag_answer",
                extra={
                    "user": user_number,
                    "confidence": rag_response.confidence,
                    "sources": rag_response.sources,
                },
            )
            await self._store_message(
                user_number,
                "assistant",
                rag_response.answer,
                {"confidence": rag_response.confidence, "sources": rag_response.sources},
            )

            # Try to escalate on low confidence, but don't fail the request if escalation fails
            if rag_response.confidence < 0.5 and guardian_result.category == "VALID_QUERY":
                conv = await self._store_message(user_number, "system", "Confianza baja, escalando")
                try:
                    await self.handoff.escalate(conv, user_number, metadata={"reason": "low_confidence"}, tenant_id=self.tenant_id or "", phone_id=self.whatsapp_service.phone_id or "", last_message=message, channel=channel)
                except Exception as exc:
                    logger.warning(
                        "escalation_failed_gracefully",
                        extra={
                            "user": user_number,
                            "error": str(exc),
                            "confidence": rag_response.confidence,
                        }
                    )

            agent_response = AgentResponse(
                message=rag_response.answer,
                intent=guardian_result.intent,
                category=guardian_result.category,
                data={
                    "guardian": guardian_result.model_dump(),
                    "rag": rag_response.model_dump(),
                },
            )

        await self._maybe_dispatch_conversion_alert(
            user_number=user_number,
            channel=channel,
            cleaned_message=cleaned,
            reply_message=agent_response.message,
            guardian_result=guardian_result,
            faq_intent=faq_intent,
        )
        return agent_response

    async def handle_outside_window(self, user_number: str, response: AgentResponse) -> str:
        """Fallback to an approved template when outside the 24h window."""

        result = await self.template_service.send_fallback_template(user_number, response)
        logger.info(
            "template_fallback_sent",
            extra={
                "user": user_number,
                "template": result.template_name,
                "intent": response.intent,
            },
        )
        return result.template_name

    async def has_processed_message(self, message_id: str) -> bool:
        """Return True if the inbound message id has already been processed."""
        if not message_id:
            return False

        try:
            from services.deduplication_service import get_deduplication_service
            dedup = get_deduplication_service()
            if await dedup.is_processed(message_id, tenant_id=self.tenant_id):
                return True
        except Exception:
            pass

        query = self.session.query(Conversation).filter(
            Conversation.message_id == message_id,
            Conversation.role == "user",
        )
        if self.tenant_id:
            query = query.filter(Conversation.tenant_id == self.tenant_id)
        return query.first() is not None
