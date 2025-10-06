"""Color type stub for FastAPI compatibility."""

from __future__ import annotations

from typing import Any, Iterable


class Color(str):
    """Simple string-based color representation."""

    @classmethod
    def __get_validators__(cls) -> Iterable:
        yield cls.validate

    @classmethod
    def validate(cls, value: Any) -> "Color":
        return cls(str(value))
