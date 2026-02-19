"""
Remediation Service - Approval Workflow for Zombie Resource Cleanup

Manages the remediation approval workflow:
1. create_request() - User requests remediation
2. list_pending() - Reviewer sees pending requests
3. approve() / reject() - Reviewer takes action
4. execute() - System executes approved requests
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4
from decimal import Decimal
from typing import List, Dict, Any, Optional, cast
import hashlib
import json
import re
import aioboto3
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.core.service import BaseService
import structlog
import time

from app.models.remediation import (
    RemediationRequest,
    RemediationStatus,
    RemediationAction,
)
from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.gcp_connection import GCPConnection
from app.models.saas_connection import SaaSConnection
from app.models.license_connection import LicenseConnection

__all__ = ["RemediationService", "RemediationStatus", "RemediationAction"]
from app.models.remediation_settings import RemediationSettings
from app.modules.governance.domain.security.audit_log import AuditLogger, AuditEventType
from app.modules.governance.domain.security.remediation_policy import (
    PolicyConfig,
    PolicyDecision,
    RemediationPolicyEngine,
)
from app.shared.core.security_metrics import REMEDIATION_TOTAL
from app.shared.core.ops_metrics import REMEDIATION_DURATION_SECONDS
from app.shared.core.constants import SYSTEM_USER_ID
from app.shared.adapters.aws_utils import map_aws_credentials
from app.shared.core.safety_service import SafetyGuardrailService
from app.shared.core.config import get_settings
from app.shared.core.exceptions import ResourceNotFoundError
from app.shared.core.pricing import (
    FeatureFlag,
    PricingTier,
    get_tenant_tier,
    is_feature_enabled,
)
from app.modules.optimization.domain.actions import RemediationActionFactory
from app.modules.optimization.domain.actions.base import RemediationContext, ExecutionStatus

logger = structlog.get_logger()


class RemediationService(BaseService):
    """
    Manages the remediation approval workflow.

    Workflow:
    1. create_request() - User requests remediation
    2. list_pending() - Reviewer sees pending requests
    3. approve() / reject() - Reviewer takes action
    4. execute() - System executes approved requests
    """

    # Mapping CamelCase to snake_case for aioboto3 credentials - DEPRECATED: Use aws_utils

    def __init__(
        self,
        db: AsyncSession,
        region: str = "us-east-1",
        credentials: Optional[Dict[str, str]] = None,
    ) -> None:
        super().__init__(db)
        self.region = region
        self.credentials = credentials
        self.session = aioboto3.Session()

    async def _get_client(self, service_name: str) -> Any:
        """Helper to get aioboto3 client with optional credentials and endpoint override."""
        settings = get_settings()

        kwargs = {"region_name": self.region}

        if settings.AWS_ENDPOINT_URL:
            kwargs["endpoint_url"] = settings.AWS_ENDPOINT_URL

        if self.credentials:
            kwargs.update(map_aws_credentials(self.credentials))

        return self.session.client(service_name, **kwargs)

    async def _get_remediation_settings(
        self, tenant_id: UUID
    ) -> RemediationSettings | None:
        try:
            result = await self.db.execute(
                select(RemediationSettings).where(
                    RemediationSettings.tenant_id == tenant_id
                )
            )
            settings = result.scalar_one_or_none()
            return settings if isinstance(settings, RemediationSettings) else None
        except Exception as exc:
            logger.warning(
                "remediation_settings_lookup_failed",
                tenant_id=str(tenant_id),
                error=str(exc),
            )
            return None

    async def _build_policy_config(
        self, tenant_id: UUID
    ) -> tuple[PolicyConfig, RemediationSettings | None]:
        settings = await self._get_remediation_settings(tenant_id)
        if not settings:
            return PolicyConfig(), None

        threshold_raw = getattr(
            settings, "policy_low_confidence_warn_threshold", Decimal("0.90")
        )
        config = PolicyConfig(
            enabled=bool(getattr(settings, "policy_enabled", True)),
            block_production_destructive=bool(
                getattr(settings, "policy_block_production_destructive", True)
            ),
            require_gpu_override=bool(
                getattr(settings, "policy_require_gpu_override", True)
            ),
            low_confidence_warn_threshold=Decimal(str(threshold_raw)),
        )
        return config, settings

    async def _resolve_credentials(self, request: RemediationRequest) -> Dict[str, Any]:
        """Resolve provider credentials from the tenant connection bound to the request."""
        connection_id = getattr(request, "connection_id", None)
        if not connection_id:
            return dict(self.credentials or {})

        provider = (getattr(request, "provider", "") or "").strip().lower()

        if provider == "aws":
            aws_result = await self.db.execute(
                select(AWSConnection).where(AWSConnection.id == connection_id)
            )
            aws_conn = cast(Optional[AWSConnection], aws_result.scalar_one_or_none())
            if aws_conn:
                return {
                    "role_arn": aws_conn.role_arn,
                    "external_id": aws_conn.external_id,
                    "region": aws_conn.region,
                }
            return {}

        if provider == "azure":
            azure_result = await self.db.execute(
                select(AzureConnection).where(AzureConnection.id == connection_id)
            )
            azure_conn = cast(
                Optional[AzureConnection], azure_result.scalar_one_or_none()
            )
            if azure_conn:
                return {
                    "tenant_id": azure_conn.azure_tenant_id,
                    "client_id": azure_conn.client_id,
                    "client_secret": azure_conn.client_secret,
                    "subscription_id": azure_conn.subscription_id,
                }
            return {}

        if provider == "gcp":
            gcp_result = await self.db.execute(
                select(GCPConnection).where(GCPConnection.id == connection_id)
            )
            gcp_conn = cast(Optional[GCPConnection], gcp_result.scalar_one_or_none())
            if gcp_conn and gcp_conn.service_account_json:
                try:
                    parsed = json.loads(gcp_conn.service_account_json)
                    if isinstance(parsed, dict):
                        return dict(parsed)
                except (TypeError, ValueError) as exc:
                    logger.warning(
                        "remediation_invalid_gcp_service_account_json",
                        connection_id=str(connection_id),
                        error=str(exc),
                    )
            return {}

        if provider == "saas":
            saas_result = await self.db.execute(
                select(SaaSConnection).where(SaaSConnection.id == connection_id)
            )
            saas_conn = cast(Optional[SaaSConnection], saas_result.scalar_one_or_none())
            if saas_conn:
                return {
                    "vendor": saas_conn.vendor,
                    "api_key": saas_conn.api_key,
                    "connector_config": dict(saas_conn.connector_config or {}),
                }
            return {}

        if provider == "license":
            license_result = await self.db.execute(
                select(LicenseConnection).where(LicenseConnection.id == connection_id)
            )
            license_conn = cast(
                Optional[LicenseConnection], license_result.scalar_one_or_none()
            )
            if license_conn:
                return {
                    "vendor": license_conn.vendor,
                    "api_key": license_conn.api_key,
                    "connector_config": dict(license_conn.connector_config or {}),
                }
            return {}

        return {}

    async def preview_policy(
        self, request: RemediationRequest, tenant_id: UUID
    ) -> dict[str, Any]:
        tier = await get_tenant_tier(tenant_id, self.db)
        policy_config, _ = await self._build_policy_config(tenant_id)
        evaluation = RemediationPolicyEngine().evaluate(request, policy_config)
        return {
            "decision": evaluation.decision.value,
            "summary": evaluation.summary,
            "rule_hits": [hit.to_dict() for hit in evaluation.rule_hits],
            "tier": tier.value,
            "config": {
                "enabled": policy_config.enabled,
                "block_production_destructive": policy_config.block_production_destructive,
                "require_gpu_override": policy_config.require_gpu_override,
                "low_confidence_warn_threshold": float(
                    policy_config.low_confidence_warn_threshold
                ),
            },
        }

    async def preview_policy_input(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        resource_id: str,
        resource_type: str,
        action: RemediationAction,
        provider: str = "aws",
        confidence_score: float | None = None,
        explainability_notes: str | None = None,
        review_notes: str | None = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Evaluate policy for an in-memory remediation payload.

        This avoids persisting a request and enables pre-request dry-run previews.
        """
        synthetic_request = RemediationRequest(
            id=uuid4(),
            tenant_id=tenant_id,
            resource_id=resource_id,
            resource_type=resource_type,
            provider=provider,
            region=self.region,
            action=action,
            status=RemediationStatus.PENDING,
            estimated_monthly_savings=Decimal("0"),
            confidence_score=(
                Decimal(str(confidence_score)) if confidence_score is not None else None
            ),
            explainability_notes=explainability_notes,
            requested_by_user_id=user_id,
            review_notes=review_notes,
            action_parameters=parameters,
        )
        return await self.preview_policy(synthetic_request, tenant_id)

    async def create_request(
        self,
        tenant_id: UUID,
        user_id: UUID,
        resource_id: str,
        resource_type: str,
        action: RemediationAction,
        estimated_savings: float,
        create_backup: bool = False,
        backup_retention_days: int = 30,
        backup_cost_estimate: float = 0,
        confidence_score: Optional[float] = None,
        explainability_notes: Optional[str] = None,
        provider: str = "aws",
        connection_id: Optional[UUID] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> RemediationRequest:
        """Create a new remediation request (pending approval)."""
        provider_norm = (provider or "aws").strip().lower()
        if provider_norm not in {"aws", "azure", "gcp", "saas", "license"}:
            raise ValueError(f"Invalid provider: {provider_norm}")

        # P2: Resource Ownership Verification (connection scoped to tenant)
        if connection_id:
            try:
                from app.models.aws_connection import AWSConnection
                from app.models.azure_connection import AzureConnection
                from app.models.gcp_connection import GCPConnection
                from app.models.saas_connection import SaaSConnection
                from app.models.license_connection import LicenseConnection

                model_map = {
                    "aws": AWSConnection,
                    "azure": AzureConnection,
                    "gcp": GCPConnection,
                    "saas": SaaSConnection,
                    "license": LicenseConnection,
                }
                connection_model = model_map[provider_norm]
                await self.get_by_id(connection_model, connection_id, tenant_id)
            except Exception as exc:
                logger.warning(
                    "remediation_connection_scope_failed",
                    tenant_id=str(tenant_id),
                    provider=provider_norm,
                    connection_id=str(connection_id),
                    error=str(exc),
                )
                raise ValueError(
                    "Unauthorized: Connection does not belong to tenant"
                ) from exc

        request = RemediationRequest(
            tenant_id=tenant_id,
            resource_id=resource_id,
            resource_type=resource_type,
            region=self.region,
            action=action,
            status=RemediationStatus.PENDING,
            estimated_monthly_savings=Decimal(str(estimated_savings)),
            confidence_score=(
                Decimal(str(confidence_score)) if confidence_score is not None else None
            ),
            explainability_notes=explainability_notes,
            create_backup=create_backup,
            backup_retention_days=backup_retention_days,
            backup_cost_estimate=Decimal(str(backup_cost_estimate))
            if backup_cost_estimate
            else None,
            requested_by_user_id=user_id,
            provider=provider_norm,
            connection_id=connection_id,
            action_parameters=parameters,
        )

        self.db.add(request)
        await self.db.commit()
        await self.db.refresh(request)

        logger.info(
            "remediation_request_created",
            request_id=str(request.id),
            resource=resource_id,
            action=action.value,
            backup=create_backup,
        )

        return request

    async def list_pending(
        self, tenant_id: UUID, limit: int = 50, offset: int = 0
    ) -> List[RemediationRequest]:
        """List open remediation requests for a tenant (actionable queue)."""
        MAX_PAGE_SIZE = 200
        limit = min(limit, MAX_PAGE_SIZE)
        stmt = (
            self._scoped_query(RemediationRequest, tenant_id)
            .where(
                RemediationRequest.status.in_(
                    (
                        RemediationStatus.PENDING,
                        RemediationStatus.PENDING_APPROVAL,
                        RemediationStatus.APPROVED,
                        RemediationStatus.SCHEDULED,
                        RemediationStatus.EXECUTING,
                    )
                )
            )
            .order_by(RemediationRequest.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def approve(
        self,
        request_id: UUID,
        tenant_id: UUID,
        reviewer_id: UUID,
        notes: Optional[str] = None,
        reviewer_role: Optional[str] = None,
    ) -> RemediationRequest:
        """
        Approve a remediation request.
        Does NOT execute yet - that's a separate step for safety.
        """
        result = await self.db.execute(
            select(RemediationRequest)
            .where(RemediationRequest.id == request_id)
            .where(RemediationRequest.tenant_id == tenant_id)
            .with_for_update()
        )  # with_for_update: enforce row lock for atomic execution
        request = result.scalar_one_or_none()

        if not request:
            raise ResourceNotFoundError(f"Request {request_id} not found")

        if request.status not in {
            RemediationStatus.PENDING,
            RemediationStatus.PENDING_APPROVAL,
        }:
            raise ValueError(f"Request is {request.status.value}, not pending approval")

        if getattr(request, "escalation_required", False) is True:
            normalized_role = (reviewer_role or "").strip().lower()
            settings = await self._get_remediation_settings(tenant_id)
            required_role = (
                (
                    (
                        getattr(settings, "policy_escalation_required_role", "owner")
                        if settings
                        else "owner"
                    )
                    or "owner"
                )
                .strip()
                .lower()
            )
            if required_role not in {"owner", "admin"}:
                required_role = "owner"

            role_allowed = (
                normalized_role == "owner" or normalized_role == required_role
            )
            if not role_allowed:
                raise ValueError(
                    f"Escalated remediation requests require {required_role} approval."
                )

            # Resolve GPU escalation loops by embedding explicit override marker.
            marker = "gpu-approved"
            if notes:
                if marker not in notes.lower():
                    notes = f"{notes}\n[{marker}]"
            else:
                notes = f"Owner escalation approval [{marker}]"

            request.escalation_required = False
            request.escalation_reason = None

        request.status = RemediationStatus.APPROVED
        request.reviewed_by_user_id = reviewer_id
        request.review_notes = notes
        request.escalation_required = False
        request.escalation_reason = None

        await self.db.commit()
        await self.db.refresh(request)

        logger.info(
            "remediation_approved",
            request_id=str(request_id),
            reviewer=str(reviewer_id),
        )

        return request

    async def reject(
        self,
        request_id: UUID,
        tenant_id: UUID,
        reviewer_id: UUID,
        notes: Optional[str] = None,
    ) -> RemediationRequest:
        """Reject a remediation request."""
        result = await self.db.execute(
            select(RemediationRequest)
            .where(RemediationRequest.id == request_id)
            .where(RemediationRequest.tenant_id == tenant_id)
            .with_for_update()
        )
        request = result.scalar_one_or_none()

        if not request:
            raise ResourceNotFoundError(f"Request {request_id} not found")

        if request.status not in {
            RemediationStatus.PENDING,
            RemediationStatus.PENDING_APPROVAL,
        }:
            raise ValueError(f"Request is {request.status.value}, not pending approval")

        request.status = RemediationStatus.REJECTED
        request.reviewed_by_user_id = reviewer_id
        request.review_notes = notes
        request.escalation_required = False
        request.escalation_reason = None

        await self.db.commit()
        await self.db.refresh(request)

        logger.info(
            "remediation_rejected",
            request_id=str(request_id),
            reviewer=str(reviewer_id),
        )

        return request

    async def execute(
        self, request_id: UUID, tenant_id: UUID, bypass_grace_period: bool = False
    ) -> RemediationRequest:
        """
        Execute an approved remediation request through the registered action strategy.
        """
        start_time = time.time()

        result = await self.db.execute(
            select(RemediationRequest)
            .where(RemediationRequest.id == request_id)
            .where(RemediationRequest.tenant_id == tenant_id)
            .with_for_update()
        )
        request = result.scalar_one_or_none()

        if not request:
            raise ResourceNotFoundError(f"Request {request_id} not found")

        try:
            tenant_tier = await get_tenant_tier(tenant_id, self.db)
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
        provider = str(getattr(request, "provider", "aws") or "aws").strip().lower()
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

        audit_logger = AuditLogger(db=self.db, tenant_id=str(tenant_id))
        grace_period_bypassed = False

        try:
            safety = SafetyGuardrailService(self.db)
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

            policy_config, remediation_settings = await self._build_policy_config(
                tenant_id
            )

            policy_evaluation = RemediationPolicyEngine().evaluate(request, policy_config)
            policy_details: dict[str, Any] = {
                "request_id": str(request_id),
                "action": action_value,
                "stage": "pre_execution",
                "tier": tier_value,
                "policy": policy_evaluation.to_dict(),
            }
            await audit_logger.log(
                event_type=AuditEventType.POLICY_EVALUATED,
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
                    event_type=AuditEventType.POLICY_WARNED,
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
                    event_type=AuditEventType.POLICY_BLOCKED,
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
                        db=self.db,
                    )
                await self.db.commit()
                await self.db.refresh(request)
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
                    event_type=AuditEventType.POLICY_ESCALATED,
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
                        db=self.db,
                    )
                await self.db.commit()
                await self.db.refresh(request)
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
                await self.db.commit()

                logger.info(
                    "remediation_scheduled_grace_period",
                    request_id=str(request_id),
                    scheduled_at=scheduled_at.isoformat(),
                    grace_hours=hours,
                )

                await audit_logger.log(
                    event_type=AuditEventType.REMEDIATION_EXECUTION_STARTED,
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
                    db=self.db,
                    job_type=JobType.REMEDIATION,
                    tenant_id=tenant_id,
                    payload={"request_id": str(request_id)},
                    scheduled_for=scheduled_at,
                )

                return request

            request.status = RemediationStatus.EXECUTING
            await self.db.commit()

            await audit_logger.log(
                event_type=AuditEventType.REMEDIATION_EXECUTION_STARTED,
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

            credentials = await self._resolve_credentials(request)
            context = RemediationContext(
                db_session=self.db,
                tenant_id=tenant_id,
                tier=tier_value,
                region=getattr(request, "region", None) or self.region,
                credentials=credentials,
                create_backup=bool(getattr(request, "create_backup", False)),
                backup_retention_days=int(getattr(request, "backup_retention_days", 30) or 30),
                parameters=dict(getattr(request, "action_parameters", None) or {}),
            )

            strategy = RemediationActionFactory.get_strategy(provider, action)
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
                event_type=AuditEventType.REMEDIATION_EXECUTED,
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

        except Exception as e:
            request.status = RemediationStatus.FAILED
            request.execution_error = str(e)[:500]

            await audit_logger.log(
                event_type=AuditEventType.REMEDIATION_FAILED,
                actor_id=actor_id,
                resource_id=resource_id,
                resource_type=resource_type,
                success=False,
                error_message=str(e),
                details={"request_id": str(request_id), "action": action_value},
            )

            logger.error(
                "remediation_failed",
                request_id=str(request_id),
                error=str(e),
            )

        await self.db.commit()
        await self.db.refresh(request)

        # Track successful execution in metrics (SEC-03)
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
                db=self.db,
            )

        return request


    async def enforce_hard_limit(self, tenant_id: UUID) -> List[UUID]:
        """
        Enforce hard limits for a tenant.
        1. Checks budget status via UsageTracker.
        2. If HARD_LIMIT is reached:
           - Automatically executes only high-confidence, low-risk pending requests.
           - Uses AUTOPILOT_BYPASS_GRACE_PERIOD setting (default fail-safe is no bypass).
        """
        from app.shared.llm.usage_tracker import UsageTracker, BudgetStatus

        tracker = UsageTracker(self.db)
        status = await tracker.check_budget(tenant_id)

        if status != BudgetStatus.HARD_LIMIT:
            return []

        logger.warning("enforcing_hard_limit_for_tenant", tenant_id=str(tenant_id))

        settings = get_settings()
        safe_actions = {
            RemediationAction.STOP_INSTANCE,
            RemediationAction.RESIZE_INSTANCE,
            RemediationAction.STOP_RDS_INSTANCE,
        }

        # 1. Fetch pending, high-confidence, low-risk remediation requests for this tenant.
        # Priority: Highest savings first.
        result = await self.db.execute(
            select(RemediationRequest)
            .where(RemediationRequest.tenant_id == tenant_id)
            .where(RemediationRequest.status == RemediationStatus.PENDING)
            .where(
                RemediationRequest.confidence_score >= Decimal("0.90")
            )  # Only high confidence
            .where(RemediationRequest.action.in_(safe_actions))
            .order_by(RemediationRequest.estimated_monthly_savings.desc())
        )
        requests = result.scalars().all()

        executed_ids = []
        for req in requests:
            try:
                if req.action not in safe_actions:
                    logger.warning(
                        "hard_limit_request_requires_manual_review",
                        request_id=str(req.id),
                        tenant_id=str(tenant_id),
                        action=req.action.value if req.action else None,
                    )
                    continue

                # Auto-approve for hard limit emergency
                req.status = RemediationStatus.APPROVED
                req.reviewed_by_user_id = SYSTEM_USER_ID
                req.review_notes = "AUTO_APPROVED: Budget Hard Limit Exceeded"
                await self.db.commit()

                await self.execute(
                    req.id,
                    tenant_id,
                    bypass_grace_period=settings.AUTOPILOT_BYPASS_GRACE_PERIOD,
                )
                executed_ids.append(req.id)
            except Exception as e:
                logger.error(
                    "hard_limit_enforcement_failed",
                    request_id=str(req.id),
                    error=str(e),
                )

        return executed_ids

    async def generate_iac_plan(
        self, request: RemediationRequest, tenant_id: UUID
    ) -> str:
        """
        Generates a Terraform decommissioning plan for the resource.
        Supports 'state rm' and 'removed' blocks for GitOps workflows.

        Phase 8: Gated by Pro tier.
        """
        from app.shared.core.pricing import (
            get_tenant_tier,
            FeatureFlag,
            is_feature_enabled,
        )

        tier = await get_tenant_tier(tenant_id, self.db)

        if not is_feature_enabled(tier, FeatureFlag.GITOPS_REMEDIATION):
            return "# GitOps Remediation is a Pro-tier feature. Please upgrade to unlock IaC plans."

        resource_id = request.resource_id
        provider = request.provider.lower()

        # Mapping Valdrix resource types to Terraform resource types
        tf_mapping = {
            "EC2 Instance": "aws_instance",
            "Elastic IP": "aws_eip",
            "EBS Volume": "aws_ebs_volume",
            "RDS Instance": "aws_db_instance",
            "S3 Bucket": "aws_s3_bucket",
            "Snapshot": "aws_ebs_snapshot",
            # Azure Mappings
            "Azure VM": "azurerm_virtual_machine",
            "Managed Disk": "azurerm_managed_disk",
            "Public IP": "azurerm_public_ip",
            # GCP Mappings
            "GCP Instance": "google_compute_instance",
            "Address": "google_compute_address",
            "Disk": "google_compute_disk",
        }

        tf_type = tf_mapping.get(request.resource_type, "cloud_resource")
        tf_id = self._sanitize_tf_identifier(
            provider, request.resource_type, resource_id
        )

        planlines = [
            "# Valdrix GitOps Remediation Plan",
            f"# Resource: {resource_id} ({request.resource_type})",
            f"# Savings: ${request.estimated_monthly_savings}/mo",
            f"# Action: {request.action.value}",
            "",
        ]

        if provider == "aws":
            planlines.append("# Option 1: Manual State Removal")
            planlines.append(f"terraform state rm {tf_type}.{tf_id}")
            planlines.append("")

            planlines.append(
                "# Option 2: Terraform 'removed' block (Recommended for TF 1.7+)"
            )
            planlines.append("removed {")
            planlines.append(f"  from = {tf_type}.{tf_id}")
            planlines.append("  lifecycle {")
            planlines.append("    destroy = true")
            planlines.append("  }")
            planlines.append("}")

        elif provider == "azure":
            planlines.append("# Option 1: Manual State Removal")
            planlines.append(f"terraform state rm {tf_type}.{tf_id}")
            planlines.append("")
            planlines.append("# Option 2: Terraform 'removed' block")
            planlines.append("removed {")
            planlines.append(f"  from = {tf_type}.{tf_id}")
            planlines.append("  lifecycle {")
            planlines.append("    destroy = true")
            planlines.append("  }")
            planlines.append("}")

        elif provider == "gcp":
            planlines.append("# Option 1: Manual State Removal")
            planlines.append(f"terraform state rm {tf_type}.{tf_id}")
            planlines.append("")
            planlines.append("# Option 2: Terraform 'removed' block")
            planlines.append("removed {")
            planlines.append(f"  from = {tf_type}.{tf_id}")
            planlines.append("  lifecycle {")
            planlines.append("    destroy = true")
            planlines.append("  }")
            planlines.append("}")

        return "\n".join(planlines)

    @staticmethod
    def _sanitize_tf_identifier(
        provider: str, resource_type: str, resource_id: str
    ) -> str:
        """
        Produce a Terraform-safe identifier with deterministic collision resistance.
        """
        normalized = re.sub(r"[^a-zA-Z0-9_]", "_", resource_id).strip("_").lower()
        if not normalized:
            normalized = "resource"
        if normalized[0].isdigit():
            normalized = f"r_{normalized}"
        stem = normalized[:48]
        digest_input = f"{provider}:{resource_type}:{resource_id}".encode()
        digest = hashlib.sha256(digest_input).hexdigest()[:10]
        return f"{stem}_{digest}"

    async def bulk_generate_iac_plan(
        self, requests: List[RemediationRequest], tenant_id: UUID
    ) -> str:
        """Generates a combined IaC plan for multiple resources."""
        plans = [await self.generate_iac_plan(req, tenant_id) for req in requests]
        header = f"# Valdrix Bulk IaC Remediation Plan\n# Generated: {datetime.now(timezone.utc).isoformat()}\n\n"
        return header + "\n\n" + "\n" + "-" * 40 + "\n".join(plans)
