"""Backoffice endpoints — super-admin only."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.auth import AuthenticatedUser, get_current_user
from config.supabase import get_supabase_client

router = APIRouter()


def require_super_admin(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    if not user.is_super_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super-admin required")
    return user


class TenantSummary(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    owner_email: str | None = None
    created_at: str | None = None


class CreateTenantAdminRequest(BaseModel):
    name: str
    slug: str
    owner_email: str


@router.get("/tenants", response_model=list[TenantSummary])
async def list_all_tenants(admin: AuthenticatedUser = Depends(require_super_admin)):
    """List all tenants with owner info."""
    sb = get_supabase_client()
    result = (
        sb.table("tenants")
        .select("id, name, slug, plan, created_at")
        .order("created_at", desc=True)
        .execute()
    )
    tenants = result.data or []

    # Fetch owner emails via tenant_users
    tenant_ids = [t["id"] for t in tenants]
    if tenant_ids:
        users_result = (
            sb.table("tenant_users")
            .select("tenant_id, user_id, role")
            .in_("tenant_id", tenant_ids)
            .eq("role", "owner")
            .execute()
        )
        owner_map = {r["tenant_id"]: r["user_id"] for r in (users_result.data or [])}
    else:
        owner_map = {}

    summaries = []
    for t in tenants:
        owner_user_id = owner_map.get(t["id"])
        owner_email = None
        if owner_user_id:
            try:
                u = sb.auth.admin.get_user_by_id(owner_user_id)
                owner_email = u.user.email if u and u.user else None
            except Exception:
                pass
        summaries.append(TenantSummary(
            id=t["id"],
            name=t["name"],
            slug=t["slug"],
            plan=t.get("plan", "free"),
            owner_email=owner_email,
            created_at=t.get("created_at"),
        ))

    return summaries


@router.post("/tenants", response_model=TenantSummary, status_code=status.HTTP_201_CREATED)
async def create_tenant_for_client(
    body: CreateTenantAdminRequest,
    admin: AuthenticatedUser = Depends(require_super_admin),
):
    """Create a tenant and invite an owner by email (backoffice path)."""
    sb = get_supabase_client()

    # Create tenant
    tenant_result = sb.table("tenants").insert({"name": body.name, "slug": body.slug}).execute()
    if not tenant_result.data:
        raise HTTPException(status_code=500, detail="Failed to create tenant")
    tenant = tenant_result.data[0]

    # Look up or invite the owner user
    try:
        users = sb.auth.admin.list_users()
        owner_user = next((u for u in users if u.email == body.owner_email), None)
    except Exception:
        owner_user = None

    if owner_user:
        sb.table("tenant_users").insert({
            "user_id": owner_user.id,
            "tenant_id": tenant["id"],
            "role": "owner",
        }).execute()

    return TenantSummary(
        id=tenant["id"],
        name=tenant["name"],
        slug=tenant["slug"],
        plan=tenant.get("plan", "free"),
        owner_email=body.owner_email if owner_user else None,
        created_at=tenant.get("created_at"),
    )
