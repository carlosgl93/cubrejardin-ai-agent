"""Incremental learning pipeline service."""

from __future__ import annotations

from typing import List

from models.database import InMemorySession, KnowledgeBaseDocument, LearningQueueEntry
from utils import logger


class LearningService:
    """Handle learning queue lifecycle."""

    def __init__(self, session: InMemorySession) -> None:
        self.session = session

    def queue_example(self, question: str, answer: str, metadata: dict) -> LearningQueueEntry:
        """Add new example to learning queue."""

        entry = LearningQueueEntry(question=question, answer=answer, metadata=metadata)
        self.session.add(entry)
        self.session.commit()
        logger.info("learning_queued", extra={"id": entry.id})
        return entry

    def approve_examples(self, entry_ids: List[int]) -> List[KnowledgeBaseDocument]:
        """Approve learning entries and add to knowledge base."""

        docs: List[KnowledgeBaseDocument] = []
        for entry_id in entry_ids:
            entry = self.session.get(LearningQueueEntry, entry_id)
            if not entry:
                continue
            document = KnowledgeBaseDocument(
                title=entry.metadata.get("title", f"Entry {entry_id}"),
                content=entry.answer,
                metadata=entry.metadata,
            )
            self.session.add(document)
            self.session.delete(entry)
            docs.append(document)
        self.session.commit()
        logger.info("learning_approved", extra={"count": len(docs)})
        return docs

    def reject_examples(self, entry_ids: List[int]) -> None:
        """Reject learning entries."""

        for entry_id in entry_ids:
            entry = self.session.get(LearningQueueEntry, entry_id)
            if entry:
                self.session.delete(entry)
        self.session.commit()
        logger.info("learning_rejected", extra={"count": len(entry_ids)})
