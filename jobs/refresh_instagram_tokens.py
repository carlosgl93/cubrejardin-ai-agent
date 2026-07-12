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


def _refresh_with_retry(current_token: str, attempts: int = 2) -> dict:
    """Try refresh once; on transient errors (5xx, network), retry once more."""
    import time
    last_err = None
    for attempt in range(attempts):
        try:
            return _refresh_token(current_token)
        except httpx.HTTPStatusError as e:
            last_err = e
            # Retry only on 5xx (server-side blip)
            if e.response.status_code < 500:
                raise
        except httpx.HTTPError as e:
            last_err = e
            # Network errors are transient — retry
        # Wait briefly between retries (linear backoff)
        if attempt < attempts - 1:
            time.sleep(1)
    raise last_err


def refresh_due_tokens() -> int:
    """Refresh all IG tokens expiring within 7 days.
    Returns number of tokens refreshed."""
    count = 0
    for row in _fetch_due_creds():
        tenant_id = row["tenant_id"]
        current = row["page_access_token"]
        try:
            new_token_data = _refresh_with_retry(current)
        except Exception as e:
            _update_creds(tenant_id, status="revoked")
            print(f"[IG refresh] revoked {tenant_id} after retry: {e}")
            continue

        expires_in = new_token_data.get("expires_in", 5184000)
        new_expires = (
            datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        ).isoformat()
        _update_creds(
            tenant_id,
            page_access_token=new_token_data["access_token"],
            token_expires_at=new_expires,
        )
        count += 1
    return count
