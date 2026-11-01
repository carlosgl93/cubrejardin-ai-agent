"""Deduplication service for idempotent message handling across channels."""

from __future__ import annotations

import asyncio
import time
from typing import Optional

from config.settings import get_settings
from config.supabase import get_supabase_client
from utils import logger


class DeduplicationService:
    """Atomic, multi-layer message deduplication (In-Memory TTL + Redis + Supabase)."""

    def __init__(self, redis_url: Optional[str] = None) -> None:
        self._lock = asyncio.Lock()
        self._cache: dict[str, tuple[str, float]] = {}  # key -> (status, expires_at)
        self._redis = None
        self._redis_available = True
        self._redis_url = redis_url

    async def _get_redis(self):
        if not self._redis_available:
            return None
        if self._redis is None:
            try:
                import redis.asyncio as aioredis

                url = self._redis_url or get_settings().redis_url
                if not url:
                    self._redis_available = False
                    return None
                # Connect with short timeouts to avoid blocking webhooks if Redis is down
                client = aioredis.from_url(
                    url, socket_timeout=0.8, socket_connect_timeout=0.8
                )
                await client.ping()
                self._redis = client
            except Exception as exc:
                self._redis_available = False
                self._redis = None
                logger.info(
                    "redis_dedup_unavailable_using_memory_and_db",
                    extra={"error": str(exc)},
                )
                return None
        return self._redis

    def _cleanup_memory(self, now: float) -> None:
        expired = [k for k, (_, exp) in self._cache.items() if exp <= now]
        for k in expired:
            self._cache.pop(k, None)

    async def claim_message(
        self,
        message_id: str,
        tenant_id: Optional[str] = None,
        ttl_seconds: int = 300,
    ) -> bool:
        """Atomically claim a message ID.

        Returns True if this is the first time the message is seen (claim acquired).
        Returns False if the message is already being processed or was processed.
        """
        if not message_id:
            return True

        key = f"dedup:{tenant_id or 'global'}:{message_id}"
        now = time.monotonic()

        # Layer 1: In-Memory TTL check & claim under async lock
        async with self._lock:
            self._cleanup_memory(now)
            entry = self._cache.get(key)
            if entry and entry[1] > now:
                return False
            # Mark in-memory as processing immediately
            self._cache[key] = ("processing", now + ttl_seconds)

        # Layer 2: Redis atomic SET NX if Redis is online
        redis_client = await self._get_redis()
        if redis_client:
            try:
                acquired = await redis_client.set(
                    key, "processing", ex=ttl_seconds, nx=True
                )
                if not acquired:
                    async with self._lock:
                        self._cache[key] = ("duplicate", now + ttl_seconds)
                    return False
            except Exception as exc:
                logger.warning(
                    "redis_claim_failed_falling_back", extra={"error": str(exc)}
                )

        # Layer 3: Database check (Supabase conversations table)
        try:
            sb = get_supabase_client()
            if sb:
                query = (
                    sb.table("conversations")
                    .select("id")
                    .eq("message_id", message_id)
                )
                if tenant_id:
                    query = query.eq("tenant_id", tenant_id)
                res = query.limit(1).execute()
                if res and res.data:
                    async with self._lock:
                        self._cache[key] = ("done", now + ttl_seconds)
                    return False
        except Exception as db_exc:
            logger.warning("db_dedup_check_failed", extra={"error": str(db_exc)})

        return True

    async def mark_done(
        self,
        message_id: str,
        tenant_id: Optional[str] = None,
        ttl_seconds: int = 600,
    ) -> None:
        """Mark a message ID as completed."""
        if not message_id:
            return

        key = f"dedup:{tenant_id or 'global'}:{message_id}"
        now = time.monotonic()

        async with self._lock:
            self._cache[key] = ("done", now + ttl_seconds)

        redis_client = await self._get_redis()
        if redis_client:
            try:
                await redis_client.set(key, "done", ex=ttl_seconds)
            except Exception:
                pass

    async def is_processed(
        self,
        message_id: str,
        tenant_id: Optional[str] = None,
    ) -> bool:
        """Check if message was already claimed or processed."""
        if not message_id:
            return False

        key = f"dedup:{tenant_id or 'global'}:{message_id}"
        now = time.monotonic()

        async with self._lock:
            entry = self._cache.get(key)
            if entry and entry[1] > now:
                return True

        redis_client = await self._get_redis()
        if redis_client:
            try:
                exists = await redis_client.exists(key)
                if exists:
                    return True
            except Exception:
                pass

        try:
            sb = get_supabase_client()
            if sb:
                query = (
                    sb.table("conversations")
                    .select("id")
                    .eq("message_id", message_id)
                )
                if tenant_id:
                    query = query.eq("tenant_id", tenant_id)
                res = query.limit(1).execute()
                if res and res.data:
                    return True
        except Exception:
            pass

        return False


_global_dedup_service: Optional[DeduplicationService] = None


def get_deduplication_service() -> DeduplicationService:
    """Return a singleton instance of DeduplicationService."""
    global _global_dedup_service
    if _global_dedup_service is None:
        _global_dedup_service = DeduplicationService()
    return _global_dedup_service
