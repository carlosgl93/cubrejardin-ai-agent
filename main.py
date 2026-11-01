"""FastAPI entry point."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import api_router
from config import settings

app = FastAPI(title=settings.app_name, debug=settings.debug)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.admin_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

# Register channel adapters exactly once at import time (before any worker
# begins serving requests). The registry is treated as immutable after this.
from channels.registry import register_adapter
from channels.whatsapp import WhatsAppAdapter
from channels.instagram import InstagramAdapter
from channels.messenger import MessengerAdapter

register_adapter(WhatsAppAdapter())
register_adapter(InstagramAdapter())
register_adapter(MessengerAdapter())


@app.get("/")
def root() -> dict:
    """Return service metadata."""

    return {"name": settings.app_name, "environment": settings.environment}


@app.get("/health")
async def health() -> dict:
    """Return service health status and component checks."""
    checks = {}
    is_healthy = True

    # Supabase connectivity check
    if settings.supabase_url and settings.supabase_service_role_key:
        try:
            from config.supabase import get_supabase_client

            sb = get_supabase_client()
            sb.table("tenants").select("id").limit(1).execute()
            checks["supabase"] = "ok"
        except Exception as exc:
            checks["supabase"] = f"degraded: {exc}"
            is_healthy = False
    else:
        checks["supabase"] = "unconfigured"

    # Redis connectivity check
    if settings.redis_url:
        try:
            import redis.asyncio as aioredis

            r = aioredis.from_url(
                settings.redis_url,
                socket_timeout=0.5,
                socket_connect_timeout=0.5,
            )
            await r.ping()
            await r.aclose()
            checks["redis"] = "ok"
        except Exception:
            checks["redis"] = "fallback_memory"
    else:
        checks["redis"] = "memory"

    return {
        "status": "ok" if is_healthy else "degraded",
        "app": settings.app_name,
        "environment": settings.environment,
        "checks": checks,
    }

