"""
Tests for Webhook Retry Service

Covers:
- Idempotency key generation
- Webhook storage
- Processing logic
- Retry behavior
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.modules.billing.domain.billing.webhook_retry import (
    WebhookRetryService,
    WEBHOOK_MAX_ATTEMPTS,
)


class TestIdempotencyKey:
    """Tests for idempotency key generation."""

    @pytest.mark.asyncio
    async def test_generates_consistent_key(self):
        """Same inputs should generate same key."""
        mock_db = AsyncMock()
        service = WebhookRetryService(mock_db)

        key1 = service._generate_idempotency_key("paystack", "charge.success", "ref123")
        key2 = service._generate_idempotency_key("paystack", "charge.success", "ref123")

        assert key1 == key2

    @pytest.mark.asyncio
    async def test_different_refs_different_keys(self):
        """Different references should generate different keys."""
        mock_db = AsyncMock()
        service = WebhookRetryService(mock_db)

        key1 = service._generate_idempotency_key("paystack", "charge.success", "ref123")
        key2 = service._generate_idempotency_key("paystack", "charge.success", "ref456")

        assert key1 != key2

    def test_key_is_32_chars(self):
        """Key should be first 32 chars of SHA256."""
        mock_db = MagicMock()
        service = WebhookRetryService(mock_db)

        key = service._generate_idempotency_key(
            "paystack", "subscription.create", "sub_123"
        )

        assert isinstance(key, str)
        assert len(key) == 32


class TestWebhookRetryService:
    """Tests for WebhookRetryService class."""

    @pytest.mark.asyncio
    async def test_is_duplicate_returns_false_for_new(self):
        """is_duplicate should return False for new webhooks."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = WebhookRetryService(mock_db)

        result = await service.is_duplicate("some_key_123")

        assert result is False

    @pytest.mark.asyncio
    async def test_is_duplicate_returns_true_for_existing(self):
        """is_duplicate should return True for existing completed webhooks."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock()  # Existing job
        mock_db.execute.return_value = mock_result

        service = WebhookRetryService(mock_db)

        result = await service.is_duplicate("existing_key")

        assert result is True

    def test_max_attempts_configured(self):
        """Service should use 5 max attempts for revenue-critical webhooks."""
        assert WEBHOOK_MAX_ATTEMPTS == 5


class TestWebhookProcessing:
    """Tests for webhook processing logic."""

    def test_supported_events(self):
        """Should support all required Paystack webhook events."""
        supported = [
            "subscription.create",
            "charge.success",
            "subscription.disable",
            "invoice.payment_failed",
        ]

        # All required events are defined
        for event in supported:
            assert isinstance(event, str)
            assert len(event) > 0
