from __future__ import annotations

import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import structlog
from sqlalchemy import select

from app.models.remediation import RemediationAction, RemediationRequest, RemediationStatus
from app.modules.governance.domain.security.remediation_policy import PolicyDecision, RemediationPolicyEngine
from app.modules.optimization.domain.actions.base import ExecutionStatus, RemediationContext
from app.shared.core.constants import SYSTEM_USER_ID
from app.shared.core.exceptions import ResourceNotFoundError
from app.shared.core.ops_metrics import REMEDIATION_DURATION_SECONDS
from app.shared.core.pricing import FeatureFlag, PricingTier, is_feature_enabled
from app.shared.core.security_metrics import REMEDIATION_TOTAL
from app.shared.core.provider import normalize_provider

logger = structlog.get_logger()


async def execute_remediation_request(
    service: Any,
    request_id: UUID,
    tenant_id: UUID,
    *,
    bypass_grace_period: bool = False,
) -> RemediationRequest:
    """
    Execute an approved remediation request through the registered action strategy.
    """
    start_time = time.time()
    from app.modules.optimization.domain import remediation as remediation_module

    result = await service.db.execute(
        select(RemediationRequest)
        .where(RemediationRequest.id == request_id)
        .where(RemediationRequest.tenant_id == tenant_id)
        .with_for_update()
    )
    request = cast(RemediationRequest | None, await service._scalar_one_or_none(result))

    if not request:
        raise ResourceNotFoundError(f"Request {request_id} not found")

    try:
        tenant_tier = await remediation_module.get_tenant_tier(tenant_id, service.db)
    except Exception as exc:
        logger.warning(
            "tenant_tier_lookup_failed_in_execute",
            tenant_id=str(tenant_id),
            error=str(exc),
        )
        tenant_tier = PricingTier.FREE

    tier_value = (
        tenant_tier.value if isinstance(tenant_tier, PricingTier) else str(tenant_tier)
    )
    resource_id = str(getattr(request, "resource_id", "") or "")
    resource_type = str(getattr(request, "resource_type", "unknown") or "unknown")
    provider = normalize_provider(getattr(request, "provider", None))
    if not provider:
        raise ValueError("Invalid or missing provider on remediation request")
    actor_id = str(getattr(request, "reviewed_by_user_id", None) or SYSTEM_USER_ID)

    action_raw = getattr(request, "action", None)
    if isinstance(action_raw, RemediationAction):
        action = action_raw
    else:
        try:
            action = RemediationAction(str(action_raw))
            request.action = action
        except Exception as exc:
            raise ValueError(f"Invalid remediation action on request: {action_raw}") from exc
    action_value = action.value

    savings_value = getattr(request, "estimated_monthly_savings", Decimal("0")) or Decimal("0")
    if not isinstance(savings_value, Decimal):
        savings_value = Decimal(str(savings_value))

    audit_logger = remediation_module.AuditLogger(
        db=service.db, tenant_id=str(tenant_id)
    )
    grace_period_bypassed = False

    try:
        safety = remediation_module.SafetyGuardrailService(service.db)
        await safety.check_all_guards(tenant_id, savings_value)

        if request.status != RemediationStatus.APPROVED:
            if request.status == RemediationStatus.SCHEDULED:
                now = datetime.now(timezone.utc)
                scheduled_execution_at = getattr(request, "scheduled_execution_at", None)
                if scheduled_execution_at and now < scheduled_execution_at:
                    if not bypass_grace_period:
                        logger.info(
                            "remediation_execution_deferred_grace_period",
                            request_id=str(request_id),
                            remaining_minutes=(scheduled_execution_at - now).total_seconds() / 60,
                        )
                        return request
                    grace_period_bypassed = True
                    logger.warning(
                        "remediation_grace_period_bypassed",
                        request_id=str(request_id),
                        scheduled_execution_at=scheduled_execution_at.isoformat(),
                    )
            else:
                raise ValueError(
                    f"Request must be approved or scheduled (current: {request.status.value})"
                )

        policy_config, remediation_settings = await service._build_policy_config(
            tenant_id
        )

        system_policy_context = await service._apply_system_policy_context(
            request,
            tenant_id=tenant_id,
            provider=provider,
            connection_id=getattr(request, "connection_id", None),
        )
        policy_evaluation = RemediationPolicyEngine().evaluate(request, policy_config)
        policy_details: dict[str, Any] = {
            "request_id": str(request_id),
            "action": action_value,
            "stage": "pre_execution",
            "tier": tier_value,
            "policy": policy_evaluation.to_dict(),
            "policy_context_source": (
                system_policy_context.get("source")
                if system_policy_context
                else None
            ),
        }
        await audit_logger.log(
            event_type=remediation_module.AuditEventType.POLICY_EVALUATED,
            actor_id=actor_id,
            resource_id=resource_id,
            resource_type=resource_type,
            success=True,
            details=policy_details,
        )

        if policy_evaluation.decision == PolicyDecision.WARN:
            logger.warning(
                "remediation_policy_warned",
                request_id=str(request_id),
                summary=policy_evaluation.summary,
            )
            await audit_logger.log(
                event_type=remediation_module.AuditEventType.POLICY_WARNED,
                actor_id=actor_id,
                resource_id=resource_id,
                resource_type=resource_type,
                success=True,
                details=policy_details,
            )
        elif policy_evaluation.decision == PolicyDecision.BLOCK:
            request.status = RemediationStatus.FAILED
            request.execution_error = f"POLICY_BLOCK: {policy_evaluation.summary}"
            await audit_logger.log(
                event_type=remediation_module.AuditEventType.POLICY_BLOCKED,
                actor_id=actor_id,
                resource_id=resource_id,
                resource_type=resource_type,
                success=False,
                error_message=request.execution_error,
                details=policy_details,
            )
            should_notify_slack = bool(
                remediation_settings
                and bool(
                    getattr(
                        remediation_settings, "policy_violation_notify_slack", True
                    )
                )
                and is_feature_enabled(tenant_tier, FeatureFlag.SLACK_INTEGRATION)
            )
            should_notify_jira = bool(
                remediation_settings
                and bool(
                    getattr(
                        remediation_settings, "policy_violation_notify_jira", False
                    )
                )
                and is_feature_enabled(
                    tenant_tier, FeatureFlag.INCIDENT_INTEGRATIONS
                )
            )
            should_notify_workflow = bool(
                is_feature_enabled(tenant_tier, FeatureFlag.INCIDENT_INTEGRATIONS)
            )
            should_notify_teams = bool(
                is_feature_enabled(tenant_tier, FeatureFlag.INCIDENT_INTEGRATIONS)
            )
            if (
                should_notify_slack
                or should_notify_jira
                or should_notify_workflow
                or should_notify_teams
            ):
                from app.shared.core.notifications import NotificationDispatcher

                await NotificationDispatcher.notify_policy_event(
                    tenant_id=str(tenant_id),
                    decision=policy_evaluation.decision.value,
                    summary=policy_evaluation.summary,
                    resource_id=resource_id,
                    action=action_value,
                    notify_slack=should_notify_slack,
                    notify_jira=should_notify_jira,
                    notify_teams=should_notify_teams,
                    notify_workflow=should_notify_workflow,
                    request_id=str(request_id),
                    db=service.db,
                )
            await service.db.commit()
            await service.db.refresh(request)
            return request
        elif policy_evaluation.decision == PolicyDecision.ESCALATE:
            request.status = RemediationStatus.PENDING_APPROVAL
            request.escalation_required = True
            request.escalation_reason = policy_evaluation.summary
            request.escalated_at = datetime.now(timezone.utc)
            request.execution_error = None
            policy_details["escalation_workflow_feature_enabled"] = (
                is_feature_enabled(tenant_tier, FeatureFlag.ESCALATION_WORKFLOW)
            )
            await audit_logger.log(
                event_type=remediation_module.AuditEventType.POLICY_ESCALATED,
                actor_id=actor_id,
                resource_id=resource_id,
                resource_type=resource_type,
                success=False,
                error_message=policy_evaluation.summary,
                details=policy_details,
            )
            should_notify_slack = bool(
                remediation_settings
                and bool(
                    getattr(
                        remediation_settings, "policy_violation_notify_slack", True
                    )
                )
                and is_feature_enabled(tenant_tier, FeatureFlag.SLACK_INTEGRATION)
            )
            should_notify_jira = bool(
                remediation_settings
                and bool(
                    getattr(
                        remediation_settings, "policy_violation_notify_jira", False
                    )
                )
                and is_feature_enabled(
                    tenant_tier, FeatureFlag.INCIDENT_INTEGRATIONS
                )
            )
            should_notify_workflow = bool(
                is_feature_enabled(tenant_tier, FeatureFlag.INCIDENT_INTEGRATIONS)
            )
            should_notify_teams = bool(
                is_feature_enabled(tenant_tier, FeatureFlag.INCIDENT_INTEGRATIONS)
            )
            if (
                should_notify_slack
                or should_notify_jira
                or should_notify_workflow
                or should_notify_teams
            ):
                from app.shared.core.notifications import NotificationDispatcher

                await NotificationDispatcher.notify_policy_event(
                    tenant_id=str(tenant_id),
                    decision=policy_evaluation.decision.value,
                    summary=policy_evaluation.summary,
                    resource_id=resource_id,
                    action=action_value,
                    notify_slack=should_notify_slack,
                    notify_jira=should_notify_jira,
                    notify_teams=should_notify_teams,
                    notify_workflow=should_notify_workflow,
                    request_id=str(request_id),
                    db=service.db,
                )
            await service.db.commit()
            await service.db.refresh(request)
            return request

        if request.status == RemediationStatus.APPROVED and not bypass_grace_period:
            from datetime import timedelta

            hours = 24
            if action == RemediationAction.RECLAIM_LICENSE_SEAT:
                hours = (
                    getattr(remediation_settings, "license_reclaim_grace_period_days", 1)
                    or 1
                ) * 24

            grace_period = timedelta(hours=hours)
            scheduled_at = datetime.now(timezone.utc) + grace_period

            request.status = RemediationStatus.SCHEDULED
            request.scheduled_execution_at = scheduled_at
            await service.db.commit()

            logger.info(
                "remediation_scheduled_grace_period",
                request_id=str(request_id),
                scheduled_at=scheduled_at.isoformat(),
                grace_hours=hours,
            )

            await audit_logger.log(
                event_type=remediation_module.AuditEventType.REMEDIATION_EXECUTION_STARTED,
                actor_id=actor_id,
                resource_id=resource_id,
                resource_type=resource_type,
                success=True,
                details={
                    "request_id": str(request_id),
                    "action": action_value,
                    "scheduled_execution_at": scheduled_at.isoformat(),
                    "note": f"Resource scheduled for execution after {hours}h grace period.",
                },
            )

            from app.modules.governance.domain.jobs.processor import enqueue_job
            from app.models.background_job import JobType

            await enqueue_job(
                db=service.db,
                job_type=JobType.REMEDIATION,
                tenant_id=tenant_id,
                payload={"request_id": str(request_id)},
                scheduled_for=scheduled_at,
            )

            return request

        request.status = RemediationStatus.EXECUTING
        await service.db.commit()

        await audit_logger.log(
            event_type=remediation_module.AuditEventType.REMEDIATION_EXECUTION_STARTED,
            actor_id=actor_id,
            resource_id=resource_id,
            resource_type=resource_type,
            success=True,
            details={
                "request_id": str(request_id),
                "action": action_value,
                "triggered_by": "background_worker",
                "grace_period_bypassed": grace_period_bypassed,
            },
        )

        credentials = await service._resolve_credentials(request)
        execution_region = getattr(request, "region", None) or service.region
        if str(execution_region or "").strip().lower() in {"", "global"}:
            credential_region = str((credentials or {}).get("region") or "").strip()
            if credential_region and credential_region.lower() != "global":
                execution_region = credential_region
        if (
            provider == "aws"
            and str(execution_region or "").strip().lower() in {"", "global"}
        ):
            execution_region = await service._resolve_aws_region_hint(
                tenant_id=tenant_id,
                connection_id=getattr(request, "connection_id", None),
            )
        context = RemediationContext(
            db_session=service.db,
            tenant_id=tenant_id,
            tier=tier_value,
            region=execution_region,
            credentials=credentials,
            create_backup=bool(getattr(request, "create_backup", False)),
            backup_retention_days=int(getattr(request, "backup_retention_days", 30) or 30),
            parameters=service._strip_system_policy_context(
                getattr(request, "action_parameters", None)
            ),
        )

        strategy = remediation_module.RemediationActionFactory.get_strategy(
            provider, action
        )
        execution_result = await strategy.execute(resource_id, context)

        if execution_result.status == ExecutionStatus.SUCCESS:
            request.status = RemediationStatus.COMPLETED
            request.executed_at = datetime.now(timezone.utc)
            request.backup_resource_id = execution_result.backup_id
            request.execution_error = None
        elif execution_result.status == ExecutionStatus.SKIPPED:
            request.status = RemediationStatus.FAILED
            request.execution_error = (
                execution_result.error_message
                or "Action skipped by validation or tier policy."
            )
        else:
            request.status = RemediationStatus.FAILED
            request.execution_error = execution_result.error_message or "Action failed."

        logger.info(
            "remediation_executed",
            request_id=str(request_id),
            resource=resource_id,
            status=request.status.value,
        )

        await audit_logger.log(
            event_type=remediation_module.AuditEventType.REMEDIATION_EXECUTED,
            actor_id=actor_id,
            resource_id=resource_id,
            resource_type=resource_type,
            success=request.status == RemediationStatus.COMPLETED,
            error_message=request.execution_error,
            details={
                "request_id": str(request_id),
                "action": action_value,
                "execution_status": execution_result.status.value,
                "backup_id": request.backup_resource_id,
                "savings": float(savings_value),
            },
        )

        duration = time.time() - start_time
        REMEDIATION_DURATION_SECONDS.labels(
            action=action_value, provider=provider
        ).observe(duration)

    except Exception as exc:
        request.status = RemediationStatus.FAILED
        request.execution_error = str(exc)[:500]

        await audit_logger.log(
            event_type=remediation_module.AuditEventType.REMEDIATION_FAILED,
            actor_id=actor_id,
            resource_id=resource_id,
            resource_type=resource_type,
            success=False,
            error_message=str(exc),
            details={"request_id": str(request_id), "action": action_value},
        )

        logger.error(
            "remediation_failed",
            request_id=str(request_id),
            error=str(exc),
        )

    await service.db.commit()
    await service.db.refresh(request)

    if request.status == RemediationStatus.COMPLETED:
        REMEDIATION_TOTAL.labels(
            status="success",
            resource_type=resource_type,
            action=action_value,
        ).inc()

        from app.shared.core.notifications import NotificationDispatcher

        await NotificationDispatcher.notify_remediation_completed(
            tenant_id=str(tenant_id),
            resource_id=resource_id,
            action=action_value,
            savings=float(savings_value),
            request_id=str(request_id),
            provider=provider,
            notify_workflow=bool(
                is_feature_enabled(tenant_tier, FeatureFlag.GITOPS_REMEDIATION)
                or is_feature_enabled(
                    tenant_tier, FeatureFlag.INCIDENT_INTEGRATIONS
                )
            ),
            db=service.db,
        )

    return request
