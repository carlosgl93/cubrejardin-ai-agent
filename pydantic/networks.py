"""Network related types for the local pydantic shim."""

from __future__ import annotations

from typing import Any, Iterable

AnyUrl = str


class NameEmail(str):
    """Simple representation of a name/email pair."""

    @classmethod
    def __get_validators__(cls) -> Iterable:
        yield cls.validate

    @classmethod
    def validate(cls, value: Any) -> "NameEmail":
        return cls(str(value))
