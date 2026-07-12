"""Tenant management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.auth import AuthenticatedUser, get_current_user
from api.tenant_context import TenantContext, get_tenant_context
from config.supabase import get_supabase_client

router = APIRouter()


class CreateTenantRequest(BaseModel):
    name: str
    slug: str


class TenantResponse(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    whatsapp_connected: bool = False
    instagram_connected: bool = False


def _fetch_whatsapp_state(tenant_id: str) -> dict:
    """Return whether the tenant has an active WhatsApp credential row."""
    supabase = get_supabase_client()
    res = (
        supabase.table("tenant_whatsapp_credentials")
        .select("status")
        .eq("tenant_id", tenant_id)
        .limit(1)
        .maybe_single()
        .execute()
    )
    return {"whatsapp_connected": bool(res.data and res.data.get("status") == "active")}


def _fetch_instagram_state(tenant_id: str) -> dict:
    """Return whether the tenant has an active Instagram credential row."""
    supabase = get_supabase_client()
    res = (
        supabase.table("tenant_instagram_credentials")
        .select("status")
        .eq("tenant_id", tenant_id)
        .limit(1)
        .maybe_single()
        .execute()
    )
    return {"instagram_connected": bool(res.data and res.data.get("status") == "active")}


@router.post("/", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    req: CreateTenantRequest,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Create a new tenant and assign the authenticated user as owner."""
    client = get_supabase_client()

    # Check if user already has a tenant
    existing = (
        client.table("tenant_users")
        .select("tenant_id")
        .eq("user_id", user.sub)
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already belongs to a tenant",
        )

    # Create tenant
    tenant_result = (
        client.table("tenants")
        .insert({"name": req.name, "slug": req.slug})
        .execute()
    )
    if not tenant_result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create tenant",
        )

    tenant = tenant_result.data[0]

    # Associate user as owner
    client.table("tenant_users").insert(
        {"user_id": user.sub, "tenant_id": tenant["id"], "role": "owner"}
    ).execute()

    return TenantResponse(
        id=tenant["id"],
        name=tenant["name"],
        slug=tenant["slug"],
        plan=tenant.get("plan", "free"),
    )


@router.get("/me", response_model=TenantResponse)
async def get_my_tenant(
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Get the tenant for the authenticated user."""
    client = get_supabase_client()

    result = (
        client.table("tenants")
        .select("id, name, slug, plan")
        .eq("id", ctx.tenant_id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    t = result.data
    wa_state = _fetch_whatsapp_state(ctx.tenant_id)
    ig_state = _fetch_instagram_state(ctx.tenant_id)
    return TenantResponse(
        id=t["id"],
        name=t["name"],
        slug=t["slug"],
        plan=t.get("plan", "free"),
        whatsapp_connected=wa_state["whatsapp_connected"],
        instagram_connected=ig_state["instagram_connected"],
    )


class BotConfigRequest(BaseModel):
    system_prompt: str | None = None
    greeting: str | None = None
    handoff_trigger: str | None = None
    business_hours: dict | None = None


class BotConfigResponse(BaseModel):
    id: str
    tenant_id: str
    system_prompt: str | None
    greeting: str | None
    handoff_trigger: str | None
    business_hours: dict


@router.get("/config", response_model=BotConfigResponse)
async def get_bot_config(ctx: TenantContext = Depends(get_tenant_context)):
    """Get bot configuration for the tenant."""
    sb = get_supabase_client()
    result = (
        sb.table("tenant_bot_config")
        .select("*")
        .eq("tenant_id", ctx.tenant_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        # Return empty defaults — config not yet saved
        return BotConfigResponse(
            id="",
            tenant_id=ctx.tenant_id,
            system_prompt=None,
            greeting=None,
            handoff_trigger=None,
            business_hours={"enabled": False, "timezone": "America/Santiago", "schedule": {}},
        )
    row = result.data[0]
    return BotConfigResponse(
        id=row["id"],
        tenant_id=row["tenant_id"],
        system_prompt=row.get("system_prompt"),
        greeting=row.get("greeting"),
        handoff_trigger=row.get("handoff_trigger"),
        business_hours=row.get("business_hours") or {},
    )


@router.put("/config", response_model=BotConfigResponse)
async def upsert_bot_config(
    body: BotConfigRequest,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Create or update bot configuration. Owner/admin only."""
    if ctx.role not in ("owner", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")

    sb = get_supabase_client()
    payload = {
        "tenant_id": ctx.tenant_id,
        **{k: v for k, v in body.model_dump().items() if v is not None},
    }
    result = (
        sb.table("tenant_bot_config")
        .upsert(payload, on_conflict="tenant_id")
        .execute()
    )
    row = result.data[0]
    return BotConfigResponse(
        id=row["id"],
        tenant_id=row["tenant_id"],
        system_prompt=row.get("system_prompt"),
        greeting=row.get("greeting"),
        handoff_trigger=row.get("handoff_trigger"),
        business_hours=row.get("business_hours") or {},
    )
