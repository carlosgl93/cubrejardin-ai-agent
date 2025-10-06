"""Minimal httpx stub to enable offline testing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


class HTTPError(Exception):
    """Base HTTP exception."""


class HTTPStatusError(HTTPError):
    """Raised when the response contains an HTTP error status."""

    def __init__(self, message: str, *, request: Any | None = None, response: Any | None = None) -> None:
        super().__init__(message)
        self.request = request
        self.response = response


@dataclass
class Response:
    """Simple HTTP response container."""

    status_code: int = 200
    text: str = ""
    json_body: Dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.json_body is None:
            self.json_body = {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise HTTPStatusError("HTTP error", response=self)

    def json(self) -> Dict[str, Any]:
        return dict(self.json_body)


class Client:
    """Very small subset of httpx.Client used in tests."""

    def __init__(self, timeout: float | None = None) -> None:
        self.timeout = timeout
        self.last_request: Dict[str, Any] | None = None

    def post(
        self,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Response:
        self.last_request = {"url": url, "headers": headers or {}, "json": json or {}}
        return Response(status_code=200, text="{}", json_body={"status": "ok"})
