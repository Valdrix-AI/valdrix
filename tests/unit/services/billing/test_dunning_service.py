"""
Tests for DunningService - Payment Retry Workflow
"""

from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from app.modules.billing.domain.billing.dunning_service import (
    DunningService,
    DUNNING_RETRY_SCHEDULE_DAYS,
    DUNNING_MAX_ATTEMPTS,
)
from app.modules.billing.domain.billing.paystack_billing import (
    SubscriptionStatus,
    PricingTier,
)


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def mock_subscription():
    sub = MagicMock()
    sub.id = uuid4()
    sub.tenant_id = uuid4()
    sub.tier = PricingTier.GROWTH.value
    sub.status = SubscriptionStatus.ACTIVE.value
    sub.dunning_attempts = 0
    sub.last_dunning_at = None
    sub.dunning_next_retry_at = None
    sub.paystack_auth_code = "AUTH_xxx"
    return sub


def setup_mock_db_result(mock_db, subscription):
    """Setup mock to return subscription for any execute call."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = subscription
    mock_db.execute.return_value = mock_result


@pytest.mark.asyncio
async def test_process_failed_payment_first_attempt(mock_db, mock_subscription):
    """Test first payment failure triggers dunning workflow."""
    setup_mock_db_result(mock_db, mock_subscription)

    with patch(
        "app.modules.billing.domain.billing.dunning_service.enqueue_job",
        new_callable=AsyncMock,
    ) as mock_enqueue:
        mock_enqueue.return_value = MagicMock()

        with patch.object(
            DunningService, "_send_payment_failed_email", new_callable=AsyncMock
        ):
            dunning = DunningService(mock_db)
            result = await dunning.process_failed_payment(mock_subscription.id)

            assert result["status"] == "scheduled_retry"
            assert result["attempt"] == 1
            assert mock_subscription.dunning_attempts == 1
            assert mock_subscription.status == SubscriptionStatus.ATTENTION.value
            mock_enqueue.assert_called_once()


@pytest.mark.asyncio
async def test_process_failed_payment_subscription_missing(mock_db):
    """Missing subscription returns error without raising."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    dunning = DunningService(mock_db)
    result = await dunning.process_failed_payment(uuid4())
    assert result["status"] == "error"
    assert result["reason"] == "subscription_not_found"


@pytest.mark.asyncio
async def test_process_failed_payment_max_attempts_reached(mock_db, mock_subscription):
    """Test max attempts triggers tier downgrade."""
    mock_subscription.dunning_attempts = (
        DUNNING_MAX_ATTEMPTS - 1
    )  # Will become max on this call
    setup_mock_db_result(mock_db, mock_subscription)

    with patch.object(
        DunningService, "_send_account_downgraded_email", new_callable=AsyncMock
    ):
        dunning = DunningService(mock_db)
        result = await dunning.process_failed_payment(mock_subscription.id)

        assert result["status"] == "downgraded"
        assert mock_subscription.tier == PricingTier.FREE_TRIAL.value
        assert mock_subscription.status == SubscriptionStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_process_failed_payment_enqueue_failure(mock_db, mock_subscription):
    """Enqueue failures should not abort state updates."""
    setup_mock_db_result(mock_db, mock_subscription)

    with patch(
        "app.modules.billing.domain.billing.dunning_service.enqueue_job",
        new_callable=AsyncMock,
    ) as mock_enqueue:
        mock_enqueue.side_effect = RuntimeError("queue down")

        with patch.object(
            DunningService, "_send_payment_failed_email", new_callable=AsyncMock
        ) as mock_email:
            dunning = DunningService(mock_db)
            result = await dunning.process_failed_payment(mock_subscription.id)

            assert result["status"] == "enqueue_failed"
            mock_db.commit.assert_awaited()
            mock_email.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_payment_success(mock_db, mock_subscription):
    """Test successful payment retry clears dunning state."""
    mock_subscription.dunning_attempts = 2
    setup_mock_db_result(mock_db, mock_subscription)

    with patch(
        "app.modules.billing.domain.billing.dunning_service.BillingService"
    ) as mock_billing_cls:
        mock_billing = MagicMock()
        mock_billing.charge_renewal = AsyncMock(return_value=True)
        mock_billing_cls.return_value = mock_billing

        with patch.object(
            DunningService, "_send_payment_recovered_email", new_callable=AsyncMock
        ):
            dunning = DunningService(mock_db)
            result = await dunning.retry_payment(mock_subscription.id)

            assert result["status"] == "success"
            assert mock_subscription.dunning_attempts == 0
            assert mock_subscription.status == SubscriptionStatus.ACTIVE.value


@pytest.mark.asyncio
async def test_retry_payment_failure_continues_dunning(mock_db, mock_subscription):
    """Test failed retry increments dunning attempts."""
    mock_subscription.dunning_attempts = 1
    setup_mock_db_result(mock_db, mock_subscription)

    with patch(
        "app.modules.billing.domain.billing.dunning_service.BillingService"
    ) as mock_billing_cls:
        mock_billing = MagicMock()
        mock_billing.charge_renewal = AsyncMock(return_value=False)
        mock_billing_cls.return_value = mock_billing

        with patch(
            "app.modules.billing.domain.billing.dunning_service.enqueue_job",
            new_callable=AsyncMock,
        ) as mock_enqueue:
            mock_enqueue.return_value = MagicMock()

            with patch.object(
                DunningService, "_send_payment_failed_email", new_callable=AsyncMock
            ):
                dunning = DunningService(mock_db)
                result = await dunning.retry_payment(mock_subscription.id)

                assert result["status"] == "scheduled_retry"
                assert mock_subscription.dunning_attempts == 2


