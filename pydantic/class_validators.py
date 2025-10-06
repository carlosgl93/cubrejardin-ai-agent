"""Simplified validator utilities for the local pydantic shim."""

from __future__ import annotations

from typing import Any, Callable


class Validator:
    """Wrapper representing a class validator."""

    def __init__(self, func: Callable[..., Any]) -> None:
        self.func = func

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.func(*args, **kwargs)


def validator(*_args: Any, **_kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """No-op decorator compatible with pydantic's validator."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        return func

    return decorator


def root_validator(*args: Any, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Alias of validator for compatibility."""

    return validator(*args, **kwargs)
