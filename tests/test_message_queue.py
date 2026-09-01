"""Tests for message queue service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from services.message_queue import (
    MessageQueueService,
    MessageProcessor,
    QueuedMessage,
    MessagePriority,
)


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    with patch('services.message_queue.redis') as mock:
        client = AsyncMock()
        mock.from_url.return_value = client
        yield client


@pytest.fixture
def sample_message():
    """Create a sample queued message."""
    return QueuedMessage(
        id="msg_123",
        recipient="+56912345678",
        text="Hello!",
        channel="whatsapp",
        priority=MessagePriority.NORMAL,
        created_at="2024-01-15T10:00:00Z",
    )


class TestQueuedMessage:
    """Tests for QueuedMessage dataclass."""

    def test_to_json(self, sample_message):
        """Test serialization to JSON."""
        json_str = sample_message.to_json()
        data = json.loads(json_str)

        assert data["id"] == "msg_123"
        assert data["recipient"] == "+56912345678"
        assert data["priority"] == "normal"

    def test_from_json(self, sample_message):
        """Test deserialization from JSON."""
        json_str = sample_message.to_json()
        restored = QueuedMessage.from_json(json_str)

        assert restored.id == sample_message.id
        assert restored.recipient == sample_message.recipient
        assert restored.priority == MessagePriority.NORMAL

    def test_default_retry_count(self):
        """Test default retry count is 0."""
        msg = QueuedMessage(
            id="test",
            recipient="+56912345678",
            text="test",
            channel="whatsapp",
            priority=MessagePriority.NORMAL,
            created_at="2024-01-15T10:00:00Z",
        )
        assert msg.retry_count == 0
        assert msg.max_retries == 3


class TestMessageQueueService:
    """Tests for MessageQueueService."""

    @pytest.mark.asyncio
    async def test_enqueue(self, mock_redis, sample_message):
        """Test enqueueing a message."""
        service = MessageQueueService(redis_url="redis://localhost:6379")
        client = await service.get_client()

        result = await service.enqueue(sample_message)

        assert result is True
        mock_redis.lpush.assert_called()

    @pytest.mark.asyncio
    async def test_enqueue_with_priority(self, mock_redis, sample_message):
        """Test enqueueing with priority override."""
        service = MessageQueueService(redis_url="redis://localhost:6379")

        result = await service.enqueue(sample_message, priority=MessagePriority.HIGH)

        assert result is True
        # Should use high priority queue
        call_args = mock_redis.lpush.call_args[0]
        assert "high" in call_args[0]


class TestMessageProcessor:
    """Tests for MessageProcessor."""

    @pytest.mark.asyncio
    async def test_process_message_success(self, mock_redis, sample_message):
        """Test successful message processing."""
        queue = AsyncMock(spec=MessageQueueService)
        sender = AsyncMock()

        processor = MessageProcessor(queue, sender)

        await processor._process_message(sample_message)

        sender.assert_called_once_with(
            sample_message.recipient,
            sample_message.text
        )
        queue.acknowledge.assert_called_once_with(sample_message)

    @pytest.mark.asyncio
    async def test_process_message_retry_on_failure(self, mock_redis, sample_message):
        """Test retry on message send failure."""
        queue = AsyncMock(spec=MessageQueueService)
        sender = AsyncMock(side_effect=Exception("Send failed"))

        processor = MessageProcessor(queue, sender)

        await processor._process_message(sample_message)

        sender.assert_called_once()
        queue.retry.assert_called_once_with(sample_message)
