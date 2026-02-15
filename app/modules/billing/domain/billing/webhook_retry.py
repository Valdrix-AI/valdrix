"""
Webhook Retry Service - Revenue Protection (Tier 2)

Provides durable webhook processing using background_jobs infrastructure:
- Store failed webhooks for automatic retry
- Idempotency keys to prevent duplicate processing
- Exponential backoff on failures

Usage:
    service = WebhookRetryService(db)

    # Store webhook for processing (idempotent)
    job = await service.store_webhook(
        provider="paystack",
        event_type="charge.success",
        payload=data,
        idempotency_key=reference
    )

    # Process webhook (called by JobProcessor)
    result = await service.process_webhook(job_id)
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
import hashlib
import json
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.background_job import BackgroundJob, JobStatus, JobType
from app.modules.governance.domain.jobs.processor import enqueue_job
from app.shared.core.config import get_settings

logger = structlog.get_logger()

# Webhook configuration
WEBHOOK_MAX_ATTEMPTS = 5  # More retries for revenue-critical
WEBHOOK_IDEMPOTENCY_TTL_HOURS = 48  # Keep idempotency keys for 48h


class WebhookRetryService:
    """
    Durable webhook processing with retry and idempotency.

    Revenue Protection Features:
    - Webhooks are stored before processing (survives crashes)
    - Automatic retry with exponential backoff
    - Idempotency prevents duplicate subscription activations
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    def _generate_idempotency_key(
        self, provider: str, event_type: str, reference: str
    ) -> str:
        """Generate idempotency key from webhook data."""
        data = f"{provider}:{event_type}:{reference}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]

    async def is_duplicate(self, idempotency_key: str) -> bool:
        """Check if webhook was already processed successfully."""
        result = await self.db.execute(
            select(BackgroundJob).where(
                BackgroundJob.job_type == JobType.WEBHOOK_RETRY,
                BackgroundJob.payload["idempotency_key"].as_string() == idempotency_key,
                BackgroundJob.status == JobStatus.COMPLETED,
            )
        )

        existing = result.scalar_one_or_none()
        return existing is not None

    async def store_webhook(
        self,
        provider: str,
        event_type: str,
        payload: Dict[str, Any],
        reference: Optional[str] = None,
        signature: Optional[str] = None,
        raw_payload: Optional[str] = None,
    ) -> Optional[BackgroundJob]:
        """
        Store webhook for durable processing.

        Args:
            provider: Webhook source (e.g., "paystack", "stripe")
            event_type: Event type (e.g., "charge.success")
            payload: Full webhook payload
            reference: Unique reference for idempotency (e.g., transaction ref)

        Returns:
            BackgroundJob if new, None if duplicate
        """
        # Generate idempotency key
        ref = reference or payload.get("data", {}).get(
            "reference", str(datetime.now(timezone.utc))
        )
        idempotency_key = self._generate_idempotency_key(provider, event_type, ref)

        # Check for duplicate
        if await self.is_duplicate(idempotency_key):
            logger.info(
                "webhook_duplicate_ignored",
                provider=provider,
                event_type=event_type,
                idempotency_key=idempotency_key,
            )
            return None

        # Check for existing pending job
        result = await self.db.execute(
            select(BackgroundJob).where(
                BackgroundJob.job_type == JobType.WEBHOOK_RETRY,
                BackgroundJob.payload["idempotency_key"].as_string() == idempotency_key,
                BackgroundJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            logger.info(
                "webhook_already_queued",
                job_id=str(existing.id),
                status=existing.status,
            )
            return existing

        # Store new webhook job
        job_payload = {
            "provider": provider,
            "event_type": event_type,
            "payload": payload,
            "idempotency_key": idempotency_key,
            "reference": ref,
            "signature": signature,
            "raw_payload": raw_payload,
        }

        job = await enqueue_job(
            db=self.db,
            job_type=JobType.WEBHOOK_RETRY,
            payload=job_payload,
            max_attempts=WEBHOOK_MAX_ATTEMPTS,
        )

        logger.info(
            "webhook_stored",
            job_id=str(job.id),
            provider=provider,
            event_type=event_type,
            idempotency_key=idempotency_key,
        )

        return job

    async def get_pending_webhooks(
        self, provider: Optional[str] = None
    ) -> list[BackgroundJob]:
        """Get all pending webhook jobs."""
        query = (
            select(BackgroundJob)
            .where(
                BackgroundJob.job_type == JobType.WEBHOOK_RETRY,
                BackgroundJob.status == JobStatus.PENDING,
            )
            .order_by(BackgroundJob.scheduled_for)
        )

        if provider:
            query = query.where(
                BackgroundJob.payload["provider"].as_string() == provider
            )

        result = await self.db.execute(query)
        return list(result.scalars().all())


async def process_paystack_webhook(
    job: BackgroundJob, db: AsyncSession
) -> Dict[str, Any]:
    """
    Process Paystack webhook from background job.

    Called by JobProcessor._handle_webhook_retry()
    """
    from app.modules.billing.domain.billing.paystack_billing import WebhookHandler

    if not job.payload:
        return {"status": "error", "reason": "Missing payload"}

    payload = job.payload
    webhook_data = payload.get("payload", {})
    raw_payload = payload.get("raw_payload")
    signature = payload.get("signature")

    logger.info(
        "processing_paystack_webhook",
        job_id=str(job.id),
        event_type=payload.get("event_type"),
    )

    handler = WebhookHandler(db)

    event: str | None = None
    data: Dict[str, Any] = {}
    if raw_payload and signature:
        try:
            payload_bytes = raw_payload.encode("utf-8")
            if not handler.verify_signature(payload_bytes, signature):
                logger.critical(
                    "paystack_retry_signature_invalid",
                    job_id=str(job.id),
                    event_type=payload.get("event_type"),
                )
                return {"status": "error", "reason": "invalid_stored_signature"}
            parsed = json.loads(raw_payload)
            if not isinstance(parsed, dict):
                return {"status": "error", "reason": "invalid_raw_payload"}
            event = parsed.get("event", payload.get("event_type"))
            data = parsed.get("data", {})
        except Exception as exc:
            logger.error(
                "paystack_retry_payload_parse_failed",
                job_id=str(job.id),
                error=str(exc),
            )
            return {"status": "error", "reason": "invalid_raw_payload"}
    else:
        # Backward compatibility path for already-queued jobs without raw payload/signature.
        # Fail closed in production/staging environments.
        settings = get_settings()
        if settings.ENVIRONMENT in {"production", "staging"}:
            logger.critical(
                "paystack_retry_missing_signature_material",
                job_id=str(job.id),
                event_type=payload.get("event_type"),
            )
            return {"status": "error", "reason": "missing_signature_material"}

        event = webhook_data.get("event", payload.get("event_type"))
        data = webhook_data.get("data", {})

    result = {"status": "processed", "event": event}

    # Route to appropriate handler based on event type
    if event == "subscription.create":
        await handler._handle_subscription_create(data)
    elif event == "charge.success":
        await handler._handle_charge_success(data)
    elif event == "subscription.disable":
        await handler._handle_subscription_disable(data)
    elif event == "invoice.payment_failed":
        await handler._handle_invoice_failed(data)
    else:
        result["status"] = "ignored"
        result["reason"] = f"Unknown event type: {event}"

    return result
