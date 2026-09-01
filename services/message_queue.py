"""Message queue service using Redis for async message sending."""

from __future__ import annotations

import json
import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional
from dataclasses import dataclass, asdict

import redis.asyncio as redis

from config import get_settings
from utils import logger


class MessagePriority(str, Enum):
    """Queue message priority levels."""
    HIGH = "high"      # Escalations, handoffs
    NORMAL = "normal" # Standard responses
    LOW = "low"       # Non-urgent notifications


@dataclass
class QueuedMessage:
    """A message to be sent asynchronously."""
    id: str
    recipient: str
    text: str
    channel: str  # 'whatsapp', 'instagram'
    priority: MessagePriority
    created_at: str
    retry_count: int = 0
    max_retries: int = 3
    metadata: dict = None

    def to_json(self) -> str:
        """Serialize to JSON string."""
        data = asdict(self)
        data['priority'] = self.priority.value
        return json.dumps(data)

    @classmethod
    def from_json(cls, data: str) -> QueuedMessage:
        """Deserialize from JSON string."""
        obj = json.loads(data)
        obj['priority'] = MessagePriority(obj['priority'])
        return cls(**obj)


class MessageQueueService:
    """Redis-based message queue for async WhatsApp/Instagram sending."""

    QUEUE_KEY = "whatsapp_bot:message_queue"
    PROCESSING_KEY = "whatsapp_bot:message_queue:processing"
    DEAD_LETTER_KEY = "whatsapp_bot:message_queue:dead_letter"
    METRICS_KEY = "whatsapp_bot:metrics"

    def __init__(self, redis_url: Optional[str] = None) -> None:
        settings = get_settings()
        self.redis_url = redis_url or settings.redis_url
        self._client: Optional[redis.Redis] = None

    async def get_client(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._client is None:
            self._client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
        return self._client

    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None

    async def enqueue(
        self,
        message: QueuedMessage,
        priority: Optional[MessagePriority] = None
    ) -> bool:
        """Add a message to the queue.

        Args:
            message: The message to enqueue
            priority: Override message priority (uses message.priority if None)

        Returns:
            True if successfully enqueued
        """
        client = await self.get_client()

        try:
            queue_key = f"{self.QUEUE_KEY}:{priority.value if priority else message.priority.value}"
            await client.lpush(queue_key, message.to_json())

            logger.info(
                "message_queued",
                extra={
                    "message_id": message.id,
                    "recipient": message.recipient,
                    "priority": (priority or message.priority).value,
                    "queue_key": queue_key
                }
            )
            return True

        except Exception as exc:
            logger.error(
                "message_queue_enqueue_failed",
                extra={"message_id": message.id, "error": str(exc)}
            )
            return False

    async def dequeue(self, timeout: int = 5) -> Optional[QueuedMessage]:
        """Get next message from queue (blocking with timeout).

        Args:
            timeout: Seconds to wait for a message

        Returns:
            Next QueuedMessage or None if timeout
        """
        client = await self.get_client()

        # Try queues in priority order
        for priority in [MessagePriority.HIGH, MessagePriority.NORMAL, MessagePriority.LOW]:
            queue_key = f"{self.QUEUE_KEY}:{priority.value}"

            # Use BLPOP for blocking pop
            result = await client.brpop(queue_key, timeout=timeout)

            if result:
                _, data = result
                try:
                    message = QueuedMessage.from_json(data)

                    # Move to processing set with TTL
                    await client.zadd(self.PROCESSING_KEY, {message.to_json(): datetime.now(timezone.utc).timestamp()})

                    logger.info(
                        "message_dequeued",
                        extra={"message_id": message.id, "priority": priority.value}
                    )
                    return message

                except Exception as exc:
                    logger.error(
                        "message_queue_parse_failed",
                        extra={"data": data[:100], "error": str(exc)}
                    )

        return None

    async def acknowledge(self, message: QueuedMessage) -> None:
        """Mark message as successfully processed.

        Removes from processing set and updates metrics.
        """
        client = await self.get_client()

        # Remove from processing
        await client.zrem(self.PROCESSING_KEY, message.to_json())

        # Update metrics
        await self._increment_metric("messages_sent")

        logger.info(
            "message_acknowledged",
            extra={"message_id": message.id}
        )

    async def retry(self, message: QueuedMessage) -> bool:
        """Retry a failed message.

        Increments retry count and re-enqueues if under max_retries.
        """
        client = await self.get_client()

        message.retry_count += 1

        if message.retry_count >= message.max_retries:
            # Move to dead letter queue
            await client.lpush(self.DEAD_LETTER_KEY, message.to_json())
            await client.zrem(self.PROCESSING_KEY, message.to_json())

            logger.warning(
                "message_moved_to_dead_letter",
                extra={
                    "message_id": message.id,
                    "retry_count": message.retry_count
                }
            )
            return False

        # Re-enqueue with same priority
        await client.zrem(self.PROCESSING_KEY, message.to_json())
        await self.enqueue(message)

        logger.info(
            "message_retry_scheduled",
            extra={
                "message_id": message.id,
                "retry_count": message.retry_count
            }
        )
        return True

    async def _increment_metric(self, metric: str, value: int = 1) -> None:
        """Increment a metric counter."""
        client = await self.get_client()
        await client.hincrby(self.METRICS_KEY, metric, value)

    async def get_metrics(self) -> dict:
        """Get queue metrics."""
        client = await self.get_client()

        metrics = await client.hgetall(self.METRICS_KEY)

        # Get queue lengths
        for priority in MessagePriority:
            queue_key = f"{self.QUEUE_KEY}:{priority.value}"
            length = await client.llen(queue_key)
            metrics[f"queue_{priority.value}"] = length

        # Get dead letter count
        metrics["dead_letter_count"] = await client.llen(self.DEAD_LETTER_KEY)

        return metrics


# ─── Message Processor Worker ──────────────────────────────────────────────────

class MessageProcessor:
    """Worker that processes messages from the queue."""

    def __init__(
        self,
        queue: MessageQueueService,
        sender: Callable[[str, str], Any],  # (recipient, text) -> asyncio result
        max_concurrent: int = 5
    ) -> None:
        self.queue = queue
        self.sender = sender
        self.max_concurrent = max_concurrent
        self._running = False
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(max_concurrent)

    async def start(self) -> None:
        """Start the message processor loop."""
        self._running = True

        logger.info("message_processor_started", extra={"max_concurrent": self.max_concurrent})

        while self._running:
            try:
                message = await self.queue.dequeue(timeout=5)

                if message:
                    asyncio.create_task(self._process_message(message))

            except Exception as exc:
                logger.error("message_processor_loop_error", extra={"error": str(exc)})
                await asyncio.sleep(1)

    async def stop(self) -> None:
        """Stop the message processor."""
        self._running = False
        logger.info("message_processor_stopped")

    async def _process_message(self, message: QueuedMessage) -> None:
        """Process a single message with concurrency limiting."""
        async with self._semaphore:
            try:
                result = self.sender(message.recipient, message.text)
                if asyncio.iscoroutine(result):
                    await result
                await self.queue.acknowledge(message)

            except Exception as exc:
                logger.error(
                    "message_send_failed",
                    extra={
                        "message_id": message.id,
                        "recipient": message.recipient,
                        "error": str(exc)
                    }
                )
                await self.queue.retry(message)
