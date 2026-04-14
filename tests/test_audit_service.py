"""Tests for audit event persistence."""

from __future__ import annotations

from models.database import AuditLog, SessionLocal
from services.audit_service import record_audit_event


def test_record_audit_event_persists_entry() -> None:
    """Audit events should be written to the operational database."""

    record_audit_event(
        tenant_id="tenant-a",
        event_type="learning_validated",
        entity_type="learning_queue_entry",
        entity_id="42",
        payload={"conversation_id": 10},
    )

    session = SessionLocal()
    try:
        entry = session.query(AuditLog).one()
        assert entry.tenant_id == "tenant-a"
        assert entry.event_type == "learning_validated"
        assert entry.entity_type == "learning_queue_entry"
        assert entry.entity_id == "42"
        assert entry.payload["conversation_id"] == 10
    finally:
        session.close()
