"""Webhook endpoints for WhatsApp Cloud API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from agents.orchestrator import AgentOrchestrator
from api.dependencies import get_orchestrator, get_whatsapp_service
from services.whatsapp_service import WhatsAppService
from utils import OutsideMessagingWindowError, logger
from config import get_settings

router = APIRouter()
settings = get_settings()


class WhatsAppMessage(BaseModel):
    """Incoming WhatsApp message payload."""

    from_: str = Field(alias="from")
    id: str
    timestamp: str
    type: str
    text: Optional[dict] = None
    interactive: Optional[dict] = None


class WhatsAppValue(BaseModel):
    """Value object containing messages or statuses."""

    messaging_product: str
    metadata: dict
    messages: Optional[List[WhatsAppMessage]] = None
    statuses: Optional[List[dict]] = None


class WhatsAppChange(BaseModel):
    """Change entry provided by Meta."""

    value: WhatsAppValue


class WhatsAppEntry(BaseModel):
    """Single entry item."""

    id: str
    changes: List[WhatsAppChange]


class WhatsAppWebhook(BaseModel):
    """Root webhook payload."""

    object: str
    entry: List[WhatsAppEntry]


def _parse_meta_timestamp(ts: str) -> datetime:
    """Convert Meta unix timestamp strings into aware datetimes."""

    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


@router.get("/whatsapp")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_challenge: str = Query(alias="hub.challenge"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
) -> int:
    """Meta verification callback."""

    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_webhook_verify_token:
        logger.info("whatsapp_webhook_verified")
        return int(hub_challenge)
    logger.warning("whatsapp_webhook_verify_failed")
    raise HTTPException(status_code=403, detail="Invalid verify token")


@router.post("/whatsapp")
async def whatsapp_webhook(
    request: Request,
    x_hub_signature_256: str = Header(default=""),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    whatsapp_service: WhatsAppService = Depends(get_whatsapp_service),
) -> dict:
    """Handle WhatsApp webhook callbacks from Meta."""

    raw_body = await request.body()
    
    # Skip signature validation if explicitly disabled (for local testing with Meta dashboard)
    if not settings.skip_webhook_signature_validation:
        if not whatsapp_service.validate_webhook_signature(raw_body, x_hub_signature_256):
            logger.warning("whatsapp_invalid_signature")
            raise HTTPException(status_code=403, detail="Invalid signature")

    data = await request.json()
    webhook = WhatsAppWebhook.model_validate(data)
    delivery_results: List[dict] = []

    for entry in webhook.entry:
        for change in entry.changes:
            messages = change.value.messages or []
            for msg in messages:
                if msg.type == "text" and msg.text:
                    user_number = msg.from_
                    body_text = msg.text.get("body", "")
                    if not body_text:
                        continue
                    if await orchestrator.has_processed_message(msg.id):
                        continue
                    logger.info(
                        "whatsapp_message_received",
                        extra={
                            "from": user_number,
                            "phone_number": user_number,
                            "message_id": msg.id,
                            "message_text": body_text[:100],  # Log first 100 chars
                            "text": f"Message received from {user_number}"
                        },
                    )
                    whatsapp_service.record_incoming_interaction(user_number, timestamp=_parse_meta_timestamp(msg.timestamp))
                    
                    # Try to mark as read, but don't fail if it doesn't work (e.g., test messages)
                    try:
                        await whatsapp_service.mark_as_read(msg.id)
                    except Exception as mark_read_error:
                        logger.warning(
                            "whatsapp_mark_read_failed",
                            extra={"message_id": msg.id, "error": str(mark_read_error)}
                        )
                    
                    agent_response = await orchestrator.process_message(user_number, body_text, message_id=msg.id)
                    try:
                        await whatsapp_service.send_text_message(user_number, agent_response.message)
                        delivery_results.append(
                            {"user": user_number, "message_id": msg.id, "status": "delivered"}
                        )
                    except OutsideMessagingWindowError as exc:
                        logger.warning(
                            "whatsapp_send_outside_window",
                            extra={"user": user_number, "message_id": msg.id},
                        )
                        delivery_results.append(
                            {
                                "user": user_number,
                                "message_id": msg.id,
                                "status": "outside_window",
                                "detail": str(exc),
                            }
                        )
                        template = await orchestrator.handle_outside_window(user_number, agent_response)
                        delivery_results.append(
                            {
                                "user": user_number,
                                "message_id": msg.id,
                                "status": "template_sent",
                                "template": template,
                            }
                        )

    return {"status": "ok", "results": delivery_results}
