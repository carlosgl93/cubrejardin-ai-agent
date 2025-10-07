"""Application settings module."""

from functools import lru_cache
from typing import List

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
    debug: bool = False

    # 🔑 OpenAI
    openai_api_key: str = Field(..., validation_alias="OPENAI_API_KEY")
    openai_model: str = "gpt-4o-mini"   # estable
    openai_temperature: float = 0.2
    embedding_model: str = "text-embedding-3-small"

    # 📦 Infra
    database_url: str = "postgresql+psycopg://postgres:postgres@db:5432/whatsapp"
    redis_url: str = "redis://redis:6379/0"

    # 📱 WhatsApp / Meta
    whatsapp_account_sid: str = Field(..., validation_alias="WHATSAPP_ACCOUNT_SID")
    whatsapp_auth_token: str = Field(..., validation_alias="WHATSAPP_AUTH_TOKEN")
    whatsapp_from_number: str = Field(..., validation_alias="WHATSAPP_FROM_NUMBER")
    whatsapp_phone_number_id: str = Field("000000000000000", validation_alias="WHATSAPP_PHONE_NUMBER_ID")
    facebook_page_access_token: str = Field("test-token", validation_alias="FACEBOOK_PAGE_ACCESS_TOKEN")
    facebook_target_app_id: str = Field("263902037430900", validation_alias="FACEBOOK_TARGET_APP_ID")

    # 🌐 Webhook
    webhook_base_url: HttpUrl = Field(..., validation_alias="WEBHOOK_BASE_URL")
    webhook_secret: str = Field(..., validation_alias="WHATSAPP_WEBHOOK_SECRET")

    # 📚 Vector store
    vector_store_path: str = "data/vector_store/index.faiss"
    documents_path: str = "data/documents"

    # 🤖 System prompts
    guardian_system_prompt: str = ""
    rag_system_prompt: str = ""
    handoff_system_prompt: str = ""

    # ⚡ Rate limits
    rate_limit_per_minute: int = 5

    # 🔓 CORS
    admin_allowed_origins: List[str] = Field(default_factory=lambda: ["*"])


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
