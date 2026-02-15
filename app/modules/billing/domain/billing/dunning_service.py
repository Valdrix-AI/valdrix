"""
Dunning Service - Payment Retry and Customer Notification Workflow

Implements production-grade dunning for failed payments:
1. Retry payment with exponential backoff (day 1, 3, 7)
2. Send email notification on each failure
3. Downgrade to TRIAL tier after max attempts
"""

from datetime import datetime, timezone, timedelta
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
from typing import TYPE_CHECKING, Any, Dict, Optional
from app.shared.core.config import get_settings

from app.modules.billing.domain.billing.paystack_billing import (
    TenantSubscription,
    SubscriptionStatus,
    BillingService,
)
from app.shared.core.pricing import PricingTier
from app.models.background_job import JobType
from app.modules.governance.domain.jobs.processor import enqueue_job

logger = structlog.get_logger()

if TYPE_CHECKING:
    from app.modules.notifications.domain.email_service import EmailService


# Dunning Configuration
DUNNING_RETRY_SCHEDULE_DAYS = [1, 3, 7]  # Retry on day 1, 3, 7 after first failure
DUNNING_MAX_ATTEMPTS = 3


class DunningService:
    """
    Handles failed payment recovery workflow.

    Dunning Flow:
    1. Webhook receives invoice.payment_failed → calls process_failed_payment
    2. Subscription status → ATTENTION, schedule retry
    3. DUNNING job executes → retry_payment
    4. On success: clear dunning, status → ACTIVE
    5. On final failure: downgrade → TRIAL, send notice
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_primary_tenant_email(self, tenant_id: UUID) -> Optional[str]:
        from app.models.tenant import User
        from app.shared.core.security import decrypt_string

        result = await self.db.execute(
            select(User).where(User.tenant_id == tenant_id).limit(1)
        )
        user = result.scalar_one_or_none()
        if not user:
            return None
        return decrypt_string(user.email, context="pii")

    def _build_email_service(self) -> "EmailService":
        from app.modules.notifications.domain.email_service import EmailService

        settings = get_settings()
        return EmailService(
            smtp_host=str(settings.SMTP_HOST),
            smtp_port=int(settings.SMTP_PORT),
            smtp_user=str(settings.SMTP_USER),
            smtp_password=str(settings.SMTP_PASSWORD),
            from_email=str(getattr(settings, "SMTP_FROM", "billing@valdrix.io")),
        )

    async def process_failed_payment(
        self, subscription_id: UUID, is_webhook: bool = True
    ) -> Dict[str, Any]:
        """
        Process a failed payment - called by webhook or job handler.

        Args:
            subscription_id: The TenantSubscription.id
            is_webhook: True if called from webhook (first failure)

        Returns:
            Status dict with action taken
        """
        result = await self.db.execute(
            select(TenantSubscription).where(TenantSubscription.id == subscription_id)
        )
        subscription = result.scalar_one_or_none()

        if not subscription:
            logger.error(
                "dunning_subscription_not_found", subscription_id=str(subscription_id)
            )
            return {"status": "error", "reason": "subscription_not_found"}

        now = datetime.now(timezone.utc)

        # Increment attempt counter
        subscription.dunning_attempts += 1
        subscription.last_dunning_at = now
        subscription.status = SubscriptionStatus.ATTENTION.value

        attempt = subscription.dunning_attempts

        logger.info(
            "dunning_payment_failed",
            tenant_id=str(subscription.tenant_id),
            attempt=attempt,
            max_attempts=DUNNING_MAX_ATTEMPTS,
        )

        # Check if we've exhausted retries
        if attempt >= DUNNING_MAX_ATTEMPTS:
            return await self._handle_final_failure(subscription)

        # Schedule next retry
        retry_delay_days = DUNNING_RETRY_SCHEDULE_DAYS[
            min(attempt - 1, len(DUNNING_RETRY_SCHEDULE_DAYS) - 1)
        ]
        next_retry = now + timedelta(days=retry_delay_days)
        subscription.dunning_next_retry_at = next_retry

        # Enqueue retry job
        try:
            await enqueue_job(
                db=self.db,
                job_type=JobType.DUNNING,
                tenant_id=subscription.tenant_id,
                payload={"subscription_id": subscription.id, "attempt": attempt + 1},
                scheduled_for=next_retry,
            )
        except Exception as e:
            logger.error(
                "dunning_enqueue_failed",
                subscription_id=str(subscription.id),
                error=str(e),
            )
            await self.db.commit()
            await self._send_payment_failed_email(subscription, attempt, next_retry)
            return {
                "status": "enqueue_failed",
                "attempt": attempt,
                "next_retry_at": next_retry.isoformat(),
            }

        await self.db.commit()

        # Send notification email
        await self._send_payment_failed_email(subscription, attempt, next_retry)

        return {
            "status": "scheduled_retry",
            "attempt": attempt,
            "next_retry_at": next_retry.isoformat(),
        }

    async def retry_payment(self, subscription_id: UUID) -> Dict[str, Any]:
        """
        Attempt to charge the subscription again.
        Called by DunningHandler.

        Returns:
            {"status": "success"} or {"status": "failed", "reason": ...}
        """
        result = await self.db.execute(
            select(TenantSubscription).where(TenantSubscription.id == subscription_id)
        )
        subscription = result.scalar_one_or_none()

        if not subscription:
            return {"status": "error", "reason": "subscription_not_found"}

        billing = BillingService(self.db)

        try:
            success = await billing.charge_renewal(subscription)

            if success:
                return await self._handle_retry_success(subscription)
            else:
                return await self.process_failed_payment(
                    subscription.id, is_webhook=False
                )

        except Exception as e:
            logger.error(
                "dunning_charge_exception",
                subscription_id=str(subscription_id),
                error=str(e),
            )
            return await self.process_failed_payment(subscription.id, is_webhook=False)

    async def _handle_retry_success(
        self, subscription: TenantSubscription
    ) -> Dict[str, Any]:
        """Clear dunning state after successful payment."""
        subscription.status = SubscriptionStatus.ACTIVE.value
        subscription.dunning_attempts = 0
        subscription.last_dunning_at = None
        subscription.dunning_next_retry_at = None

        await self.db.commit()

        logger.info(
            "dunning_retry_success",
            tenant_id=str(subscription.tenant_id),
            msg="Payment recovered, subscription reactivated",
        )

        # Send success email
        await self._send_payment_recovered_email(subscription)

        return {"status": "success", "action": "subscription_reactivated"}

    async def _handle_final_failure(
        self, subscription: TenantSubscription
    ) -> Dict[str, Any]:
        """Handle max retries exhausted - downgrade to TRIAL."""
        subscription.status = SubscriptionStatus.CANCELLED.value
        subscription.tier = PricingTier.FREE_TRIAL.value
        subscription.canceled_at = datetime.now(timezone.utc)
        subscription.dunning_next_retry_at = None

        await self.db.commit()

        logger.warning(
            "dunning_max_attempts_reached",
            tenant_id=str(subscription.tenant_id),
            msg="Subscription downgraded to TRIAL due to payment failure",
        )

        # Send final notice email
        await self._send_account_downgraded_email(subscription)

        return {
            "status": "downgraded",
            "action": "tier_changed_to_trial",
            "reason": "max_dunning_attempts_exhausted",
        }

    async def _send_payment_failed_email(
        self, subscription: TenantSubscription, attempt: int, next_retry: datetime
    ) -> None:
        """Send payment failed notification email."""
        try:
            email = await self._get_primary_tenant_email(subscription.tenant_id)
            if not email:
                logger.warning(
                    "dunning_email_no_user", tenant_id=str(subscription.tenant_id)
                )
                return

            email_service = self._build_email_service()
            await email_service.send_dunning_notification(
                to_email=email,
                attempt=attempt,
                max_attempts=DUNNING_MAX_ATTEMPTS,
                next_retry_date=next_retry,
                tier=subscription.tier,
            )

        except Exception as e:
            # Don't fail dunning if email fails
            logger.error("dunning_email_failed", error=str(e))

    async def _send_payment_recovered_email(
        self, subscription: TenantSubscription
    ) -> None:
        """Send payment recovered confirmation email."""
        try:
            email = await self._get_primary_tenant_email(subscription.tenant_id)
            if not email:
                return

            email_service = self._build_email_service()
            await email_service.send_payment_recovered_notification(to_email=email)

        except Exception as e:
            logger.error("dunning_recovery_email_failed", error=str(e))

    async def _send_account_downgraded_email(
        self, subscription: TenantSubscription
    ) -> None:
        """Send account downgraded notice."""
        try:
            email = await self._get_primary_tenant_email(subscription.tenant_id)
            if not email:
                return

            email_service = self._build_email_service()
            await email_service.send_account_downgraded_notification(to_email=email)

        except Exception as e:
            logger.error("dunning_downgrade_email_failed", error=str(e))
