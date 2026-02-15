"""
Notification Dispatcher - Unified Event-Driven Notifications

Bridges services (ZombieService, RemediationService) to actual providers (Slack, etc.).
This allows adding new channels (Teams, Discord, Email) without modifying domain logic.
"""

import structlog
from typing import Any, Dict, TYPE_CHECKING
from app.modules.notifications.domain import (
    get_jira_service,
    get_slack_service,
    get_tenant_teams_service,
    get_workflow_dispatchers,
    get_tenant_workflow_dispatchers,
    get_tenant_jira_service,
    get_tenant_slack_service,
)
from app.shared.core.config import get_settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class NotificationDispatcher:
    """
    Dispatcher responsible for routing alerts to appropriate providers.
    Currently focuses on Slack as the primary channel.
    """

    @staticmethod
    async def _resolve_slack_service(
        tenant_id: str | None = None,
        db: "AsyncSession | None" = None,
    ) -> Any:
        if tenant_id:
            if db is None:
                logger.warning(
                    "notification_slack_skipped_missing_tenant_db_context",
                    tenant_id=tenant_id,
                )
                return None
            return await get_tenant_slack_service(db, tenant_id)
        return get_slack_service()

    @staticmethod
    async def _resolve_teams_service(
        tenant_id: str | None = None,
        db: "AsyncSession | None" = None,
    ) -> Any:
        if not tenant_id:
            return None
        if db is None:
            logger.warning(
                "notification_teams_skipped_missing_tenant_db_context",
                tenant_id=tenant_id,
            )
            return None
        return await get_tenant_teams_service(db, tenant_id)

    @staticmethod
    async def send_alert(
        title: str,
        message: str,
        severity: str = "warning",
        tenant_id: str | None = None,
        db: "AsyncSession | None" = None,
    ) -> None:
        """Sends a generic alert to configured channels."""
        slack = await NotificationDispatcher._resolve_slack_service(
            tenant_id=tenant_id,
            db=db,
        )
        if slack:
            await slack.send_alert(title, message, severity)

        teams = await NotificationDispatcher._resolve_teams_service(
            tenant_id=tenant_id,
            db=db,
        )
        if teams:
            await teams.send_alert(title=title, message=message, severity=severity)

        logger.info("notification_dispatched", title=title, severity=severity)

    @staticmethod
    async def notify_zombies(
        zombies: Dict[str, Any],
        estimated_savings: float = 0.0,
        tenant_id: str | None = None,
        db: "AsyncSession | None" = None,
    ) -> None:
        """Dispatches zombie resource detection alerts."""
        slack = await NotificationDispatcher._resolve_slack_service(
            tenant_id=tenant_id,
            db=db,
        )
        if slack:
            await slack.notify_zombies(zombies, estimated_savings)

        teams = await NotificationDispatcher._resolve_teams_service(
            tenant_id=tenant_id,
            db=db,
        )
        if teams:
            await teams.notify_zombies(zombies, estimated_savings)

    @staticmethod
    async def notify_budget_alert(
        current_spend: float,
        budget_limit: float,
        percent_used: float,
        tenant_id: str | None = None,
        db: "AsyncSession | None" = None,
    ) -> None:
        """Dispatches budget threshold alerts."""
        slack = await NotificationDispatcher._resolve_slack_service(
            tenant_id=tenant_id,
            db=db,
        )
        if slack:
            await slack.notify_budget_alert(current_spend, budget_limit, percent_used)

        teams = await NotificationDispatcher._resolve_teams_service(
            tenant_id=tenant_id,
            db=db,
        )
        if teams:
            await teams.notify_budget_alert(current_spend, budget_limit, percent_used)

    @staticmethod
    async def notify_remediation_completed(
        tenant_id: str,
        resource_id: str,
        action: str,
        savings: float,
        request_id: str | None = None,
        provider: str | None = None,
        notify_workflow: bool = False,
        db: "AsyncSession | None" = None,
    ) -> None:
        """Dispatches remediation completion alerts."""
        title = f"Remediation Successful: {action.title()} {resource_id}"
        message = f"Tenant: {tenant_id}\nResource: {resource_id}\nAction: {action}\nMonthly Savings: ${savings:.2f}"

        await NotificationDispatcher.send_alert(
            title,
            message,
            severity="info",
            tenant_id=tenant_id,
            db=db,
        )
        if notify_workflow:
            await NotificationDispatcher._dispatch_workflow_event(
                event_type="remediation.completed",
                payload={
                    "tenant_id": tenant_id,
                    "request_id": request_id,
                    "resource_id": resource_id,
                    "action": action,
                    "provider": provider,
                    "status": "completed",
                    "monthly_savings_usd": savings,
                    "evidence_links": NotificationDispatcher._build_remediation_evidence_links(
                        request_id=request_id
                    ),
                },
                db=db,
                tenant_id=tenant_id,
            )

    @staticmethod
    def _build_remediation_evidence_links(request_id: str | None) -> dict[str, str]:
        settings = get_settings()
        api_base_url = (settings.WORKFLOW_EVIDENCE_BASE_URL or settings.API_URL).rstrip(
            "/"
        )
        frontend_base_url = (settings.FRONTEND_URL or api_base_url).rstrip("/")
        links = {
            "ops_dashboard": f"{frontend_base_url}/ops",
            "pending_requests_api": f"{api_base_url}/api/v1/zombies/pending",
        }
        if request_id:
            links.update(
                {
                    "policy_preview_api": f"{api_base_url}/api/v1/zombies/policy-preview/{request_id}",
                    "remediation_plan_api": f"{api_base_url}/api/v1/zombies/plan/{request_id}",
                    "approve_api": f"{api_base_url}/api/v1/zombies/approve/{request_id}",
                    "execute_api": f"{api_base_url}/api/v1/zombies/execute/{request_id}",
                }
            )
        return links

    @staticmethod
    async def _dispatch_workflow_event(
        event_type: str,
        payload: dict[str, Any],
        db: "AsyncSession | None" = None,
        tenant_id: str | None = None,
    ) -> None:
        dispatchers: list[Any] = []
        if tenant_id:
            if db is None:
                logger.warning(
                    "workflow_dispatch_skipped_missing_tenant_db_context",
                    event_type=event_type,
                    tenant_id=tenant_id,
                )
                return
            dispatchers = await get_tenant_workflow_dispatchers(db, tenant_id)
            if not dispatchers:
                logger.info(
                    "workflow_dispatch_skipped_no_tenant_dispatchers",
                    event_type=event_type,
                    tenant_id=tenant_id,
                )
                return
        else:
            dispatchers = get_workflow_dispatchers()
        if not dispatchers:
            logger.info(
                "workflow_dispatch_skipped_no_dispatchers", event_type=event_type
            )
            return
        for dispatcher in dispatchers:
            ok = await dispatcher.dispatch(event_type, payload)
            if not ok:
                logger.warning(
                    "workflow_dispatch_failed",
                    event_type=event_type,
                    provider=getattr(dispatcher, "provider", "unknown"),
                    tenant_id=payload.get("tenant_id"),
                    request_id=payload.get("request_id"),
                )
                continue
            logger.info(
                "workflow_dispatch_succeeded",
                event_type=event_type,
                provider=getattr(dispatcher, "provider", "unknown"),
                tenant_id=payload.get("tenant_id"),
                request_id=payload.get("request_id"),
            )

    @staticmethod
    async def notify_policy_event(
        tenant_id: str,
        decision: str,
        summary: str,
        resource_id: str,
        action: str,
        notify_slack: bool = True,
        notify_jira: bool = False,
        notify_teams: bool = False,
        notify_workflow: bool = False,
        request_id: str | None = None,
        db: "AsyncSession | None" = None,
    ) -> None:
        """Dispatches remediation policy violation/escalation alerts."""
        title = f"Policy {decision.title()}: {action}"
        message = (
            f"Tenant: {tenant_id}\n"
            f"Resource: {resource_id}\n"
            f"Action: {action}\n"
            f"Policy Decision: {decision}\n"
            f"Summary: {summary}"
        )
        severity = "critical" if decision in {"block", "escalate"} else "warning"
        if notify_slack:
            slack = None
            if db is not None:
                slack = await get_tenant_slack_service(db, tenant_id)
            else:
                slack = get_slack_service()

            if slack:
                await slack.send_alert(title, message, severity)
            else:
                logger.warning(
                    "policy_notification_slack_not_configured",
                    tenant_id=tenant_id,
                    decision=decision,
                )

        if notify_teams:
            teams = None
            if db is not None:
                teams = await get_tenant_teams_service(db, tenant_id)
            if teams:
                await teams.send_alert(
                    title=title,
                    message=message,
                    severity=severity,
                    actions=NotificationDispatcher._build_remediation_evidence_links(
                        request_id=request_id
                    ),
                )
            else:
                logger.warning(
                    "policy_notification_teams_not_configured",
                    tenant_id=tenant_id,
                    decision=decision,
                )

        if notify_jira:
            jira = None
            if db is not None:
                jira = await get_tenant_jira_service(db, tenant_id)
            else:
                jira = get_jira_service()
            if jira:
                await jira.create_policy_issue(
                    tenant_id=tenant_id,
                    decision=decision,
                    policy_summary=summary,
                    resource_id=resource_id,
                    action=action,
                    severity=severity,
                )
            else:
                logger.warning(
                    "policy_notification_jira_not_configured",
                    tenant_id=tenant_id,
                    decision=decision,
                )
        if notify_workflow:
            await NotificationDispatcher._dispatch_workflow_event(
                event_type=f"policy.{decision}",
                payload={
                    "tenant_id": tenant_id,
                    "request_id": request_id,
                    "decision": decision,
                    "summary": summary,
                    "resource_id": resource_id,
                    "action": action,
                    "severity": severity,
                    "evidence_links": NotificationDispatcher._build_remediation_evidence_links(
                        request_id=request_id
                    ),
                },
                db=db,
                tenant_id=tenant_id,
            )

        logger.info(
            "policy_notification_dispatched",
            tenant_id=tenant_id,
            decision=decision,
            notify_slack=notify_slack,
            notify_jira=notify_jira,
            notify_workflow=notify_workflow,
        )
