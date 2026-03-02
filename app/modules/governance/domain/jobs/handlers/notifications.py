"""
Notification and Webhook Job Handlers
"""

from typing import Dict, Any
from urllib.parse import urlparse
import ipaddress
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.background_job import BackgroundJob
from app.modules.governance.domain.jobs.handlers.base import BaseJobHandler
from app.shared.core.config import get_settings

logger = structlog.get_logger()


def _is_private_or_link_local(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False

    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
    )


def _host_allowed(host: str, allowlist: set[str]) -> bool:
    if not allowlist:
        return False
    if host in allowlist:
        return True
    return any(host.endswith(f".{allowed}") for allowed in allowlist)


def _sanitize_headers(headers: Dict[str, Any]) -> Dict[str, str]:
    sanitized: Dict[str, str] = {}
    if not isinstance(headers, dict):
        return {"Content-Type": "application/json"}

    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        key_lower = key.strip().lower()
        if key_lower == "content-type":
            content_type = value.split(";")[0].strip().lower()
            if content_type != "application/json":
                raise ValueError(
                    "content-type must be application/json for webhook retries"
                )
            sanitized["Content-Type"] = "application/json"
        elif key_lower in {"authorization", "user-agent"} or key_lower.startswith("x-"):
            sanitized[key] = value

    if "Content-Type" not in sanitized:
        sanitized["Content-Type"] = "application/json"
    return sanitized


def _validate_webhook_url(
    url: str, allowlist: set[str], require_https: bool, block_private_ips: bool
) -> None:
    parsed = urlparse(url)
    if require_https and parsed.scheme.lower() != "https":
        raise ValueError("Webhook URL must use HTTPS")
    if not parsed.hostname:
        raise ValueError("Webhook URL must include a host")
    if parsed.username or parsed.password:
        raise ValueError("Webhook URL must not include credentials")

    host = parsed.hostname.lower()
    if block_private_ips and (host in {"localhost"} or host.endswith(".local")):
        raise ValueError("Webhook URL must not target local hostnames")
    if block_private_ips and _is_private_or_link_local(host):
        raise ValueError("Webhook URL must not target private or link-local addresses")

    if not _host_allowed(host, allowlist):
        raise ValueError("Webhook URL host is not in allowlist")


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

        _validate_webhook_url(
            url=url,
            allowlist=allowlist,
            require_https=settings.WEBHOOK_REQUIRE_HTTPS,
            block_private_ips=settings.WEBHOOK_BLOCK_PRIVATE_IPS,
        )

        try:
            headers = _sanitize_headers(headers)
        except ValueError as exc:
            logger.warning("webhook_headers_rejected", error=str(exc))
            raise

        from app.shared.core.http import get_http_client

        client = get_http_client()
        response = await client.post(url, json=data, headers=headers, timeout=30)
        response.raise_for_status()

        return {"status": "completed", "status_code": response.status_code}
