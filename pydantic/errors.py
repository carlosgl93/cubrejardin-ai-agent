"""Error definitions for the local pydantic shim."""

from __future__ import annotations


class PydanticError(Exception):
    """Base error for compatibility."""


class MissingError(PydanticError):
    """Raised when a required value is missing."""
