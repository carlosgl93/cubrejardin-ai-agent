"""Test configuration."""

from __future__ import annotations

import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_REQUIRED_ENV = {
    "OPENAI_API_KEY": "test-key",
    "WHATSAPP_ACCOUNT_SID": "AC00000000000000000000000000000000",
    "WHATSAPP_AUTH_TOKEN": "auth-token",
    "WHATSAPP_FROM_NUMBER": "+1234567890",
    "WEBHOOK_BASE_URL": "https://example.com",
    "WHATSAPP_WEBHOOK_SECRET": "secret",
}

for env_key, env_value in _REQUIRED_ENV.items():
    os.environ.setdefault(env_key, env_value)

collect_ignore_glob = ["scripts/test_conversation.py"]
