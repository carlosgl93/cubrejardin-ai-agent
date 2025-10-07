"""Configuration package for WhatsApp AI agent system."""

from .settings import get_settings

settings = get_settings()

__all__ = ["settings"]
