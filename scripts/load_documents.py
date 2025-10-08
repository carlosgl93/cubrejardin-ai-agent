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


def main() -> None:
    """Load markdown documents into database and vector store."""

    session = SessionLocal()
    vector_store = VectorStoreService()
    openai_service = OpenAIService()
    for path in DOCUMENTS_DIR.glob("*.md"):
        content = path.read_text(encoding="utf-8")
        document = KnowledgeBaseDocument(title=path.stem.replace("_", " "), content=content, metadata={"path": str(path)})
        session.add(document)
        session.commit()
        embedding_response = openai_service.embed(input_texts=[content])
        embedding = embedding_response["data"][0]["embedding"]
        vector_store.add_embeddings([embedding], [{"title": document.title, "content": content, "id": document.id}])
        print(f"Loaded {document.title}")
    session.close()


if __name__ == "__main__":
    main()
