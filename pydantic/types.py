"""Secret types for the local pydantic shim."""

from __future__ import annotations

from typing import Any, Iterable


class SecretStr(str):
    """String wrapper mimicking pydantic's SecretStr."""

    def get_secret_value(self) -> str:
        return str(self)

    @classmethod
    def __get_validators__(cls) -> Iterable:
        yield cls.validate

    @classmethod
    def validate(cls, value: Any) -> "SecretStr":
        return cls(str(value))


class SecretBytes(bytes):
    """Bytes wrapper mimicking pydantic's SecretBytes."""

    def get_secret_value(self) -> bytes:
        return bytes(self)

    @classmethod
    def __get_validators__(cls) -> Iterable:
        yield cls.validate

    @classmethod
    def validate(cls, value: Any) -> "SecretBytes":
        if isinstance(value, bytes):
            return cls(value)
        return cls(str(value).encode())
