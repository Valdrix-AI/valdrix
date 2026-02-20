"""
Remediation Service - Approval Workflow for Zombie Resource Cleanup

Manages the remediation approval workflow:
1. create_request() - User requests remediation
2. list_pending() - Reviewer sees pending requests
3. approve() / reject() - Reviewer takes action
4. execute() - System executes approved requests
"""

from uuid import UUID, uuid4
from decimal import Decimal
from typing import List, Dict, Any, Optional
import inspect
import aioboto3
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.core.service import BaseService
import structlog

from app.models.remediation import (
    RemediationRequest,
    RemediationStatus,
    RemediationAction,
)
from app.models.cloud import CloudAccount

__all__ = ["RemediationService", "RemediationStatus", "RemediationAction"]
from app.models.remediation_settings import RemediationSettings
from app.modules.governance.domain.security.audit_log import (  # noqa: F401
    AuditEventType,
    AuditLogger,
)
from app.modules.governance.domain.security.remediation_policy import (
    PolicyConfig,
    RemediationPolicyEngine,
)
from app.shared.adapters.aws_utils import map_aws_credentials
from app.shared.core.config import get_settings
from app.shared.core.exceptions import ResourceNotFoundError
from app.shared.core.safety_service import SafetyGuardrailService  # noqa: F401
from app.shared.core.provider import normalize_provider
from app.shared.core.connection_queries import get_connection_model
from app.shared.core.connection_state import (
    resolve_connection_profile,
    resolve_connection_region,
)
from app.shared.core.pricing import (
    PricingTier,
    get_tenant_tier,
)
from app.modules.optimization.domain.actions import RemediationActionFactory  # noqa: F401

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
    _SYSTEM_POLICY_CONTEXT_KEY = "_system_policy_context"

    def __init__(
        self,
        db: AsyncSession,
        region: str = "global",
        credentials: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(db)
        self.region = region
        self.credentials = credentials
        self.session = aioboto3.Session()
        # Request-scoped cache for repeated policy/settings lookups in the same service lifecycle.
        self._remediation_settings_cache: dict[UUID, RemediationSettings | None] = {}

    async def _get_client(self, service_name: str) -> Any:
        """Helper to get aioboto3 client with optional credentials and endpoint override."""
        settings = get_settings()

        kwargs = {"region_name": self.region}

        if settings.AWS_ENDPOINT_URL:
            kwargs["endpoint_url"] = settings.AWS_ENDPOINT_URL

        if self.credentials:
            kwargs.update(map_aws_credentials(self.credentials))

        return self.session.client(service_name, **kwargs)

    @staticmethod
    async def _scalar_one_or_none(result: Any) -> Any:
        """
        Safe scalar extractor for SQLAlchemy results and async test doubles.

        Production SQLAlchemy result objects expose a synchronous
        `scalar_one_or_none()`, while AsyncMock-heavy tests can return awaitables.
        """
        extractor = getattr(result, "scalar_one_or_none", None)
        if not callable(extractor):
            return None
        value = extractor()
        if inspect.isawaitable(value):
            return await value
        return value

    async def _resolve_aws_region_hint(
        self,
        *,
        tenant_id: UUID | None = None,
        connection_id: UUID | None = None,
        connection: Any | None = None,
    ) -> str:
        """
        Resolve a concrete AWS region from request hint + optional connection context.

        `global` is treated as a non-concrete sentinel for cross-provider API defaults.
        """
        region_hint = str(self.region or "").strip().lower()
        if region_hint and region_hint != "global":
            return region_hint

        if connection is not None:
            connection_region = resolve_connection_region(connection)
            if connection_region != "global":
                return connection_region

        if tenant_id and connection_id:
            connection_model = get_connection_model("aws")
            if connection_model is not None:
                try:
                    scoped = await self.get_by_id(connection_model, connection_id, tenant_id)
                    if scoped is not None:
                        scoped_region = resolve_connection_region(scoped)
                        if scoped_region != "global":
                            return scoped_region
                except Exception as exc:
                    logger.warning(
                        "remediation_aws_region_resolution_failed",
                        tenant_id=str(tenant_id),
                        connection_id=str(connection_id),
                        error=str(exc),
                    )

        return str(get_settings().AWS_DEFAULT_REGION or "").strip() or "us-east-1"

    async def _get_remediation_settings(
        self, tenant_id: UUID
    ) -> RemediationSettings | None:
        if tenant_id in self._remediation_settings_cache:
            return self._remediation_settings_cache[tenant_id]

        try:
            result = await self.db.execute(
                select(RemediationSettings).where(
                    RemediationSettings.tenant_id == tenant_id
                )
            )
            settings = await self._scalar_one_or_none(result)
            resolved = settings if isinstance(settings, RemediationSettings) else None
            self._remediation_settings_cache[tenant_id] = resolved
            return resolved
        except Exception as exc:
            logger.warning(
                "remediation_settings_lookup_failed",
                tenant_id=str(tenant_id),
                error=str(exc),
            )
            self._remediation_settings_cache[tenant_id] = None
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

    async def _build_system_policy_context(
        self,
        *,
        tenant_id: UUID,
        provider: str,
        connection_id: UUID | None,
    ) -> dict[str, Any]:
        provider_norm = normalize_provider(provider)
        if not provider_norm:
            return {}

        if connection_id:
            account_context: dict[str, Any] | None = None
            account_result = await self.db.execute(
                select(CloudAccount)
                .where(CloudAccount.tenant_id == tenant_id)
                .where(CloudAccount.id == connection_id)
                .where(CloudAccount.provider == provider_norm)
            )
            account = await self._scalar_one_or_none(account_result)
            if isinstance(account, CloudAccount):
                account_context = {
                    "source": "cloud_account",
                    "connection_id": str(connection_id),
                    "is_production": bool(getattr(account, "is_production", False)),
                    "criticality": getattr(account, "criticality", None),
                }
                if account_context["is_production"] or account_context["criticality"]:
                    return account_context

            connection_model = get_connection_model(provider_norm)
            if connection_model is not None:
                connection_result = await self.db.execute(
                    select(connection_model)
                    .where(connection_model.tenant_id == tenant_id)
                    .where(connection_model.id == connection_id)
                )
                connection = await self._scalar_one_or_none(connection_result)
                if connection is not None:
                    profile = resolve_connection_profile(connection)
                    is_production = profile.get("is_production")
                    return {
                        "source": str(profile.get("source") or "connection_profile"),
                        "connection_id": str(connection_id),
                        "is_production": (
                            is_production
                            if isinstance(is_production, bool)
                            else None
                        ),
                        "criticality": profile.get("criticality"),
                    }

            if account_context is not None:
                return account_context

        return {}

    def _sanitize_action_parameters(
        self,
        parameters: Optional[Dict[str, Any]],
        *,
        system_policy_context: Optional[dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        safe_parameters: Dict[str, Any] = (
            dict(parameters) if isinstance(parameters, dict) else {}
        )
        safe_parameters.pop(self._SYSTEM_POLICY_CONTEXT_KEY, None)

        if system_policy_context:
            safe_parameters[self._SYSTEM_POLICY_CONTEXT_KEY] = dict(
                system_policy_context
            )

        return safe_parameters or None

    def _strip_system_policy_context(
        self, parameters: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        safe_parameters: Dict[str, Any] = (
            dict(parameters) if isinstance(parameters, dict) else {}
        )
        safe_parameters.pop(self._SYSTEM_POLICY_CONTEXT_KEY, None)
        return safe_parameters

    async def _apply_system_policy_context(
        self,
        request: RemediationRequest,
        *,
        tenant_id: UUID,
        provider: str,
        connection_id: UUID | None,
    ) -> dict[str, Any]:
        system_context = await self._build_system_policy_context(
            tenant_id=tenant_id,
            provider=provider,
            connection_id=connection_id,
        )
        request.action_parameters = self._sanitize_action_parameters(
            getattr(request, "action_parameters", None),
            system_policy_context=system_context,
        )
        return system_context

    async def _resolve_credentials(self, request: RemediationRequest) -> Dict[str, Any]:
        """Resolve provider credentials from the tenant connection bound to the request."""
        from app.modules.optimization.domain.remediation_credentials import (
            resolve_connection_credentials,
        )

        return await resolve_connection_credentials(self, request)

    async def preview_policy(
        self, request: RemediationRequest, tenant_id: UUID
    ) -> dict[str, Any]:
        provider = normalize_provider(getattr(request, "provider", None))
        connection_id = getattr(request, "connection_id", None)
        if provider:
            await self._apply_system_policy_context(
                request,
                tenant_id=tenant_id,
                provider=provider,
                connection_id=connection_id,
            )

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
        provider: str,
        confidence_score: float | None = None,
        explainability_notes: str | None = None,
        review_notes: str | None = None,
        parameters: Optional[Dict[str, Any]] = None,
        connection_id: Optional[UUID] = None,
    ) -> dict[str, Any]:
        """
        Evaluate policy for an in-memory remediation payload.

        This avoids persisting a request and enables pre-request dry-run previews.
        """
        provider_norm = normalize_provider(provider)
        if not provider_norm:
            raise ValueError("Invalid provider for policy preview")
        preview_region = (
            await self._resolve_aws_region_hint(
                tenant_id=tenant_id,
                connection_id=connection_id,
            )
            if provider_norm == "aws"
            else "global"
        )
        system_context = await self._build_system_policy_context(
            tenant_id=tenant_id,
            provider=provider_norm,
            connection_id=connection_id,
        )
        synthetic_request = RemediationRequest(
            id=uuid4(),
            tenant_id=tenant_id,
            resource_id=resource_id,
            resource_type=resource_type,
            provider=provider_norm,
            connection_id=connection_id,
            region=preview_region,
            action=action,
            status=RemediationStatus.PENDING,
            estimated_monthly_savings=Decimal("0"),
            confidence_score=(
                Decimal(str(confidence_score)) if confidence_score is not None else None
            ),
            explainability_notes=explainability_notes,
            requested_by_user_id=user_id,
            review_notes=review_notes,
            action_parameters=self._sanitize_action_parameters(
                parameters, system_policy_context=system_context
            ),
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
        provider: str,
        create_backup: bool = False,
        backup_retention_days: int = 30,
        backup_cost_estimate: float = 0,
        confidence_score: Optional[float] = None,
        explainability_notes: Optional[str] = None,
        connection_id: Optional[UUID] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> RemediationRequest:
        """Create a new remediation request (pending approval)."""
        provider_norm = normalize_provider(provider)
        if not provider_norm:
            raise ValueError(f"Invalid provider: {provider}")
        scoped_connection: Any | None = None

        # P2: Resource Ownership Verification (connection scoped to tenant)
        if connection_id:
            try:
                connection_model = get_connection_model(provider_norm)
                if connection_model is None:
                    raise ValueError(f"Invalid provider model for {provider_norm}")
                scoped_connection = await self.get_by_id(
                    connection_model, connection_id, tenant_id
                )
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

        request_region = (
            await self._resolve_aws_region_hint(
                tenant_id=tenant_id,
                connection_id=connection_id,
                connection=scoped_connection,
            )
            if provider_norm == "aws"
            else "global"
        )

        system_context = await self._build_system_policy_context(
            tenant_id=tenant_id,
            provider=provider_norm,
            connection_id=connection_id,
        )

        request = RemediationRequest(
            tenant_id=tenant_id,
            resource_id=resource_id,
            resource_type=resource_type,
            region=request_region,
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
            action_parameters=self._sanitize_action_parameters(
                parameters, system_policy_context=system_context
            ),
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
        from app.modules.optimization.domain.remediation_execute import (
            execute_remediation_request,
        )

        # Row locking is enforced via with_for_update in execute_remediation_request.
        return await execute_remediation_request(
            self,
            request_id,
            tenant_id,
            bypass_grace_period=bypass_grace_period,
        )

    async def enforce_hard_limit(self, tenant_id: UUID) -> List[UUID]:
        """
        Enforce hard limits for a tenant.
        1. Checks budget status via UsageTracker.
        2. If HARD_LIMIT is reached:
           - Automatically executes only high-confidence, low-risk pending requests.
           - Uses AUTOPILOT_BYPASS_GRACE_PERIOD setting (default fail-safe is no bypass).
        """
        from app.modules.optimization.domain.remediation_hard_limit import (
            enforce_hard_limit_for_tenant,
        )

        return await enforce_hard_limit_for_tenant(self, tenant_id)

    async def generate_iac_plan(
        self,
        request: RemediationRequest,
        tenant_id: UUID,
        *,
        tenant_tier: PricingTier | str | None = None,
    ) -> str:
        """
        Generates a Terraform decommissioning plan for the resource.
        Supports 'state rm' and 'removed' blocks for GitOps workflows.

        Phase 8: Gated by Pro tier.
        """
        from app.modules.optimization.domain.remediation_iac import (
            generate_iac_plan_for_request,
        )

        return await generate_iac_plan_for_request(
            self,
            request,
            tenant_id,
            tenant_tier=tenant_tier,
        )

    @staticmethod
    def _sanitize_tf_identifier(
        provider: str, resource_type: str, resource_id: str
    ) -> str:
        """
        Produce a Terraform-safe identifier with deterministic collision resistance.
        """
        from app.modules.optimization.domain.remediation_iac import sanitize_tf_identifier

        return sanitize_tf_identifier(provider, resource_type, resource_id)

    async def bulk_generate_iac_plan(
        self, requests: List[RemediationRequest], tenant_id: UUID
    ) -> str:
        """Generates a combined IaC plan for multiple resources."""
        from app.modules.optimization.domain.remediation_iac import (
            bulk_generate_iac_plan_for_requests,
        )

        return await bulk_generate_iac_plan_for_requests(self, requests, tenant_id)
