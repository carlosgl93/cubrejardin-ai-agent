"""Handoff management endpoints — used by the conversations UI."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.tenant_context import TenantContext, get_tenant_context
from config.supabase import get_supabase_client
from utils import logger
from services.whatsapp_service import WhatsAppService

router = APIRouter()


class ReplyRequest(BaseModel):
    message: str


def _get_tenant_token(tenant_id: str) -> str:
    sb = get_supabase_client()
    result = (
        sb.table("tenant_whatsapp_credentials")
        .select("access_token")
        .eq("tenant_id", tenant_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    return result.data[0]["access_token"] if result.data else ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/")
async def list_handoffs(ctx: TenantContext = Depends(get_tenant_context)):
    """List active handoffs for the tenant."""
    sb = get_supabase_client()
    result = (
        sb.table("handoffs")
        .select("*")
        .eq("tenant_id", ctx.tenant_id)
        .eq("status", "active")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


@router.get("/history")
async def list_handoff_history(ctx: TenantContext = Depends(get_tenant_context)):
    """List closed/expired handoffs with resolution data."""
    sb = get_supabase_client()
    result = (
        sb.table("handoffs")
        .select("*")
        .eq("tenant_id", ctx.tenant_id)
        .in_("status", ["closed", "expired"])
        .order("closed_at", desc=True)
        .limit(100)
        .execute()
    )
    return result.data


@router.get("/stats")
async def handoff_stats(ctx: TenantContext = Depends(get_tenant_context)):
    """Summary stats for analytics."""
    sb = get_supabase_client()
    all_rows = (
        sb.table("handoffs")
        .select("status, created_at, closed_at, first_response_at, closed_by, message_count")
        .eq("tenant_id", ctx.tenant_id)
        .execute()
    ).data

    total = len(all_rows)
    active = sum(1 for r in all_rows if r["status"] == "active")
    closed = sum(1 for r in all_rows if r["status"] == "closed")
    expired = sum(1 for r in all_rows if r["status"] == "expired")

    durations = []
    response_times = []
    for r in all_rows:
        if r.get("closed_at") and r.get("created_at"):
            d = (datetime.fromisoformat(r["closed_at"].replace("Z", "+00:00")) -
                 datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))).total_seconds() / 60
            durations.append(d)
        if r.get("first_response_at") and r.get("created_at"):
            rt = (datetime.fromisoformat(r["first_response_at"].replace("Z", "+00:00")) -
                  datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))).total_seconds() / 60
            response_times.append(rt)

    closed_by_counts: dict = {}
    for r in all_rows:
        if r.get("closed_by"):
            closed_by_counts[r["closed_by"]] = closed_by_counts.get(r["closed_by"], 0) + 1

    return {
        "total": total,
        "active": active,
        "closed": closed,
        "expired": expired,
        "avg_duration_minutes": round(sum(durations) / len(durations), 1) if durations else None,
        "avg_first_response_minutes": round(sum(response_times) / len(response_times), 1) if response_times else None,
        "closed_by": closed_by_counts,
        "avg_messages": round(sum(r.get("message_count", 0) for r in all_rows) / total, 1) if total else None,
    }


@router.post("/{handoff_id}/reply")
async def reply_to_handoff(
    handoff_id: str,
    body: ReplyRequest,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Send a reply from the human agent to the WhatsApp user."""
    sb = get_supabase_client()
    result = (
        sb.table("handoffs")
        .select("*")
        .eq("id", handoff_id)
        .eq("tenant_id", ctx.tenant_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Handoff not found or already closed")

    handoff = result.data[0]
    wa = WhatsAppService(
        phone_id=handoff["wa_service_phone_id"],
        token=_get_tenant_token(ctx.tenant_id),
    )
    try:
        await wa.send_text_message(handoff["whatsapp_number"], body.message, skip_window_check=True)
    finally:
        await wa.close()

    sb.table("conversations").insert({
        "tenant_id": ctx.tenant_id,
        "channel": "whatsapp",
        "channel_user_id": handoff["whatsapp_number"],
        "role": "assistant",
        "message": body.message,
        "metadata": {"source": "human_agent"},
    }).execute()

    now = _now()
    update: dict = {
        "updated_at": now,
        "message_count": (handoff.get("message_count") or 0) + 1,
    }
    if not handoff.get("first_response_at"):
        update["first_response_at"] = now

    sb.table("handoffs").update(update).eq("id", handoff_id).execute()

    logger.info("handoff_replied_via_ui", extra={"handoff_id": handoff_id, "to": handoff["whatsapp_number"]})
    return {"status": "sent"}


@router.post("/{handoff_id}/close")
async def close_handoff(
    handoff_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Close an active handoff, returning control to the bot."""
    sb = get_supabase_client()
    result = (
        sb.table("handoffs")
        .select("id, whatsapp_number, message_count")
        .eq("id", handoff_id)
        .eq("tenant_id", ctx.tenant_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Handoff not found")

    now = _now()
    sb.table("handoffs").update({
        "status": "closed",
        "closed_at": now,
        "closed_by": "agent_ui",
    }).eq("id", handoff_id).execute()

    logger.info("handoff_closed_via_ui", extra={"handoff_id": handoff_id})
    return {"status": "closed"}
