"""Vector store service with pgvector as the production backend."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import settings
from config.supabase import get_supabase_client
from utils import logger

_LOCAL_BACKEND = "local"
_PGVECTOR_BACKEND = "pgvector"
_PGVECTOR_RESERVED_KEYS = {"tenant_id", "title", "content", "file_type", "metadata"}


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Return cosine similarity between two vectors."""

    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


class VectorStoreService:
    """Manage search and ingestion over pgvector or the legacy local store."""

    def __init__(
        self,
        index_path: str | None = None,
        *,
        tenant_id: Optional[str] = None,
        backend: Optional[str] = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.backend = (backend or settings.vector_backend).strip().lower()
        self.vectors: List[List[float]] = []
        self.metadata: List[Dict[str, Any]] = []

        if self.backend == _PGVECTOR_BACKEND:
            return
        if self.backend != _LOCAL_BACKEND:
            raise ValueError(f"Unsupported vector backend: {self.backend}")

        self.index_path = index_path or settings.vector_store_path
        self.metadata_path = f"{self.index_path}.meta.json"
        self._load()

    def _load(self) -> None:
        """Load the legacy local vector store from disk."""

        path = Path(self.index_path)
        if path.exists():
            self.vectors = json.loads(path.read_text(encoding="utf-8"))
            logger.info("vector_store_loaded", extra={"path": self.index_path})
        else:
            logger.info("vector_store_created", extra={"path": self.index_path})

        metadata_path = Path(self.metadata_path)
        if metadata_path.exists():
            self.metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    def _persist(self) -> None:
        """Persist the legacy local vector store."""

        if self.backend != _LOCAL_BACKEND:
            raise RuntimeError("Local persistence is only available for the local vector backend")

        index_path = Path(self.index_path)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(json.dumps(self.vectors, ensure_ascii=False), encoding="utf-8")
        Path(self.metadata_path).write_text(
            json.dumps(self.metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add_embeddings(
        self,
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
    ) -> List[str]:
        """Add vectors/documents to the active backend."""

        if len(embeddings) != len(metadatas):
            raise ValueError("embeddings and metadatas must have the same length")

        if self.backend == _PGVECTOR_BACKEND:
            return self._add_embeddings_pgvector(embeddings, metadatas)

        start_index = len(self.metadata)
        self.vectors.extend(embeddings)
        self.metadata.extend(metadatas)
        self._persist()
        return [
            str(metadata.get("id") or f"local-{start_index + offset}")
            for offset, metadata in enumerate(metadatas)
        ]

    def search(
        self,
        embedding: List[float],
        top_k: int = 5,
        *,
        min_similarity: Optional[float] = None,
    ) -> List[Tuple[float, Dict[str, Any]]]:
        """Search for similar documents."""

        threshold = settings.vector_search_min_similarity if min_similarity is None else min_similarity
        if self.backend == _PGVECTOR_BACKEND:
            return self._search_pgvector(embedding, top_k, threshold)

        scores = [
            (cosine_similarity(embedding, vector), metadata)
            for vector, metadata in zip(self.vectors, self.metadata)
        ]
        filtered = [item for item in scores if item[0] >= threshold]
        filtered.sort(key=lambda item: item[0], reverse=True)
        return filtered[:top_k]

    def delete_documents_by_source_title(
        self,
        source_title: str,
        *,
        tenant_id: Optional[str] = None,
    ) -> int:
        """Delete all chunks belonging to a logical source document."""

        if self.backend == _PGVECTOR_BACKEND:
            tenant = tenant_id or self.tenant_id
            if not tenant:
                raise ValueError("tenant_id is required when deleting pgvector documents")

            result = (
                get_supabase_client()
                .table("documents")
                .delete()
                .eq("tenant_id", tenant)
                .contains("metadata", {"source_title": source_title})
                .execute()
            )
            return len(result.data or [])

        kept_vectors: List[List[float]] = []
        kept_metadata: List[Dict[str, Any]] = []
        deleted = 0
        tenant = tenant_id or self.tenant_id

        for vector, metadata in zip(self.vectors, self.metadata):
            payload = metadata.get("metadata") if isinstance(metadata.get("metadata"), dict) else {}
            metadata_source_title = payload.get("source_title", metadata.get("source_title", metadata.get("title")))
            metadata_tenant = metadata.get("tenant_id") or payload.get("tenant_id")
            if metadata_source_title == source_title and (tenant is None or metadata_tenant == tenant):
                deleted += 1
                continue
            kept_vectors.append(vector)
            kept_metadata.append(metadata)

        if deleted:
            self.vectors = kept_vectors
            self.metadata = kept_metadata
            self._persist()
        return deleted

    def rebuild(self, embeddings: List[List[float]], metadatas: List[Dict[str, Any]]) -> None:
        """Rebuild the legacy local index with provided data."""

        if self.backend != _LOCAL_BACKEND:
            raise RuntimeError("rebuild is only supported by the local vector backend")

        self.vectors = embeddings[:]
        self.metadata = metadatas[:]
        self._persist()

    def _add_embeddings_pgvector(
        self,
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
    ) -> List[str]:
        """Insert embedded documents into the shared pgvector table."""

        rows: List[Dict[str, Any]] = []
        for embedding, metadata in zip(embeddings, metadatas):
            rows.append(self._build_pgvector_row(embedding, metadata))

        result = get_supabase_client().table("documents").insert(rows).execute()
        return [str(row["id"]) for row in (result.data or [])]

    def _build_pgvector_row(self, embedding: List[float], metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize an in-memory metadata payload into a pgvector row."""

        tenant_id = metadata.get("tenant_id") or self.tenant_id
        if not tenant_id:
            raise ValueError("tenant_id is required when writing to pgvector")

        document_metadata = dict(metadata.get("metadata") or {})
        for key, value in metadata.items():
            if key in _PGVECTOR_RESERVED_KEYS:
                continue
            document_metadata[key] = value

        title = metadata.get("title") or document_metadata.get("source_title") or "Untitled document"
        content = metadata.get("content")
        if not content:
            raise ValueError("content is required when writing to pgvector")

        return {
            "tenant_id": tenant_id,
            "title": title,
            "content": content,
            "file_type": metadata.get("file_type"),
            "metadata": document_metadata,
            "embedding": embedding,
        }

    def _search_pgvector(
        self,
        embedding: List[float],
        top_k: int,
        min_similarity: float,
    ) -> List[Tuple[float, Dict[str, Any]]]:
        """Search tenant documents through the match_documents RPC."""

        if not self.tenant_id:
            raise ValueError("tenant_id is required when searching with pgvector")

        result = get_supabase_client().rpc(
            settings.match_documents_rpc,
            {
                "query_embedding": embedding,
                "match_count": top_k,
                "p_tenant_id": self.tenant_id,
                "min_similarity": min_similarity,
            },
        ).execute()

        return [
            (
                float(row["similarity"]),
                {
                    "id": row.get("id"),
                    "title": row.get("title", ""),
                    "content": row.get("content", ""),
                    "metadata": row.get("metadata") or {},
                },
            )
            for row in (result.data or [])
        ]
