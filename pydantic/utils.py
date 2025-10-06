"""Utility helpers for the local pydantic shim."""

from __future__ import annotations

from typing import Any, Tuple


def lenient_issubclass(obj: Any, class_or_tuple: Tuple[type, ...] | type) -> bool:
    """Return True if obj is a subclass, ignoring non-class inputs."""

    try:
        return issubclass(obj, class_or_tuple)
    except TypeError:
        return False
