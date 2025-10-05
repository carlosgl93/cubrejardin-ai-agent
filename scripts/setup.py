"""Setup script to initialize database and vector store."""

from __future__ import annotations

from models.database import Base


def main() -> None:
    """Initialize in-memory structures (no-op)."""

    print("In-memory database ready")


if __name__ == "__main__":
    main()
