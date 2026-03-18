"""Application settings module."""

from functools import lru_cache
from typing import Dict, List

from pydantic import Field
from pydantic.networks import HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration values loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="",
    )

    app_name: str = "WhatsApp AI Agent"
    environment: str = "development"
    debug: bool = Field(False, validation_alias="DEBUG")

    # 🔑 OpenAI
    openai_api_key: str = Field(..., validation_alias="OPENAI_API_KEY")
    openai_model: str = "gpt-4o-mini"   # estable
    openai_temperature: float = 0.2
    embedding_model: str = "text-embedding-3-small"

    # 📦 Infra
    database_url: str = "postgresql+psycopg://postgres:postgres@db:5432/whatsapp"
    redis_url: str = "redis://redis:6379/0"

    # 📱 WhatsApp / Meta
    whatsapp_phone_number_id: str = Field(..., validation_alias="WHATSAPP_PHONE_NUMBER_ID")
    facebook_page_access_token: str = Field(..., validation_alias="FACEBOOK_PAGE_ACCESS_TOKEN")
    facebook_app_secret: str = Field(..., validation_alias="FACEBOOK_APP_SECRET")
    facebook_target_app_id: str = Field("263902037430900", validation_alias="FACEBOOK_TARGET_APP_ID")
    whatsapp_webhook_verify_token: str = Field(..., validation_alias="WHATSAPP_WEBHOOK_VERIFY_TOKEN")
    skip_webhook_signature_validation: bool = Field(False, validation_alias="SKIP_WEBHOOK_SIGNATURE_VALIDATION")
    skip_messaging_window_check: bool = Field(False, validation_alias="SKIP_MESSAGING_WINDOW_CHECK")
    
    # 💬 Facebook Messenger
    facebook_messenger_page_token: str = Field(..., validation_alias="FACEBOOK_MESSENGER_PAGE_TOKEN")
    facebook_messenger_verify_token: str = Field(..., validation_alias="FACEBOOK_MESSENGER_VERIFY_TOKEN")
    default_template_name: str = Field(
        "session_expired", validation_alias="DEFAULT_TEMPLATE_NAME"
    )
    template_mapping: Dict[str, str] = Field(
        default_factory=lambda: {
            "handoff": "handoff_notification",
            "session_expired": "session_expired",
        },
        validation_alias="TEMPLATE_MAPPING",
    )

    # 🌐 Webhook
    webhook_base_url: HttpUrl = Field(..., validation_alias="WEBHOOK_BASE_URL")

    # 📚 Vector store
    vector_store_path: str = "data/vector_store/index.faiss"
    documents_path: str = "data/documents"

    # 🤖 System prompts
    guardian_system_prompt: str = ""
    rag_system_prompt: str = ""
    handoff_system_prompt: str = ""

    # ⚡ Rate limits
    rate_limit_per_minute: int = 60

    # 🔓 CORS
    admin_allowed_origins: List[str] = Field(default_factory=lambda: ["*"])


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
