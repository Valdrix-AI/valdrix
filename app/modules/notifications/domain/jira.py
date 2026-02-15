"""
Jira notification service for Valdrix policy violations and escalations.
"""

from __future__ import annotations

import re
from typing import Iterable
from uuid import UUID

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class JiraService:
    """Service for creating Jira issues via REST API."""

    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        project_key: str,
        issue_type: str = "Task",
        timeout_seconds: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.api_token = api_token
        self.project_key = project_key
        self.issue_type = issue_type
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _sanitize_label(label: str) -> str:
        sanitized = re.sub(r"[^a-zA-Z0-9_-]+", "-", label.strip().lower()).strip("-")
        return sanitized[:64] if sanitized else "valdrix"

    async def create_issue(
        self,
        summary: str,
        description: str,
        labels: Iterable[str] | None = None,
    ) -> bool:
        jira_labels = [self._sanitize_label(value) for value in (labels or ())]
        payload = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": summary[:240],
                "description": description,
                "issuetype": {"name": self.issue_type},
                "labels": jira_labels,
            }
        }

        endpoint = f"{self.base_url}/rest/api/3/issue"

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    endpoint,
                    json=payload,
                    auth=httpx.BasicAuth(self.email, self.api_token),
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                )
            if response.status_code not in {200, 201}:
                logger.warning(
                    "jira_issue_create_failed",
                    status_code=response.status_code,
                    response=response.text[:300],
                )
                return False
            return True
        except Exception as exc:
            logger.warning("jira_issue_create_exception", error=str(exc))
            return False

    async def health_check(self) -> tuple[bool, int | None, str | None]:
        """
        Perform a non-invasive Jira connectivity check.

        This validates credentials and base URL without creating issues.
        """
        endpoint = f"{self.base_url}/rest/api/3/myself"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(
                    endpoint,
                    auth=httpx.BasicAuth(self.email, self.api_token),
                    headers={"Accept": "application/json"},
                )
            if response.status_code == 200:
                return True, response.status_code, None
            logger.warning(
                "jira_health_check_failed",
                status_code=response.status_code,
                response=response.text[:300],
            )
            return False, response.status_code, response.text[:300]
        except Exception as exc:
            logger.warning("jira_health_check_exception", error=str(exc))
            return False, None, str(exc)

    async def create_policy_issue(
        self,
        tenant_id: str,
        decision: str,
        policy_summary: str,
        resource_id: str,
        action: str,
        severity: str,
    ) -> bool:
        summary = f"[Valdrix Policy {decision.upper()}] {action} on {resource_id}"
        description = (
            f"h2. Valdrix remediation policy event\n"
            f"*Tenant:* {tenant_id}\n"
            f"*Decision:* {decision}\n"
            f"*Severity:* {severity}\n"
            f"*Action:* {action}\n"
            f"*Resource:* {resource_id}\n"
            f"*Summary:* {policy_summary}\n"
        )
        return await self.create_issue(
            summary=summary,
            description=description,
            labels=["valdrix", "policy", decision, severity],
        )

    async def create_cost_anomaly_issue(
        self,
        *,
        tenant_id: str,
        day: str,
        provider: str,
        account_id: str,
        account_name: str | None,
        service: str,
        kind: str,
        severity: str,
        actual_cost_usd: float,
        expected_cost_usd: float,
        delta_cost_usd: float,
        percent_change: float | None,
        confidence: float,
        probable_cause: str,
    ) -> bool:
        from app.shared.core.config import get_settings

        settings = get_settings()
        api_base = (settings.WORKFLOW_EVIDENCE_BASE_URL or settings.API_URL).rstrip("/")
        frontend_base = (settings.FRONTEND_URL or api_base).rstrip("/")
        evidence_link = (
            f"{api_base}/api/v1/costs/anomalies"
            f"?target_date={day}&provider={provider}&min_severity={severity}"
        )

        summary = f"[Valdrix Cost Anomaly {severity.upper()}] {service} ({kind}) {day}"
        description = (
            "h2. Valdrix cost anomaly detected\n"
            f"*Tenant:* {tenant_id}\n"
            f"*Date:* {day}\n"
            f"*Provider:* {provider}\n"
            f"*Account:* {(account_name or account_id)}\n"
            f"*Service:* {service}\n"
            f"*Type:* {kind}\n"
            f"*Severity:* {severity}\n"
            f"*Actual:* ${actual_cost_usd:,.2f}\n"
            f"*Expected:* ${expected_cost_usd:,.2f}\n"
            f"*Delta:* ${delta_cost_usd:,.2f}\n"
            f"*Percent change:* {percent_change if percent_change is not None else 'n/a'}\n"
            f"*Confidence:* {confidence:.2f}\n"
            f"*Cause:* {probable_cause}\n\n"
            f"*Evidence:* {evidence_link}\n"
            f"*Ops dashboard:* {frontend_base}/ops\n"
        )
        return await self.create_issue(
            summary=summary,
            description=description,
            labels=["valdrix", "cost-anomaly", severity, provider, kind],
        )


