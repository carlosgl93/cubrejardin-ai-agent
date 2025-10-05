"""Tests for GuardianAgent."""

from __future__ import annotations

from agents.guardian_agent import GuardianAgent
from models.schemas import GuardianResult


class DummyOpenAIService:
    """Stub service returning fixed classification."""

    def chat_completion(self, *, messages, response_format=None):  # type: ignore[override]
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"category": "VALID_QUERY", "confidence": 0.9, "intent": "ask_info", '
                            '"entities": {"product": "Plan"}, "sentiment": "neutral", "reason": "Matched"}'
                        )
                    }
                }
            ]
        }


def test_guardian_classification() -> None:
    """Guardian should parse structured response."""

    agent = GuardianAgent(DummyOpenAIService())
    result = agent.classify("Necesito información")
    assert isinstance(result, GuardianResult)
    assert result.category == "VALID_QUERY"
    assert result.entities["product"] == "Plan"
