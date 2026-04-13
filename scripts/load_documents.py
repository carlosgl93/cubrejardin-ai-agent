"""Load markdown documents directly into the tenant pgvector store."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings
from services.document_ingestion import ingest_document
from services.openai_service import OpenAIService
from services.vector_store import VectorStoreService


def parse_args() -> argparse.Namespace:
    """Parse script arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True, help="Tenant UUID that owns the documents")
    parser.add_argument(
        "--source-dir",
        default=settings.documents_path,
        help="Directory containing source markdown files",
    )
    return parser.parse_args()


def detect_file_type(path: Path) -> str:
    """Infer file type metadata from the source file."""

    suffix = path.suffix.lower()
    if suffix == ".md":
        return "markdown"
    if suffix == ".txt":
        return "text"
    return suffix.lstrip(".") or "text"


def main() -> None:
    """Load markdown documents into the shared pgvector store."""

    args = parse_args()
    source_dir = Path(args.source_dir)
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    vector_store = VectorStoreService(tenant_id=args.tenant_id)
    openai_service = OpenAIService()
    total_chunks = 0
    processed_files = 0

    for path in sorted(source_dir.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        title = path.stem.replace("_", " ")
        result = ingest_document(
            tenant_id=args.tenant_id,
            title=title,
            content=content,
            file_type=detect_file_type(path),
            metadata={"source_path": str(path), "source_title": title},
            openai_service=openai_service,
            vector_store=vector_store,
        )
        processed_files += 1
        total_chunks += int(result["chunks"])
        print(f"Loaded {result['title']} ({result['chunks']} chunks)")

    print(
        f"Completed tenant {args.tenant_id}: "
        f"{processed_files} files, {total_chunks} chunks from {source_dir}"
    )


if __name__ == "__main__":
    main()
