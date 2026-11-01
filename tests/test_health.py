"""Tests for GET /health endpoint."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_returns_200():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "app" in data
    assert "environment" in data
    assert "checks" in data
    assert "supabase" in data["checks"]
    assert "redis" in data["checks"]


def test_health_supabase_degraded_when_exception():
    with patch("config.supabase.get_supabase_client") as mock_sb:
        mock_table = MagicMock()
        mock_table.select.return_value.limit.return_value.execute.side_effect = RuntimeError("db down")
        mock_sb.return_value.table.return_value = mock_table

        with patch("main.settings.supabase_url", "https://example.supabase.co"), \
             patch("main.settings.supabase_service_role_key", "secret"):
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "degraded"
            assert "degraded" in data["checks"]["supabase"]

