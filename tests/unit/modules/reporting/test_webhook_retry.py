"""
Comprehensive tests for WebhookRetryService module.
Covers webhook storage, idempotency, retry logic, duplicate detection, and Paystack webhook processing.
"""
import json
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.billing.domain.billing.webhook_retry import (
    WebhookRetryService,
    process_paystack_webhook,
    WEBHOOK_MAX_ATTEMPTS,
    WEBHOOK_IDEMPOTENCY_TTL_HOURS,
)
from app.models.background_job import BackgroundJob


@pytest.fixture
def mock_db():
    """Create a mock AsyncSession."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def webhook_service(mock_db):
    """Create WebhookRetryService instance."""
    return WebhookRetryService(mock_db)


@pytest.fixture
def sample_paystack_payload():
    """Sample Paystack webhook payload."""
    return {
        "event": "charge.success",
        "data": {
            "id": 123456,
            "reference": "txn_test_123",
            "amount": 50000,
            "currency": "NGN",
            "status": "success",
            "customer": {
                "id": 1,
                "email": "test@example.com",
                "first_name": "Test",
                "last_name": "User"
            }
        }
    }


class TestIdempotencyKeyGeneration:
    """Test idempotency key generation."""

    def test_generate_idempotency_key(self, webhook_service):
        """Test idempotency key generation."""
        key = webhook_service._generate_idempotency_key(
            provider="paystack",
            event_type="charge.success",
            reference="txn_123"
        )
        
        assert isinstance(key, str)
        assert len(key) == 32  # SHA256 truncated to 32 chars

    def test_idempotency_key_deterministic(self, webhook_service):
        """Test that same inputs produce same key."""
        key1 = webhook_service._generate_idempotency_key("paystack", "charge.success", "txn_123")
        key2 = webhook_service._generate_idempotency_key("paystack", "charge.success", "txn_123")
        
        assert key1 == key2

    def test_idempotency_key_different_for_different_inputs(self, webhook_service):
        """Test that different inputs produce different keys."""
        key1 = webhook_service._generate_idempotency_key("paystack", "charge.success", "txn_123")
        key2 = webhook_service._generate_idempotency_key("paystack", "charge.success", "txn_456")
        key3 = webhook_service._generate_idempotency_key("paystack", "invoice.create", "txn_123")
        
        assert key1 != key2
        assert key1 != key3

    def test_idempotency_key_provider_matters(self, webhook_service):
        """Test that different providers produce different keys."""
        key_paystack = webhook_service._generate_idempotency_key("paystack", "charge.success", "txn_123")
        key_stripe = webhook_service._generate_idempotency_key("stripe", "charge.success", "txn_123")
        
        assert key_paystack != key_stripe


class TestDuplicateDetection:
    """Test duplicate webhook detection."""

    @pytest.mark.asyncio
    async def test_is_duplicate_not_found(self, mock_db, webhook_service):
        """Test is_duplicate returns False for new webhook."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        is_dup = await webhook_service.is_duplicate("some_key_123")
        
        assert is_dup is False

    @pytest.mark.asyncio
    async def test_is_duplicate_found_completed(self, mock_db, webhook_service):
        """Test is_duplicate returns True for completed webhook."""
        mock_job = MagicMock(spec=BackgroundJob)
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        mock_db.execute.return_value = mock_result
        
        is_dup = await webhook_service.is_duplicate("duplicate_key")
        
        assert is_dup is True

    @pytest.mark.asyncio
    async def test_is_duplicate_queries_webhook_retry_type(self, mock_db, webhook_service):
        """Test that is_duplicate queries BackgroundJob with correct type."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        await webhook_service.is_duplicate("test_key")
        
        # Verify execute was called with a query
        mock_db.execute.assert_called_once()


class TestWebhookStorage:
    """Test webhook storage functionality."""

    @pytest.mark.asyncio
    async def test_store_webhook_new(self, mock_db, webhook_service, sample_paystack_payload):
        """Test storing a new webhook."""
        # Mock duplicate check
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        # Mock enqueue_job
        with patch('app.modules.billing.domain.billing.webhook_retry.enqueue_job') as mock_enqueue:
            mock_job = MagicMock(spec=BackgroundJob)
            mock_job.id = uuid.uuid4()
            mock_enqueue.return_value = mock_job
            
            job = await webhook_service.store_webhook(
                provider="paystack",
                event_type="charge.success",
                payload=sample_paystack_payload,
                reference="txn_test_123"
            )
            
            assert job is not None
            assert job.id == mock_job.id
            mock_enqueue.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_webhook_duplicate_returns_none(self, mock_db, webhook_service, sample_paystack_payload):
        """Test storing duplicate webhook returns None."""
        # First mock for duplicate check - returns duplicate
        mock_result = MagicMock()
        mock_existing_job = MagicMock(spec=BackgroundJob)
        mock_result.scalar_one_or_none.return_value = mock_existing_job
        mock_db.execute.return_value = mock_result
        
        job = await webhook_service.store_webhook(
            provider="paystack",
            event_type="charge.success",
            payload=sample_paystack_payload,
            reference="txn_test_123"
        )
        
        assert job is None

    @pytest.mark.asyncio
    async def test_store_webhook_uses_reference_from_payload(
        self, 
        mock_db, 
        webhook_service, 
        sample_paystack_payload
    ):
        """Test that store_webhook extracts reference from payload if not provided."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        with patch('app.modules.billing.domain.billing.webhook_retry.enqueue_job') as mock_enqueue:
            mock_job = MagicMock(spec=BackgroundJob)
            mock_enqueue.return_value = mock_job
            
            # Don't provide reference, should extract from payload
            await webhook_service.store_webhook(
                provider="paystack",
                event_type="charge.success",
                payload=sample_paystack_payload
                # reference not provided
            )
            
            # Should call enqueue_job with payload containing idempotency_key
            call_args = mock_enqueue.call_args
            assert call_args is not None

    @pytest.mark.asyncio
    async def test_store_webhook_sets_max_attempts(self, mock_db, webhook_service, sample_paystack_payload):
        """Test that webhook is enqueued with correct max attempts."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        with patch('app.modules.billing.domain.billing.webhook_retry.enqueue_job') as mock_enqueue:
            mock_job = MagicMock(spec=BackgroundJob)
            mock_enqueue.return_value = mock_job
            
            await webhook_service.store_webhook(
                provider="paystack",
                event_type="charge.success",
                payload=sample_paystack_payload
            )
            
            call_args = mock_enqueue.call_args
            assert call_args[1]["max_attempts"] == WEBHOOK_MAX_ATTEMPTS

    @pytest.mark.asyncio
    async def test_store_webhook_pending_returns_existing(self, mock_db, webhook_service, sample_paystack_payload):
        """Test that pending webhook returns existing job instead of creating new."""
        # First call for is_duplicate check - not found
        # Second call for existing pending job check - found
        mock_results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=MagicMock(spec=BackgroundJob)))
        ]
        
        mock_db.execute.side_effect = mock_results
        
        job = await webhook_service.store_webhook(
            provider="paystack",
            event_type="charge.success",
            payload=sample_paystack_payload,
            reference="txn_test_123"
        )
        
        # Should return the existing pending job
        assert job is not None


class TestPendingWebhooks:
    """Test retrieving pending webhooks."""

    @pytest.mark.asyncio
    async def test_get_pending_webhooks_all(self, mock_db, webhook_service):
        """Test retrieving all pending webhooks."""
        mock_jobs = [
            MagicMock(spec=BackgroundJob),
            MagicMock(spec=BackgroundJob),
        ]
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_jobs
        mock_db.execute.return_value = mock_result
        
        jobs = await webhook_service.get_pending_webhooks()
        
        assert len(jobs) == 2
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_pending_webhooks_filtered_by_provider(self, mock_db, webhook_service):
        """Test retrieving pending webhooks for specific provider."""
        mock_jobs = [
            MagicMock(spec=BackgroundJob),
        ]
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_jobs
        mock_db.execute.return_value = mock_result
        
        jobs = await webhook_service.get_pending_webhooks(provider="paystack")
        
        assert len(jobs) == 1
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_pending_webhooks_empty(self, mock_db, webhook_service):
        """Test retrieving pending webhooks when none exist."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        
        jobs = await webhook_service.get_pending_webhooks()
        
        assert jobs == []


