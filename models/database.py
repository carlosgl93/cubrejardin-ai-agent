"""SQLAlchemy database models and session helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypeAlias

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from config import settings


def utc_now() -> datetime:
    """Return current UTC datetime."""

    return datetime.now(timezone.utc)


_PK_TYPE = BigInteger().with_variant(Integer, "sqlite")
_JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class Base(DeclarativeBase):
    """Base declarative class for SQLAlchemy models."""


class Conversation(Base):
    """Persisted inbound/outbound conversation message."""

    __tablename__ = "conversations"
    __table_args__ = (
        Index(
            "conversations_tenant_message_id_uidx",
            "tenant_id",
            "message_id",
            unique=True,
            postgresql_where=text("message_id is not null"),
            sqlite_where=text("message_id is not null"),
        ),
    )

    id: Mapped[int] = mapped_column(_PK_TYPE, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), index=True)
    user_number: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column("metadata", _JSON_TYPE, nullable=False, default=dict)
    message_id: Mapped[str | None] = mapped_column(Text, index=True)
    last_interaction_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class Escalation(Base):
    """Persisted handoff/escalation record."""

    __tablename__ = "escalations"

    id: Mapped[int] = mapped_column(_PK_TYPE, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), index=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id"))
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    handoff_type: Mapped[str] = mapped_column(Text, nullable=False, default="to_human")
    payload: Mapped[dict[str, Any]] = mapped_column("metadata", _JSON_TYPE, nullable=False, default=dict)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class LearningQueueEntry(Base):
    """Validated human answers waiting to be ingested into RAG."""

    __tablename__ = "learning_queue"

    id: Mapped[int] = mapped_column(_PK_TYPE, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), index=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id"))
    user_message: Mapped[str] = mapped_column("question", Text, nullable=False)
    human_answer: Mapped[str] = mapped_column("answer", Text, nullable=False)
    validated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    payload: Mapped[dict[str, Any]] = mapped_column("metadata", _JSON_TYPE, nullable=False, default=dict)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validated_by: Mapped[str | None] = mapped_column(String(36))
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class AuditLog(Base):
    """Application audit trail entry."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(_PK_TYPE, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(_JSON_TYPE, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


def _create_engine():
    database_url = settings.database_url
    engine_kwargs: dict[str, Any] = {"pool_pre_ping": True}

    if database_url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in database_url:
            engine_kwargs["poolclass"] = StaticPool

    return create_engine(database_url, **engine_kwargs)


engine = _create_engine()
_SessionFactory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)
DatabaseSession: TypeAlias = Session
InMemorySession = Session


def SessionLocal() -> DatabaseSession:
    """Return a database session."""

    return _SessionFactory()


def reset_database() -> None:
    """Recreate mapped tables for tests/local validation."""

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
