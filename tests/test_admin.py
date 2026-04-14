"""Tests for tenant-scoped admin operations."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api import admin
from api.tenant_context import TenantContext
from models.database import AuditLog, Conversation, LearningQueueEntry, SessionLocal


ADMIN_CTX = TenantContext(
    tenant_id="tenant-a",
    user_id="user-1",
    role="admin",
    tenant_name="Tenant A",
)
MEMBER_CTX = TenantContext(
    tenant_id="tenant-a",
    user_id="user-2",
    role="member",
    tenant_name="Tenant A",
)


def test_add_document_uses_authenticated_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    """Admin knowledge base writes must use the tenant from auth context."""

    captured: dict[str, object] = {}

    class FakeVectorStore:
        def __init__(self, *, tenant_id: str) -> None:
            captured["vector_store_tenant_id"] = tenant_id

    def fake_ingest_document(**kwargs):
        captured.update(kwargs)
        return {"ids": ["doc-1"], "title": kwargs["title"], "chunks": 2}

    def fake_record_audit_event(**kwargs):
        captured["audit"] = kwargs

    monkeypatch.setattr(admin, "VectorStoreService", FakeVectorStore)
    monkeypatch.setattr(admin, "ingest_document", fake_ingest_document)
    monkeypatch.setattr(admin, "record_audit_event", fake_record_audit_event)

    result = admin.add_document(
        title="FAQ",
        content="Contenido",
        metadata={"source_title": "FAQ"},
        ctx=ADMIN_CTX,
        openai_service=SimpleNamespace(),
    )

    assert result["ids"] == ["doc-1"]
    assert captured["tenant_id"] == ADMIN_CTX.tenant_id
    assert captured["vector_store_tenant_id"] == ADMIN_CTX.tenant_id
    assert captured["audit"]["tenant_id"] == ADMIN_CTX.tenant_id


def test_list_learning_queue_filters_by_tenant() -> None:
    """Learning queue listing must stay inside the authenticated tenant."""

    session = SessionLocal()
    try:
        session.add_all(
            [
                LearningQueueEntry(
                    tenant_id="tenant-a",
                    conversation_id=1,
                    user_message="Pregunta A",
                    human_answer="Respuesta A",
                    validated=False,
                    payload={"source": "handoff"},
                ),
                LearningQueueEntry(
                    tenant_id="tenant-b",
                    conversation_id=2,
                    user_message="Pregunta B",
                    human_answer="Respuesta B",
                    validated=False,
                    payload={"source": "handoff"},
                ),
            ]
        )
        session.commit()

        rows = admin.list_learning_queue(db=session, ctx=ADMIN_CTX, limit=50, include_ingested=False)

        assert len(rows) == 1
        assert rows[0]["user_message"] == "Pregunta A"
    finally:
        session.close()


def test_member_role_cannot_access_admin_learning_queue() -> None:
    """Tenant members without admin privileges must be rejected."""

    session = SessionLocal()
    try:
        with pytest.raises(HTTPException) as exc:
            admin.list_learning_queue(db=session, ctx=MEMBER_CTX)

        assert exc.value.status_code == 403
    finally:
        session.close()


def test_list_audit_logs_filters_by_tenant() -> None:
    """Audit log listing must be tenant-scoped."""

    session = SessionLocal()
    try:
        session.add_all(
            [
                AuditLog(
                    tenant_id="tenant-a",
                    event_type="learning_validated",
                    entity_type="learning_queue_entry",
                    entity_id="1",
                    payload={"conversation_id": 1},
                ),
                AuditLog(
                    tenant_id="tenant-b",
                    event_type="learning_validated",
                    entity_type="learning_queue_entry",
                    entity_id="2",
                    payload={"conversation_id": 2},
                ),
            ]
        )
        session.commit()

        rows = admin.list_audit_logs(db=session, ctx=ADMIN_CTX, limit=50)

        assert len(rows) == 1
        assert rows[0]["entity_id"] == "1"
    finally:
        session.close()


@pytest.mark.anyio("asyncio")
async def test_handoff_to_human_scopes_conversation_to_tenant() -> None:
    """Manual handoff must not operate on another tenant's conversation."""

    session = SessionLocal()
    try:
        conversation = Conversation(
            tenant_id="tenant-b",
            user_number="+56911111111",
            role="user",
            message="Hola",
            payload={},
        )
        session.add(conversation)
        session.commit()
        session.refresh(conversation)

        with pytest.raises(HTTPException) as exc:
            await admin.handoff_to_human(
                conversation_id=conversation.id,
                db=session,
                whatsapp_service=SimpleNamespace(),
                openai_service=SimpleNamespace(),
                ctx=ADMIN_CTX,
            )

        assert exc.value.status_code == 404
    finally:
        session.close()
