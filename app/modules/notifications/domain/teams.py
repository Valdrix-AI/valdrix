"""
Microsoft Teams notification service (tenant-scoped, SaaS-safe).

Valdrix supports Teams via an incoming webhook URL configured per tenant.
We treat the webhook URL as a secret (encrypted at rest) because it grants
message-post capability into the channel.

Design goals:
- Tenant-scoped (no env-only requirement for SaaS execution paths)
- Safe URL validation (SSRF controls, HTTPS, allowlist)
- Simple message formatting with optional action links (approval/review links)
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification_settings import NotificationSettings
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


def _validate_webhook_url(
    url: str,
    allowlist: set[str],
    *,
    require_https: bool,
    block_private_ips: bool,
) -> None:
    parsed = urlparse(url)
    if require_https and parsed.scheme.lower() != "https":
        raise ValueError("Teams webhook URL must use HTTPS")
    if not parsed.hostname:
        raise ValueError("Teams webhook URL must include a host")
    if parsed.username or parsed.password:
        raise ValueError("Teams webhook URL must not include credentials")

    host = parsed.hostname.lower()
    if block_private_ips and (host in {"localhost"} or host.endswith(".local")):
        raise ValueError("Teams webhook URL must not target local hostnames")
    if block_private_ips and _is_private_or_link_local(host):
        raise ValueError(
            "Teams webhook URL must not target private or link-local addresses"
        )
    if not _host_allowed(host, allowlist):
        raise ValueError("Teams webhook URL host is not in allowlist")


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    # Keep it deterministic and obviously truncated.
    return text[: max(0, max_chars - 12)] + "… (truncated)"


@dataclass(slots=True)
class TeamsService:
    webhook_url: str
    timeout_seconds: float

    async def health_check(self) -> tuple[bool, int | None, str | None]:
        """
        Passive health check.

        Teams incoming webhooks don't provide a safe "auth_test" equivalent.
        For scheduled acceptance evidence, we validate URL safety/allowlist only.
        """
        settings = get_settings()
        allowlist = {
            d.lower()
            for d in getattr(settings, "TEAMS_WEBHOOK_ALLOWED_DOMAINS", [])
            if d
        }
        require_https = bool(getattr(settings, "TEAMS_WEBHOOK_REQUIRE_HTTPS", True))
        block_private_ips = bool(
            getattr(settings, "TEAMS_WEBHOOK_BLOCK_PRIVATE_IPS", True)
        )
        try:
            _validate_webhook_url(
                self.webhook_url,
                allowlist,
                require_https=require_https,
                block_private_ips=block_private_ips,
            )
            return True, 200, None
        except Exception as exc:  # noqa: BLE001 - best-effort diagnostics
            return False, 400, str(exc)

    async def send_alert(
        self,
        *,
        title: str,
        message: str,
        severity: str = "warning",
        actions: dict[str, str] | None = None,
    ) -> bool:
        """
        Send an alert to Microsoft Teams via incoming webhook.

        "actions" are rendered as OpenUrl buttons (review/approve links).
        """
        settings = get_settings()
        allowlist = {
            d.lower()
            for d in getattr(settings, "TEAMS_WEBHOOK_ALLOWED_DOMAINS", [])
            if d
        }
        require_https = bool(getattr(settings, "TEAMS_WEBHOOK_REQUIRE_HTTPS", True))
        block_private_ips = bool(
            getattr(settings, "TEAMS_WEBHOOK_BLOCK_PRIVATE_IPS", True)
        )
        try:
            _validate_webhook_url(
                self.webhook_url,
                allowlist,
                require_https=require_https,
                block_private_ips=block_private_ips,
            )
        except Exception as exc:
            logger.warning("teams_webhook_url_invalid", error=str(exc))
            return False

        safe_title = _truncate(str(title or "Valdrix Alert"), 256)
        safe_message = _truncate(str(message or ""), 7000)
        safe_severity = (severity or "warning").strip().lower()
        color = {
            "info": "good",
            "warning": "warning",
            "critical": "attention",
        }.get(safe_severity, "warning")

        buttons: list[dict[str, Any]] = []
        for label, url in (actions or {}).items():
            if not label or not url:
                continue
            buttons.append(
                {
                    "type": "Action.OpenUrl",
                    "title": _truncate(str(label), 32),
                    "url": str(url),
                }
            )

        payload: dict[str, Any] = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "msteams": {"width": "Full"},
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": safe_title,
                                "weight": "Bolder",
                                "size": "Large",
                                "wrap": True,
                                "color": color,
                            },
                            {
                                "type": "TextBlock",
                                "text": safe_message,
                                "wrap": True,
                                "spacing": "Medium",
                            },
                        ],
                        "actions": buttons,
                    },
                }
            ],
        }

        try:
            from app.shared.core.http import get_http_client

            client = get_http_client()
            resp = await client.post(self.webhook_url, json=payload)
            # Teams webhooks typically return 200 OK on success.
            if 200 <= resp.status_code < 300:
                return True
            logger.warning(
                "teams_send_failed",
                status_code=resp.status_code,
                response=resp.text[:300],
            )
            return False
        except Exception as exc:
            logger.warning("teams_send_exception", error=str(exc))
            return False

    async def notify_zombies(
        self, zombies: dict[str, Any], estimated_savings: float = 0.0
    ) -> bool:
        zombie_count = sum(
            len(items) for items in zombies.values() if isinstance(items, list)
        )
        if zombie_count == 0:
            return True
        summary_lines: list[str] = []
        for cat, items in zombies.items():
            if isinstance(items, list) and items:
                summary_lines.append(f"- {cat.replace('_', ' ').title()}: {len(items)}")
        message = (
            f"Found {zombie_count} zombie resources.\n\n"
            + "\n".join(summary_lines)
            + f"\n\nEstimated savings: ${estimated_savings:.2f}/mo"
        )
        return await self.send_alert(
            title="Zombie Resources Detected",
            message=message,
            severity="warning",
        )

    async def notify_budget_alert(
        self, current_spend: float, budget_limit: float, percent_used: float
    ) -> bool:
        severity = "critical" if percent_used >= 100 else "warning"
        message = (
            f"Current spend: ${current_spend:.2f}\n"
            f"Budget limit: ${budget_limit:.2f}\n"
            f"Usage: {percent_used:.1f}%"
        )
        return await self.send_alert(
            title="Budget Alert Threshold Reached",
            message=message,
            severity=severity,
        )


async def get_tenant_teams_service(
    db: AsyncSession, tenant_id: UUID | str
) -> TeamsService | None:
    """
    Build Teams service from tenant-scoped notification settings.

    This is the recommended path for SaaS multi-tenant delivery.
    """
    try:
        tenant_uuid = UUID(str(tenant_id))
    except ValueError:
        logger.warning(
            "tenant_teams_settings_invalid_tenant_id", tenant_id=str(tenant_id)
        )
        return None

    notif = (
        await db.execute(
            select(NotificationSettings).where(
                NotificationSettings.tenant_id == tenant_uuid
            )
        )
    ).scalar_one_or_none()
    if not notif:
        return None
    if not bool(getattr(notif, "teams_enabled", False)):
        return None
    webhook_url = getattr(notif, "teams_webhook_url", None)
    if not webhook_url:
        return None

    settings = get_settings()
    timeout_seconds = float(getattr(settings, "TEAMS_TIMEOUT_SECONDS", 10.0))
    return TeamsService(webhook_url=str(webhook_url), timeout_seconds=timeout_seconds)
