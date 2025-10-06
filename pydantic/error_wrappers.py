"""Error wrapper compatibility layer."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Tuple, Union


class ErrorWrapper(Exception):
    """Minimal implementation capturing the wrapped exception."""

    def __init__(self, exc: Exception, loc: Union[Tuple[Union[int, str], ...], None] = None) -> None:
        super().__init__(str(exc))
        self.exc = exc
        self.loc = loc or ()

    def errors(self) -> Iterable[Dict[str, Any]]:
        """Return error information similar to pydantic."""

        return [{"loc": self.loc, "msg": str(self.exc)}]
