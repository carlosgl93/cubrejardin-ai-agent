"""Global test configuration."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure project root is importable
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Minimum environment variables required by settings
_REQUIRED_ENV = {
    "OPENAI_API_KEY": "test-key",
    "WHATSAPP_PHONE_NUMBER_ID": "1234567890",
    "FACEBOOK_PAGE_ACCESS_TOKEN": "test-token",
    "FACEBOOK_APP_SECRET": "app-secret",
    "FACEBOOK_TARGET_APP_ID": "263902037430900",
    "WHATSAPP_WEBHOOK_VERIFY_TOKEN": "verify-token",
    "WEBHOOK_BASE_URL": "https://example.com",
    "DEFAULT_TEMPLATE_NAME": "session_expired",
    "TEMPLATE_MAPPING": '{"handoff":"handoff_notification"}',
    # Legacy Twilio values kept for backward compatibility in stubs/tests
    "WHATSAPP_ACCOUNT_SID": "AC00000000000000000000000000000000",
    "WHATSAPP_AUTH_TOKEN": "auth-token",
    "WHATSAPP_FROM_NUMBER": "+1234567890",
}

for env_key, env_value in _REQUIRED_ENV.items():
    os.environ.setdefault(env_key, env_value)


@pytest.fixture
def anyio_backend() -> str:
    """Force AnyIO tests to run on asyncio backend to avoid trio dependency."""

    return "asyncio"


# Ignore interactive script when collecting tests
collect_ignore_glob = ["scripts/test_conversation.py"]
