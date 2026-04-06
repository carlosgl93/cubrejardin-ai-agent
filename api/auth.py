"""JWT authentication middleware for Supabase tokens."""

from typing import Optional

from fastapi import HTTPException, Header, status
from pydantic import BaseModel

from config.supabase import get_supabase_client


class AuthenticatedUser(BaseModel):
    """Decoded JWT claims for an authenticated user."""

    sub: str  # user UUID from Supabase auth.users
    email: Optional[str] = None
    role: Optional[str] = None


async def get_current_user(
    authorization: str = Header(..., description="Bearer <supabase_access_token>"),
) -> AuthenticatedUser:
    """Validate the Supabase JWT by calling GoTrue's get_user endpoint.

    This delegates token validation to Supabase's auth server, which
    handles algorithm detection, key verification, and expiry checks.

    Raises HTTPException 401 if the token is missing, invalid, or expired.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must start with 'Bearer'",
        )

    token = authorization[len("Bearer "):]

    try:
        client = get_supabase_client()
        user_response = client.auth.get_user(token)
        user = user_response.user
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: no user returned",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {e}",
        )

    return AuthenticatedUser(
        sub=user.id,
        email=user.email,
        role=user.role,
    )
