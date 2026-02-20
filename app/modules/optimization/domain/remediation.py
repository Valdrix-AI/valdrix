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
import hashlib
import inspect
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
from app.models.cloud import CloudAccount

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
from app.shared.core.provider import normalize_provider
from app.shared.core.connection_queries import get_connection_model
from app.shared.core.connection_state import (
    resolve_connection_profile,
    resolve_connection_region,
)
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
        provider = normalize_provider(getattr(request, "provider", None))
        tenant_id = getattr(request, "tenant_id", None)
        connection_id = getattr(request, "connection_id", None)
        fallback_credentials = dict(self.credentials or {})
        missing_connection_result = fallback_credentials if not connection_id else {}

        if tenant_id is None:
            return fallback_credentials
        if not provider:
            return fallback_credentials

        connection_model = get_connection_model(provider)
        if connection_model is None:
            return fallback_credentials

        def _coerce_dict(value: Any) -> dict[str, Any]:
            return dict(value) if isinstance(value, dict) else {}

        def _coerce_list(value: Any) -> list[Any]:
            return list(value) if isinstance(value, list) else []

        stmt = select(connection_model).where(connection_model.tenant_id == tenant_id)
        if connection_id:
            stmt = stmt.where(connection_model.id == connection_id)
        else:
            if hasattr(connection_model, "status"):
                stmt = stmt.where(connection_model.status == "active")
            elif hasattr(connection_model, "is_active"):
                stmt = stmt.where(connection_model.is_active.is_(True))

            order_clauses = []
            if hasattr(connection_model, "last_verified_at"):
                order_clauses.append(connection_model.last_verified_at.desc())
            order_clauses.append(connection_model.id.desc())
            stmt = stmt.order_by(*order_clauses)

        result = await self.db.execute(stmt)
        connection = await self._scalar_one_or_none(result)
        if connection is None:
            return missing_connection_result

        if provider == "aws":
            role_arn = getattr(connection, "role_arn", None)
            external_id = getattr(connection, "external_id", None)
            if not role_arn or not external_id:
                return missing_connection_result
            connection_region = resolve_connection_region(connection)
            return {
                "role_arn": role_arn,
                "external_id": external_id,
                "region": connection_region,
                "connection_id": str(getattr(connection, "id", connection_id or "")),
            }

        if provider == "azure":
            tenant = getattr(connection, "azure_tenant_id", None)
            client_id = getattr(connection, "client_id", None)
            client_secret = getattr(connection, "client_secret", None)
            subscription_id = getattr(connection, "subscription_id", None)
            if not all([tenant, client_id, client_secret, subscription_id]):
                return missing_connection_result
            return {
                "tenant_id": tenant,
                "client_id": client_id,
                "client_secret": client_secret,
                "subscription_id": subscription_id,
                "region": resolve_connection_region(connection),
                "connection_id": str(getattr(connection, "id", connection_id or "")),
            }

        if provider == "gcp":
            service_account_json = getattr(connection, "service_account_json", None)
            if isinstance(service_account_json, dict):
                return dict(service_account_json)
            if isinstance(service_account_json, str) and service_account_json.strip():
                try:
                    parsed = json.loads(service_account_json)
                    if isinstance(parsed, dict):
                        payload = dict(parsed)
                        payload.setdefault(
                            "connection_id",
                            str(getattr(connection, "id", connection_id or "")),
                        )
                        payload.setdefault("region", resolve_connection_region(connection))
                        return payload
                except (TypeError, ValueError) as exc:
                    logger.warning(
                        "remediation_invalid_gcp_service_account_json",
                        connection_id=str(connection_id),
                        error=str(exc),
                    )
            return missing_connection_result

        if provider == "saas":
            return {
                "vendor": getattr(connection, "vendor", None),
                "auth_method": getattr(connection, "auth_method", None),
                "api_key": getattr(connection, "api_key", None),
                "connector_config": _coerce_dict(
                    getattr(connection, "connector_config", None)
                ),
                "spend_feed": _coerce_list(getattr(connection, "spend_feed", None)),
                "connection_id": str(getattr(connection, "id", connection_id or "")),
                "region": resolve_connection_region(connection),
            }

        if provider == "license":
            return {
                "vendor": getattr(connection, "vendor", None),
                "auth_method": getattr(connection, "auth_method", None),
                "api_key": getattr(connection, "api_key", None),
                "connector_config": _coerce_dict(
                    getattr(connection, "connector_config", None)
                ),
                "license_feed": _coerce_list(getattr(connection, "license_feed", None)),
                "connection_id": str(getattr(connection, "id", connection_id or "")),
                "region": resolve_connection_region(connection),
            }

        if provider == "platform":
            return {
                "vendor": getattr(connection, "vendor", None),
                "auth_method": getattr(connection, "auth_method", None),
                "api_key": getattr(connection, "api_key", None),
                "api_secret": getattr(connection, "api_secret", None),
                "connector_config": _coerce_dict(
                    getattr(connection, "connector_config", None)
                ),
                "spend_feed": _coerce_list(getattr(connection, "spend_feed", None)),
                "connection_id": str(getattr(connection, "id", connection_id or "")),
                "region": resolve_connection_region(connection),
            }

        if provider == "hybrid":
            return {
                "vendor": getattr(connection, "vendor", None),
                "auth_method": getattr(connection, "auth_method", None),
                "api_key": getattr(connection, "api_key", None),
                "api_secret": getattr(connection, "api_secret", None),
                "connector_config": _coerce_dict(
                    getattr(connection, "connector_config", None)
                ),
                "spend_feed": _coerce_list(getattr(connection, "spend_feed", None)),
                "connection_id": str(getattr(connection, "id", connection_id or "")),
                "region": resolve_connection_region(connection),
            }

        return fallback_credentials

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
        print(f"DEBUG: execute() started for {request_id}")
        start_time = time.time()

        print("DEBUG: Fetching request from DB")
        result = await self.db.execute(
            select(RemediationRequest)
            .where(RemediationRequest.id == request_id)
            .where(RemediationRequest.tenant_id == tenant_id)
            .with_for_update()
        )
        request = result.scalar_one_or_none()
        print(f"DEBUG: Found request: {request}")

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

            system_policy_context = await self._apply_system_policy_context(
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
            execution_region = getattr(request, "region", None) or self.region
            if (
                provider == "aws"
                and str(execution_region or "").strip().lower() in {"", "global"}
            ):
                execution_region = await self._resolve_aws_region_hint(
                    tenant_id=tenant_id,
                    connection_id=getattr(request, "connection_id", None),
                )
            context = RemediationContext(
                db_session=self.db,
                tenant_id=tenant_id,
                tier=tier_value,
                region=execution_region,
                credentials=credentials,
                create_backup=bool(getattr(request, "create_backup", False)),
                backup_retention_days=int(getattr(request, "backup_retention_days", 30) or 30),
                parameters=self._strip_system_policy_context(
                    getattr(request, "action_parameters", None)
                ),
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
        from app.shared.core.pricing import (
            get_tenant_tier,
            FeatureFlag,
            is_feature_enabled,
        )

        resolved_tier = (
            tenant_tier
            if tenant_tier is not None
            else await get_tenant_tier(tenant_id, self.db)
        )

        if not is_feature_enabled(resolved_tier, FeatureFlag.GITOPS_REMEDIATION):
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
        else:
            # Cloud+ providers (SaaS/License/Platform/Hybrid) use a generic template.
            planlines.append("# Option 1: Manual State Removal")
            planlines.append(f"terraform state rm cloud_resource.{tf_id}")
            planlines.append("")
            planlines.append("# Option 2: Terraform 'removed' block")
            planlines.append("removed {")
            planlines.append(f"  from = cloud_resource.{tf_id}")
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
        # Resolve tier once to avoid N+1 tenant-plan lookups in bulk workflows.
        tenant_tier = await get_tenant_tier(tenant_id, self.db)
        plans = [
            await self.generate_iac_plan(req, tenant_id, tenant_tier=tenant_tier)
            for req in requests
        ]
        header = f"# Valdrix Bulk IaC Remediation Plan\n# Generated: {datetime.now(timezone.utc).isoformat()}\n\n"
        return header + "\n\n" + "\n" + "-" * 40 + "\n".join(plans)
