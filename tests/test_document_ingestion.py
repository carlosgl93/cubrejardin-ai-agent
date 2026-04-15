"""Tests for shared document ingestion helpers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.document_ingestion import chunk_document_content, ingest_document


class DummyOpenAIService:
    """Return deterministic embeddings based on chunk length."""

    def embed(self, *, input_texts):  # type: ignore[override]
        value = float(len(input_texts[0])) if input_texts else 0.0
        return {"data": [{"embedding": [value]}]}


class RecordingVectorStore:
    """Capture delete/insert operations from the ingestion service."""

    def __init__(self) -> None:
        self.deleted: List[tuple[Optional[str], str]] = []
        self.add_calls: List[Dict[str, Any]] = []

    def delete_documents_by_source_title(self, source_title: str, *, tenant_id: Optional[str] = None) -> int:
        self.deleted.append((tenant_id, source_title))
        return 0

    def add_embeddings(self, embeddings: List[List[float]], metadatas: List[Dict[str, Any]]) -> List[str]:
        self.add_calls.append({"embeddings": embeddings, "metadatas": metadatas})
        return [f"doc-{index}" for index, _ in enumerate(metadatas, start=1)]


def test_chunk_document_content_prefers_markdown_sections() -> None:
    """Markdown documents should split along headings before using sliding windows."""

    content = """
## Instalacion
Paso 1

## Garantia
Paso 2
""".strip()

    chunks = chunk_document_content(content, file_type="markdown")

    assert len(chunks) == 2
    assert chunks[0].startswith("## Instalacion")
    assert chunks[1].startswith("## Garantia")


def test_ingest_document_replaces_existing_chunks_and_sets_metadata() -> None:
    """Document ingestion should delete the previous source and insert normalized chunks."""

    vector_store = RecordingVectorStore()
    result = ingest_document(
        tenant_id="tenant-a",
        title="Manual tecnico",
        content="## Seccion A\nContenido A\n\n## Seccion B\nContenido B",
        file_type="markdown",
        metadata={"origin": "unit-test"},
        openai_service=DummyOpenAIService(),
        vector_store=vector_store,  # type: ignore[arg-type]
    )

    assert result == {"title": "Manual tecnico", "chunks": 2, "ids": ["doc-1", "doc-2"]}
    assert vector_store.deleted == [("tenant-a", "Manual tecnico")]

    call = vector_store.add_calls[0]
    assert len(call["embeddings"]) == 2
    assert call["metadatas"][0]["tenant_id"] == "tenant-a"
    assert call["metadatas"][0]["metadata"]["source_title"] == "Manual tecnico"
    assert call["metadatas"][0]["metadata"]["chunk_index"] == 0
    assert call["metadatas"][1]["metadata"]["chunk_index"] == 1
    assert call["metadatas"][0]["metadata"]["origin"] == "unit-test"
