"""Incremental learning pipeline service."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from models.database import DatabaseSession, LearningQueueEntry
from services.audit_service import record_audit_event
from services.openai_service import OpenAIService
from services.vector_store import VectorStoreService
from utils import logger


class LearningService:
    """Handle learning queue lifecycle."""

    def __init__(self, session: DatabaseSession) -> None:
        self.session = session

    def queue_human_response(
        self,
        *,
        tenant_id: Optional[str],
        conversation_id: int,
        user_message: str,
        human_answer: str,
        metadata: Optional[Dict[str, Any]] = None,
        source: str = "human_handoff",
    ) -> LearningQueueEntry:
        """Store a human-provided answer for later validation."""

        entry = LearningQueueEntry(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            user_message=user_message,
            human_answer=human_answer,
            validated=False,
            payload=metadata or {},
        )
        # extra attributes for traceability
        entry.payload.update(
            {
                "conversation_id": conversation_id,
                "source": source,
            }
        )
        self.session.add(entry)
        self.session.commit()
        self.session.refresh(entry)
        logger.info(
            "learning_queue_human_response",
            extra={"conversation_id": conversation_id, "entry_id": entry.id},
        )
        record_audit_event(
            tenant_id=tenant_id,
            event_type="learning_queued",
            entity_type="learning_queue_entry",
            entity_id=str(entry.id),
            payload={"conversation_id": conversation_id, "source": source},
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
        entry.validated = True
        self.session.commit()
        logger.info("learning_entry_validated", extra={"entry_id": entry_id})
        record_audit_event(
            tenant_id=entry.tenant_id,
            event_type="learning_validated",
            entity_type="learning_queue_entry",
            entity_id=str(entry.id),
            payload={"conversation_id": entry.conversation_id},
        )
        return entry

    def ingest_validated_learning(
        self,
        *,
        openai_service: OpenAIService,
        vector_store: VectorStoreService,
        entry_ids: Optional[List[int]] = None,
    ) -> int:
        """Embed validated queue entries and push them into the vector store."""

        # Get all validated entries
        all_entries = self.session.query(LearningQueueEntry)

        # Filter by validated status and optionally by IDs
        entries = [
            e for e in all_entries
            if e.validated and (entry_ids is None or e.id in entry_ids)
        ]

        if not entries:
            logger.info("learning_no_validated_entries", extra={"entry_ids": entry_ids or []})
            return 0

        metadatas: List[Dict[str, Any]] = []
        embeddings: List[List[float]] = []
        for entry in entries:
            source_title = entry.payload.get("source_title", f"learning-entry-{entry.id}")
            content = (
                f"Pregunta del cliente: {entry.user_message}\n"
                f"Respuesta validada: {entry.human_answer}"
            )
            response = openai_service.embed(input_texts=[content])
            embedding = response["data"][0]["embedding"]
            embeddings.append(embedding)
            vector_store.delete_documents_by_source_title(source_title, tenant_id=entry.tenant_id)
            metadatas.append(
                {
                    "tenant_id": entry.tenant_id,
                    "title": entry.payload.get("title", f"Aprendizaje validado #{entry.id}"),
                    "content": content,
                    "file_type": "learning",
                    "metadata": {
                        **dict(entry.payload),
                        "learning_entry_id": entry.id,
                        "conversation_id": entry.conversation_id,
                        "question": entry.user_message,
                        "answer": entry.human_answer,
                        "source": entry.payload.get("source", "human_handoff"),
                        "source_title": source_title,
                    },
                }
            )

        vector_store.add_embeddings(embeddings, metadatas)

        for entry in entries:
            self.session.delete(entry)

        self.session.commit()
        logger.info("learning_entries_ingested", extra={"count": len(entries)})
        for entry in entries:
            record_audit_event(
                tenant_id=entry.tenant_id,
                event_type="learning_ingested",
                entity_type="learning_queue_entry",
                entity_id=str(entry.id),
                payload={"conversation_id": entry.conversation_id},
            )
        return len(entries)

    def reject_examples(self, entry_ids: List[int]) -> None:
        """Reject learning entries."""

        for entry_id in entry_ids:
            entry = self.session.get(LearningQueueEntry, entry_id)
            if entry:
                tenant_id = entry.tenant_id
                self.session.delete(entry)
                record_audit_event(
                    tenant_id=tenant_id,
                    event_type="learning_rejected",
                    entity_type="learning_queue_entry",
                    entity_id=str(entry_id),
                    payload={},
                )
        self.session.commit()
        logger.info("learning_rejected", extra={"count": len(entry_ids)})
