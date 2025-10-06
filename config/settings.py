"""Application settings module."""

from functools import lru_cache
from typing import List
from dataclasses import dataclass
from pydantic import Field, HttpUrl
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
    app_name: str = Field(default="WhatsApp AI Agent")
    environment: str = Field(default="development")
    debug: bool = Field(default=False)

    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5-nano")
    openai_temperature: float = Field(default=0.2)

    embedding_model: str = Field(default="gpt-5-nano") # text-embedding-3-small

    database_url: str = Field(default="postgresql+psycopg://postgres:postgres@db:5432/whatsapp")
    redis_url: str = Field(default="redis://redis:6379/0")

    whatsapp_account_sid: str = Field(..., env="WHATSAPP_ACCOUNT_SID")
    whatsapp_auth_token: str = Field(..., env="WHATSAPP_AUTH_TOKEN")
    whatsapp_from_number: str = Field(..., env="WHATSAPP_FROM_NUMBER")

    webhook_base_url: HttpUrl = Field(..., env="WEBHOOK_BASE_URL")
    webhook_secret: str = Field(..., env="WHATSAPP_WEBHOOK_SECRET")

    vector_store_path: str = Field(default="data/vector_store/index.faiss")
    documents_path: str = Field(default="data/documents")

    guardian_system_prompt: str = Field(default="")
    rag_system_prompt: str = Field(default="")
    handoff_system_prompt: str = Field(default="")

    rate_limit_per_minute: int = Field(default=5)

    admin_allowed_origins: List[str] = Field(default_factory=lambda: ["*"])



@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()


settings = get_settings()
print(">>> SETTINGS LOADED:", settings.model_dump())