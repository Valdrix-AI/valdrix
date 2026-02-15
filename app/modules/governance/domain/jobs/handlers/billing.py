"""
Billing Job Handlers
"""

from typing import Dict, Any
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.background_job import BackgroundJob
from app.modules.governance.domain.jobs.handlers.base import BaseJobHandler


class RecurringBillingHandler(BaseJobHandler):
    """Processes an individual recurring billing charge for a tenant."""

    async def execute(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        from app.modules.billing.domain.billing.paystack_billing import (
            BillingService,
            TenantSubscription,
        )

        payload = job.payload or {}
        sub_id = payload.get("subscription_id")

        if not sub_id:
            raise ValueError("subscription_id required for recurring_billing")

        # Get subscription - P1: Enforce tenant isolation
        result = await db.execute(
            select(TenantSubscription).where(
                TenantSubscription.id == UUID(sub_id),
                TenantSubscription.tenant_id == job.tenant_id,
            )
        )
        subscription = result.scalar_one_or_none()

        if not subscription:
            return {"status": "failed", "reason": "subscription_not_found"}

        if subscription.status != "active":
            return {
                "status": "skipped",
                "reason": f"subscription_status_is_{subscription.status}",
            }

        # Execute charge
        billing_service = BillingService(db)
        success = await billing_service.charge_renewal(subscription)

        if success:
            # Fetch actual price for result reporting
            from app.models.pricing import PricingPlan

            plan_res = await db.execute(
                select(PricingPlan).where(PricingPlan.id == subscription.tier)
            )
            plan_obj = plan_res.scalar_one_or_none()
            price = float(plan_obj.price_usd) if plan_obj else 0.0

            return {"status": "completed", "amount_billed_usd": price}
        else:
            raise Exception("Paystack charge failed or authorization missing")
