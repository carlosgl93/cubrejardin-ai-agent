"""Minimal pydantic stub for testing."""

from __future__ import annotations

from dataclasses import field
from typing import Any, Dict, Optional, Type, TypeVar, get_type_hints

T = TypeVar("T", bound="BaseModel")


def Field(default: Any = None, alias: Optional[str] = None, env: Optional[str] = None, default_factory: Any = None):
    metadata = {"alias": alias, "env": env}
    if default_factory is not None:
        return field(default_factory=default_factory, metadata=metadata)
    return field(default=default, metadata=metadata)


HttpUrl = str


class BaseModel:
    """Simple base model mimicking Pydantic behavior."""

    def __init__(self, **data: Any) -> None:
        hints = get_type_hints(self.__class__)
        for key, value in data.items():
            setattr(self, key, value)
        for key in hints:
            if not hasattr(self, key):
                setattr(self, key, None)

    def dict(self) -> Dict[str, Any]:
        hints = get_type_hints(self.__class__)
        return {key: getattr(self, key) for key in hints}

    @classmethod
    def parse_obj(cls: Type[T], obj: Dict[str, Any]) -> T:
        return cls(**obj)


class BaseSettings(BaseModel):
    """Minimal BaseSettings stub."""

    class Config:
        env_file = None
        case_sensitive = False

    def __post_init__(self) -> None:
        pass
