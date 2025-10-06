"""Minimal pydantic stub for testing."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Type, TypeVar, Union, get_args, get_origin

T = TypeVar("T", bound="BaseModel")

_MISSING = object()


class FieldInfo:
    """Store metadata about a field definition."""

    def __init__(
        self,
        default: Any = _MISSING,
        *,
        alias: Optional[str] = None,
        env: Optional[Union[str, Iterable[str]]] = None,
        default_factory: Any = _MISSING,
        **extra: Any,
    ) -> None:
        self.default = default
        self.alias = alias
        if env is None:
            self.env: Tuple[str, ...] = ()
        elif isinstance(env, str):
            self.env = (env,)
        else:
            self.env = tuple(env)
        self.default_factory = default_factory
        self.extra = extra

    def possible_env(self, field_name: str) -> Tuple[str, ...]:
        """Return candidate environment variable names for the field."""

        candidates = list(self.env)
        if field_name:
            candidates.append(field_name)
            candidates.append(field_name.upper())
        if self.alias:
            candidates.append(self.alias)
        seen = []
        for item in candidates:
            if item and item not in seen:
                seen.append(item)
        return tuple(seen)


def Field(
    default: Any = _MISSING,
    *,
    alias: Optional[str] = None,
    env: Optional[Union[str, Iterable[str]]] = None,
    default_factory: Any = _MISSING,
    **extra: Any,
) -> FieldInfo:
    """Return field metadata similar to pydantic."""

    return FieldInfo(
        default=default,
        alias=alias,
        env=env,
        default_factory=default_factory,
        **extra,
    )


HttpUrl = str
AnyUrl = str


class BaseConfig:
    """Placeholder for compatibility with FastAPI."""

    arbitrary_types_allowed = True
    allow_population_by_field_name = True


class ValidationError(Exception):
    """Basic validation error for compatibility."""


class BaseModel:
    """Simple base model mimicking Pydantic behavior."""

    __fields__: Dict[str, Tuple[Any, Any]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        hints = dict(getattr(cls, "__annotations__", {}))
        cls.__fields__ = {}
        for name, hint in hints.items():
            default = getattr(cls, name, _MISSING)
            cls.__fields__[name] = (hint, default)

    def __init__(self, **data: Any) -> None:
        cls = self.__class__
        for name, (hint, default) in cls.__fields__.items():
            if name in data:
                value = data[name]
            else:
                value = cls._get_default_value(name, hint, default)
            setattr(self, name, cls._coerce_type(value, hint))

    @classmethod
    def _get_default_value(cls, name: str, hint: Any, default: Any) -> Any:
        if isinstance(default, FieldInfo):
            for env_name in default.possible_env(name):
                env_value = cls._env_lookup(env_name)
                if env_value is not None:
                    return env_value
            if default.default_factory is not _MISSING:
                return default.default_factory()
            if default.default is Ellipsis:
                raise ValueError(f"{name} is required")
            if default.default is not _MISSING:
                return default.default
            return None
        if default is not _MISSING:
            return default
        return None

    @classmethod
    def _env_lookup(cls, key: str) -> Optional[str]:
        if not key:
            return None
        return os.environ.get(key)

    @classmethod
    def _coerce_type(cls, value: Any, hint: Any) -> Any:
        if value is None:
            return None
        origin = get_origin(hint)
        if origin is Union:
            args = [arg for arg in get_args(hint) if arg is not type(None)]  # noqa: E721
            if not args:
                return None
            return cls._coerce_type(value, args[0])
        if origin in (list, List, tuple, set):
            item_type = get_args(hint)[0] if get_args(hint) else Any
            if isinstance(value, str):
                items = [part.strip() for part in value.split(",") if part.strip()]
            elif isinstance(value, (list, tuple, set)):
                items = list(value)
            else:
                items = [value]
            coerced = [cls._coerce_type(item, item_type) for item in items]
            if origin is tuple:
                return tuple(coerced)
            if origin is set:
                return set(coerced)
            return list(coerced)
        return cls._coerce_primitive(value, hint)

    @staticmethod
    def _coerce_primitive(value: Any, hint: Any) -> Any:
        if hint in (Any, object):
            return value
        if hint is bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {"1", "true", "yes", "on"}:
                    return True
                if lowered in {"0", "false", "no", "off"}:
                    return False
            return bool(value)
        if hint is int:
            return int(value)
        if hint is float:
            return float(value)
        if hint is str:
            return str(value)
        return value

    def dict(self) -> Dict[str, Any]:
        return {key: getattr(self, key) for key in self.__class__.__fields__}

    @classmethod
    def parse_obj(cls: Type[T], obj: Dict[str, Any]) -> T:
        return cls(**obj)

    @classmethod
    def update_forward_refs(cls, **_locals: Any) -> None:
        """Compatibility stub for Pydantic's forward ref handling."""

        return None


def create_model(name: str, **fields: Any) -> Type[BaseModel]:
    """Dynamically create a simple BaseModel subclass."""

    annotations: Dict[str, Any] = {}
    namespace: Dict[str, Any] = {}
    for field_name, definition in fields.items():
        if isinstance(definition, tuple):
            field_type, default = definition
        else:
            field_type, default = definition, _MISSING
        annotations[field_name] = field_type
        if default is not _MISSING:
            namespace[field_name] = default
    namespace["__annotations__"] = annotations
    return type(name, (BaseModel,), namespace)


class BaseSettings(BaseModel):
    """Minimal BaseSettings stub."""

    class Config:
        env_file = None
        case_sensitive = False

    def __init__(self, **data: Any) -> None:
        cls = self.__class__
        config = getattr(cls, "Config", None)
        if config is not None:
            env_file = getattr(config, "env_file", None)
            if env_file and not getattr(cls, "_env_file_loaded", False):
                cls._load_env_file(env_file)
                setattr(cls, "_env_file_loaded", True)
        super().__init__(**data)

    @classmethod
    def _env_lookup(cls, key: str) -> Optional[str]:
        if not key:
            return None
        config = getattr(cls, "Config", None)
        case_sensitive = bool(getattr(config, "case_sensitive", False)) if config else False
        if case_sensitive:
            return os.environ.get(key)
        lower_key = key.lower()
        for env_key, value in os.environ.items():
            if env_key.lower() == lower_key:
                return value
        return None

    @staticmethod
    def _load_env_file(path: str) -> None:
        env_path = Path(path)
        if not env_path.exists():
            return
        for raw_line in env_path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            os.environ.setdefault(name.strip(), value.strip())
