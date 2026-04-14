"""Tests for handoff lifecycle persistence."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agents.handoff_agent import HandoffAgent
from models.database import AuditLog, Conversation, Escalation, SessionLocal


class DummyTransport:
    """Capture pass/take control calls without network."""

    def __init__(self) -> None:
        self.pass_calls: list[tuple[str, dict]] = []
        self.take_calls: list[tuple[str, dict]] = []

    async def pass_thread_control(self, recipient_id: str, metadata=None):
        self.pass_calls.append((recipient_id, metadata or {}))
        return {"status": "ok"}

    async def take_thread_control(self, recipient_id: str, metadata=None):
        self.take_calls.append((recipient_id, metadata or {}))
        return {"status": "ok"}


class FailingTransport(DummyTransport):
    """Fail when trying to pass thread control."""

    async def pass_thread_control(self, recipient_id: str, metadata=None):
        raise RuntimeError("handoff transport failed")


@pytest.mark.anyio("asyncio")
async def test_handoff_agent_updates_escalation_lifecycle() -> None:
    """Successful handoff should move escalation through in-progress to resolved."""

    session = SessionLocal()
    try:
        conversation = Conversation(
            tenant_id="tenant-a",
            user_number="+56912345678",
            role="user",
            message="Necesito ayuda",
            payload={},
        )
        session.add(conversation)
        session.commit()
        session.refresh(conversation)

        transport = DummyTransport()
        agent = HandoffAgent(
            openai_service=SimpleNamespace(),
            whatsapp_service=transport,  # type: ignore[arg-type]
            session=session,
        )

        escalation = await agent.pass_control_to_human(
            conversation=conversation,
            metadata={"reason": "manual_review"},
        )
        assert escalation.status == "in_progress"
        assert transport.pass_calls == [("+56912345678", {"reason": "manual_review"})]

        await agent.take_control_back(
            conversation=conversation,
            metadata={"reason": "resolved"},
        )

        refreshed = session.get(Escalation, escalation.id)
        assert refreshed is not None
        assert refreshed.status == "resolved"
        assert refreshed.handoff_type == "to_bot"
        assert refreshed.payload["reason"] == "resolved"
        assert transport.take_calls == [("+56912345678", {"reason": "resolved"})]

        audit_events = [row.event_type for row in session.query(AuditLog).order_by(AuditLog.id).all()]
        assert "handoff_requested" in audit_events
        assert "handoff_resolved" in audit_events
    finally:
        session.close()


@pytest.mark.anyio("asyncio")
async def test_handoff_agent_marks_failure_when_transport_fails() -> None:
    """Failed handoff transport should leave an auditable cancelled escalation."""

    session = SessionLocal()
    try:
        conversation = Conversation(
            tenant_id="tenant-a",
            user_number="+56987654321",
            role="user",
            message="Quiero hablar con alguien",
            payload={},
        )
        session.add(conversation)
        session.commit()
        session.refresh(conversation)

        agent = HandoffAgent(
            openai_service=SimpleNamespace(),
            whatsapp_service=FailingTransport(),  # type: ignore[arg-type]
            session=session,
        )

        with pytest.raises(RuntimeError):
            await agent.pass_control_to_human(
                conversation=conversation,
                metadata={"reason": "transport_failure"},
            )

        escalation = session.query(Escalation).one()
        assert escalation.status == "cancelled"
        assert "handoff transport failed" in (escalation.notes or "")

        audit_events = [row.event_type for row in session.query(AuditLog).order_by(AuditLog.id).all()]
        assert "handoff_failed" in audit_events
    finally:
        session.close()
