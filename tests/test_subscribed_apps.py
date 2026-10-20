"""Tests for subscribe_waba_to_app and subscribe_page_to_app."""

import httpx
import pytest
from unittest.mock import AsyncMock, patch

from services.facebook_auth import subscribe_waba_to_app, subscribe_page_to_app


@pytest.mark.anyio("asyncio")
async def test_subscribe_waba_to_app_success():
    mock_resp = httpx.Response(200, json={"success": True}, request=httpx.Request("POST", "https://graph.facebook.com"))
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        res = await subscribe_waba_to_app("12345", "test-token")
        assert res is True


@pytest.mark.anyio("asyncio")
async def test_subscribe_waba_to_app_failure():
    mock_resp = httpx.Response(400, json={"error": {"message": "Invalid token"}}, request=httpx.Request("POST", "https://graph.facebook.com"))
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        res = await subscribe_waba_to_app("12345", "bad-token")
        assert res is False


@pytest.mark.anyio("asyncio")
async def test_subscribe_page_to_app_success():
    mock_resp = httpx.Response(200, json={"success": True}, request=httpx.Request("POST", "https://graph.facebook.com"))
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        res = await subscribe_page_to_app("page-999", "page-access-token")
        assert res is True


@pytest.mark.anyio("asyncio")
async def test_subscribe_page_to_app_failure():
    mock_resp = httpx.Response(500, json={"error": {"message": "Server error"}}, request=httpx.Request("POST", "https://graph.facebook.com"))
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        res = await subscribe_page_to_app("page-999", "page-access-token")
        assert res is False
