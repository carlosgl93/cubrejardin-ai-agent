"""Services module."""

from .openai_service import OpenAIService
from .vector_store import VectorStoreService
from .whatsapp_service import WhatsAppService
from .template_service import TemplateService
from .telegram_service import TelegramService
from .tenant_config_service import get_tenant_bot_config, TenantBotConfig
from .document_ingestion import (
    chunk_text,
    _split_markdown_sections,
    chunk_document_content,
    ingest_document,
)
from .audit_service import record_audit_event
from .learning_service import LearningService
from .mercadofiel_service import MercadoFielService

# New high-priority backlog implementations
from .message_queue import MessageQueueService, MessageProcessor, QueuedMessage, MessagePriority
from .telemetry import TelemetryManager, TelemetryConfig, traced, traced_span, get_telemetry, setup_fastapi_instrumentation, SpanAttributes
from .interactive_service import (
    InteractiveMessage,
    Button,
    ButtonType,
    CallbackRouter,
    CallbackHandler,
    generate_button_id,
    create_faq_buttons,
    create_product_buttons,
    create_action_buttons,
    generate_rag_buttons,
    callback_handler,
    handle_rag_suggestion,
    handle_faq_category,
)

__all__ = [
    # Original services
    "OpenAIService",
    "VectorStoreService",
    "WhatsAppService",
    "TemplateService",
    "TelegramService",
    "get_tenant_bot_config",
    "TenantBotConfig",
    "chunk_text",
    "_split_markdown_sections",
    "chunk_document_content",
    "ingest_document",
    "record_audit_event",
    "LearningService",
    "MercadoFielService",

    # Message Queue (Redis)
    "MessageQueueService",
    "MessageProcessor",
    "QueuedMessage",
    "MessagePriority",

    # OpenTelemetry
    "TelemetryManager",
    "TelemetryConfig",
    "traced",
    "traced_span",
    "get_telemetry",
    "setup_fastapi_instrumentation",
    "SpanAttributes",

    # Interactive Buttons
    "InteractiveMessage",
    "Button",
    "ButtonType",
    "CallbackRouter",
    "CallbackHandler",
    "generate_button_id",
    "create_faq_buttons",
    "create_product_buttons",
    "create_action_buttons",
    "generate_rag_buttons",
    "callback_handler",
    "handle_rag_suggestion",
    "handle_faq_category",
]
