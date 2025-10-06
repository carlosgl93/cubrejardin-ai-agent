"""Field utilities for the lightweight pydantic shim."""

from __future__ import annotations

from typing import Any, Callable, Optional

from . import BaseConfig, FieldInfo as BaseFieldInfo, _MISSING

SHAPE_SINGLETON = 1
SHAPE_LIST = 2
SHAPE_SEQUENCE = 3
SHAPE_SET = 4
SHAPE_TUPLE = 5
SHAPE_TUPLE_ELLIPSIS = 6
SHAPE_FROZENSET = 7


class FieldInfo(BaseFieldInfo):
    """Extend base FieldInfo with helpers expected by FastAPI."""

    def __init__(self, *args: Any, annotation: Any = Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.annotation = annotation

    def is_required(self) -> bool:
        return self.default is Ellipsis

    def get_default(self, call_default_factory: bool = False) -> Any:
        if self.default is not _MISSING and self.default is not Ellipsis:
            return self.default
        if call_default_factory and self.default_factory is not _MISSING:
            return self.default_factory()
        return None

    def get_default_factory(self) -> Optional[Callable[[], Any]]:
        if self.default_factory is _MISSING:
            return None
        return self.default_factory


class ModelField:
    """Very small subset of pydantic's ModelField."""

    def __init__(
        self,
        name: str,
        type_: Any,
        default: Any = _MISSING,
        field_info: Optional[FieldInfo] = None,
        **kwargs: Any,
    ) -> None:
        self.name = name
        self.alias = name
        self.type_ = type_
        self.outer_type_ = type_
        self.field_info = field_info or FieldInfo(default=default, annotation=type_)
        self.default = None if default in (_MISSING, Ellipsis) else default
        self.required = default is Ellipsis
        self.class_validators = kwargs.get("class_validators", {})
        self.has_alias = False
        self.allow_none = False
        self.sub_fields = None
        self.model_config = kwargs.get("model_config", BaseConfig())
        self.validate_always = False
        self.key_field = None
        self.validators = []
        self.pre_validators = []
        self.post_validators = []
        self.shape = kwargs.get("shape", SHAPE_SINGLETON)

    def get_default(self) -> Any:
        return self.field_info.get_default()

    def parse_json(self, value: Any, *_args: Any, **_kwargs: Any) -> Any:
        return value

    def populate_validators(self) -> None:
        return None


class _UndefinedType:
    def __repr__(self) -> str:
        return "Undefined"


Undefined = _UndefinedType()
UndefinedType = type(Undefined)
Required = Ellipsis
