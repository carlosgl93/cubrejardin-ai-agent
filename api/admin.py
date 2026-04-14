"""Administrative endpoints."""

from __future__ import annotations

from typing import List

from sqlalchemy import desc, select

from fastapi import APIRouter, Depends, HTTPException

from agents.handoff_agent import HandoffAgent
from api.dependencies import (
    get_db,
    get_openai_service,
    get_whatsapp_service,
)
from api.tenant_context import TenantContext, get_tenant_context
from models.database import AuditLog, Conversation, DatabaseSession, Escalation, LearningQueueEntry
from services.audit_service import record_audit_event
from services.document_ingestion import ingest_document
from services.learning_service import LearningService
from services.openai_service import OpenAIService
from services.vector_store import VectorStoreService
from services.whatsapp_service import WhatsAppService

router = APIRouter()
_PRIVILEGED_ROLES = {"owner", "admin"}


def _require_privileged_role(ctx: TenantContext) -> None:
    """Require a tenant role that can operate the admin surface."""

    if ctx.role not in _PRIVILEGED_ROLES:
        raise HTTPException(status_code=403, detail="Admin access requires owner or admin role")


def _bounded_limit(limit: int) -> int:
    """Clamp list limits to a sane range."""

    return max(1, min(limit, 200))


@router.get("/health")
def healthcheck() -> dict:
    """Return service health."""
    return {"status": "ok"}


@router.post("/knowledge-base")
def add_document(
    title: str,
    content: str,
    metadata: dict | None = None,
    ctx: TenantContext = Depends(get_tenant_context),
    openai_service: OpenAIService = Depends(get_openai_service),
) -> dict:
    """Add document to knowledge base."""

    _require_privileged_role(ctx)

    vector_store = VectorStoreService(tenant_id=ctx.tenant_id)
    result = ingest_document(
        tenant_id=ctx.tenant_id,
        title=title,
        content=content,
        file_type="text",
        metadata=metadata,
        openai_service=openai_service,
        vector_store=vector_store,
    )
    record_audit_event(
        tenant_id=ctx.tenant_id,
        event_type="knowledge_base_document_added",
        entity_type="document",
        entity_id=result["ids"][0] if result["ids"] else None,
        payload={"title": result["title"], "chunks": result["chunks"]},
    )
    return result


@router.get("/conversations")
def list_conversations(
    *,
    limit: int = 50,
    user_number: str | None = None,
    role: str | None = None,
    db: DatabaseSession = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
) -> List[dict]:
    """List tenant-scoped conversation history for admin review."""

    _require_privileged_role(ctx)
    statement = (
        select(Conversation)
        .where(Conversation.tenant_id == ctx.tenant_id)
        .order_by(desc(Conversation.created_at), desc(Conversation.id))
        .limit(_bounded_limit(limit))
    )
    if user_number:
        statement = statement.where(Conversation.user_number == user_number)
    if role:
        statement = statement.where(Conversation.role == role)

    entries = list(db.scalars(statement))
    return [
        {
            "id": entry.id,
            "user_number": entry.user_number,
            "role": entry.role,
            "message": entry.message,
            "message_id": entry.message_id,
            "metadata": entry.payload,
            "last_interaction_at": entry.last_interaction_at,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }
        for entry in entries
    ]


@router.get("/escalations")
def list_escalations(
    *,
    limit: int = 50,
    status: str | None = None,
    db: DatabaseSession = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
) -> List[dict]:
    """List tenant escalations for the admin surface."""

    _require_privileged_role(ctx)
    statement = (
        select(Escalation)
        .where(Escalation.tenant_id == ctx.tenant_id)
        .order_by(desc(Escalation.created_at), desc(Escalation.id))
        .limit(_bounded_limit(limit))
    )
    if status:
        statement = statement.where(Escalation.status == status)

    entries = list(db.scalars(statement))
    return [
        {
            "id": entry.id,
            "conversation_id": entry.conversation_id,
            "status": entry.status,
            "handoff_type": entry.handoff_type,
            "metadata": entry.payload,
            "notes": entry.notes,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }
        for entry in entries
    ]


