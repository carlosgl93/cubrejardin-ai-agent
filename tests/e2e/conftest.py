"""E2E test fixtures and configuration."""

from __future__ import annotations

import os
import pytest
from typing import Generator

import httpx


# ─── Fixtures ────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def api_base_url() -> str:
    """Base URL for the API under test.

    Override with API_BASE_URL environment variable or --api-url flag.
    """
    return os.environ.get("API_BASE_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def test_user_phone() -> str:
    """Phone number for test user messages.

    Use a real WhatsApp-connected number for full E2E testing.
    """
    return os.environ.get("TEST_USER_PHONE", "+56912345678")


@pytest.fixture(scope="session")
def test_tenant_id() -> str:
    """Tenant ID for authenticated requests.

    Should be a real tenant with active WhatsApp credentials.
    """
    return os.environ.get("TEST_TENANT_ID", "test-tenant-001")


@pytest.fixture(scope="session")
def admin_token() -> str | None:
    """Admin authentication token for backoffice endpoints.

    Required for super-admin operations.
    """
    return os.environ.get("ADMIN_TOKEN")


@pytest.fixture(scope="session")
def user_token() -> str | None:
    """User authentication token for tenant-scoped requests.

    Should be a JWT for test_tenant_id.
    """
    return os.environ.get("USER_TOKEN")


@pytest.fixture
def auth_headers(user_token: str | None) -> dict[str, str]:
    """Authorization headers with user token."""
    if user_token:
        return {"Authorization": f"Bearer {user_token}"}
    return {}


@pytest.fixture
def admin_headers(admin_token: str | None) -> dict[str, str]:
    """Authorization headers with admin token."""
    if admin_token:
        return {"Authorization": f"Bearer {admin_token}"}
    return {}


# ─── Pytest Configuration ────────────────────────────────────────────────────────

def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "e2e: end-to-end tests requiring running services"
    )
    config.addinivalue_line(
        "markers", "requires_auth: tests requiring authentication"
    )
    config.addinivalue_line(
        "markers", "requires_wa: tests requiring WhatsApp connection"
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-skip E2E tests if services are not running."""
    api_url = os.environ.get("API_BASE_URL", "http://localhost:8000")

    # Check if API is reachable
    try:
        import socket
        from urllib.parse import urlparse

        parsed = urlparse(api_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 80

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()

        api_available = result == 0
    except Exception:
        api_available = False

    if not api_available:
        skip_e2e = pytest.mark.skip(
            reason=f"API not available at {api_url}. Start services first."
        )
        for item in items:
            if "e2e" in item.keywords:
                item.add_marker(skip_e2e)
