"""Conversations list endpoint — used by the inbox UI.

Returns one row per (channel, channel_user_id) pair, grouped from raw
``conversations`` rows. Supports optional ``?channel=`` filter so the
inbox tab (WhatsApp | Instagram | All) can scope the response.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.tenant_context import TenantContext, get_tenant_context
from config.supabase import get_supabase_client

router = APIRouter(prefix="/api", tags=["conversations"])


def _list_contacts(tenant_id: str, channel: Optional[str]) -> list[dict]:
    """Return one grouped contact per (channel, channel_user_id) pair.

    Channel column comes from migration 006_instagram_channel.sql. Empty /
    ``None`` channel param returns contacts from all channels.
    """
    supabase = get_supabase_client()
    q = (
        supabase.table("conversations")
        .select("channel, channel_user_id, message, created_at")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .limit(1000)
    )
    if channel:
        q = q.eq("channel", channel)
    rows = q.execute().data or []

    grouped: dict[tuple[str, str], dict] = {}
    for r in rows:
        key = (r["channel"], r["channel_user_id"])
        if key not in grouped:
            grouped[key] = {
                "channel": r["channel"],
                "channel_user_id": r["channel_user_id"],
                "last_message": r["message"],
                "last_at": r["created_at"],
                "count": 1,
            }
        else:
            grouped[key]["count"] += 1
    return list(grouped.values())


@router.get("/conversations")
async def list_conversations(
    channel: Optional[str] = Query(default=None, description="Filter by channel: 'whatsapp' | 'instagram'. Omit for all."),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """List recent conversation contacts for the current tenant."""
    contacts = _list_contacts(tenant_id=ctx.tenant_id, channel=channel)
    return {"contacts": contacts}