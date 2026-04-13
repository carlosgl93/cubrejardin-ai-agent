"""Tests for learning ingestion into the shared documents table contract."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from models.database import LearningQueueEntry, SessionLocal
from services.learning_service import LearningService


class DummyOpenAIService:
    """Return deterministic embeddings."""

    def embed(self, *, input_texts):  # type: ignore[override]
        value = float(len(input_texts[0])) if input_texts else 0.0
        return {"data": [{"embedding": [value]}]}


class RecordingVectorStore:
    """Capture delete/insert calls made by the learning service."""

    def __init__(self) -> None:
        self.deleted: List[tuple[Optional[str], str]] = []
        self.add_calls: List[Dict[str, Any]] = []

    def delete_documents_by_source_title(self, source_title: str, *, tenant_id: Optional[str] = None) -> int:
        self.deleted.append((tenant_id, source_title))
        return 0

    def add_embeddings(self, embeddings: List[List[float]], metadatas: List[Dict[str, Any]]) -> List[str]:
        self.add_calls.append({"embeddings": embeddings, "metadatas": metadatas})
        return [f"doc-{index}" for index, _ in enumerate(metadatas, start=1)]


def test_learning_service_ingests_validated_entries_into_documents() -> None:
    """Validated learning rows should be converted into tenant-aware document payloads."""

    session = SessionLocal()
    entry = LearningQueueEntry(
        tenant_id="tenant-a",
        conversation_id=123,
        user_message="Necesito saber la garantia",
        human_answer="La garantia es de 12 meses",
        validated=True,
        payload={"title": "Garantia", "source": "human_handoff"},
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)

    service = LearningService(session)
    vector_store = RecordingVectorStore()
    ingested = service.ingest_validated_learning(
        openai_service=DummyOpenAIService(),
        vector_store=vector_store,  # type: ignore[arg-type]
        entry_ids=[entry.id],
    )

    assert ingested == 1
    assert session.query(LearningQueueEntry) == []
    assert vector_store.deleted == [("tenant-a", f"learning-entry-{entry.id}")]

    call = vector_store.add_calls[0]
    metadata = call["metadatas"][0]
    assert metadata["tenant_id"] == "tenant-a"
    assert metadata["title"] == "Garantia"
    assert metadata["file_type"] == "learning"
    assert "Pregunta del cliente:" in metadata["content"]
    assert "Respuesta validada: La garantia es de 12 meses" in metadata["content"]
    assert metadata["metadata"]["learning_entry_id"] == entry.id
    assert metadata["metadata"]["question"] == "Necesito saber la garantia"

    session.close()
