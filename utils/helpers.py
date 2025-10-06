"""Helper utilities for the WhatsApp AI agent system."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional


def utc_now() -> datetime:
    """Return current UTC datetime."""

    return datetime.now(timezone.utc)


def sanitize_text(text: str) -> str:
    """Basic sanitization for incoming text."""

    return text.strip().replace("\u200b", "")


def chunk_list(items: Iterable[Any], size: int) -> List[List[Any]]:
    """Split iterable into chunks of given size."""

    chunk: List[Any] = []
    result: List[List[Any]] = []
    for item in items:
        chunk.append(item)
        if len(chunk) >= size:
            result.append(chunk)
            chunk = []
    if chunk:
        result.append(chunk)
    return result


def build_response_message(text: str, disclaimer: Optional[str] = None) -> str:
    """Compose response message with optional disclaimer."""

    if disclaimer:
        return f"{text}\n\n_{disclaimer}_"
    return text


def redact_sensitive(text: str) -> str:
    """Redact potential sensitive tokens."""

    tokens = text.split()
    redacted = ["[REDACTED]" if len(token) > 16 else token for token in tokens]
    return " ".join(redacted)


def calculate_confidence_label(score: float) -> str:
    """Return textual label for confidence score."""

    if score >= 0.75:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"


def flatten_entities(entities: Dict[str, Any]) -> str:
    """Format entities dictionary into string."""

    return ", ".join(f"{key}:{value}" for key, value in entities.items())
