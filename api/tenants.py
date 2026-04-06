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
    return TenantResponse(id=t["id"], name=t["name"], slug=t["slug"], plan=t.get("plan", "free"))