class TestWebhookPayloadValidation:
    """Test webhook payload validation."""

    @pytest.mark.asyncio
    async def test_store_webhook_with_minimal_payload(self, mock_db, webhook_service):
        """Test storing webhook with minimal required data."""
        minimal_payload = {"data": {"reference": "test_ref"}}
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        with patch('app.modules.billing.domain.billing.webhook_retry.enqueue_job') as mock_enqueue:
            mock_job = MagicMock(spec=BackgroundJob)
            mock_enqueue.return_value = mock_job
            
            job = await webhook_service.store_webhook(
                provider="paystack",
                event_type="charge.success",
                payload=minimal_payload
            )
            
            assert job is not None

    @pytest.mark.asyncio
    async def test_store_webhook_with_empty_payload(self, mock_db, webhook_service):
        """Test storing webhook with empty payload."""
        empty_payload = {}
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        with patch('app.modules.billing.domain.billing.webhook_retry.enqueue_job') as mock_enqueue:
            mock_job = MagicMock(spec=BackgroundJob)
            mock_enqueue.return_value = mock_job
            
            await webhook_service.store_webhook(
                provider="paystack",
                event_type="charge.success",
                payload=empty_payload
            )
            
            mock_enqueue.assert_called_once()


class TestProcessPaystackWebhook:
    """Test Paystack webhook processing."""

    @pytest.mark.asyncio
    async def test_process_paystack_webhook_charge_success(self, mock_db):
        """Test processing charge.success webhook."""
        mock_job = MagicMock(spec=BackgroundJob)
        mock_job.id = uuid.uuid4()
        mock_job.payload = {
            "provider": "paystack",
            "event_type": "charge.success",
            "payload": {
                "event": "charge.success",
                "data": {
                    "id": 123,
                    "reference": "txn_123",
                    "amount": 50000,
                    "status": "success"
                }
            }
        }
        
        with patch('app.modules.billing.domain.billing.paystack_billing.WebhookHandler') as mock_handler_class:
            mock_handler = AsyncMock()
            mock_handler_class.return_value = mock_handler
            mock_handler._handle_charge_success = AsyncMock()
            
            result = await process_paystack_webhook(mock_job, mock_db)
            
            assert result["status"] == "processed"
            assert result["event"] == "charge.success"
            mock_handler._handle_charge_success.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_paystack_webhook_subscription_create(self, mock_db):
        """Test processing subscription.create webhook."""
        mock_job = MagicMock(spec=BackgroundJob)
        mock_job.payload = {
            "event_type": "subscription.create",
            "payload": {
                "event": "subscription.create",
                "data": {
                    "id": 456,
                    "customer_id": 1,
                    "plan": "premium"
                }
            }
        }
        
        with patch('app.modules.billing.domain.billing.paystack_billing.WebhookHandler') as mock_handler_class:
            mock_handler = AsyncMock()
            mock_handler_class.return_value = mock_handler
            mock_handler._handle_subscription_create = AsyncMock()
            
            result = await process_paystack_webhook(mock_job, mock_db)
            
            assert result["status"] == "processed"
            mock_handler._handle_subscription_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_paystack_webhook_subscription_disable(self, mock_db):
        """Test processing subscription.disable webhook."""
        mock_job = MagicMock(spec=BackgroundJob)
        mock_job.payload = {
            "event_type": "subscription.disable",
            "payload": {
                "event": "subscription.disable",
                "data": {"id": 789}
            }
        }
        
        with patch('app.modules.billing.domain.billing.paystack_billing.WebhookHandler') as mock_handler_class:
            mock_handler = AsyncMock()
            mock_handler_class.return_value = mock_handler
            mock_handler._handle_subscription_disable = AsyncMock()
            
            result = await process_paystack_webhook(mock_job, mock_db)
            
            assert result["status"] == "processed"
            mock_handler._handle_subscription_disable.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_paystack_webhook_invoice_failed(self, mock_db):
        """Test processing invoice.payment_failed webhook."""
        mock_job = MagicMock(spec=BackgroundJob)
        mock_job.payload = {
            "event_type": "invoice.payment_failed",
            "payload": {
                "event": "invoice.payment_failed",
                "data": {"inv_id": 111, "status": "failed"}
            }
        }
        
        with patch('app.modules.billing.domain.billing.paystack_billing.WebhookHandler') as mock_handler_class:
            mock_handler = AsyncMock()
            mock_handler_class.return_value = mock_handler
            mock_handler._handle_invoice_failed = AsyncMock()
            
            result = await process_paystack_webhook(mock_job, mock_db)
            
            assert result["status"] == "processed"
            mock_handler._handle_invoice_failed.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_paystack_webhook_unknown_event(self, mock_db):
        """Test processing unknown event type."""
        mock_job = MagicMock(spec=BackgroundJob)
        mock_job.payload = {
            "event_type": "unknown.event",
            "payload": {
                "event": "unknown.event",
                "data": {}
            }
        }
        
        with patch('app.modules.billing.domain.billing.paystack_billing.WebhookHandler') as mock_handler_class:
            mock_handler = AsyncMock()
            mock_handler_class.return_value = mock_handler
            
            result = await process_paystack_webhook(mock_job, mock_db)
            
            assert result["status"] == "ignored"
            assert "Unknown event type" in result["reason"]

    @pytest.mark.asyncio
    async def test_process_paystack_webhook_missing_payload(self, mock_db):
        """Test processing webhook with missing payload."""
        mock_job = MagicMock(spec=BackgroundJob)
        mock_job.payload = None
        
        result = await process_paystack_webhook(mock_job, mock_db)
        
        assert result["status"] == "error"
        assert result["reason"] == "Missing payload"

    @pytest.mark.asyncio
    async def test_process_paystack_webhook_verifies_signature_with_raw_payload(self, mock_db):
        payload_dict = {"event": "charge.success", "data": {"reference": "txn_abc"}}
        mock_job = MagicMock(spec=BackgroundJob)
        mock_job.id = uuid.uuid4()
        mock_job.payload = {
            "event_type": "charge.success",
            "payload": payload_dict,
            "raw_payload": json.dumps(payload_dict),
            "signature": "valid-signature",
        }

        with patch("app.modules.billing.domain.billing.paystack_billing.WebhookHandler") as mock_handler_class:
            mock_handler = MagicMock()
            mock_handler_class.return_value = mock_handler
            mock_handler.verify_signature.return_value = True
            mock_handler._handle_charge_success = AsyncMock()

            result = await process_paystack_webhook(mock_job, mock_db)

        assert result["status"] == "processed"
        mock_handler.verify_signature.assert_called_once()
        mock_handler._handle_charge_success.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_paystack_webhook_missing_signature_material_fails_closed_in_production(self, mock_db):
        mock_job = MagicMock(spec=BackgroundJob)
        mock_job.id = uuid.uuid4()
        mock_job.payload = {
            "event_type": "charge.success",
            "payload": {"event": "charge.success", "data": {}},
        }

        with patch("app.modules.billing.domain.billing.paystack_billing.WebhookHandler") as mock_handler_class, \
             patch("app.modules.billing.domain.billing.webhook_retry.get_settings") as mock_get_settings:
            mock_handler_class.return_value = AsyncMock()
            mock_get_settings.return_value = MagicMock(ENVIRONMENT="production")
            result = await process_paystack_webhook(mock_job, mock_db)

        assert result["status"] == "error"
        assert result["reason"] == "missing_signature_material"


