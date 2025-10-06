"""Lightweight OpenAI stub for offline testing."""

from __future__ import annotations

from typing import Any, Dict, List

api_key: str | None = None


class ChatCompletion:
    """Simulate ChatCompletion endpoint."""

    @staticmethod
    def create(**kwargs: Any) -> Dict[str, Any]:
        messages: List[Dict[str, str]] = kwargs.get("messages", [])
        last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        return {
            "choices": [
                {
                    "message": {
                        "content": f"Respuesta simulada para: {last_user}",
                    }
                }
            ]
        }


class Embedding:
    """Simulate Embedding endpoint."""

    @staticmethod
    def create(**kwargs: Any) -> Dict[str, Any]:
        inputs = kwargs.get("input", [])
        if isinstance(inputs, str):
            inputs = [inputs]
        data = []
        for text in inputs:
            length = max(len(text), 1)
            data.append({"embedding": [1.0 / length] * 1536})
        return {"data": data}


class error:  # type: ignore
    """Namespace for error types."""

    class APIError(Exception):
        pass

    class APIConnectionError(Exception):
        pass

    class RateLimitError(Exception):
        pass

    class Timeout(Exception):
        pass


APIError = error.APIError
APIConnectionError = error.APIConnectionError
RateLimitError = error.RateLimitError
Timeout = error.Timeout
