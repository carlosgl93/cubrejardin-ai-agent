"""Audit logging helpers."""

from __future__ import annotations

from typing import Any, Dict, Optional

from models.database import AuditLog, SessionLocal
from utils import logger


def record_audit_event(
    *,
    tenant_id: Optional[str],
    event_type: str,
    entity_type: str,
    entity_id: Optional[str],
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    """Record an audit event.

    Audit persistence is best-effort. Operational flows should continue even if
    the audit write fails.
    """

    session = None
    try:
        session = SessionLocal()
        session.add(
            AuditLog(
                tenant_id=tenant_id,
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                payload=payload or {},
            )
        )
        session.commit()
    except Exception as exc:
        if session is not None:
            session.rollback()
        logger.warning(
            "audit_event_persist_failed",
            extra={
                "tenant_id": tenant_id,
                "event_type": event_type,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "error": str(exc),
            },
        )
    finally:
        if session is not None:
            session.close()

    logger.info(
        "audit_event",
        extra={
            "tenant_id": tenant_id,
            "event_type": event_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "payload": payload or {},
        },
    )
