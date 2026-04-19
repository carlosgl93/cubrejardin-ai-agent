"""Telegram Bot service for agent handoff notifications."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from config import get_settings
from utils import logger

settings = get_settings()


class TelegramService:
    BASE_URL = "https://api.telegram.org/bot"

    def __init__(self, token: Optional[str] = None) -> None:
        self.token = token or settings.telegram_bot_token
        self._client = httpx.AsyncClient(
            base_url=f"{self.BASE_URL}{self.token}",
            timeout=10.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def send_message(
        self,
        chat_id: str,
        text: str,
        *,
        parse_mode: str = "HTML",
        reply_to_message_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id
        response = await self._client.post("/sendMessage", json=payload)
        response.raise_for_status()
        result = response.json().get("result", {})
        logger.info("telegram_message_sent", extra={"chat_id": chat_id, "message_id": result.get("message_id")})
        return result

    async def set_webhook(self, webhook_url: str) -> Dict[str, Any]:
        response = await self._client.post("/setWebhook", json={"url": webhook_url, "allowed_updates": ["message"]})
        response.raise_for_status()
        return response.json()

    async def delete_webhook(self) -> Dict[str, Any]:
        response = await self._client.post("/deleteWebhook")
        response.raise_for_status()
        return response.json()