@pytest.mark.asyncio
async def test_retry_payment_subscription_missing(mock_db):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    dunning = DunningService(mock_db)
    result = await dunning.retry_payment(uuid4())
    assert result["status"] == "error"
    assert result["reason"] == "subscription_not_found"


@pytest.mark.asyncio
async def test_retry_payment_exception_path(mock_db, mock_subscription):
    """Exception during charge should continue dunning workflow."""
    setup_mock_db_result(mock_db, mock_subscription)

    with patch(
        "app.modules.billing.domain.billing.dunning_service.BillingService"
    ) as mock_billing_cls:
        mock_billing = MagicMock()
        mock_billing.charge_renewal = AsyncMock(side_effect=Exception("boom"))
        mock_billing_cls.return_value = mock_billing

        with patch.object(
            DunningService, "process_failed_payment", new_callable=AsyncMock
        ) as mock_process:
            mock_process.return_value = {"status": "scheduled_retry"}
            dunning = DunningService(mock_db)
            result = await dunning.retry_payment(mock_subscription.id)
            assert result["status"] == "scheduled_retry"
            mock_process.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_retry_success_clears_state(mock_db, mock_subscription):
    """Test _handle_retry_success resets dunning state."""
    mock_subscription.dunning_attempts = 2
    mock_subscription.status = SubscriptionStatus.ATTENTION.value

    dunning = DunningService(mock_db)
    with patch.object(
        DunningService, "_send_payment_recovered_email", new_callable=AsyncMock
    ):
        await dunning._handle_retry_success(mock_subscription)

        assert mock_subscription.dunning_attempts == 0
        assert mock_subscription.status == SubscriptionStatus.ACTIVE.value
        mock_db.commit.assert_called()


@pytest.mark.asyncio
async def test_handle_final_failure_downgrades(mock_db, mock_subscription):
    """Test _handle_final_failure downgrades to trial."""
    dunning = DunningService(mock_db)
    with patch.object(
        DunningService, "_send_account_downgraded_email", new_callable=AsyncMock
    ):
        await dunning._handle_final_failure(mock_subscription)

        assert mock_subscription.tier == PricingTier.FREE_TRIAL.value
        assert mock_subscription.status == SubscriptionStatus.CANCELLED.value
        assert mock_subscription.canceled_at is not None
        mock_db.commit.assert_called()


@pytest.mark.asyncio
async def test_send_payment_failed_email_no_user(mock_db, mock_subscription):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    dunning = DunningService(mock_db)
    with patch(
        "app.modules.notifications.domain.email_service.EmailService"
    ) as mock_email:
        await dunning._send_payment_failed_email(
            mock_subscription, 1, datetime.now(timezone.utc)
        )
        mock_email.assert_not_called()


@pytest.mark.asyncio
async def test_send_payment_failed_email_exception_swallowed(
    mock_db, mock_subscription
):
    user = MagicMock()
    user.email = "encrypted@example.com"
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = user
    mock_db.execute.return_value = mock_result

    dunning = DunningService(mock_db)
    with (
        patch(
            "app.modules.notifications.domain.email_service.EmailService"
        ) as mock_email,
        patch(
            "app.shared.core.security.decrypt_string", return_value="user@example.com"
        ),
    ):
        mock_email.return_value.send_dunning_notification = AsyncMock(
            side_effect=RuntimeError("smtp down")
        )
        await dunning._send_payment_failed_email(
            mock_subscription, 1, datetime.now(timezone.utc)
        )


@pytest.mark.asyncio
async def test_send_payment_recovered_email_no_user(mock_db, mock_subscription):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    dunning = DunningService(mock_db)
    with patch(
        "app.modules.notifications.domain.email_service.EmailService"
    ) as mock_email:
        await dunning._send_payment_recovered_email(mock_subscription)
        mock_email.assert_not_called()


@pytest.mark.asyncio
async def test_send_account_downgraded_email_exception_swallowed(
    mock_db, mock_subscription
):
    user = MagicMock()
    user.email = "encrypted@example.com"
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = user
    mock_db.execute.return_value = mock_result

    dunning = DunningService(mock_db)
    with (
        patch(
            "app.modules.notifications.domain.email_service.EmailService"
        ) as mock_email,
        patch(
            "app.shared.core.security.decrypt_string", return_value="user@example.com"
        ),
    ):
        mock_email.return_value.send_account_downgraded_notification = AsyncMock(
            side_effect=RuntimeError("smtp down")
        )
        await dunning._send_account_downgraded_email(mock_subscription)


def test_retry_schedule_days():
    """Test retry schedule is correctly configured."""
    assert DUNNING_RETRY_SCHEDULE_DAYS == [1, 3, 7]
    assert DUNNING_MAX_ATTEMPTS == 3
