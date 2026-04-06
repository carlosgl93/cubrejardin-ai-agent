"""Vector store service using simple cosine similarity."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import settings
from utils import logger


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


class VectorStoreService:
    """Manage vector store operations.

    When ``tenant_id`` is provided, searches are delegated to the Supabase
    ``match_documents`` RPC function instead of the local JSON file store.
    """

    def __init__(self, index_path: str | None = None, *, tenant_id: Optional[str] = None) -> None:
        self.tenant_id = tenant_id
        if tenant_id:
            # Supabase-backed — no local file needed
            self.vectors: List[List[float]] = []
            self.metadata: List[Dict[str, Any]] = []
            return
        self.index_path = index_path or settings.vector_store_path
        self.metadata_path = f"{self.index_path}.meta.json"
        self.vectors = []
        self.metadata = []
        self._load()

    def _load(self) -> None:
        """Load index from disk if exists."""

        path = Path(self.index_path)
        if path.exists():
            with open(path, "r", encoding="utf-8") as file:
                self.vectors = json.load(file)
            logger.info("vector_store_loaded", extra={"path": self.index_path})
        else:
            logger.info("vector_store_created", extra={"path": self.index_path})
        if Path(self.metadata_path).exists():
            with open(self.metadata_path, "r", encoding="utf-8") as file:
                self.metadata = json.load(file)

    def _persist(self) -> None:
        """Persist index and metadata."""

        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
        with open(self.index_path, "w", encoding="utf-8") as file:
            json.dump(self.vectors, file, ensure_ascii=False)
        with open(self.metadata_path, "w", encoding="utf-8") as file:
            json.dump(self.metadata, file, ensure_ascii=False, indent=2)

    def add_embeddings(self, embeddings: List[List[float]], metadatas: List[Dict[str, Any]]) -> None:
        """Add vectors to index."""

        self.vectors.extend(embeddings)
        self.metadata.extend(metadatas)
        self._persist()

    def search(self, embedding: List[float], top_k: int = 5) -> List[Tuple[float, Dict[str, Any]]]:
        """Search for similar documents.

        Delegates to Supabase ``match_documents`` when a ``tenant_id`` is set,
        otherwise falls back to the local cosine-similarity search.
        """

        if self.tenant_id:
            return self._search_supabase(embedding, top_k)

        scores = [
            (cosine_similarity(embedding, vector), metadata)
            for vector, metadata in zip(self.vectors, self.metadata)
        ]
        scores.sort(key=lambda item: item[0], reverse=True)
        return scores[:top_k]

    def _search_supabase(self, embedding: List[float], top_k: int) -> List[Tuple[float, Dict[str, Any]]]:
        """Search tenant documents via Supabase pgvector."""

        from config.supabase import get_supabase_client

        sb = get_supabase_client()
        result = sb.rpc(
            "match_documents",
            {
                "query_embedding": embedding,
                "match_count": top_k,
                "p_tenant_id": self.tenant_id,
            },
        ).execute()

        return [
            (
                row["similarity"],
                {"title": row["title"], "content": row["content"]},
            )
            for row in (result.data or [])
        ]

    def rebuild(self, embeddings: List[List[float]], metadatas: List[Dict[str, Any]]) -> None:
        """Rebuild index with provided data."""

        self.vectors = embeddings[:]
        self.metadata = metadatas[:]
        self._persist()
