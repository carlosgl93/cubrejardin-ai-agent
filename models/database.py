"""In-memory database models mimicking SQLAlchemy interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type, TypeVar

T = TypeVar("T", bound="BaseModel")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class BaseModel:
    id: int = field(init=False)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def assign_id(self, identifier: int) -> None:
        self.id = identifier


@dataclass
class Conversation(BaseModel):
    user_number: str = ""
    role: str = ""
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    last_interaction_at: Optional[datetime] = None


@dataclass
class Escalation(BaseModel):
    conversation_id: int = 0
    status: str = "pending"
    handoff_type: str = "to_human"  # indica si fue a humano o de vuelta al bot
    metadata: Dict[str, Any] = field(default_factory=dict)  # detalles de la escalada
    timestamp: datetime = field(default_factory=utc_now)  # cuándo ocurrió
    notes: Optional[str] = None  # comentarios opcionales


@dataclass
class LearningQueueEntry(BaseModel):
    question: str = ""
    answer: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeBaseDocument(BaseModel):
    title: str = ""
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class InMemorySession:
    """Very small in-memory session to simulate ORM behavior."""

    storage: Dict[Type[BaseModel], List[BaseModel]] = {}
    counters: Dict[Type[BaseModel], int] = {}

    def add(self, instance: BaseModel) -> None:
        cls = type(instance)
        bucket = self.storage.setdefault(cls, [])
        counter = self.counters.setdefault(cls, 0) + 1
        self.counters[cls] = counter
        instance.assign_id(counter)
        bucket.append(instance)

    def commit(self) -> None:
        pass

    def refresh(self, instance: BaseModel) -> None:
        pass

    def delete(self, instance: BaseModel) -> None:
        cls = type(instance)
        bucket = self.storage.get(cls, [])
        self.storage[cls] = [item for item in bucket if item.id != instance.id]

    def get(self, model: Type[T], identifier: int) -> Optional[T]:
        bucket = self.storage.get(model, [])
        for item in bucket:
            if item.id == identifier:
                return item  # type: ignore[return-value]
        return None

    def query(self, model: Type[T]) -> List[T]:
        return list(self.storage.get(model, []))  # type: ignore[return-value]

    def close(self) -> None:
        pass


def SessionLocal() -> InMemorySession:
    return InMemorySession()


class Base:
    metadata = None


engine = None