class TestWebhookConfiguration:
    """Test webhook configuration constants."""

    def test_webhook_max_attempts_is_reasonable(self):
        """Test that max attempts is set to a reasonable value."""
        assert WEBHOOK_MAX_ATTEMPTS == 5
        assert WEBHOOK_MAX_ATTEMPTS > 0

    def test_webhook_idempotency_ttl_is_reasonable(self):
        """Test that idempotency TTL is set to a reasonable value."""
        assert WEBHOOK_IDEMPOTENCY_TTL_HOURS == 48
        assert WEBHOOK_IDEMPOTENCY_TTL_HOURS > 0


class TestWebhookIntegration:
    """Integration tests for webhook flow."""

    @pytest.mark.asyncio
    async def test_full_webhook_flow(self, mock_db, webhook_service, sample_paystack_payload):
        """Test complete webhook flow: store -> retrieve -> process."""
        # Step 1: Store webhook
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        with patch('app.modules.billing.domain.billing.webhook_retry.enqueue_job') as mock_enqueue:
            mock_job = MagicMock(spec=BackgroundJob)
            mock_job.id = uuid.uuid4()
            mock_job.payload = {
                "provider": "paystack",
                "event_type": "charge.success",
                "payload": sample_paystack_payload
            }
            mock_enqueue.return_value = mock_job
            
            # Store webhook
            stored_job = await webhook_service.store_webhook(
                provider="paystack",
                event_type="charge.success",
                payload=sample_paystack_payload,
                reference="txn_test_123"
            )
            
            assert stored_job is not None
            
            # Step 2: Process webhook
            with patch('app.modules.billing.domain.billing.paystack_billing.WebhookHandler') as mock_handler_class:
                mock_handler = AsyncMock()
                mock_handler_class.return_value = mock_handler
                mock_handler._handle_charge_success = AsyncMock()
                
                result = await process_paystack_webhook(mock_job, mock_db)
                
                assert result["status"] == "processed"
