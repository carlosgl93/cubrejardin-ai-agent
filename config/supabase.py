"""Supabase client initialization for backend (service role)."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any

from config.settings import get_settings

if TYPE_CHECKING:
    from supabase import Client
else:
    Client = Any


@lru_cache
def get_supabase_client() -> Client:
    """Return a cached Supabase client using the service role key.

    The service role key bypasses RLS, which is required for
    server-to-server operations like webhook handlers that
    don't have a user JWT context.
    """
    from supabase import create_client

    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
