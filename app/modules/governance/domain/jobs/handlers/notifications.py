"""Notification and Webhook Job Handlers."""

from typing import Dict, Any
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.background_job import BackgroundJob
from app.modules.governance.domain.jobs.handlers.base import BaseJobHandler
from app.shared.core.config import get_settings
from app.shared.core.webhooks import sanitize_webhook_headers, validate_webhook_url

logger = structlog.get_logger()


class NotificationHandler(BaseJobHandler):
    """Handle notification job (Slack, Email, etc.)."""

    async def execute(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        from app.modules.notifications.domain import (
            get_slack_service,
            get_tenant_slack_service,
        )

        payload = job.payload or {}
        message = payload.get("message")
        title = payload.get("title", "Valdrics Notification")
        severity = payload.get("severity", "info")

        if not message:
            raise ValueError("message required for notification")

        service = None
        if job.tenant_id:
            service = await get_tenant_slack_service(db, job.tenant_id)
        else:
            service = get_slack_service()
        if not service:
            return {"status": "skipped", "reason": "slack_not_configured"}

        success = await service.send_alert(
            title=title, message=message, severity=severity
        )

        return {"status": "completed", "success": success}


class WebhookRetryHandler(BaseJobHandler):
    """Handle webhook retry job (e.g., Paystack)."""

    async def execute(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        payload = job.payload or {}
        provider = payload.get("provider", "generic")

        if provider == "paystack":
            from app.modules.billing.domain.billing.webhook_retry import (
                process_paystack_webhook,
            )

            return await process_paystack_webhook(job, db)

        # Generic HTTP webhook retry

        url = payload.get("url")
        data = payload.get("data")
        headers = payload.get("headers", {})

        if not url:
            raise ValueError("url required for generic webhook_retry")

        settings = get_settings()
        allowlist = {d.lower() for d in settings.WEBHOOK_ALLOWED_DOMAINS if d}
        if not allowlist:
            raise ValueError(
                "WEBHOOK_ALLOWED_DOMAINS must be configured for generic webhook retries"
            )

        validate_webhook_url(
            url=url,
            allowlist=allowlist,
            require_https=settings.WEBHOOK_REQUIRE_HTTPS,
            block_private_ips=settings.WEBHOOK_BLOCK_PRIVATE_IPS,
        )

        try:
            headers = sanitize_webhook_headers(headers)
        except ValueError as exc:
            logger.warning("webhook_headers_rejected", error=str(exc))
            raise

        from app.shared.core.http import get_http_client

        client = get_http_client()
        response = await client.post(url, json=data, headers=headers, timeout=30)
        response.raise_for_status()

        return {"status": "completed", "status_code": response.status_code}
