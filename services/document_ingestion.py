"""Shared document chunking and ingestion helpers."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from services.openai_service import OpenAIService
from services.vector_store import VectorStoreService
from utils import logger

DEFAULT_CHUNK_SIZE = 1500
DEFAULT_CHUNK_OVERLAP = 200
_MARKDOWN_HEADING_RE = re.compile(r"^#{2,6}\s+")
_HEADING_PARSE_RE = re.compile(r"^(#{1,6})\s+(.+)$")


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


def _split_markdown_with_headings(content: str) -> List[Tuple[str, str]]:
    """Split markdown into (section_text, heading_path) pairs."""

    sections: List[Tuple[str, str]] = []
    current_lines: List[str] = []
    heading_stack: List[Tuple[int, str]] = []
    section_heading = ""
    has_body = False

    for line in content.splitlines():
        heading_match = _HEADING_PARSE_RE.match(line.strip())
        if heading_match:
            level = len(heading_match.group(1))
            heading_title = heading_match.group(2).strip()
            if level >= 2 and current_lines and has_body:
                section_text = "\n".join(current_lines).strip()
                if section_text:
                    sections.append((section_text, section_heading))
                current_lines = []
                has_body = False
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, heading_title))
            section_heading = " > ".join(item[1] for item in heading_stack)
            current_lines.append(line)
            continue
        if line.strip():
            has_body = True
        current_lines.append(line)

    if current_lines:
        section_text = "\n".join(current_lines).strip()
        if section_text:
            sections.append((section_text, section_heading))

    return sections


def chunk_document_with_context(
    content: str,
    *,
    file_type: str = "text",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[Tuple[str, str]]:
    """Chunk a document and return (chunk_text, heading_path) pairs."""

    normalized_type = file_type.lower()
    if normalized_type in {"md", "markdown"}:
        sections = _split_markdown_with_headings(content)
        if len(sections) > 1:
            chunks: List[Tuple[str, str]] = []
            for section_text, heading_path in sections:
                if len(section_text) <= chunk_size:
                    chunks.append((section_text, heading_path))
                    continue
                for piece in chunk_text(section_text, chunk_size=chunk_size, overlap=overlap):
                    chunks.append((piece, heading_path))
            return [(piece, heading) for piece, heading in chunks if piece.strip()]

    return [(piece, "") for piece in chunk_text(content, chunk_size=chunk_size, overlap=overlap)]


def _build_contextual_header(source_title: str, heading_path: str) -> str:
    """Build a concise header anchoring a chunk to its parent document and section."""

    if heading_path:
        return f"Documento: {source_title} | Sección: {heading_path}"
    return f"Documento: {source_title}"


def _summarize_chunk_context(
    openai_service: OpenAIService,
    source_title: str,
    heading_path: str,
    chunk: str,
) -> str:
    """Optionally generate a one-sentence Spanish context summary for a chunk."""

    prompt = (
        "Resume en una sola oración corta en español el contexto de este fragmento "
        f"del documento '{source_title}'"
        + (f" (sección '{heading_path}')" if heading_path else "")
        + " para mejorar su búsqueda. Responde solo la oración."
    )
    try:
        response = openai_service.chat_completion(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": chunk[:1500]},
            ]
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.warning("chunk_context_summary_failed", extra={"error": str(exc)})
        return ""


def ingest_document(
    *,
    tenant_id: str,
    title: str,
    content: str,
    openai_service: OpenAIService,
    vector_store: VectorStoreService,
    file_type: str = "text",
    metadata: Optional[Dict[str, Any]] = None,
    contextualize_with_llm: bool = False,
) -> Dict[str, Any]:
    """Replace a logical source document with freshly embedded contextual chunks."""

    normalized_title = title.strip()
    normalized_content = content.strip()
    if not normalized_title or not normalized_content:
        raise ValueError("title and content are required")

    base_metadata = dict(metadata or {})
    source_title = str(base_metadata.get("source_title") or normalized_title)
    chunk_pairs = chunk_document_with_context(normalized_content, file_type=file_type)
    contextual_chunks: List[str] = []
    embeddings: List[List[float]] = []

    for chunk, heading_path in chunk_pairs:
        header = _build_contextual_header(source_title, heading_path)
        summary = (
            _summarize_chunk_context(openai_service, source_title, heading_path, chunk)
            if contextualize_with_llm
            else ""
        )
        prefix = f"{header}\n{summary}" if summary else header
        contextual_text = f"{prefix}\n\n{chunk}"
        contextual_chunks.append(contextual_text)
        embedding_response = openai_service.embed(input_texts=[contextual_text])
        embeddings.append(embedding_response["data"][0]["embedding"])

    vector_store.delete_documents_by_source_title(source_title, tenant_id=tenant_id)

    metadatas: List[Dict[str, Any]] = []
    total_chunks = len(chunk_pairs)
    for index, ((_, heading_path), contextual_text) in enumerate(zip(chunk_pairs, contextual_chunks)):
        chunk_metadata = dict(base_metadata)
        chunk_metadata.update(
            {
                "source_title": source_title,
                "chunk_index": index,
                "total_chunks": total_chunks,
            }
        )
        if heading_path:
            chunk_metadata["heading_path"] = heading_path
        display_title = source_title if total_chunks == 1 else f"{source_title} (part {index + 1})"
        metadatas.append(
            {
                "tenant_id": tenant_id,
                "title": display_title,
                "content": contextual_text,
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
