from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx

from jobs.refresh_instagram_tokens import refresh_due_tokens


def test_refresh_updates_expiring_tokens():
    expires_soon = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    fake_creds = [{
        "tenant_id": "T_1",
        "page_access_token": "OLD_TOKEN",
        "token_expires_at": expires_soon,
    }]
    with patch("jobs.refresh_instagram_tokens._fetch_due_creds", return_value=fake_creds), \
         patch("jobs.refresh_instagram_tokens._refresh_token", return_value={
             "access_token": "NEW_TOKEN",
             "expires_in": 5184000,
         }), \
         patch("jobs.refresh_instagram_tokens._update_creds") as update:
        refresh_due_tokens()
    update.assert_called_once()
    args, kwargs = update.call_args
    assert kwargs["page_access_token"] == "NEW_TOKEN"


def test_revokes_after_retry_exhausted():
    expires_soon = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    fake_creds = [{
        "tenant_id": "T_FAIL",
        "page_access_token": "BAD_TOKEN",
        "token_expires_at": expires_soon,
    }]
    network_err = httpx.ConnectError("boom")
    with patch("jobs.refresh_instagram_tokens._fetch_due_creds", return_value=fake_creds), \
         patch("jobs.refresh_instagram_tokens._refresh_token", side_effect=network_err), \
         patch("jobs.refresh_instagram_tokens._update_creds") as update:
        refresh_due_tokens()
    update.assert_called_once()
    args, kwargs = update.call_args
    assert kwargs["status"] == "revoked"


def test_revokes_on_non_retryable_4xx_after_one_attempt():
    """4xx should NOT retry - bad token is bad token."""
    expires_soon = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    fake_creds = [{
        "tenant_id": "T_4XX",
        "page_access_token": "BAD_TOKEN",
        "token_expires_at": expires_soon,
    }]
    resp = httpx.Response(400, request=httpx.Request("GET", "https://x"))
    err = httpx.HTTPStatusError("bad", request=resp.request, response=resp)
    with patch("jobs.refresh_instagram_tokens._fetch_due_creds", return_value=fake_creds), \
         patch("jobs.refresh_instagram_tokens._refresh_token", side_effect=err) as refresh, \
         patch("jobs.refresh_instagram_tokens._update_creds") as update:
        refresh_due_tokens()
    assert refresh.call_count == 1
    update.assert_called_once()
    args, kwargs = update.call_args
    assert kwargs["status"] == "revoked"