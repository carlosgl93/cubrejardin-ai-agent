"""Minimal schema helpers for FastAPI compatibility."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Set, Tuple, Type

from .fields import FieldInfo


def field_schema(_field: Any, **_kwargs: Any) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    return {}, {}


def get_flat_models_from_fields(_fields: Iterable[Any], _known_models: Set[Type[Any]] | None = None) -> Set[Any]:
    return set()


def get_model_name_map(_models: Iterable[Type[Any]]) -> Dict[Type[Any], str]:
    return {}


def model_process_schema(_model: Any, _model_name_map: Mapping[Any, str]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    return {}, {}


def get_annotation_from_field_info(annotation: Any, field_info: FieldInfo, _field_name: Any = None) -> Any:
    candidate = getattr(field_info, "annotation", None)
    return candidate if candidate is not None else annotation
