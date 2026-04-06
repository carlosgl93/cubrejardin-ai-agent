"""Webhook endpoints for WhatsApp Cloud API."""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from agents.orchestrator import AgentOrchestrator
from api.dependencies import get_facebook_messenger_service, get_openai_service, get_orchestrator
from config import get_settings
from config.supabase import get_supabase_client
from models.database import SessionLocal
from services.facebook_messenger_service import FacebookMessengerService
from services.openai_service import OpenAIService
from services.template_service import TemplateService
from services.vector_store import VectorStoreService
from services.whatsapp_service import WhatsAppService
from utils import OutsideMessagingWindowError, logger

router = APIRouter()
settings = get_settings()


def _validate_whatsapp_signature(payload: bytes, signature: str) -> bool:
    """Validate X-Hub-Signature-256 using the shared app secret."""
    if not signature:
        return False
    expected = hmac.new(
        settings.facebook_app_secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    provided = signature.split("=", 1)[1] if "=" in signature else signature
    return hmac.compare_digest(expected, provided)


def _resolve_tenant_credentials(phone_number_id: str) -> Optional[dict]:
    """Look up active tenant credentials for a given phone_number_id."""
    sb = get_supabase_client()
    result = (
        sb.table("tenant_whatsapp_credentials")
        .select("tenant_id, phone_number_id, access_token")
        .eq("phone_number_id", phone_number_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


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
    openai_service: OpenAIService = Depends(get_openai_service),
) -> dict:
    """Handle WhatsApp webhook callbacks from Meta."""

    raw_body = await request.body()

    if not settings.skip_webhook_signature_validation:
        if not _validate_whatsapp_signature(raw_body, x_hub_signature_256):
            logger.warning("whatsapp_invalid_signature")
            raise HTTPException(status_code=403, detail="Invalid signature")

    data = await request.json()
    webhook = WhatsAppWebhook.model_validate(data)
    delivery_results: List[dict] = []

    for entry in webhook.entry:
        for change in entry.changes:
            # Resolve tenant from the phone number that received the message
            phone_number_id = change.value.metadata.get("phone_number_id", "")
            tenant_creds = _resolve_tenant_credentials(phone_number_id)
            if not tenant_creds:
                logger.warning(
                    "whatsapp_webhook_unknown_phone_id",
                    extra={"phone_number_id": phone_number_id},
                )
                continue

            tenant_id = tenant_creds["tenant_id"]
            wa_service = WhatsAppService(
                phone_id=tenant_creds["phone_number_id"],
                token=tenant_creds["access_token"],
            )
            tenant_vector_store = VectorStoreService(tenant_id=tenant_id)
            orchestrator = AgentOrchestrator(
                session=SessionLocal(),
                openai_service=openai_service,
                vector_store=tenant_vector_store,
                whatsapp_service=wa_service,
                template_service=TemplateService(whatsapp_service=wa_service),
            )

            try:
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
                                "tenant_id": tenant_id,
                                "from": user_number,
                                "phone_number": user_number,
                                "message_id": msg.id,
                                "message_text": body_text[:100],
                                "text": f"Message received from {user_number}",
                            },
                        )
                        wa_service.record_incoming_interaction(
                            user_number, timestamp=_parse_meta_timestamp(msg.timestamp)
                        )

                        try:
                            await wa_service.mark_as_read(msg.id)
                        except Exception as mark_read_error:
                            logger.warning(
                                "whatsapp_mark_read_failed",
                                extra={"message_id": msg.id, "error": str(mark_read_error)},
                            )

                        agent_response = await orchestrator.process_message(
                            user_number, body_text, message_id=msg.id
                        )
                        try:
                            await wa_service.send_text_message(user_number, agent_response.message)
                            delivery_results.append(
                                {"tenant_id": tenant_id, "user": user_number, "message_id": msg.id, "status": "delivered"}
                            )
                        except OutsideMessagingWindowError as exc:
                            logger.warning(
                                "whatsapp_send_outside_window",
                                extra={"user": user_number, "message_id": msg.id},
                            )
                            delivery_results.append(
                                {
                                    "tenant_id": tenant_id,
                                    "user": user_number,
                                    "message_id": msg.id,
                                    "status": "outside_window",
                                    "detail": str(exc),
                                }
                            )
                            template = await orchestrator.handle_outside_window(user_number, agent_response)
                            delivery_results.append(
                                {
                                    "tenant_id": tenant_id,
                                    "user": user_number,
                                    "message_id": msg.id,
                                    "status": "template_sent",
                                    "template": template,
                                }
                            )
                        except Exception as send_error:
                            logger.error(
                                "whatsapp_send_failed",
                                extra={
                                    "tenant_id": tenant_id,
                                    "user": user_number,
                                    "message_id": msg.id,
                                    "error": str(send_error),
                                },
                            )
                            delivery_results.append(
                                {"tenant_id": tenant_id, "user": user_number, "message_id": msg.id, "status": "send_failed", "error": str(send_error)}
                            )
            finally:
                await wa_service.close()

    return {"status": "ok", "results": delivery_results}


