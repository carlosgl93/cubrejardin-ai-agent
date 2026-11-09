"""Tests for local JWT decoding and auth fallback."""

import time
import jwt
import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock, patch

from api.auth import get_current_user, _USER_CACHE
from config.settings import Settings


@pytest.fixture(autouse=True)
def clear_cache():
    _USER_CACHE.clear()
    yield
    _USER_CACHE.clear()


@pytest.mark.asyncio
async def test_get_current_user_local_jwt_success():
    secret = "test-secret-key-that-is-long-enough-32-chars-long"
    payload = {
        "sub": "user-uuid-1234",
        "email": "agent@example.com",
        "role": "authenticated",
        "aud": "authenticated",
        "exp": int(time.time()) + 3600,
    }
    token = jwt.encode(payload, secret, algorithm="HS256")

    mock_settings = MagicMock()
    mock_settings.supabase_jwt_secret = secret
    mock_settings.super_admin_emails = "admin@example.com"

    with patch("api.auth.get_settings", return_value=mock_settings):
        user = await get_current_user(f"Bearer {token}")
        assert user.sub == "user-uuid-1234"
        assert user.email == "agent@example.com"
        assert user.role == "authenticated"
        assert user.is_super_admin is False

        # Fast cache hit
        user_cached = await get_current_user(f"Bearer {token}")
        assert user_cached is user


@pytest.mark.asyncio
async def test_get_current_user_expired_jwt():
    secret = "test-secret-key-that-is-long-enough-32-chars-long"
    payload = {
        "sub": "user-uuid-1234",
        "exp": int(time.time()) - 100,
    }
    token = jwt.encode(payload, secret, algorithm="HS256")

    mock_settings = MagicMock()
    mock_settings.supabase_jwt_secret = secret

    with patch("api.auth.get_settings", return_value=mock_settings):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(f"Bearer {token}")
        assert exc_info.value.status_code == 401
        assert "Signature has expired" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_fallback_to_gotrue():
    secret = "test-secret-key-that-is-long-enough-32-chars-long"
    # Token with different secret to trigger fallback
    token = jwt.encode({"sub": "user-uuid-5678"}, "wrong-secret-that-is-at-least-32-bytes-long", algorithm="HS256")

    mock_settings = MagicMock()
    mock_settings.supabase_jwt_secret = secret
    mock_settings.super_admin_emails = ""

    mock_sb = MagicMock()
    mock_user = MagicMock()
    mock_user.id = "user-uuid-5678"
    mock_user.email = "gotrue@example.com"
    mock_user.role = "authenticated"
    mock_sb.auth.get_user.return_value.user = mock_user

    with patch("api.auth.get_settings", return_value=mock_settings), \
         patch("api.auth.get_supabase_client", return_value=mock_sb):
        user = await get_current_user(f"Bearer {token}")
        assert user.sub == "user-uuid-5678"
        assert user.email == "gotrue@example.com"
        mock_sb.auth.get_user.assert_called_once_with(token)
