"""Webhook endpoints for WhatsApp."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from agents.orchestrator import AgentOrchestrator
from api.dependencies import get_orchestrator
from utils import logger

router = APIRouter()


@router.post("/twilio")
async def whatsapp_webhook(
    request: Request,
    x_twilio_signature: str = Header(default=""),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
) -> dict:
    """Receive WhatsApp messages from Twilio."""

    form = await request.form()
    payload = dict(form)
    user_number = payload.get("From", "")
    body = payload.get("Body", "")
    if not user_number or not body:
        raise HTTPException(status_code=400, detail="Invalid payload")
    logger.info("webhook_received", extra={"user": user_number})
    response_text = orchestrator.process_message(user_number, body)
    return {"message": response_text}