# ============================================================================
# Facebook Messenger Webhooks
# ============================================================================


class MessengerMessage(BaseModel):
    """Incoming Messenger message."""

    mid: str
    text: Optional[str] = None


class MessengerSender(BaseModel):
    """Messenger sender information."""

    id: str


class MessengerRecipient(BaseModel):
    """Messenger recipient information."""

    id: str


class MessengerMessaging(BaseModel):
    """Messenger messaging event."""

    sender: MessengerSender
    recipient: MessengerRecipient
    timestamp: int
    message: Optional[MessengerMessage] = None


class MessengerEntry(BaseModel):
    """Messenger webhook entry."""

    id: str
    time: int
    messaging: List[MessengerMessaging]


class MessengerWebhook(BaseModel):
    """Facebook Messenger webhook payload."""

    object: str
    entry: List[MessengerEntry]


@router.get("/facebook")
async def verify_facebook_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_challenge: str = Query(alias="hub.challenge"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
) -> int:
    """Facebook Messenger verification callback."""

    if hub_mode == "subscribe" and hub_verify_token == settings.facebook_messenger_verify_token:
        logger.info("facebook_messenger_webhook_verified")
        return int(hub_challenge)
    logger.warning("facebook_messenger_webhook_verify_failed")
    raise HTTPException(status_code=403, detail="Invalid verify token")


@router.post("/facebook")
async def facebook_messenger_webhook(
    request: Request,
    x_hub_signature_256: str = Header(default=""),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    messenger_service: FacebookMessengerService = Depends(get_facebook_messenger_service),
) -> dict:
    """Handle Facebook Messenger webhook callbacks."""

    raw_body = await request.body()
    
    # Validate webhook signature
    if not settings.skip_webhook_signature_validation:
        if not messenger_service.validate_webhook_signature(raw_body, x_hub_signature_256):
            logger.warning("facebook_messenger_invalid_signature")
            raise HTTPException(status_code=403, detail="Invalid signature")

    data = await request.json()
    webhook = MessengerWebhook.model_validate(data)
    delivery_results: List[dict] = []

    for entry in webhook.entry:
        for messaging_event in entry.messaging:
            # Only process text messages
            if not messaging_event.message or not messaging_event.message.text:
                continue
            
            sender_id = messaging_event.sender.id
            message_text = messaging_event.message.text
            message_id = messaging_event.message.mid
            
            # Check if already processed
            if await orchestrator.has_processed_message(message_id):
                continue
            
            logger.info(
                "facebook_messenger_message_received",
                extra={
                    "from": sender_id,
                    "user_id": sender_id,
                    "message_id": message_id,
                    "message_text": message_text[:100],
                    "text": f"Message received from {sender_id}"
                },
            )
            
            # Record interaction timestamp
            messenger_service.record_incoming_interaction(
                sender_id,
                timestamp=_parse_meta_timestamp(str(messaging_event.timestamp))
            )
            
            # Send typing indicator
            try:
                await messenger_service.send_typing_action(sender_id, "typing_on")
            except Exception as typing_error:
                logger.warning(
                    "facebook_messenger_typing_failed",
                    extra={"user_id": sender_id, "error": str(typing_error)}
                )
            
            # Process message through orchestrator
            agent_response = await orchestrator.process_message(
                sender_id,
                message_text,
                message_id=message_id
            )
            
            # Send response
            try:
                await messenger_service.send_text_message(sender_id, agent_response.message)
                delivery_results.append({
                    "user": sender_id,
                    "message_id": message_id,
                    "status": "delivered"
                })
            except Exception as send_error:
                logger.error(
                    "facebook_messenger_send_failed",
                    extra={
                        "user": sender_id,
                        "message_id": message_id,
                        "error": str(send_error)
                    }
                )
                delivery_results.append({
                    "user": sender_id,
                    "message_id": message_id,
                    "status": "failed",
                    "error": str(send_error)
                })

    return {"status": "ok", "results": delivery_results}
