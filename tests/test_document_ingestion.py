"""Tests for shared document ingestion helpers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.document_ingestion import (
    chunk_document_content,
    chunk_document_with_context,
    ingest_document,
)


class DummyOpenAIService:
    """Return deterministic embeddings based on chunk length."""

    def __init__(self) -> None:
        self.embedded_inputs: List[str] = []
        self.chat_calls: int = 0

    def embed(self, *, input_texts):  # type: ignore[override]
        self.embedded_inputs.extend(input_texts)
        value = float(len(input_texts[0])) if input_texts else 0.0
        return {"data": [{"embedding": [value]}]}

    def chat_completion(self, *, messages):  # type: ignore[override]
        self.chat_calls += 1
        return {"choices": [{"message": {"content": "Resumen contextual del fragmento."}}]}


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
    assert call["metadatas"][0]["metadata"]["heading_path"] == "Seccion A"
    assert call["metadatas"][0]["content"].startswith("Documento: Manual tecnico | Sección: Seccion A\n\n")


def test_chunk_document_with_context_tracks_heading_hierarchy() -> None:
    """Nested markdown headings should preserve parent > child heading paths."""

    content = """
# Catalogo 2026
## Pisos
### Vinyl Click
Resistente al agua.
## Envios
Despacho en 24h.
""".strip()

    chunks = chunk_document_with_context(content, file_type="markdown")

    assert len(chunks) == 2
    assert chunks[0][1] == "Catalogo 2026 > Pisos > Vinyl Click"
    assert chunks[1][1] == "Catalogo 2026 > Envios"


def test_ingest_document_with_llm_context_summary() -> None:
    """When contextualize_with_llm=True, a one-sentence summary is prepended before embedding."""

    openai_service = DummyOpenAIService()
    vector_store = RecordingVectorStore()
    ingest_document(
        tenant_id="tenant-a",
        title="Lista precios",
        content="SKU-100: $19.990 CLP",
        file_type="text",
        openai_service=openai_service,  # type: ignore[arg-type]
        vector_store=vector_store,  # type: ignore[arg-type]
        contextualize_with_llm=True,
    )

    assert openai_service.chat_calls == 1
    stored_content = vector_store.add_calls[0]["metadatas"][0]["content"]
    assert stored_content.startswith("Documento: Lista precios\nResumen contextual del fragmento.\n\nSKU-100")
    assert openai_service.embedded_inputs[0] == stored_content
