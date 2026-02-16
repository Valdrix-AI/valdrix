"""
Workflow dispatch service for GitHub/GitLab/generic CI integrations.

This module sends deterministic remediation/policy events into external
automation systems so runbooks can be enforced via CI workflows.
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import json
from typing import Any, Protocol
from urllib.parse import quote, urlparse
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification_settings import NotificationSettings
from app.shared.core.config import get_settings

logger = structlog.get_logger()


class WorkflowDispatcher(Protocol):
    provider: str

    async def dispatch(self, event_type: str, payload: dict[str, Any]) -> bool:
        """Dispatch a workflow event to an external automation target."""


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
        raise ValueError("Workflow webhook URL must use HTTPS")
    if not parsed.hostname:
        raise ValueError("Workflow webhook URL must include a host")
    if parsed.username or parsed.password:
        raise ValueError("Workflow webhook URL must not include credentials")

    host = parsed.hostname.lower()
    if block_private_ips and (host in {"localhost"} or host.endswith(".local")):
        raise ValueError("Workflow webhook URL must not target local hostnames")
    if block_private_ips and _is_private_or_link_local(host):
        raise ValueError(
            "Workflow webhook URL must not target private or link-local addresses"
        )
    if not _host_allowed(host, allowlist):
        raise ValueError("Workflow webhook URL host is not in allowlist")


def _serialize_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, default=str, separators=(",", ":"), sort_keys=True)


@dataclass(slots=True)
class GitHubActionsDispatcher:
    owner: str
    repo: str
    workflow_id: str
    ref: str
    token: str
    timeout_seconds: float
    provider: str = "github_actions"

    async def dispatch(self, event_type: str, payload: dict[str, Any]) -> bool:
        endpoint = (
            f"https://api.github.com/repos/{self.owner}/{self.repo}"
            f"/actions/workflows/{self.workflow_id}/dispatches"
        )
        body = {
            "ref": self.ref,
            "inputs": {
                "event_type": event_type[:64],
                "tenant_id": str(payload.get("tenant_id", ""))[:128],
                "request_id": str(payload.get("request_id", ""))[:128],
                "payload_json": _serialize_payload(payload)[:60000],
            },
        }
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            from app.shared.core.http import get_http_client

            client = get_http_client()
            response = await client.post(endpoint, json=body, headers=headers)
            if response.status_code in {200, 201, 204}:
                return True
            logger.warning(
                "workflow_dispatch_failed",
                provider=self.provider,
                status_code=response.status_code,
                response=response.text[:300],
            )
            return False
        except Exception as exc:
            logger.warning(
                "workflow_dispatch_exception", provider=self.provider, error=str(exc)
            )
            return False


@dataclass(slots=True)
class GitLabCIDispatcher:
    base_url: str
    project_id: str
    ref: str
    trigger_token: str
    timeout_seconds: float
    provider: str = "gitlab_ci"

    async def dispatch(self, event_type: str, payload: dict[str, Any]) -> bool:
        encoded_project = quote(self.project_id, safe="")
        endpoint = f"{self.base_url.rstrip('/')}/api/v4/projects/{encoded_project}/trigger/pipeline"
        form = {
            "token": self.trigger_token,
            "ref": self.ref,
            "variables[VALDRIX_EVENT_TYPE]": event_type[:64],
            "variables[VALDRIX_TENANT_ID]": str(payload.get("tenant_id", ""))[:128],
            "variables[VALDRIX_REQUEST_ID]": str(payload.get("request_id", ""))[:128],
            "variables[VALDRIX_PAYLOAD_JSON]": _serialize_payload(payload)[:10000],
        }
        try:
            from app.shared.core.http import get_http_client

            client = get_http_client()
            response = await client.post(endpoint, data=form)
            if response.status_code in {200, 201}:
                return True
            logger.warning(
                "workflow_dispatch_failed",
                provider=self.provider,
                status_code=response.status_code,
                response=response.text[:300],
            )
            return False
        except Exception as exc:
            logger.warning(
                "workflow_dispatch_exception", provider=self.provider, error=str(exc)
            )
            return False


@dataclass(slots=True)
class GenericCIWebhookDispatcher:
    url: str
    bearer_token: str | None
    timeout_seconds: float
    provider: str = "generic_ci_webhook"

    async def dispatch(self, event_type: str, payload: dict[str, Any]) -> bool:
        settings = get_settings()
        allowlist = {d.lower() for d in settings.WEBHOOK_ALLOWED_DOMAINS if d}
        try:
            _validate_webhook_url(
                self.url,
                allowlist,
                require_https=settings.WEBHOOK_REQUIRE_HTTPS,
                block_private_ips=settings.WEBHOOK_BLOCK_PRIVATE_IPS,
            )
        except Exception as exc:
            logger.warning(
                "workflow_webhook_url_invalid",
                provider=self.provider,
                error=str(exc),
            )
            return False

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"

        body = {"event_type": event_type, "payload": payload}
        try:
            from app.shared.core.http import get_http_client

            client = get_http_client()
            response = await client.post(self.url, json=body, headers=headers)
            if 200 <= response.status_code < 300:
                return True
            logger.warning(
                "workflow_dispatch_failed",
                provider=self.provider,
                status_code=response.status_code,
                response=response.text[:300],
            )
            return False
        except Exception as exc:
            logger.warning(
                "workflow_dispatch_exception", provider=self.provider, error=str(exc)
            )
            return False


def get_workflow_dispatchers() -> list[WorkflowDispatcher]:
    """
    Build all configured workflow dispatchers.

    Dispatchers are env-configured; if a provider is enabled but incomplete,
    it is skipped and a warning is logged.
    """
    settings = get_settings()
    if getattr(settings, "SAAS_STRICT_INTEGRATIONS", False):
        logger.info("env_workflow_dispatchers_disabled_by_saas_strict_mode")
        return []

    dispatchers: list[WorkflowDispatcher] = []
    timeout_seconds = float(settings.WORKFLOW_DISPATCH_TIMEOUT_SECONDS)

    if settings.GITHUB_ACTIONS_ENABLED:
        if (
            settings.GITHUB_ACTIONS_OWNER
            and settings.GITHUB_ACTIONS_REPO
            and settings.GITHUB_ACTIONS_WORKFLOW_ID
            and settings.GITHUB_ACTIONS_TOKEN
        ):
            dispatchers.append(
                GitHubActionsDispatcher(
                    owner=settings.GITHUB_ACTIONS_OWNER,
                    repo=settings.GITHUB_ACTIONS_REPO,
                    workflow_id=settings.GITHUB_ACTIONS_WORKFLOW_ID,
                    ref=settings.GITHUB_ACTIONS_REF,
                    token=settings.GITHUB_ACTIONS_TOKEN,
                    timeout_seconds=timeout_seconds,
                )
            )
        else:
            logger.warning(
                "workflow_dispatch_config_incomplete", provider="github_actions"
            )

    if settings.GITLAB_CI_ENABLED:
        if settings.GITLAB_CI_PROJECT_ID and settings.GITLAB_CI_TRIGGER_TOKEN:
            dispatchers.append(
                GitLabCIDispatcher(
                    base_url=settings.GITLAB_CI_BASE_URL,
                    project_id=settings.GITLAB_CI_PROJECT_ID,
                    ref=settings.GITLAB_CI_REF,
                    trigger_token=settings.GITLAB_CI_TRIGGER_TOKEN,
                    timeout_seconds=timeout_seconds,
                )
            )
        else:
            logger.warning("workflow_dispatch_config_incomplete", provider="gitlab_ci")

    if settings.GENERIC_CI_WEBHOOK_ENABLED:
        if settings.GENERIC_CI_WEBHOOK_URL:
            dispatchers.append(
                GenericCIWebhookDispatcher(
                    url=settings.GENERIC_CI_WEBHOOK_URL,
                    bearer_token=settings.GENERIC_CI_WEBHOOK_BEARER_TOKEN,
                    timeout_seconds=timeout_seconds,
                )
            )
        else:
            logger.warning(
                "workflow_dispatch_config_incomplete", provider="generic_ci_webhook"
            )

    return dispatchers


async def get_tenant_workflow_dispatchers(
    db: AsyncSession,
    tenant_id: UUID | str,
) -> list[WorkflowDispatcher]:
    """
    Build workflow dispatchers from tenant-scoped notification settings.

    This is the primary path for SaaS multi-tenant workflow automation.
    """
    try:
        tenant_uuid = UUID(str(tenant_id))
    except ValueError:
        logger.warning(
            "tenant_workflow_settings_invalid_tenant_id", tenant_id=str(tenant_id)
        )
        return []

    result = await db.execute(
        select(NotificationSettings).where(
            NotificationSettings.tenant_id == tenant_uuid
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        return []

    settings = get_settings()
    timeout_seconds = float(settings.WORKFLOW_DISPATCH_TIMEOUT_SECONDS)
    dispatchers: list[WorkflowDispatcher] = []

    if bool(getattr(notif, "workflow_github_enabled", False)):
        owner = getattr(notif, "workflow_github_owner", None)
        repo = getattr(notif, "workflow_github_repo", None)
        workflow_id = getattr(notif, "workflow_github_workflow_id", None)
        token = getattr(notif, "workflow_github_token", None)
        ref = (getattr(notif, "workflow_github_ref", None) or "main").strip() or "main"
        if owner and repo and workflow_id and token:
            dispatchers.append(
                GitHubActionsDispatcher(
                    owner=owner,
                    repo=repo,
                    workflow_id=workflow_id,
                    ref=ref,
                    token=token,
                    timeout_seconds=timeout_seconds,
                )
            )
        else:
            logger.warning(
                "tenant_workflow_dispatch_config_incomplete",
                provider="github_actions",
                tenant_id=str(tenant_uuid),
            )

    if bool(getattr(notif, "workflow_gitlab_enabled", False)):
        base_url = (
            getattr(notif, "workflow_gitlab_base_url", None) or "https://gitlab.com"
        ).strip()
        project_id = getattr(notif, "workflow_gitlab_project_id", None)
        ref = (getattr(notif, "workflow_gitlab_ref", None) or "main").strip() or "main"
        trigger_token = getattr(notif, "workflow_gitlab_trigger_token", None)
        if project_id and trigger_token:
            dispatchers.append(
                GitLabCIDispatcher(
                    base_url=base_url,
                    project_id=project_id,
                    ref=ref,
                    trigger_token=trigger_token,
                    timeout_seconds=timeout_seconds,
                )
            )
        else:
            logger.warning(
                "tenant_workflow_dispatch_config_incomplete",
                provider="gitlab_ci",
                tenant_id=str(tenant_uuid),
            )

    if bool(getattr(notif, "workflow_webhook_enabled", False)):
        url = getattr(notif, "workflow_webhook_url", None)
        bearer = getattr(notif, "workflow_webhook_bearer_token", None)
        if url:
            dispatchers.append(
                GenericCIWebhookDispatcher(
                    url=url,
                    bearer_token=bearer,
                    timeout_seconds=timeout_seconds,
                )
            )
        else:
            logger.warning(
                "tenant_workflow_dispatch_config_incomplete",
                provider="generic_ci_webhook",
                tenant_id=str(tenant_uuid),
            )

    return dispatchers
