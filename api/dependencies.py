"""Dependency injection for FastAPI routes."""

from __future__ import annotations

from typing import AsyncGenerator, Generator

from fastapi import Depends

from agents.orchestrator import AgentOrchestrator
from models.database import SessionLocal
from services.openai_service import OpenAIService
from services.vector_store import VectorStoreService
from services.whatsapp_service import WhatsAppService
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


def get_orchestrator(
    db=Depends(get_db),
    openai_service: OpenAIService = Depends(get_openai_service),
    vector_store: VectorStoreService = Depends(get_vector_store),
    whatsapp_service: WhatsAppService = Depends(get_whatsapp_service),
) -> AgentOrchestrator:
    """Provide orchestrator instance."""

    return AgentOrchestrator(
        session=db,
        openai_service=openai_service,
        vector_store=vector_store,
        whatsapp_service=whatsapp_service,
        template_service=TemplateService(whatsapp_service=whatsapp_service),
    )
