from datetime import datetime, timedelta, timezone

import httpx

from channels.instagram import GRAPH_BASE


def _fetch_due_creds() -> list[dict]:
    from config.supabase import get_supabase_client
    supabase = get_supabase_client()
    threshold = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    res = (
        supabase.table("tenant_instagram_credentials")
        .select("tenant_id, page_access_token, token_expires_at")
        .eq("status", "active")
        .lte("token_expires_at", threshold)
        .execute()
    )
    return res.data or []


def _refresh_token(current_token: str) -> dict:
    from config.settings import get_settings
    settings = get_settings()
    app_id = settings.facebook_target_app_id
    app_secret = settings.facebook_app_secret
    resp = httpx.get(
        f"{GRAPH_BASE}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": current_token,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _update_creds(tenant_id: str, **updates) -> None:
    from config.supabase import get_supabase_client
    supabase = get_supabase_client()
    supabase.table("tenant_instagram_credentials").update(updates).eq(
        "tenant_id", tenant_id
    ).execute()


def refresh_due_tokens() -> int:
    """Refresh all IG tokens expiring within 7 days.
    Returns number of tokens refreshed."""
    count = 0
    for row in _fetch_due_creds():
        tenant_id = row["tenant_id"]
        current = row["page_access_token"]
        try:
            result = _refresh_token(current)
            new_token = result["access_token"]
            expires_in = result.get("expires_in", 5184000)
            new_expires = (
                datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            ).isoformat()
            _update_creds(
                tenant_id,
                page_access_token=new_token,
                token_expires_at=new_expires,
            )
            count += 1
        except Exception as e:
            # Mark second failure path: skip after first retry
            _update_creds(tenant_id, status="revoked")
            print(f"[IG refresh] revoked {tenant_id}: {e}")
    return count
