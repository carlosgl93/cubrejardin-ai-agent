from datetime import datetime, timedelta, timezone
from unittest.mock import patch

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
