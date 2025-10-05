"""API package."""

from fastapi import APIRouter

from .webhooks import router as webhook_router
from .admin import router as admin_router

api_router = APIRouter()
api_router.include_router(webhook_router, prefix="/webhook", tags=["webhook"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])

__all__ = ["api_router"]