@router.get("/audit-logs")
def list_audit_logs(
    *,
    limit: int = 50,
    event_type: str | None = None,
    db: DatabaseSession = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
) -> List[dict]:
    """List tenant audit events stored in the operational database."""

    _require_privileged_role(ctx)
    statement = (
        select(AuditLog)
        .where(AuditLog.tenant_id == ctx.tenant_id)
        .order_by(desc(AuditLog.created_at), desc(AuditLog.id))
        .limit(_bounded_limit(limit))
    )
    if event_type:
        statement = statement.where(AuditLog.event_type == event_type)

    entries = list(db.scalars(statement))
    return [
        {
            "id": entry.id,
            "event_type": entry.event_type,
            "entity_type": entry.entity_type,
            "entity_id": entry.entity_id,
            "payload": entry.payload,
            "created_at": entry.created_at,
        }
        for entry in entries
    ]


@router.post("/handoff/to-human")
async def handoff_to_human(
    conversation_id: int,
    db: DatabaseSession = Depends(get_db),
    whatsapp_service: WhatsAppService = Depends(get_whatsapp_service),
    openai_service: OpenAIService = Depends(get_openai_service),
    ctx: TenantContext = Depends(get_tenant_context),
) -> dict:
    """Force a handoff to human agents via admin panel."""

    _require_privileged_role(ctx)
    statement = (
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .where(Conversation.tenant_id == ctx.tenant_id)
        .limit(1)
    )
    conversation = db.scalar(statement)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    agent = HandoffAgent(
        openai_service=openai_service,
        whatsapp_service=whatsapp_service,
        session=db,
    )
    escalation = await agent.pass_control_to_human(conversation=conversation, metadata={"trigger": "admin_manual"})
    return {"escalation_id": escalation.id}


@router.post("/handoff/to-bot")
async def handoff_to_bot(
    conversation_id: int,
    db: DatabaseSession = Depends(get_db),
    whatsapp_service: WhatsAppService = Depends(get_whatsapp_service),
    openai_service: OpenAIService = Depends(get_openai_service),
    ctx: TenantContext = Depends(get_tenant_context),
) -> dict:
    """Return control of the thread to the bot."""

    _require_privileged_role(ctx)
    statement = (
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .where(Conversation.tenant_id == ctx.tenant_id)
        .limit(1)
    )
    conversation = db.scalar(statement)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    agent = HandoffAgent(
        openai_service=openai_service,
        whatsapp_service=whatsapp_service,
        session=db,
    )
    await agent.take_control_back(conversation=conversation, metadata={"trigger": "admin_manual"})
    return {"status": "ok"}


@router.get("/learning-queue")
def list_learning_queue(
    *,
    limit: int = 100,
    include_ingested: bool = False,
    db: DatabaseSession = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
) -> List[dict]:
    """List learning queue entries."""

    _require_privileged_role(ctx)
    statement = (
        select(LearningQueueEntry)
        .where(LearningQueueEntry.tenant_id == ctx.tenant_id)
        .order_by(desc(LearningQueueEntry.created_at), desc(LearningQueueEntry.id))
        .limit(_bounded_limit(limit))
    )
    if not include_ingested:
        statement = statement.where(LearningQueueEntry.ingested_at.is_(None))

    entries = list(db.scalars(statement))
    return [
        {
            "id": entry.id,
            "conversation_id": entry.conversation_id,
            "user_message": entry.user_message,
            "human_answer": entry.human_answer,
            "validated": entry.validated,
            "validated_at": entry.validated_at,
            "ingested_at": entry.ingested_at,
            "metadata": entry.payload,
        }
        for entry in entries
    ]


@router.post("/learning/{entry_id}/validate")
def validate_learning_entry(
    entry_id: int,
    db: DatabaseSession = Depends(get_db),
    openai_service: OpenAIService = Depends(get_openai_service),
    ctx: TenantContext = Depends(get_tenant_context),
) -> dict:
    """Validate and ingest a human-provided learning entry."""

    _require_privileged_role(ctx)
    service = LearningService(db)
    entry = db.get(LearningQueueEntry, entry_id)
    if not entry or entry.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="Learning entry not found")
    entry = service.validate_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Learning entry not found")
    vector_store = VectorStoreService(tenant_id=entry.tenant_id)
    ingested = service.ingest_validated_learning(
        openai_service=openai_service,
        vector_store=vector_store,
        entry_ids=[entry_id],
    )
    return {"ingested": ingested}
