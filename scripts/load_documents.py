"""Load documents into knowledge base."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.database import KnowledgeBaseDocument, SessionLocal
from services.openai_service import OpenAIService
from services.vector_store import VectorStoreService

DOCUMENTS_DIR = Path("data/documents")


def chunk_faq_document(content: str) -> list[str]:
    """Split FAQ document into individual Q&A pairs."""
    chunks = []
    lines = content.split('\n')
    current_chunk = []
    
    for line in lines:
        # Start of a new question (### heading)
        if line.startswith('###'):
            # Save previous chunk if it exists
            if current_chunk:
                chunks.append('\n'.join(current_chunk))
            # Start new chunk with this question
            current_chunk = [line]
        else:
            # Add line to current chunk
            if current_chunk or line.strip():  # Skip leading empty lines
                current_chunk.append(line)
    
    # Add last chunk
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
    
    return chunks


def main() -> None:
    """Load markdown documents into database and vector store."""

    session = SessionLocal()
    vector_store = VectorStoreService()
    openai_service = OpenAIService()
    
    for path in DOCUMENTS_DIR.glob("*.md"):
        content = path.read_text(encoding="utf-8")
        title = path.stem.replace("_", " ")
        
        # Store full document in database
        document = KnowledgeBaseDocument(
            title=title,
            content=content,
            metadata={"path": str(path)}
        )
        session.add(document)
        session.commit()
        
        # For FAQs, chunk into individual Q&A pairs
        if path.stem == "faqs":
            chunks = chunk_faq_document(content)
            print(f"Chunking {title} into {len(chunks)} Q&A pairs")
            
            for i, chunk in enumerate(chunks):
                if not chunk.strip():
                    continue
                print(f"  Processing chunk {i+1}/{len(chunks)}...")
                embedding_response = openai_service.embed(input_texts=[chunk])
                embedding = embedding_response["data"][0]["embedding"]
                vector_store.add_embeddings(
                    [embedding],
                    [{
                        "title": f"{title} - Q{i+1}",
                        "content": chunk,
                        "id": f"{document.id}_chunk_{i}",
                        "source": title
                    }]
                )
            print(f"Loaded {title} ({len(chunks)} chunks)")
        else:
            # For other documents, embed as single chunk
            embedding_response = openai_service.embed(input_texts=[content])
            embedding = embedding_response["data"][0]["embedding"]
            vector_store.add_embeddings(
                [embedding],
                [{"title": title, "content": content, "id": document.id}]
            )
            print(f"Loaded {title}")
    
    session.close()


if __name__ == "__main__":
    main()
