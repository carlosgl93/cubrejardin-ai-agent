"""Incremental learning pipeline service."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from models.database import InMemorySession, KnowledgeBaseDocument, LearningQueueEntry
from services.openai_service import OpenAIService
from services.vector_store import VectorStoreService
from utils import logger


class LearningService:
    """Handle learning queue lifecycle."""

    def __init__(self, session: InMemorySession) -> None:
        self.session = session

    def queue_human_response(
        self,
        *,
        conversation_id: int,
        user_message: str,
        human_answer: str,
        metadata: Optional[Dict[str, Any]] = None,
        source: str = "human_handoff",
    ) -> LearningQueueEntry:
        """Store a human-provided answer for later validation."""

        entry = LearningQueueEntry(
            question=user_message,
            answer=human_answer,
            metadata=metadata or {},
        )
        # extra attributes for traceability
        entry.metadata.update(
            {
                "conversation_id": conversation_id,
                "source": source,
            }
        )
        self.session.add(entry)
        self.session.commit()
        logger.info(
            "learning_queue_human_response",
            extra={"conversation_id": conversation_id, "entry_id": entry.id},
        )
        return entry

    def list_queue(self) -> List[LearningQueueEntry]:
        """Return current queue entries."""

        return self.session.query(LearningQueueEntry)

    def validate_entry(self, entry_id: int) -> Optional[LearningQueueEntry]:
        """Mark a queue entry as validated."""

        entry = self.session.get(LearningQueueEntry, entry_id)
        if not entry:
            return None
        entry.metadata["validated"] = True
        self.session.commit()
        logger.info("learning_entry_validated", extra={"entry_id": entry_id})
        return entry

    def ingest_validated_learning(
        self,
        *,
        openai_service: OpenAIService,
        vector_store: VectorStoreService,
        entry_ids: Optional[List[int]] = None,
    ) -> int:
        """Embed validated queue entries and push them into the vector store."""

        entries = [
            entry
            for entry in self.session.query(LearningQueueEntry)
            if entry.metadata.get("validated") and (entry_ids is None or entry.id in entry_ids)
        ]
        if not entries:
            logger.info("learning_no_validated_entries", extra={"entry_ids": entry_ids or []})
            return 0

        metadatas: List[Dict[str, Any]] = []
        embeddings: List[List[float]] = []
        for entry in entries:
            response = openai_service.embed(input_texts=[entry.question])
            embedding = response["data"][0]["embedding"]
            embeddings.append(embedding)
            metadatas.append(
                {
                    "id": f"learning-{entry.id}",
                    "conversation_id": entry.metadata.get("conversation_id"),
                    "title": entry.metadata.get("title", "Aprendizaje validado"),
                    "content": entry.answer,
                    "question": entry.question,
                    "source": entry.metadata.get("source", "human_handoff"),
                }
            )

        vector_store.add_embeddings(embeddings, metadatas)

        # Opcional: convertir entradas validadas en documentos de KB
        for entry in entries:
            document = KnowledgeBaseDocument(
                title=entry.metadata.get("title", f"Entry {entry.id}"),
                content=entry.answer,
                metadata=entry.metadata,
            )
            self.session.add(document)
            self.session.delete(entry)

        self.session.commit()
        logger.info("learning_entries_ingested", extra={"count": len(entries)})
        return len(entries)

    def reject_examples(self, entry_ids: List[int]) -> None:
        """Reject learning entries."""

        for entry_id in entry_ids:
            entry = self.session.get(LearningQueueEntry, entry_id)
            if entry:
                self.session.delete(entry)
        self.session.commit()
        logger.info("learning_rejected", extra={"count": len(entry_ids)})
