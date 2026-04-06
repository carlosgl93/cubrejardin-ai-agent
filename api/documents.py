"""Document management endpoints for tenant knowledge base."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.dependencies import get_openai_service
from api.tenant_context import TenantContext, get_tenant_context
from config.supabase import get_supabase_client
from services.openai_service import OpenAIService
from utils import logger

router = APIRouter()

CHUNK_SIZE = 1500  # characters per chunk
CHUNK_OVERLAP = 200


class CreateDocumentRequest(BaseModel):
    title: str
    content: str


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Split text into overlapping chunks."""
    if len(text) <= chunk_size:
        return [text]
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


@router.get("")
async def list_documents(
    ctx: TenantContext = Depends(get_tenant_context),
) -> list:
    """List all documents for the tenant (grouped by source title)."""
    sb = get_supabase_client()
    result = (
        sb.table("documents")
        .select("id, title, content, file_type, created_at, metadata")
        .eq("tenant_id", ctx.tenant_id)
        .order("created_at", desc=True)
        .execute()
    )

    # Group chunks — show only the first chunk per source document
    seen_titles: set[str] = set()
    documents = []
    for row in result.data:
        meta = row.get("metadata") or {}
        source_title = meta.get("source_title", row["title"])
        if source_title in seen_titles:
            continue
        seen_titles.add(source_title)
        content = row["content"]
        documents.append(
            {
                "id": row["id"],
                "title": source_title,
                "content": content[:200] + ("..." if len(content) > 200 else ""),
                "file_type": row.get("file_type"),
                "created_at": row.get("created_at"),
                "total_chunks": meta.get("total_chunks", 1),
            }
        )

    return documents


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_document(
    body: CreateDocumentRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    openai_service: OpenAIService = Depends(get_openai_service),
) -> dict:
    """Create a new document, embed it, and store for RAG."""
    title = body.title.strip()
    content = body.content.strip()
    if not title or not content:
        raise HTTPException(status_code=400, detail="Title and content are required")

    sb = get_supabase_client()
    chunks = _chunk_text(content)

    rows = []
    for i, chunk in enumerate(chunks):
        embedding_response = openai_service.embed(input_texts=[chunk])
        embedding = embedding_response["data"][0]["embedding"]

        rows.append(
            {
                "tenant_id": ctx.tenant_id,
                "title": title if len(chunks) == 1 else f"{title} (part {i + 1})",
                "content": chunk,
                "file_type": "text",
                "embedding": embedding,
                "metadata": {
                    "source_title": title,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                },
            }
        )

    result = sb.table("documents").insert(rows).execute()

    logger.info(
        "document_created",
        extra={"tenant_id": ctx.tenant_id, "title": title, "chunks": len(chunks)},
    )

    return {
        "title": title,
        "chunks": len(chunks),
        "ids": [r["id"] for r in result.data],
    }


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
) -> dict:
    """Delete a document and all its chunks."""
    sb = get_supabase_client()

    # Find the document to get its source_title
    doc = (
        sb.table("documents")
        .select("id, title, metadata")
        .eq("id", document_id)
        .eq("tenant_id", ctx.tenant_id)
        .limit(1)
        .execute()
    )
    if not doc.data:
        raise HTTPException(status_code=404, detail="Document not found")

    meta = doc.data[0].get("metadata") or {}
    source_title = meta.get("source_title", doc.data[0]["title"])

    # Delete all chunks with the same source_title for this tenant
    sb.table("documents").delete().eq("tenant_id", ctx.tenant_id).contains(
        "metadata", {"source_title": source_title}
    ).execute()

    logger.info(
        "document_deleted",
        extra={"tenant_id": ctx.tenant_id, "title": source_title},
    )

    return {"status": "deleted", "title": source_title}
