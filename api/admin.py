"""Administrative endpoints."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

from agents.handoff_agent import HandoffAgent
from api.dependencies import (
    get_db,
    get_openai_service,
    get_vector_store,
    get_whatsapp_service,
)
from models.database import Conversation, InMemorySession, KnowledgeBaseDocument, LearningQueueEntry
from services.learning_service import LearningService
from services.openai_service import OpenAIService
from services.vector_store import VectorStoreService
from services.whatsapp_service import WhatsAppService

router = APIRouter()


@router.get("/health")
def healthcheck() -> dict:
    """Return service health."""
    return {"status": "ok"}


@router.post("/knowledge-base")
def add_document(
    title: str,
    content: str,
    metadata: dict | None = None,
    db: InMemorySession = Depends(get_db),
    vector_store: VectorStoreService = Depends(get_vector_store),
    openai_service: OpenAIService = Depends(get_openai_service),
) -> dict:
    """Add document to knowledge base."""

    document = KnowledgeBaseDocument(title=title, content=content, metadata=metadata or {})
    db.add(document)
    db.commit()
    embedding_response = openai_service.embed(input_texts=[content])
    embedding = embedding_response["data"][0]["embedding"]
    vector_store.add_embeddings([embedding], [{"title": title, "content": content, "id": document.id}])
    return {"id": document.id}


@router.post("/handoff/to-human")
def handoff_to_human(
    conversation_id: int,
    db: InMemorySession = Depends(get_db),
    whatsapp_service: WhatsAppService = Depends(get_whatsapp_service),
    openai_service: OpenAIService = Depends(get_openai_service),
) -> dict:
    """Force a handoff to human agents via admin panel."""

    conversation = db.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    agent = HandoffAgent(
        openai_service=openai_service,
        whatsapp_service=whatsapp_service,
        session=db,
    )
    escalation = agent.pass_control_to_human(conversation=conversation, metadata={"trigger": "admin_manual"})
    return {"escalation_id": escalation.id}


@router.post("/handoff/to-bot")
def handoff_to_bot(
    conversation_id: int,
    db: InMemorySession = Depends(get_db),
    whatsapp_service: WhatsAppService = Depends(get_whatsapp_service),
    openai_service: OpenAIService = Depends(get_openai_service),
) -> dict:
    """Return control of the thread to the bot."""

    conversation = db.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    agent = HandoffAgent(
        openai_service=openai_service,
        whatsapp_service=whatsapp_service,
        session=db,
    )
    agent.take_control_back(conversation=conversation, metadata={"trigger": "admin_manual"})
    return {"status": "ok"}


@router.get("/learning-queue")
def list_learning_queue(db: InMemorySession = Depends(get_db)) -> List[dict]:
    """List learning queue entries."""

    service = LearningService(db)
    entries = service.list_queue()
    return [
        {
            "id": entry.id,
            "conversation_id": entry.conversation_id,
            "user_message": entry.user_message,
            "human_answer": entry.human_answer,
            "validated": entry.validated,
            "metadata": entry.metadata,
        }
        for entry in entries
    ]


@router.post("/learning/{entry_id}/validate")
def validate_learning_entry(
    entry_id: int,
    db: InMemorySession = Depends(get_db),
    openai_service: OpenAIService = Depends(get_openai_service),
    vector_store: VectorStoreService = Depends(get_vector_store),
) -> dict:
    """Validate and ingest a human-provided learning entry."""

    service = LearningService(db)
    entry = service.validate_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Learning entry not found")
    ingested = service.ingest_validated_learning(
        openai_service=openai_service,
        vector_store=vector_store,
        entry_ids=[entry_id],
    )
    return {"ingested": ingested}