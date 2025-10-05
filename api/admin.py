"""Administrative endpoints."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends

from api.dependencies import get_db, get_openai_service, get_vector_store
from models.database import InMemorySession, KnowledgeBaseDocument, LearningQueueEntry
from services.learning_service import LearningService
from services.openai_service import OpenAIService
from services.vector_store import VectorStoreService

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


@router.get("/learning-queue")
def list_learning_queue(db: InMemorySession = Depends(get_db)) -> List[dict]:
    """List learning queue entries."""

    entries = db.query(LearningQueueEntry)
    return [
        {
            "id": entry.id,
            "question": entry.question,
            "answer": entry.answer,
            "metadata": entry.metadata,
        }
        for entry in entries
    ]


@router.post("/learning-queue/approve")
def approve_learning(entries: List[int], db: InMemorySession = Depends(get_db)) -> dict:
    """Approve learning entries."""

    service = LearningService(db)
    documents = service.approve_examples(entries)
    return {"approved": len(documents)}


@router.post("/learning-queue/reject")
def reject_learning(entries: List[int], db: InMemorySession = Depends(get_db)) -> dict:
    """Reject learning entries."""

    service = LearningService(db)
    service.reject_examples(entries)
    return {"rejected": len(entries)}
