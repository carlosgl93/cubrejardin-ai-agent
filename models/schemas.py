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
    entities: Dict[str, Any] = Field(default_factory=dict)
    sentiment: str
    reason: str


class RAGResponse(BaseModel):
    """Response from RAG agent."""

    answer: str
    confidence: float
    sources: List[Dict[str, Any]]
    disclaimer: Optional[str]


class AgentResponse(BaseModel):
    """Structured response returned by the orchestrator."""

    message: str
    intent: Optional[str] = None
    category: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)


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


class StockOperation(BaseModel):
    """Parsed stock operation from user message."""

    action: str  # STOCK_ADD, STOCK_REMOVE, STOCK_QUERY, STOCK_SALE, STOCK_SET, STOCK_HISTORY, STOCK_ALERTS, PRODUCT_LIST, UNKNOWN
    product_id: Optional[int] = None
    quantity: Optional[int] = None
    page: Optional[int] = None  # For pagination in PRODUCT_LIST
    search_term: Optional[str] = None  # For search in PRODUCT_LIST
    confidence: float = 0.0
