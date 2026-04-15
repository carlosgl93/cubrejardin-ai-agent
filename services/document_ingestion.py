"""Shared document chunking and ingestion helpers."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from services.openai_service import OpenAIService
from services.vector_store import VectorStoreService

DEFAULT_CHUNK_SIZE = 1500
DEFAULT_CHUNK_OVERLAP = 200
_MARKDOWN_HEADING_RE = re.compile(r"^#{2,6}\s+")


def chunk_text(
    text: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[str]:
    """Split plain text into overlapping chunks."""

    normalized = text.strip()
    if not normalized:
        return []
    if len(normalized) <= chunk_size:
        return [normalized]

    chunks: List[str] = []
    start = 0
    while start < len(normalized):
        end = start + chunk_size
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(end - overlap, start + 1)
    return chunks


def _split_markdown_sections(content: str) -> List[str]:
    """Split markdown on section headings when available."""

    sections: List[str] = []
    current: List[str] = []

    for line in content.splitlines():
        if _MARKDOWN_HEADING_RE.match(line) and current:
            section = "\n".join(current).strip()
            if section:
                sections.append(section)
            current = [line]
            continue
        current.append(line)

    if current:
        section = "\n".join(current).strip()
        if section:
            sections.append(section)

    return sections


def chunk_document_content(
    content: str,
    *,
    file_type: str = "text",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[str]:
    """Chunk a document, preferring markdown sections when possible."""

    normalized_type = file_type.lower()
    if normalized_type in {"md", "markdown"}:
        sections = _split_markdown_sections(content)
        if len(sections) > 1:
            chunks: List[str] = []
            for section in sections:
                if len(section) <= chunk_size:
                    chunks.append(section)
                    continue
                chunks.extend(chunk_text(section, chunk_size=chunk_size, overlap=overlap))
            return [chunk for chunk in chunks if chunk.strip()]

    return chunk_text(content, chunk_size=chunk_size, overlap=overlap)


def ingest_document(
    *,
    tenant_id: str,
    title: str,
    content: str,
    openai_service: OpenAIService,
    vector_store: VectorStoreService,
    file_type: str = "text",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Replace a logical source document with freshly embedded chunks."""

    normalized_title = title.strip()
    normalized_content = content.strip()
    if not normalized_title or not normalized_content:
        raise ValueError("title and content are required")

    base_metadata = dict(metadata or {})
    source_title = str(base_metadata.get("source_title") or normalized_title)
    chunks = chunk_document_content(normalized_content, file_type=file_type)
    embeddings: List[List[float]] = []

    for chunk in chunks:
        embedding_response = openai_service.embed(input_texts=[chunk])
        embeddings.append(embedding_response["data"][0]["embedding"])

    vector_store.delete_documents_by_source_title(source_title, tenant_id=tenant_id)

    metadatas: List[Dict[str, Any]] = []
    total_chunks = len(chunks)
    for index, chunk in enumerate(chunks):
        chunk_metadata = dict(base_metadata)
        chunk_metadata.update(
            {
                "source_title": source_title,
                "chunk_index": index,
                "total_chunks": total_chunks,
            }
        )
        display_title = source_title if total_chunks == 1 else f"{source_title} (part {index + 1})"
        metadatas.append(
            {
                "tenant_id": tenant_id,
                "title": display_title,
                "content": chunk,
                "file_type": file_type,
                "metadata": chunk_metadata,
            }
        )

    inserted_ids = vector_store.add_embeddings(embeddings, metadatas)
    return {
        "title": source_title,
        "chunks": total_chunks,
        "ids": inserted_ids,
    }
