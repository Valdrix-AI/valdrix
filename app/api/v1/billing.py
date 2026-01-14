"""
Billing API Endpoints - Paystack Integration

Provides:
- GET /billing/subscription - Current subscription status
- POST /billing/checkout - Initialize Paystack checkout
- POST /billing/webhook - Handle Paystack webhooks
"""

from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import structlog

from app.core.auth import CurrentUser, requires_role
from app.db.session import get_db
from app.core.config import get_settings

logger = structlog.get_logger()
router = APIRouter(prefix="/billing", tags=["Billing"])
settings = get_settings()


class CheckoutRequest(BaseModel):
    tier: str  # starter, growth, pro, enterprise
    callback_url: Optional[str] = None


class SubscriptionResponse(BaseModel):
    tier: str
    status: str
    next_payment_date: Optional[str] = None


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
):
    """Get current subscription status for tenant."""
    try:
        from app.services.billing.paystack_billing import TenantSubscription
        from sqlalchemy import select

        result = await db.execute(
            select(TenantSubscription).where(
                TenantSubscription.tenant_id == user.tenant_id
            )
        )
        sub = result.scalar_one_or_none()

        if not sub:
            return SubscriptionResponse(tier="trial", status="active")

        return SubscriptionResponse(
            tier=sub.tier,
            status=sub.status,
            next_payment_date=sub.next_payment_date.isoformat() if sub.next_payment_date else None
        )
    except Exception as e:
        logger.error("get_subscription_failed", error=str(e))
        raise HTTPException(500, "Failed to fetch subscription")


@router.post("/checkout")
async def create_checkout(
    request: CheckoutRequest,
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
):
    """Initialize Paystack checkout session."""
    if not settings.PAYSTACK_SECRET_KEY:
        raise HTTPException(503, "Billing not configured")

    try:
        from app.services.billing.paystack_billing import BillingService, PricingTier

        # Validate tier
        try:
            tier = PricingTier(request.tier.lower())
        except ValueError:
            raise HTTPException(400, f"Invalid tier: {request.tier}")

        billing = BillingService(db)
        
        # Default callback URL
        callback = request.callback_url or f"{settings.FRONTEND_URL}/billing?success=true"
        
        result = await billing.create_checkout_session(
            tenant_id=user.tenant_id,
            tier=tier,
            email=user.email,
            callback_url=callback
        )

        return {"checkout_url": result["url"], "reference": result["reference"]}

    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("checkout_failed", error=str(e))
        raise HTTPException(500, "Failed to create checkout session")


@router.post("/cancel")
async def cancel_subscription(
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db),
):
    """Cancel current subscription."""
    try:
        from app.services.billing.paystack_billing import BillingService

        billing = BillingService(db)
        await billing.cancel_subscription(user.tenant_id)

        return {"status": "cancelled"}

    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("cancel_failed", error=str(e))
        raise HTTPException(500, "Failed to cancel subscription")


@router.post("/webhook")
async def handle_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Handle Paystack webhook events with durable processing.
    
    Webhooks are stored in background_jobs before processing,
    enabling automatic retry on failure.
    """
    try:
        from app.services.billing.paystack_billing import WebhookHandler
        from app.services.billing.webhook_retry import WebhookRetryService
        import json

        payload = await request.body()
        signature = request.headers.get("x-paystack-signature", "")

        if not signature:
            raise HTTPException(401, "Missing signature")

        # Verify signature first
        handler = WebhookHandler(db)
        if not handler.verify_signature(payload, signature):
            raise HTTPException(401, "Invalid signature")

        # Parse payload
        data = json.loads(payload)
        event_type = data.get("event", "unknown")
        reference = data.get("data", {}).get("reference", "")

        # Store webhook for durable processing
        retry_service = WebhookRetryService(db)
        job = await retry_service.store_webhook(
            provider="paystack",
            event_type=event_type,
            payload=data,
            reference=reference
        )

        if job is None:
            # Duplicate webhook, already processed
            return {"status": "duplicate", "message": "Already processed"}

        # Process immediately (job stored for retry if fails)
        try:
            result = await handler.handle(payload, signature)
            return result
        except Exception as process_error:
            logger.warning(
                "webhook_processing_failed_will_retry",
                job_id=str(job.id),
                error=str(process_error)
            )
            # Job is already stored, will be retried by JobProcessor
            return {"status": "queued", "job_id": str(job.id)}

    except ValueError as e:
        logger.error("webhook_invalid", error=str(e))
        raise HTTPException(401, str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("webhook_failed", error=str(e))
        raise HTTPException(500, "Webhook processing failed")

