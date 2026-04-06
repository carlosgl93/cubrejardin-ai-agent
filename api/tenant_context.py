"""Tenant context resolution from authenticated user."""

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel

from api.auth import AuthenticatedUser, get_current_user
from config.supabase import get_supabase_client


class TenantContext(BaseModel):
    """Resolved tenant context for the current request."""

    tenant_id: str
    user_id: str
    role: str  # 'owner', 'admin', 'member'
    tenant_name: str = ""


async def get_tenant_context(
    user: AuthenticatedUser = Depends(get_current_user),
) -> TenantContext:
    """Resolve the tenant for the authenticated user.

    Looks up the tenant_users table to find which tenant the user belongs to.
    Raises HTTPException 403 if the user has no tenant.
    """
    client = get_supabase_client()

    result = (
        client.table("tenant_users")
        .select("tenant_id, role, tenants(name)")
        .eq("user_id", user.sub)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tenant associated with this user. Please complete signup.",
        )

    row = result.data[0]
    tenant_name = ""
    if row.get("tenants"):
        tenant_name = row["tenants"].get("name", "")

    return TenantContext(
        tenant_id=row["tenant_id"],
        user_id=user.sub,
        role=row["role"],
        tenant_name=tenant_name,
    )
