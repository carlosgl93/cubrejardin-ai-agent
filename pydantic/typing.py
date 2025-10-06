"""Typing helpers for the local pydantic shim."""

from __future__ import annotations

from typing import Any


def evaluate_forwardref(tp: Any, globalns: dict[str, Any] | None = None, localns: dict[str, Any] | None = None) -> Any:
    """Return the provided type unchanged."""

    return tp
