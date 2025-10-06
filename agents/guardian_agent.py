"""Guardian agent implementation."""

from __future__ import annotations

import json
from typing import Any, Dict

from services.openai_service import OpenAIService
from config.prompts import guardian_prompt
from models.schemas import GuardianResult
from utils.helpers import sanitize_text


class GuardianAgent:
    """Input guardrail agent."""

    def __init__(self, openai_service: OpenAIService) -> None:
        self.openai_service = openai_service
        self.system_prompt = guardian_prompt()

    def classify(self, message: str) -> GuardianResult:
        """Classify inbound message and extract metadata."""

        cleaned = sanitize_text(message)
        messages = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": cleaned,
            },
        ]
        response = self.openai_service.chat_completion(
            messages=messages,
            response_format={"type": "json_object"},
        )
        content = response["choices"][0]["message"]["content"]
        data: Dict[str, Any] = json.loads(content)
        return GuardianResult(**data)
