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
from typing import List, Dict, Any, Optional
import asyncio
import hashlib
import re
import aioboto3
from botocore.exceptions import ClientError
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
        Execute an approved remediation request.

        If create_backup is True, creates snapshot before deleting volume.
        If bypass_grace_period is True, executes immediately (emergency use).
        """
        start_time = time.time()

        # Fetch the request first
        result = await self.db.execute(
            select(RemediationRequest)
            .where(RemediationRequest.id == request_id)
            .where(RemediationRequest.tenant_id == tenant_id)
            .with_for_update()
        )
        request = result.scalar_one_or_none()

        if not request:
            raise ResourceNotFoundError(f"Request {request_id} not found")

        grace_period_bypassed = False
        try:
            # Check all safety guards (Kill Switch, Circuit Breaker, Hard Cap)
            safety = SafetyGuardrailService(self.db)
            await safety.check_all_guards(
                tenant_id, request.estimated_monthly_savings or Decimal("0")
            )

            # 1. Validation & Pre-execution State Check
            if request.status != RemediationStatus.APPROVED:
                # BE-SEC-3: If already scheduled, check if grace period has passed
                if request.status == RemediationStatus.SCHEDULED:
                    now = datetime.now(timezone.utc)
                    if (
                        request.scheduled_execution_at
                        and now < request.scheduled_execution_at
                    ):
                        if not bypass_grace_period:
                            logger.info(
                                "remediation_execution_deferred_grace_period",
                                request_id=str(request_id),
                                remaining_minutes=(
                                    request.scheduled_execution_at - now
                                ).total_seconds()
                                / 60,
                            )
                            return request
                        grace_period_bypassed = True
                        logger.warning(
                            "remediation_grace_period_bypassed",
                            request_id=str(request_id),
                            scheduled_execution_at=request.scheduled_execution_at.isoformat(),
                        )
                    # If grace period passed, proceed to EXECUTING below
                else:
                    raise ValueError(
                        f"Request must be approved or scheduled (current: {request.status.value})"
                    )

            # 1. Create immutable pre-execution audit log FIRST (SEC-03)
            audit_logger = AuditLogger(db=self.db, tenant_id=str(tenant_id))
            actor_id = (
                str(request.reviewed_by_user_id)
                if request.reviewed_by_user_id
                else str(SYSTEM_USER_ID)
            )
            try:
                tenant_tier = await get_tenant_tier(tenant_id, self.db)
            except Exception as exc:
                logger.warning(
                    "tenant_tier_lookup_failed_in_execute",
                    tenant_id=str(tenant_id),
                    error=str(exc),
                )
                tenant_tier = PricingTier.FREE_TRIAL
            tier_value = (
                tenant_tier.value
                if isinstance(tenant_tier, PricingTier)
                else str(tenant_tier)
            )
            policy_config, remediation_settings = await self._build_policy_config(
                tenant_id
            )

            # Apply deterministic policy gating before scheduling/execution.
            policy_engine = RemediationPolicyEngine()
            policy_evaluation = policy_engine.evaluate(request, policy_config)
            policy_details: dict[str, Any] = {
                "request_id": str(request_id),
                "action": request.action.value,
                "stage": "pre_execution",
                "tier": tier_value,
                "policy": policy_evaluation.to_dict(),
            }
            await audit_logger.log(
                event_type=AuditEventType.POLICY_EVALUATED,
                actor_id=actor_id,
                resource_id=request.resource_id,
                resource_type=request.resource_type,
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
                    resource_id=request.resource_id,
                    resource_type=request.resource_type,
                    success=True,
                    details=policy_details,
                )
            elif policy_evaluation.decision == PolicyDecision.BLOCK:
                request.status = RemediationStatus.FAILED
                request.execution_error = f"POLICY_BLOCK: {policy_evaluation.summary}"
                await audit_logger.log(
                    event_type=AuditEventType.POLICY_BLOCKED,
                    actor_id=actor_id,
                    resource_id=request.resource_id,
                    resource_type=request.resource_type,
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
                        resource_id=request.resource_id,
                        action=request.action.value,
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
                    resource_id=request.resource_id,
                    resource_type=request.resource_type,
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
                        resource_id=request.resource_id,
                        action=request.action.value,
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

            # BE-SEC-3: Implement 24-hour Grace Period (Delayed Deletion)
            if request.status == RemediationStatus.APPROVED and not bypass_grace_period:
                # First time execution: Schedule for 24h later
                from datetime import timedelta

                grace_period = timedelta(hours=24)
                scheduled_at = datetime.now(timezone.utc) + grace_period

                request.status = RemediationStatus.SCHEDULED
                request.scheduled_execution_at = scheduled_at
                await self.db.commit()

                logger.info(
                    "remediation_scheduled_grace_period",
                    request_id=str(request_id),
                    scheduled_at=scheduled_at.isoformat(),
                )

                # Log scheduling in audit trail
                await audit_logger.log(
                    event_type=AuditEventType.REMEDIATION_EXECUTION_STARTED,
                    actor_id=actor_id,
                    resource_id=request.resource_id,
                    resource_type=request.resource_type,
                    success=True,
                    details={
                        "request_id": str(request_id),
                        "action": request.action.value,
                        "scheduled_execution_at": scheduled_at.isoformat(),
                        "note": "Resource scheduled for deletion after 24h grace period.",
                    },
                )

                # BE-SEC-3: Enqueue background job for automatic execution after grace period
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

            # SOC2: Log the actual start of execution (after grace period)
            await audit_logger.log(
                event_type=AuditEventType.REMEDIATION_EXECUTION_STARTED,
                actor_id=actor_id,
                resource_id=request.resource_id,
                resource_type=request.resource_type,
                success=True,
                details={
                    "request_id": str(request_id),
                    "action": request.action.value,
                    "triggered_by": "background_worker",
                    "grace_period_bypassed": grace_period_bypassed,
                },
            )

            # 2. Create backup BEFORE any deletion

            if request.create_backup:
                try:
                    if request.action == RemediationAction.DELETE_VOLUME:
                        backup_id = await self._create_volume_backup(
                            request.resource_id,
                            request.backup_retention_days,
                        )
                        request.backup_resource_id = backup_id
                    elif request.action == RemediationAction.DELETE_RDS_INSTANCE:
                        backup_id = await self._create_rds_backup(
                            request.resource_id,
                            request.backup_retention_days,
                        )
                        request.backup_resource_id = backup_id
                    elif request.action == RemediationAction.DELETE_REDSHIFT_CLUSTER:
                        backup_id = await self._create_redshift_backup(
                            request.resource_id,
                            request.backup_retention_days,
                        )
                        request.backup_resource_id = backup_id

                    await self.db.commit()  # Ensure backup record is persisted
                except Exception as b_err:
                    # CRITICAL: Fail the request if backup fails - do not proceed to deletion
                    request.status = RemediationStatus.FAILED
                    request.execution_error = f"BACKUP_FAILED: {str(b_err)}"
                    await self.db.commit()
                    logger.error(
                        "remediation_backup_failed_aborting",
                        request_id=str(request_id),
                        error=str(b_err),
                    )

                    await audit_logger.log(
                        event_type=AuditEventType.REMEDIATION_FAILED,
                        actor_id=actor_id,
                        resource_id=request.resource_id,
                        resource_type=request.resource_type,  # Added missing resource_type
                        success=False,
                        error_message=f"Backup failed: {str(b_err)}",
                    )
                    return request

            # 3. NOW execute deletion with confirmation
            await self._execute_action(request.resource_id, request.action)

            request.status = RemediationStatus.COMPLETED
            request.executed_at = datetime.now(timezone.utc)
            request.escalation_required = False
            request.escalation_reason = None
            logger.info(
                "remediation_executed",
                request_id=str(request_id),
                resource=request.resource_id,
            )

            # Permanent Audit Log (SEC-03) - SOC2 compliant
            await audit_logger.log(
                event_type=AuditEventType.REMEDIATION_EXECUTED,
                actor_id=actor_id,
                resource_id=request.resource_id,
                resource_type=request.resource_type,
                success=True,
                details={
                    "request_id": str(request_id),
                    "action": request.action.value,
                    "backup_id": request.backup_resource_id,
                    "savings": float(request.estimated_monthly_savings or 0),
                },
            )

            # Record metrics
            duration = time.time() - start_time
            REMEDIATION_DURATION_SECONDS.labels(
                action=request.action.value, provider=request.provider or "aws"
            ).observe(duration)

        except Exception as e:
            # ... (logger.error already there)
            request.status = RemediationStatus.FAILED
            request.execution_error = str(e)[:500]

            # Log failure in SOC2 Audit Log
            audit_logger = AuditLogger(db=self.db, tenant_id=tenant_id)
            await audit_logger.log(
                event_type=AuditEventType.REMEDIATION_FAILED,
                actor_id=str(request.reviewed_by_user_id)
                if request.reviewed_by_user_id
                else str(SYSTEM_USER_ID),
                resource_id=request.resource_id,
                resource_type=request.resource_type,
                success=False,
                error_message=str(e),
                details={"request_id": str(request_id), "action": request.action.value},
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
                resource_type=request.resource_type,
                action=request.action.value,
            ).inc()

            # Notification dispatch
            from app.shared.core.notifications import NotificationDispatcher

            await NotificationDispatcher.notify_remediation_completed(
                tenant_id=str(tenant_id),
                resource_id=request.resource_id,
                action=request.action.value,
                savings=float(request.estimated_monthly_savings or 0),
                request_id=str(request_id),
                provider=(request.provider or "aws"),
                notify_workflow=bool(
                    is_feature_enabled(tenant_tier, FeatureFlag.GITOPS_REMEDIATION)
                    or is_feature_enabled(
                        tenant_tier, FeatureFlag.INCIDENT_INTEGRATIONS
                    )
                ),
                db=self.db,
            )

        return request

    async def _create_volume_backup(
        self,
        volume_id: str,
        retention_days: int,
    ) -> str:
        """Create a snapshot backup before deleting a volume."""
        try:
            async with await self._get_client("ec2") as ec2:
                response = await ec2.create_snapshot(
                    VolumeId=volume_id,
                    Description=f"Backup before remediation - retain {retention_days} days",
                    TagSpecifications=[
                        {
                            "ResourceType": "snapshot",
                            "Tags": [
                                {"Key": "Valdrix", "Value": "remediation-backup"},
                                {"Key": "RetentionDays", "Value": str(retention_days)},
                                {"Key": "OriginalVolume", "Value": volume_id},
                            ],
                        }
                    ],
                )

                backup_id = str(response["SnapshotId"])
                logger.info(
                    "backup_created",
                    volume_id=volume_id,
                    snapshot_id=backup_id,
                )
                return backup_id

        except ClientError as e:
            logger.error("backup_creation_failed", volume_id=volume_id, error=str(e))
            raise

    async def _create_rds_backup(
        self,
        instance_id: str,
        retention_days: int,
    ) -> str:
        """Create a DB snapshot backup before deleting an RDS instance."""
        try:
            snapshot_id = f"valdrix-backup-{instance_id}-{int(time.time())}"

            async with await self._get_client("rds") as rds:
                await rds.create_db_snapshot(
                    DBSnapshotIdentifier=snapshot_id,
                    DBInstanceIdentifier=instance_id,
                    Tags=[
                        {"Key": "Valdrix", "Value": "remediation-backup"},
                        {"Key": "RetentionDays", "Value": str(retention_days)},
                    ],
                )
                logger.info(
                    "rds_backup_initiated",
                    instance_id=instance_id,
                    snapshot_id=snapshot_id,
                )
                return snapshot_id
        except ClientError as e:
            logger.error("rds_backup_failed", instance_id=instance_id, error=str(e))
            raise

    async def _create_redshift_backup(
        self,
        cluster_id: str,
        retention_days: int,
    ) -> str:
        """Create a cluster snapshot backup before deleting a Redshift cluster."""
        try:
            snapshot_id = f"valdrix-backup-{cluster_id}-{int(time.time())}"

            async with await self._get_client("redshift") as redshift:
                await redshift.create_cluster_snapshot(
                    SnapshotIdentifier=snapshot_id,
                    ClusterIdentifier=cluster_id,
                    Tags=[
                        {"Key": "Valdrix", "Value": "remediation-backup"},
                        {"Key": "RetentionDays", "Value": str(retention_days)},
                    ],
                )
                logger.info(
                    "redshift_backup_initiated",
                    cluster_id=cluster_id,
                    snapshot_id=snapshot_id,
                )
                return snapshot_id
        except ClientError as e:
            logger.error("redshift_backup_failed", cluster_id=cluster_id, error=str(e))
            raise

    async def _execute_action(
        self,
        resource_id: str,
        action: RemediationAction,
    ) -> None:
        """Execute the actual AWS action."""
        try:
            if action == RemediationAction.DELETE_VOLUME:
                async with await self._get_client("ec2") as ec2:
                    attachments: list[dict[str, Any]] = []
                    volume_info = await ec2.describe_volumes(VolumeIds=[resource_id])
                    if isinstance(volume_info, dict):
                        volumes_obj = volume_info.get("Volumes", [])
                        if isinstance(volumes_obj, list) and volumes_obj:
                            first = volumes_obj[0]
                            if isinstance(first, dict):
                                attachment_obj = first.get("Attachments", [])
                                if isinstance(attachment_obj, list):
                                    attachments = [
                                        a for a in attachment_obj if isinstance(a, dict)
                                    ]
                    for attachment in attachments:
                        state = (attachment.get("State") or "").lower()
                        if state in {"attached", "attaching", "busy"}:
                            detach_kwargs = {"VolumeId": resource_id}
                            instance_id = attachment.get("InstanceId")
                            if instance_id:
                                detach_kwargs["InstanceId"] = instance_id
                            await ec2.detach_volume(**detach_kwargs)

                    if attachments:
                        deadline = time.monotonic() + 180
                        while time.monotonic() < deadline:
                            refreshed = await ec2.describe_volumes(
                                VolumeIds=[resource_id]
                            )
                            refreshed_attachments: list[Any] = []
                            if isinstance(refreshed, dict):
                                refreshed_volumes_obj = refreshed.get("Volumes", [])
                                if (
                                    isinstance(refreshed_volumes_obj, list)
                                    and refreshed_volumes_obj
                                ):
                                    first = refreshed_volumes_obj[0]
                                    if isinstance(first, dict):
                                        attachment_obj = first.get("Attachments", [])
                                        if isinstance(attachment_obj, list):
                                            refreshed_attachments = attachment_obj
                            if not refreshed_attachments:
                                break
                            await asyncio.sleep(5)
                        else:
                            raise ValueError(
                                f"Volume {resource_id} did not detach before delete timeout"
                            )

                    await ec2.delete_volume(VolumeId=resource_id)

            elif action == RemediationAction.DELETE_SNAPSHOT:
                async with await self._get_client("ec2") as ec2:
                    await ec2.delete_snapshot(SnapshotId=resource_id)

            elif action == RemediationAction.RELEASE_ELASTIC_IP:
                async with await self._get_client("ec2") as ec2:
                    await ec2.release_address(AllocationId=resource_id)

            elif action == RemediationAction.STOP_INSTANCE:
                async with await self._get_client("ec2") as ec2:
                    await ec2.stop_instances(InstanceIds=[resource_id])

            elif action == RemediationAction.TERMINATE_INSTANCE:
                async with await self._get_client("ec2") as ec2:
                    await ec2.terminate_instances(InstanceIds=[resource_id])

            elif action == RemediationAction.DELETE_S3_BUCKET:
                async with await self._get_client("s3") as s3:
                    await s3.delete_bucket(Bucket=resource_id)

            elif action == RemediationAction.DELETE_ECR_IMAGE:
                repo, digest = resource_id.split("@")
                async with await self._get_client("ecr") as ecr:
                    await ecr.batch_delete_image(
                        repositoryName=repo, imageIds=[{"imageDigest": digest}]
                    )

            elif action == RemediationAction.DELETE_SAGEMAKER_ENDPOINT:
                async with await self._get_client("sagemaker") as sagemaker:
                    await sagemaker.delete_endpoint(EndpointName=resource_id)
                    await sagemaker.delete_endpoint_config(
                        EndpointConfigName=resource_id
                    )

            elif action == RemediationAction.DELETE_REDSHIFT_CLUSTER:
                async with await self._get_client("redshift") as redshift:
                    await redshift.delete_cluster(
                        ClusterIdentifier=resource_id, SkipFinalClusterSnapshot=True
                    )

            elif action == RemediationAction.DELETE_LOAD_BALANCER:
                async with await self._get_client("elbv2") as elb:
                    await elb.delete_load_balancer(LoadBalancerArn=resource_id)

            elif action == RemediationAction.STOP_RDS_INSTANCE:
                async with await self._get_client("rds") as rds:
                    await rds.stop_db_instance(DBInstanceIdentifier=resource_id)

            elif action == RemediationAction.DELETE_RDS_INSTANCE:
                async with await self._get_client("rds") as rds:
                    await rds.delete_db_instance(
                        DBInstanceIdentifier=resource_id, SkipFinalSnapshot=True
                    )

            elif action == RemediationAction.DELETE_NAT_GATEWAY:
                async with await self._get_client("ec2") as ec2:
                    await ec2.delete_nat_gateway(NatGatewayId=resource_id)

            else:
                raise ValueError(f"Unknown action: {action}")

        except ClientError as e:
            logger.error("aws_action_failed", resource=resource_id, error=str(e))
            raise

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
