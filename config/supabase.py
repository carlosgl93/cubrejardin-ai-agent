"""Supabase client initialization for backend (service role)."""

from functools import lru_cache

from supabase import create_client, Client

from config.settings import get_settings


@lru_cache
def get_supabase_client() -> Client:
    """Return a cached Supabase client using the service role key.

    The service role key bypasses RLS, which is required for
    server-to-server operations like webhook handlers that
    don't have a user JWT context.
    """
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
