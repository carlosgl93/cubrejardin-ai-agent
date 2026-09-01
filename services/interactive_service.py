"""Interactive buttons and callback handling for WhatsApp/Instagram."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from functools import wraps

from pydantic import BaseModel, Field

from utils import logger


class ButtonType(str, Enum):
    """Types of interactive buttons."""
    QUICK_REPLY = "quick_reply"      # Single tap response
    URL = "url"                      # Opens URL
    COPY_CODE = "copy_code"          # Copy to clipboard


@dataclass
class Button:
    """A single interactive button."""
    id: str
    title: str
    button_type: ButtonType = ButtonType.QUICK_REPLY
    payload: Optional[str] = None    # Data sent when clicked
    url: Optional[str] = None        # For URL buttons

    def to_dict(self) -> Dict[str, Any]:
        """Convert to WhatsApp/Meta API format."""
        if self.button_type == ButtonType.URL:
            return {
                "type": "url",
                "title": self.title,
                "url": self.url,
            }
        else:
            return {
                "type": "reply",
                "reply": {
                    "id": self.id,
                    "title": self.title,
                },
            }


@dataclass
class InteractiveMessage:
    """A message with interactive buttons."""
    body_text: str
    header: Optional[str] = None
    footer: Optional[str] = None
    buttons: List[Button] = field(default_factory=list)
    buttons_header: Optional[str] = None

    def to_whatsapp_payload(self) -> Dict[str, Any]:
        """Generate WhatsApp Cloud API payload."""
        # WhatsApp supports max 3 buttons in a single section
        if len(self.buttons) > 3:
            logger.warning(
                "buttons_truncated",
                extra={"requested": len(self.buttons), "max": 3}
            )
            buttons = self.buttons[:3]
        else:
            buttons = self.buttons

        components = []

        # Header
        if self.header:
            components.append({
                "type": "header",
                "parameters": [{"type": "text", "text": self.header}]
            })

        # Body
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": self.body_text}]
        })

        # Buttons
        if buttons:
            components.append({
                "type": "button",
                "sub_type": "quick_reply",
                "index": "0",
                "parameters": [
                    {
                        "type": "payload",
                        "payload": json.dumps({"id": b.id, "payload": b.payload})
                    }
                    if b.button_type == ButtonType.QUICK_REPLY else
                    {
                        "type": "url",
                        "payload": b.payload
                    }
                    for b in buttons
                ]
            })

        # Footer
        if self.footer:
            components.append({
                "type": "footer",
                "text": self.footer
            })

        return {
            "messaging_product": "whatsapp",
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": self.body_text},
                "action": {
                    "buttons": [b.to_dict() for b in buttons]
                }
            }
        }


# ─── Callback Router ───────────────────────────────────────────────────────────

CallbackHandler = Callable[[str, str, str], Any]  # (user_id, button_id, payload) -> str response


class CallbackRouter:
    """Router for handling button callback clicks."""

    _instance: Optional[CallbackRouter] = None

    def __init__(self) -> None:
        self._handlers: Dict[str, CallbackHandler] = {}
        self._routes: Dict[str, str] = {}  # button_id -> handler_name

    @classmethod
    def get_instance(cls) -> CallbackRouter:
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(
        self,
        handler_name: str,
        handler: CallbackHandler
    ) -> None:
        """Register a callback handler."""
        self._handlers[handler_name] = handler
        logger.info("callback_handler_registered", extra={"handler": handler_name})

    def route(self, button_id: str) -> Optional[str]:
        """Get handler name for a button ID."""
        return self._routes.get(button_id)

    def add_route(self, button_id: str, handler_name: str) -> None:
        """Map a button ID to a handler."""
        self._routes[button_id] = handler_name

    async def handle_callback(
        self,
        user_id: str,
        button_id: str,
        payload: Optional[str] = None
    ) -> Optional[str]:
        """Process a button callback click.

        Args:
            user_id: The user who clicked the button
            button_id: The button identifier
            payload: Optional additional data

        Returns:
            Response message to send back to user
        """
        handler_name = self.route(button_id)

        if not handler_name:
            logger.warning(
                "callback_no_handler",
                extra={"button_id": button_id, "user_id": user_id}
            )
            return None

        handler = self._handlers.get(handler_name)

        if not handler:
            logger.error(
                "callback_handler_missing",
                extra={"handler_name": handler_name, "button_id": button_id}
            )
            return None

        try:
            logger.info(
                "callback_handled",
                extra={
                    "button_id": button_id,
                    "handler": handler_name,
                    "user_id": user_id
                }
            )

            result = handler(user_id, button_id, payload)

            # Handle async handlers
            if hasattr(result, '__await__'):
                return await result

            return result

        except Exception as exc:
            logger.error(
                "callback_handler_error",
                extra={
                    "button_id": button_id,
                    "handler": handler_name,
                    "error": str(exc)
                }
            )
            return "Lo siento, hubo un error procesando tu selección. Por favor intenta de nuevo."


# ─── Button Builder Utilities ──────────────────────────────────────────────────

def generate_button_id(prefix: str, data: str) -> str:
    """Generate a unique, deterministic button ID.

    Args:
        prefix: Prefix for the button (e.g., 'faq', 'product', 'action')
        data: Unique data (e.g., 'tiqui_tiqui_info', 'product_123')

    Returns:
        A unique button ID like 'faq_tiqui_tiqui_info_a1b2c3d4'
    """
    hash_suffix = hashlib.md5(f"{data}".encode()).hexdigest()[:8]
    return f"{prefix}_{data}_{hash_suffix}"


def create_faq_buttons(faq_items: List[Dict[str, str]]) -> List[Button]:
    """Create buttons for FAQ items.

    Args:
        faq_items: List of dicts with 'id', 'title', 'category'

    Returns:
        List of Button objects
    """
    buttons = []

    for item in faq_items[:3]:  # Max 3 buttons
        button_id = generate_button_id("faq", item.get("id", item.get("title", "")))

        buttons.append(Button(
            id=button_id,
            title=item.get("title", "Ver más"),
            button_type=ButtonType.QUICK_REPLY,
            payload=item.get("category", item.get("id", ""))
        ))

    return buttons


def create_product_buttons(products: List[Dict[str, Any]]) -> List[Button]:
    """Create buttons for product options.

    Args:
        products: List of dicts with 'id', 'name', 'price'

    Returns:
        List of Button objects
    """
    buttons = []

    for product in products[:3]:
        button_id = generate_button_id("product", str(product.get("id", "")))

        title = product.get("name", "Ver producto")
        price = product.get("price")
        if price:
            title = f"{title} (${price:,.0f})"

        buttons.append(Button(
            id=button_id,
            title=title[:25],  # WhatsApp max title length
            button_type=ButtonType.QUICK_REPLY,
            payload=str(product.get("id", ""))
        ))

    return buttons


def create_action_buttons(actions: List[Dict[str, str]]) -> List[Button]:
    """Create buttons for action options.

    Args:
        actions: List of dicts with 'id', 'title', 'action'

    Returns:
        List of Button objects
    """
    buttons = []

    for action in actions[:3]:
        button_id = generate_button_id("action", action.get("id", ""))

        buttons.append(Button(
            id=button_id,
            title=action.get("title", "Acción")[:25],
            button_type=ButtonType.QUICK_REPLY,
            payload=action.get("action", action.get("id", ""))
        ))

    return buttons


# ─── RAG Button Integration ────────────────────────────────────────────────────

@dataclass
class RAGButtonSuggestion:
    """A suggested button generated from RAG context."""
    title: str
    payload: str
    relevance_score: float = 0.8


def generate_rag_buttons(
    query: str,
    context: str,
    max_buttons: int = 3
) -> List[Button]:
    """Generate interactive buttons based on RAG query and context.

    This function uses the RAG context to suggest relevant follow-up actions.

    Args:
        query: The original user query
        context: Retrieved context from vector store
        max_buttons: Maximum number of buttons to generate

    Returns:
        List of suggested buttons
    """
    suggestions = []

    # Common button patterns based on context analysis
    context_lower = context.lower()

    # Product-related buttons
    if any(word in context_lower for word in ['producto', 'venden', 'catalogo', 'precio']):
        suggestions.append(RAGButtonSuggestion(
            title="Ver catálogo completo",
            payload="catalog",
            relevance_score=0.9
        ))

    # Installation-related buttons
    if any(word in context_lower for word in ['instalacion', 'instalan', 'servicio']):
        suggestions.append(RAGButtonSuggestion(
            title="Solicitar instalación",
            payload="request_installation",
            relevance_score=0.85
        ))

    # Delivery-related buttons
    if any(word in context_lower for word in ['envio', 'despacho', 'region', 'comuna']):
        suggestions.append(RAGButtonSuggestion(
            title="Ver zonas de envío",
            payload="delivery_zones",
            relevance_score=0.8
        ))

    # Contact buttons
    if any(word in context_lower for word in ['contacto', 'hablar', 'humano', 'asesor']):
        suggestions.append(RAGButtonSuggestion(
            title="Hablar con asesor",
            payload="contact_human",
            relevance_score=0.95
        ))

    # Quote/request buttons
    if any(word in context_lower for word in ['presupuesto', 'cotizar', 'cantidad', 'metros']):
        suggestions.append(RAGButtonSuggestion(
            title="Solicitar presupuesto",
            payload="request_quote",
            relevance_score=0.9
        ))

    # Sort by relevance and take top N
    suggestions.sort(key=lambda x: x.relevance_score, reverse=True)
    suggestions = suggestions[:max_buttons]

    # Convert to Button objects
    buttons = []
    for i, suggestion in enumerate(suggestions):
        button_id = generate_button_id("rag", f"suggestion_{i}")

        buttons.append(Button(
            id=button_id,
            title=suggestion.title[:25],
            button_type=ButtonType.QUICK_REPLY,
            payload=suggestion.payload
        ))

        # Register the button route
        router = CallbackRouter.get_instance()
        router.add_route(button_id, "rag_suggestion")

    return buttons


# ─── Callback Handler Decorator ────────────────────────────────────────────────

def callback_handler(name: str) -> Callable:
    """Decorator to register a callback handler.

    Usage:
        @callback_handler("faq_handler")
        async def handle_faq(user_id: str, button_id: str, payload: str) -> str:
            return "FAQ response"
    """
    def decorator(func: CallbackHandler) -> CallbackHandler:
        router = CallbackRouter.get_instance()
        router.register(name, func)

        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    return decorator


# ─── Pre-defined Handler Implementations ──────────────────────────────────────

@callback_handler("rag_suggestion")
def handle_rag_suggestion(user_id: str, button_id: str, payload: str) -> str:
    """Handle RAG-generated suggestion buttons."""
    responses = {
        "catalog": "Aquí puedes ver nuestro catálogo completo: www.cubrejardin.cl",
        "request_installation": "Para solicitar instalación, indícame los metros cuadrados y te envío un presupuesto.",
        "delivery_zones": "Realizamos envíos en Santiago y Concón. Para otras zonas, podemos enviar a un contacto en Santiago.",
        "contact_human": "Te conecto con un asesor humano. Un momento por favor...",
        "request_quote": "Para cotizar, indícame: 1) Producto(s) 2) Metros cuadrados 3) Comuna de entrega",
    }

    return responses.get(payload, "Gracias por tu interés. ¿Hay algo más en lo que pueda ayudarte?")


@callback_handler("faq_category")
def handle_faq_category(user_id: str, button_id: str, payload: str) -> str:
    """Handle FAQ category selection buttons."""
    category_responses = {
        "tiqui_tiqui": "🌱 Tiqui Tiqui es una planta rastrera ideal para cubrir áreas. Cuesta $690/planta y se plantan 10 por m².",
        "delivery": "🚚 Realizamos envíos en Santiago y zonas cercanas. El despacho mínimo es $8.000.",
        "installation": "🔧 Sí, hacemos instalación sobre 30m². Incluye riego y plantas.",
        "payment": "💳 Puedes pagar con transferencia o efectivo contra entrega.",
        "products": "🌿 Visitanos en www.cubrejardin.cl para ver todo nuestro catálogo.",
    }

    return category_responses.get(payload, "Gracias por tu selección. ¿En qué más puedo ayudarte?")
