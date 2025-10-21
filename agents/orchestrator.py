"""Agent orchestrator module."""

from __future__ import annotations

import asyncio
from typing import Optional

from models.database import Conversation, InMemorySession, utc_now
from models.schemas import AgentResponse, GuardianResult, RAGResponse
from services.openai_service import OpenAIService
from services.vector_store import VectorStoreService
from services.whatsapp_service import WhatsAppService
from services.template_service import TemplateService
from services.mercadofiel_service import MercadoFielService
from utils import logger
from utils.helpers import sanitize_text

from .guardian_agent import GuardianAgent
from .handoff_agent import HandoffAgent
from .rag_agent import RAGAgent
from .stock_agent import StockAgent


class AgentOrchestrator:
    """Coordinate multi-agent workflow."""

    def __init__(
        self,
        *,
        session: InMemorySession,
        openai_service: OpenAIService,
        vector_store: VectorStoreService,
        whatsapp_service: WhatsAppService,
        template_service: TemplateService,
        mercadofiel_service: Optional[MercadoFielService] = None,
    ) -> None:
        self.session = session
        self.openai_service = openai_service
        self.vector_store = vector_store
        self.whatsapp_service = whatsapp_service
        self.template_service = template_service
        self.mercadofiel_service = mercadofiel_service or MercadoFielService()
        self.guardian = GuardianAgent(openai_service)
        self.rag = RAGAgent(openai_service, vector_store)
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
        metadata: Optional[dict] = None,
    ) -> Conversation:
        """Persist conversation message in a background thread."""

        def _persist() -> Conversation:
            timestamp = utc_now()
            entry = Conversation(user_number=user_number, role=role, message=message, metadata=metadata or {})
            entry.created_at = timestamp
            if role == "user":
                entry.last_interaction_at = timestamp
            entry.updated_at = timestamp
            self.session.add(entry)
            self.session.commit()
            return entry

        return await asyncio.to_thread(_persist)

    async def process_message(
        self,
        user_number: str,
        message: str,
        *,
        message_id: Optional[str] = None,
    ) -> AgentResponse:
        """Process inbound message and return response."""

        cleaned = sanitize_text(message)
        guardian_result: GuardianResult = await asyncio.to_thread(self.guardian.classify, cleaned)
        user_metadata = guardian_result.model_dump()
        if message_id:
            user_metadata["message_id"] = message_id
        await self._store_message(user_number, "user", cleaned, user_metadata)
        logger.info("guardian_classification", extra=guardian_result.model_dump())

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
            message_text = await self.handoff.escalate(conv, user_number, metadata={"reason": "user_request"})
            return AgentResponse(
                message=message_text,
                intent="handoff",
                category=guardian_result.category,
                data={"guardian": guardian_result.model_dump()},
            )

        if guardian_result.category == "GREETING":
            response = "¡Hola! ¿En qué puedo ayudarte hoy?"
            await self._store_message(user_number, "assistant", response)
            return AgentResponse(
                message=response,
                intent=guardian_result.intent,
                category=guardian_result.category,
                data={"guardian": guardian_result.model_dump()},
            )

        # Handle stock operations
        if guardian_result.category == "STOCK_OPERATION":
            logger.info("stock_operation_detected", extra={"user": user_number, "text": cleaned})
            
            # Try quick regex parse first
            quick_result = self.stock.quick_parse(cleaned)
            if quick_result:
                stock_op = quick_result
            else:
                # Fall back to AI parsing
                stock_op_result = await asyncio.to_thread(self.stock.parse_stock_command, cleaned)
                stock_op = stock_op_result.model_dump()
            
            # Extract parsed data
            action = stock_op.get("action")
            product_id = stock_op.get("product_id")
            quantity = stock_op.get("quantity")
            page = stock_op.get("page", 1)
            search_term = stock_op.get("search_term")
            
            # Actions that don't require product_id
            actions_without_product_id = ["STOCK_ALERTS", "PRODUCT_LIST"]
            
            # Validate we have required data (except for actions that don't need product_id)
            if not product_id and action not in actions_without_product_id:
                # Generate helpful error message with all available commands
                available_commands = (
                    "❌ No identifiqué el comando correctamente.\n\n"
                    "📋 *Comandos Disponibles:*\n\n"
                    "*Agregar Stock:*\n"
                    "• entrada 123 50\n"
                    "• +3 100\n"
                    "• agregar 20 del producto 456\n\n"
                    "*Ventas:*\n"
                    "• venta 123 5\n"
                    "• vendi 10 del producto 3\n"
                    "• -3 50 (quitar stock)\n\n"
                    "*Consultas:*\n"
                    "• stock 123\n"
                    "• ?3\n"
                    "• cuanto stock tiene el 456\n\n"
                    "*Gestión:*\n"
                    "• set 123 100 (establecer stock)\n"
                    "• historial 123\n"
                    "• alertas\n"
                    "• productos (listar tus productos)\n"
                    "• buscar tomates"
                )
                await self._store_message(user_number, "assistant", available_commands)
                return AgentResponse(
                    message=available_commands,
                    intent="stock_operation_help",
                    category="STOCK_OPERATION",
                    data={"error": "missing_product_id", "action": action}
                )
            
            # Execute appropriate API call based on action
            if action == "STOCK_ADD":
                if not quantity:
                    response_message = "❌ Falta la cantidad. Usa formato: entrada 123 50"
                    await self._store_message(user_number, "assistant", response_message)
                    return AgentResponse(message=response_message, intent="stock_operation_error", category="STOCK_OPERATION")
                
                api_result = await self.mercadofiel_service.add_stock(
                    product_id=product_id,
                    quantity=quantity,
                    phone_number=user_number,
                    notes=f"Mensaje original: {cleaned}"
                )
            
            elif action == "STOCK_REMOVE":
                if not quantity:
                    response_message = "❌ Falta la cantidad. Usa formato: salida 123 30"
                    await self._store_message(user_number, "assistant", response_message)
                    return AgentResponse(message=response_message, intent="stock_operation_error", category="STOCK_OPERATION")
                
                api_result = await self.mercadofiel_service.remove_stock(
                    product_id=product_id,
                    quantity=quantity,
                    phone_number=user_number,
                    is_sale=False,
                    notes=f"Mensaje original: {cleaned}"
                )
            
            elif action == "STOCK_SALE":
                if not quantity:
                    response_message = "❌ Falta la cantidad. Usa formato: venta 123 5"
                    await self._store_message(user_number, "assistant", response_message)
                    return AgentResponse(message=response_message, intent="stock_operation_error", category="STOCK_OPERATION")
                
                api_result = await self.mercadofiel_service.remove_stock(
                    product_id=product_id,
                    quantity=quantity,
                    phone_number=user_number,
                    is_sale=True,
                    notes=f"Venta registrada. Mensaje original: {cleaned}"
                )
            
            elif action == "STOCK_QUERY":
                api_result = await self.mercadofiel_service.query_stock(product_id, phone_number=user_number)
            
            elif action == "STOCK_HISTORY":
                api_result = await self.mercadofiel_service.get_history(product_id, phone_number=user_number, limit=10)
            
            elif action == "STOCK_ALERTS":
                api_result = await self.mercadofiel_service.get_alerts(phone_number=user_number, resolved=False)
            
            elif action == "PRODUCT_LIST":
                page = stock_op.get("page", 1)
                search_term = stock_op.get("search_term")
                
                logger.info("product_list_request", extra={
                    "phone_number": user_number,
                    "page": page,
                    "search_term": search_term,
                    "text": "Requesting product list for supplier"
                })
                
                api_result = await self.mercadofiel_service.get_products(
                    phone_number=user_number,
                    page=page,
                    limit=10,
                    search=search_term
                )
            
            elif action == "STOCK_SET":
                if not quantity:
                    response_message = "❌ Falta la cantidad. Usa formato: set 123 100"
                    await self._store_message(user_number, "assistant", response_message)
                    return AgentResponse(message=response_message, intent="stock_operation_error", category="STOCK_OPERATION")
                
                api_result = await self.mercadofiel_service.set_stock(
                    product_id=product_id,
                    new_quantity=quantity,
                    phone_number=user_number,
                    notes=f"Mensaje original: {cleaned}"
                )
            
            else:
                # Unknown action
                response_message = (
                    "❌ No identifiqué el comando correctamente.\n\n"
                    "📋 *Comandos Disponibles:*\n\n"
                    "*Agregar Stock:*\n"
                    "• entrada 123 50\n"
                    "• +3 100\n"
                    "• agregar 20 del producto 456\n\n"
                    "*Ventas:*\n"
                    "• venta 123 5\n"
                    "• vendi 10 del producto 3\n"
                    "• -3 50 (quitar stock)\n\n"
                    "*Consultas:*\n"
                    "• stock 123\n"
                    "• ?3\n"
                    "• cuanto stock tiene el 456\n\n"
                    "*Gestión:*\n"
                    "• set 123 100 (establecer stock)\n"
                    "• historial 123\n"
                    "• alertas\n"
                    "• productos (listar tus productos)\n"
                    "• buscar tomates"
                )
                await self._store_message(user_number, "assistant", response_message)
                return AgentResponse(
                    message=response_message,
                    intent="stock_operation_error",
                    category="STOCK_OPERATION",
                    data={"error": "unknown_action", "parsed_action": action}
                )
            
            # Get message from API result
            response_message = api_result.get("message", "Operación completada")
            
            await self._store_message(
                user_number,
                "assistant",
                response_message,
                {
                    "stock_operation": stock_op,
                    "api_result": api_result
                }
            )
            
            return AgentResponse(
                message=response_message,
                intent="stock_operation",
                category="STOCK_OPERATION",
                data={
                    "guardian": guardian_result.model_dump(),
                    "stock": stock_op,
                    "result": api_result
                },
            )

        rag_response: RAGResponse = await asyncio.to_thread(self.rag.answer, cleaned)
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

        if rag_response.confidence < 0.5 and guardian_result.category == "VALID_QUERY":
            conv = await self._store_message(user_number, "system", "Confianza baja, escalando")
            await self.handoff.escalate(conv, user_number, metadata={"reason": "low_confidence"})

        return AgentResponse(
            message=rag_response.answer,
            intent=guardian_result.intent,
            category=guardian_result.category,
            data={
                "guardian": guardian_result.model_dump(),
                "rag": rag_response.model_dump(),
            },
        )

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

        def _check() -> bool:
            for convo in self.session.query(Conversation):
                if convo.role != "user":
                    continue
                metadata = convo.metadata or {}
                if metadata.get("message_id") == message_id:
                    return True
            return False

        return await asyncio.to_thread(_check)
