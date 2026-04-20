"""API package."""

from fastapi import APIRouter

from .webhooks import router as webhook_router
from .admin import router as admin_router
from .templates import router as templates_router
from .tenants import router as tenants_router
from .facebook_auth import router as facebook_auth_router
from .documents import router as documents_router
from .telegram_webhook import router as telegram_router
from .handoffs import router as handoffs_router
from .backoffice import router as backoffice_router

api_router = APIRouter()
api_router.include_router(webhook_router, prefix="/webhook", tags=["webhook"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
api_router.include_router(templates_router, prefix="/templates", tags=["templates"])
api_router.include_router(tenants_router, prefix="/api/tenants", tags=["tenants"])
api_router.include_router(facebook_auth_router, prefix="/api/auth/facebook", tags=["facebook-auth"])
api_router.include_router(documents_router, prefix="/api/documents", tags=["documents"])
api_router.include_router(telegram_router, prefix="/webhook", tags=["telegram"])
api_router.include_router(handoffs_router, prefix="/api/handoffs", tags=["handoffs"])
api_router.include_router(backoffice_router, prefix="/api/backoffice", tags=["backoffice"])

__all__ = ["api_router"]
