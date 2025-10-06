"""OpenAI client service with retry and rate limiting."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from openai import OpenAI
from config import settings
from utils import logger

# Manejo compatible de excepciones según versión del SDK
try:
    # SDK antiguo (<1.0)
    from openai.error import APIConnectionError, APIError, RateLimitError, Timeout
except ImportError:
    # SDK nuevo (>=1.0)
    from openai import APIStatusError
    APIConnectionError = APIError = RateLimitError = Timeout = APIStatusError


class RateLimiter:
    """Simple token bucket rate limiter."""

    def __init__(self, calls_per_minute: int) -> None:
        self.capacity = calls_per_minute
        self.tokens = calls_per_minute
        self.reset_time = time.monotonic() + 60

    def acquire(self) -> None:
        """Acquire a token, blocking if necessary."""

        now = time.monotonic()
        if now >= self.reset_time:
            self.tokens = self.capacity
            self.reset_time = now + 60
        if self.tokens <= 0:
            sleep_time = self.reset_time - now
            time.sleep(max(sleep_time, 0.01))
            self.acquire()
        else:
            self.tokens -= 1


class OpenAIService:
    """Wrapper around OpenAI API calls (modern client)."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.client = OpenAI(api_key=api_key or settings.openai_api_key)
        self.rate_limiter = RateLimiter(settings.rate_limit_per_minute)

    def _retry(self, func, *args, **kwargs):  # type: ignore[no-untyped-def]
        attempts = 0
        while True:
            try:
                return func(*args, **kwargs)
            except (RateLimitError, APIError, APIConnectionError, Timeout) as exc:
                attempts += 1
                if attempts >= 5:
                    logger.error("openai_max_retries", extra={"error": str(exc)})
                    raise
                sleep = min(2 ** attempts, 10)
                logger.warning("openai_retry", extra={"attempt": attempts, "sleep": sleep})
                time.sleep(sleep)

    def chat_completion(
        self,
        *,
        messages: Any,
        response_format: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Call OpenAI ChatCompletion with retries."""

        self.rate_limiter.acquire()
        kwargs: Dict[str, Any] = {
            "model": settings.openai_model,
            "messages": messages,
            "temperature": settings.openai_temperature,
        }
        if response_format:
            kwargs["response_format"] = response_format

        logger.info("openai_request", extra={"messages": len(messages)})
        response = self._retry(self.client.chat.completions.create, **kwargs)
        return response.model_dump()  # convierte a dict

    def embed(self, *, input_texts: Any) -> Dict[str, Any]:
        """Generate embeddings for provided texts."""

        self.rate_limiter.acquire()
        response = self._retry(
            self.client.embeddings.create,
            model=settings.embedding_model,
            input=input_texts,
        )
        return response.model_dump()  # también como dict
