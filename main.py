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

register_adapter(WhatsAppAdapter())


@app.get("/")
def root() -> dict:
    """Return service metadata."""

    return {"name": settings.app_name, "environment": settings.environment}
