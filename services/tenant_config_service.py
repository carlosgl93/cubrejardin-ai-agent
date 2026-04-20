"""Tenant bot config loader with simple in-process cache."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from config.supabase import get_supabase_client
from utils import logger

_CACHE_TTL = 300  # seconds


@dataclass
class TenantBotConfig:
    system_prompt: Optional[str] = None
    greeting: Optional[str] = None
    handoff_trigger: Optional[str] = None


@dataclass
class _CacheEntry:
    config: TenantBotConfig
    expires_at: float


_cache: dict[str, _CacheEntry] = {}


def get_tenant_bot_config(tenant_id: str) -> TenantBotConfig:
    """Return bot config for tenant_id, using a 5-minute in-process cache."""
    now = time.monotonic()
    entry = _cache.get(tenant_id)
    if entry and entry.expires_at > now:
        return entry.config

    try:
        sb = get_supabase_client()
        result = (
            sb.table("tenant_bot_config")
            .select("system_prompt, greeting, handoff_trigger")
            .eq("tenant_id", tenant_id)
            .limit(1)
            .execute()
        )
        if result.data:
            row = result.data[0]
            config = TenantBotConfig(
                system_prompt=row.get("system_prompt") or None,
                greeting=row.get("greeting") or None,
                handoff_trigger=row.get("handoff_trigger") or None,
            )
        else:
            config = TenantBotConfig()
    except Exception as exc:
        logger.warning("tenant_config_load_failed", extra={"tenant_id": tenant_id, "error": str(exc)})
        config = TenantBotConfig()

    _cache[tenant_id] = _CacheEntry(config=config, expires_at=now + _CACHE_TTL)
    return config
