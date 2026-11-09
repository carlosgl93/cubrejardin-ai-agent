"""JWT authentication middleware for Supabase tokens."""

import time
from typing import Optional, Tuple

import jwt
from fastapi import HTTPException, Header, status
from pydantic import BaseModel

from config.supabase import get_supabase_client
from config.settings import get_settings
from utils import logger


class AuthenticatedUser(BaseModel):
    """Decoded JWT claims for an authenticated user."""

    sub: str  # user UUID from Supabase auth.users
    email: Optional[str] = None
    role: Optional[str] = None
    is_super_admin: bool = False


_USER_CACHE: dict[str, Tuple[AuthenticatedUser, float]] = {}
_USER_CACHE_TTL = 60.0  # seconds


async def get_current_user(
    authorization: str = Header(..., description="Bearer <supabase_access_token>"),
) -> AuthenticatedUser:
    """Validate the Supabase JWT.

    Tries local verification first with SUPABASE_JWT_SECRET to prevent network
    timeouts and external HTTP overhead. Falls back to GoTrue's get_user endpoint
    if local verification fails or secret is not configured.

    Raises HTTPException 401 if the token is missing, invalid, or expired.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must start with 'Bearer'",
        )

    token = authorization[len("Bearer "):].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: empty token",
        )

    now = time.monotonic()
    cached = _USER_CACHE.get(token)
    if cached and cached[1] > now:
        return cached[0]

    settings = get_settings()
    admin_emails = [e.strip() for e in settings.super_admin_emails.split(",") if e.strip()]

    # 1. Try fast local JWT verification
    payload = None
    if settings.supabase_jwt_secret:
        try:
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token: Signature has expired",
            )
        except Exception as jwt_err:
            logger.debug("local_jwt_decode_fallback", extra={"error": str(jwt_err)})
            payload = None

    if payload and payload.get("sub"):
        user_sub = str(payload["sub"])
        user_email = payload.get("email")
        user_role = payload.get("role")
        auth_user = AuthenticatedUser(
            sub=user_sub,
            email=user_email,
            role=user_role,
            is_super_admin=bool(user_email and user_email in admin_emails),
        )
        _USER_CACHE[token] = (auth_user, now + _USER_CACHE_TTL)
        return auth_user

    # 2. Fallback to Supabase GoTrue endpoint
    try:
        client = get_supabase_client()
        user_response = client.auth.get_user(token)
        user = user_response.user
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: no user returned",
            )
        auth_user = AuthenticatedUser(
            sub=user.id,
            email=user.email,
            role=user.role,
            is_super_admin=bool(user.email and user.email in admin_emails),
        )
        _USER_CACHE[token] = (auth_user, now + _USER_CACHE_TTL)
        return auth_user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {e}",
        )
