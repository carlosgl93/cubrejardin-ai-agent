"""Tests for the lightweight pydantic settings implementation."""

from __future__ import annotations

import importlib
import textwrap

from config.settings import Settings


def test_settings_apply_defaults(monkeypatch):
    """Defaults and environment variables should populate fields."""

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("WHATSAPP_ACCOUNT_SID", "AC123")
    monkeypatch.setenv("WHATSAPP_AUTH_TOKEN", "token123")
    monkeypatch.setenv("WHATSAPP_FROM_NUMBER", "+12345")
    monkeypatch.setenv("WEBHOOK_BASE_URL", "https://callback.example")
    monkeypatch.setenv("WHATSAPP_WEBHOOK_SECRET", "secret123")

    settings = Settings()

    assert settings.openai_api_key == "sk-test"
    assert settings.whatsapp_from_number == "+12345"
    assert settings.openai_model == "gpt-4o-mini"
    assert settings.rate_limit_per_minute == 5
    assert settings.admin_allowed_origins == ["*"]


def test_settings_default_factory_creates_new_instances(monkeypatch):
    """default_factory values should not leak between instances."""

    monkeypatch.setenv("OPENAI_API_KEY", "sk-another")
    monkeypatch.setenv("WHATSAPP_ACCOUNT_SID", "AC456")
    monkeypatch.setenv("WHATSAPP_AUTH_TOKEN", "token456")
    monkeypatch.setenv("WHATSAPP_FROM_NUMBER", "+67890")
    monkeypatch.setenv("WEBHOOK_BASE_URL", "https://example.org")
    monkeypatch.setenv("WHATSAPP_WEBHOOK_SECRET", "secret456")

    settings_one = Settings()
    settings_one.admin_allowed_origins.append("https://allowed.test")

    settings_two = Settings()
    assert settings_two.admin_allowed_origins == ["*"]


def test_settings_reload_uses_cached_env(tmp_path, monkeypatch):
    """Values from env files should be loaded when available."""

    env_file = tmp_path / ".env"
    env_file.write_text(
        textwrap.dedent(
            """
            OPENAI_API_KEY=file-key
            WHATSAPP_ACCOUNT_SID=ACFILE
            WHATSAPP_AUTH_TOKEN=file-token
            WHATSAPP_FROM_NUMBER=+1999
            WEBHOOK_BASE_URL=https://file.test
            WHATSAPP_WEBHOOK_SECRET=file-secret
            """
        ).strip()
        + "\n"
    )

    for key in (
        "OPENAI_API_KEY",
        "WHATSAPP_ACCOUNT_SID",
        "WHATSAPP_AUTH_TOKEN",
        "WHATSAPP_FROM_NUMBER",
        "WEBHOOK_BASE_URL",
        "WHATSAPP_WEBHOOK_SECRET",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.chdir(tmp_path)
    module = importlib.import_module("config.settings")
    importlib.reload(module)

    settings = module.Settings()

    assert settings.openai_api_key == "file-key"
    assert settings.whatsapp_account_sid == "ACFILE"
    assert settings.whatsapp_auth_token == "file-token"
    assert settings.whatsapp_from_number == "+1999"
    assert str(settings.webhook_base_url) == "https://file.test/"
    assert settings.webhook_secret == "file-secret"

    importlib.reload(module)
