"""Tests for the lightweight pydantic settings implementation."""

from __future__ import annotations

import importlib
import textwrap

from config.settings import Settings


def test_settings_apply_defaults(monkeypatch):
    """Defaults and environment variables should populate fields."""

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "1234567890")
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "token123")
    monkeypatch.setenv("FACEBOOK_APP_SECRET", "appsecret")
    monkeypatch.setenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "verify-token")
    monkeypatch.setenv("WEBHOOK_BASE_URL", "https://callback.example")
    monkeypatch.setenv("DEFAULT_TEMPLATE_NAME", "session_expired")
    monkeypatch.setenv("TEMPLATE_MAPPING", '{"handoff":"handoff_notification"}')

    settings = Settings()

    assert settings.openai_api_key == "sk-test"
    assert settings.whatsapp_phone_number_id == "1234567890"
    assert settings.openai_model == "gpt-4o-mini"
    assert settings.rate_limit_per_minute == 5
    assert settings.admin_allowed_origins == ["*"]
    assert settings.default_template_name == "session_expired"
    assert settings.template_mapping["handoff"] == "handoff_notification"


def test_settings_default_factory_creates_new_instances(monkeypatch):
    """default_factory values should not leak between instances."""

    monkeypatch.setenv("OPENAI_API_KEY", "sk-another")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "67890")
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "token456")
    monkeypatch.setenv("FACEBOOK_APP_SECRET", "othersecret")
    monkeypatch.setenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "verify-token-2")
    monkeypatch.setenv("WEBHOOK_BASE_URL", "https://example.org")
    monkeypatch.setenv("DEFAULT_TEMPLATE_NAME", "session_expired")
    monkeypatch.setenv("TEMPLATE_MAPPING", '{"default":"session_expired"}')

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
            WHATSAPP_PHONE_NUMBER_ID=9999
            FACEBOOK_PAGE_ACCESS_TOKEN=file-token
            FACEBOOK_APP_SECRET=file-secret
            WHATSAPP_WEBHOOK_VERIFY_TOKEN=file-verify
            WEBHOOK_BASE_URL=https://file.test
            DEFAULT_TEMPLATE_NAME=session_expired
            TEMPLATE_MAPPING={"handoff":"handoff_notification"}
            """
        ).strip()
        + "\n"
    )

    for key in (
        "OPENAI_API_KEY",
        "WHATSAPP_PHONE_NUMBER_ID",
        "FACEBOOK_PAGE_ACCESS_TOKEN",
        "FACEBOOK_APP_SECRET",
        "WHATSAPP_WEBHOOK_VERIFY_TOKEN",
        "WEBHOOK_BASE_URL",
        "DEFAULT_TEMPLATE_NAME",
        "TEMPLATE_MAPPING",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.chdir(tmp_path)
    module = importlib.import_module("config.settings")
    importlib.reload(module)

    settings = module.Settings()

    assert settings.openai_api_key == "file-key"
    assert settings.whatsapp_phone_number_id == "9999"
    assert settings.facebook_page_access_token == "file-token"
    assert settings.facebook_app_secret == "file-secret"
    assert str(settings.webhook_base_url) == "https://file.test/"
    assert settings.whatsapp_webhook_verify_token == "file-verify"
    assert settings.default_template_name == "session_expired"
    assert settings.template_mapping["handoff"] == "handoff_notification"

    importlib.reload(module)
