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
    tenant_name: str = "el negocio"


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
        tenant_name = "el negocio"
        try:
            t_res = (
                sb.table("tenants")
                .select("name")
                .eq("id", tenant_id)
                .limit(1)
                .maybe_single()
                .execute()
            )
            if t_res and t_res.data and t_res.data.get("name"):
                tenant_name = t_res.data["name"]
        except Exception:
            pass

        if result.data:
            row = result.data[0]
            config = TenantBotConfig(
                system_prompt=row.get("system_prompt") or None,
                greeting=row.get("greeting") or None,
                handoff_trigger=row.get("handoff_trigger") or None,
                tenant_name=tenant_name,
            )
        else:
            config = TenantBotConfig(tenant_name=tenant_name)
    except Exception as exc:
        logger.warning("tenant_config_load_failed", extra={"tenant_id": tenant_id, "error": str(exc)})
        config = TenantBotConfig()

    _cache[tenant_id] = _CacheEntry(config=config, expires_at=now + _CACHE_TTL)
    return config
