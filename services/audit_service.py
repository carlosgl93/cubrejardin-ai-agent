"""Audit event recording stub."""

from __future__ import annotations

from typing import Any, Dict, Optional

from utils import logger


def record_audit_event(
    *,
    tenant_id: Optional[str],
    event_type: str,
    entity_type: str,
    entity_id: str,
    payload: Dict[str, Any],
) -> None:
    logger.info(
        "audit_event",
        extra={
            "tenant_id": tenant_id,
            "event_type": event_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "payload": payload,
        },
    )
