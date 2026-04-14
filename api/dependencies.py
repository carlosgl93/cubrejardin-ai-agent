"""Dependency injection for FastAPI routes."""

from __future__ import annotations

from typing import Any, AsyncGenerator, Generator, Optional

from fastapi import Depends

from agents.orchestrator import AgentOrchestrator
from models.database import SessionLocal
from services.openai_service import OpenAIService
from services.vector_store import VectorStoreService
from services.whatsapp_service import WhatsAppService
from services.facebook_messenger_service import FacebookMessengerService
from services.template_service import TemplateService


def get_db() -> Generator:
    """Provide database session."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_openai_service() -> OpenAIService:
    """Provide OpenAI service singleton."""

    return OpenAIService()


def get_vector_store() -> VectorStoreService:
    """Provide vector store service."""

    return VectorStoreService()


async def get_whatsapp_service() -> AsyncGenerator[WhatsAppService, None]:
    """Provide WhatsApp service and ensure cleanup."""

    service = WhatsAppService()
    try:
        yield service
    finally:
        await service.close()


async def get_facebook_messenger_service() -> AsyncGenerator[FacebookMessengerService, None]:
    """Provide Facebook Messenger service and ensure cleanup."""

    service = FacebookMessengerService()
    try:
        yield service
    finally:
        await service.close()


def build_orchestrator(
    *,
    db: Any,
    openai_service: OpenAIService,
    vector_store: VectorStoreService,
    messaging_service: Any,
    template_service: Optional[TemplateService] = None,
    tenant_id: Optional[str] = None,
) -> AgentOrchestrator:
    """Build an orchestrator for the provided transport and tenant context."""

    if getattr(vector_store, "backend", None) == "pgvector" and not tenant_id:
        raise ValueError("tenant_id is required when building an orchestrator with pgvector")

    return AgentOrchestrator(
        session=db,
        openai_service=openai_service,
        vector_store=vector_store,
        whatsapp_service=messaging_service,
        template_service=template_service or TemplateService(whatsapp_service=messaging_service),
        tenant_id=tenant_id,
    )


def get_orchestrator(
    db=Depends(get_db),
    openai_service: OpenAIService = Depends(get_openai_service),
    vector_store: VectorStoreService = Depends(get_vector_store),
    whatsapp_service: WhatsAppService = Depends(get_whatsapp_service),
) -> AgentOrchestrator:
    """Provide the default orchestrator instance for local/test routes.

    Production pgvector flows must supply an explicit tenant-aware vector store.
    """

    return build_orchestrator(
        db=db,
        openai_service=openai_service,
        vector_store=vector_store,
        messaging_service=whatsapp_service,
        tenant_id=getattr(vector_store, "tenant_id", None),
    )