def get_jira_service() -> JiraService | None:
    """Factory for Jira service. Returns None when not fully configured."""
    from app.shared.core.config import get_settings

    settings = get_settings()
    if getattr(settings, "SAAS_STRICT_INTEGRATIONS", False):
        logger.info("env_jira_service_disabled_by_saas_strict_mode")
        return None

    if (
        settings.JIRA_BASE_URL
        and settings.JIRA_EMAIL
        and settings.JIRA_API_TOKEN
        and settings.JIRA_PROJECT_KEY
    ):
        return JiraService(
            base_url=settings.JIRA_BASE_URL,
            email=settings.JIRA_EMAIL,
            api_token=settings.JIRA_API_TOKEN,
            project_key=settings.JIRA_PROJECT_KEY,
            issue_type=settings.JIRA_ISSUE_TYPE,
            timeout_seconds=settings.JIRA_TIMEOUT_SECONDS,
        )
    return None


async def get_tenant_jira_service(
    db: AsyncSession, tenant_id: UUID | str
) -> JiraService | None:
    """
    Build Jira service from tenant-scoped notification settings.
    Returns None if Jira integration is disabled or incomplete for the tenant.
    """
    from app.models.notification_settings import NotificationSettings
    from app.shared.core.config import get_settings

    try:
        tenant_uuid = UUID(str(tenant_id))
    except ValueError:
        logger.warning(
            "tenant_jira_settings_invalid_tenant_id", tenant_id=str(tenant_id)
        )
        return None
    result = await db.execute(
        select(NotificationSettings).where(
            NotificationSettings.tenant_id == tenant_uuid
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        return None

    jira_enabled = bool(getattr(notif, "jira_enabled", False))
    jira_base_url = getattr(notif, "jira_base_url", None)
    jira_email = getattr(notif, "jira_email", None)
    jira_project_key = getattr(notif, "jira_project_key", None)
    jira_issue_type = (
        getattr(notif, "jira_issue_type", None) or "Task"
    ).strip() or "Task"
    jira_api_token = getattr(notif, "jira_api_token", None)

    if not jira_enabled:
        return None

    if (
        not jira_base_url
        or not jira_email
        or not jira_project_key
        or not jira_api_token
    ):
        logger.warning(
            "tenant_jira_settings_incomplete",
            tenant_id=str(tenant_uuid),
            has_base_url=bool(jira_base_url),
            has_email=bool(jira_email),
            has_project_key=bool(jira_project_key),
            has_token=bool(jira_api_token),
        )
        return None

    settings = get_settings()
    return JiraService(
        base_url=jira_base_url,
        email=jira_email,
        api_token=jira_api_token,
        project_key=jira_project_key,
        issue_type=jira_issue_type,
        timeout_seconds=settings.JIRA_TIMEOUT_SECONDS,
    )
