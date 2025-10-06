"""Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MessageSchema(BaseModel):
    """Schema for WhatsApp message."""

    from_number: str = Field(..., alias="From")
    body: str = Field(..., alias="Body")


class GuardianResult(BaseModel):
    """Result from guardian classification."""

    category: str
    confidence: float
    intent: str
    entities: Dict[str, Any]
    sentiment: str
    reason: str


class RAGResponse(BaseModel):
    """Response from RAG agent."""

    answer: str
    confidence: float
    sources: List[Dict[str, Any]]
    disclaimer: Optional[str]


class EscalationSummary(BaseModel):
    """Summary for escalated conversations."""

    conversation_id: int
    summary: str
    status: str


class LearningQueueItem(BaseModel):
    """Learning queue entry."""

    id: int
    question: str
    answer: str
    metadata: Dict[str, Any]
    created_at: datetime
