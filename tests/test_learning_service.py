"""Tests for learning ingestion into the shared documents table contract."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Type
from dataclasses import dataclass, field
from datetime import datetime, timezone

from models.database import BaseModel


# Create a SQLAlchemy-compatible mock session
class MockSession:
    """A mock session that supports both dataclass-style and SQLAlchemy-style queries."""

    def __init__(self, storage_type: Type[BaseModel] = None) -> None:
        self.storage: Dict[Type[BaseModel], List[BaseModel]] = {}
        self.counters: Dict[Type[BaseModel], int] = {}
        self._storage_type = storage_type
        self._entries: List[BaseModel] = []  # Direct list for simple queries
        self._next_id = 1

    def add(self, instance: BaseModel) -> None:
        instance.assign_id(self._next_id)
        self._next_id += 1
        self._entries.append(instance)

    def commit(self) -> None:
        pass

    def refresh(self, instance: BaseModel) -> None:
        pass

    def delete(self, instance: BaseModel) -> None:
        if instance in self._entries:
            self._entries.remove(instance)

    def get(self, model: Type[BaseModel], identifier: int) -> Optional[BaseModel]:
        for item in self._entries:
            if hasattr(item, 'id') and item.id == identifier:
                return item
        return None

    def query(self, model: Type[BaseModel]) -> List[BaseModel]:
        """Return all entries of the given model type."""
        return [e for e in self._entries if isinstance(e, model)]

    def scalars(self, statement: Any) -> List[BaseModel]:
        """Execute a select statement and return results."""
        # For this simple mock, just return all entries
        return self._entries

    def close(self) -> None:
        pass


class DummyOpenAIService:
    """Return deterministic embeddings."""

    def embed(self, *, input_texts):  # type: ignore[Override]
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

    # Import the actual LearningQueueEntry from models.database
    from models.database import LearningQueueEntry

    # Create mock session
    session = MockSession()

    # Create a learning queue entry using the real class
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

    # Use the actual LearningService with our mock session
    from services.learning_service import LearningService

    service = LearningService(session)
    vector_store = RecordingVectorStore()

    ingested = service.ingest_validated_learning(
        openai_service=DummyOpenAIService(),
        vector_store=vector_store,
        entry_ids=[entry.id],
    )

    assert ingested == 1
    # After deletion, query should return empty list
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
