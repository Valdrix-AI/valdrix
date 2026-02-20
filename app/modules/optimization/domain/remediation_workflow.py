from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select

from app.models.remediation import (
    RemediationAction,
    RemediationRequest,
    RemediationStatus,
)
from app.shared.core.connection_queries import get_connection_model
from app.shared.core.exceptions import ResourceNotFoundError
from app.shared.core.provider import normalize_provider

logger = structlog.get_logger()


async def preview_policy_for_request(
    service: Any,
    request: RemediationRequest,
    tenant_id: UUID,
) -> dict[str, Any]:
    provider = normalize_provider(getattr(request, "provider", None))
    connection_id = getattr(request, "connection_id", None)
    if provider:
        await service._apply_system_policy_context(
            request,
            tenant_id=tenant_id,
            provider=provider,
            connection_id=connection_id,
        )

    from app.modules.optimization.domain import remediation as remediation_module

    tier = await remediation_module.get_tenant_tier(tenant_id, service.db)
    policy_config, _ = await service._build_policy_config(tenant_id)
    evaluation = remediation_module.RemediationPolicyEngine().evaluate(
        request, policy_config
    )
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


async def preview_policy_input_payload(
    service: Any,
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
    parameters: dict[str, Any] | None = None,
    connection_id: UUID | None = None,
) -> dict[str, Any]:
    """
    Evaluate policy for an in-memory remediation payload.

    This avoids persisting a request and enables pre-request dry-run previews.
    """
    provider_norm = normalize_provider(provider)
    if not provider_norm:
        raise ValueError("Invalid provider for policy preview")
    preview_region = (
        await service._resolve_aws_region_hint(
            tenant_id=tenant_id,
            connection_id=connection_id,
        )
        if provider_norm == "aws"
        else "global"
    )
    system_context = await service._build_system_policy_context(
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
        action_parameters=service._sanitize_action_parameters(
            parameters, system_policy_context=system_context
        ),
    )
    return await preview_policy_for_request(service, synthetic_request, tenant_id)


async def create_remediation_request(
    service: Any,
    *,
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
    confidence_score: float | None = None,
    explainability_notes: str | None = None,
    connection_id: UUID | None = None,
    parameters: dict[str, Any] | None = None,
) -> RemediationRequest:
    """Create a new remediation request (pending approval)."""
    provider_norm = normalize_provider(provider)
    if not provider_norm:
        raise ValueError(f"Invalid provider: {provider}")
    scoped_connection: Any | None = None

    if connection_id:
        try:
            connection_model = get_connection_model(provider_norm)
            if connection_model is None:
                raise ValueError(f"Invalid provider model for {provider_norm}")
            scoped_connection = await service.get_by_id(
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
        await service._resolve_aws_region_hint(
            tenant_id=tenant_id,
            connection_id=connection_id,
            connection=scoped_connection,
        )
        if provider_norm == "aws"
        else "global"
    )

    system_context = await service._build_system_policy_context(
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
        action_parameters=service._sanitize_action_parameters(
            parameters, system_policy_context=system_context
        ),
    )

    service.db.add(request)
    await service.db.commit()
    await service.db.refresh(request)

    logger.info(
        "remediation_request_created",
        request_id=str(request.id),
        resource=resource_id,
        action=action.value,
        backup=create_backup,
    )

    return request


async def list_pending_requests(
    service: Any,
    tenant_id: UUID,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[RemediationRequest]:
    """List open remediation requests for a tenant (actionable queue)."""
    max_page_size = 200
    bounded_limit = min(limit, max_page_size)
    stmt = (
        service._scoped_query(RemediationRequest, tenant_id)
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
        .limit(bounded_limit)
    )
    result = await service.db.execute(stmt)
    return list(result.scalars().all())


async def approve_request(
    service: Any,
    *,
    request_id: UUID,
    tenant_id: UUID,
    reviewer_id: UUID,
    notes: str | None = None,
    reviewer_role: str | None = None,
) -> RemediationRequest:
    """
    Approve a remediation request.
    Does NOT execute yet - that's a separate step for safety.
    """
    result = await service.db.execute(
        select(RemediationRequest)
        .where(RemediationRequest.id == request_id)
        .where(RemediationRequest.tenant_id == tenant_id)
        .with_for_update()
    )
    request = await service._scalar_one_or_none(result)

    if not request:
        raise ResourceNotFoundError(f"Request {request_id} not found")

    if request.status not in {
        RemediationStatus.PENDING,
        RemediationStatus.PENDING_APPROVAL,
    }:
        raise ValueError(f"Request is {request.status.value}, not pending approval")

    if getattr(request, "escalation_required", False) is True:
        normalized_role = (reviewer_role or "").strip().lower()
        settings = await service._get_remediation_settings(tenant_id)
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

        role_allowed = normalized_role == "owner" or normalized_role == required_role
        if not role_allowed:
            raise ValueError(
                f"Escalated remediation requests require {required_role} approval."
            )

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

    await service.db.commit()
    await service.db.refresh(request)

    logger.info(
        "remediation_approved",
        request_id=str(request_id),
        reviewer=str(reviewer_id),
    )

    return request


async def reject_request(
    service: Any,
    *,
    request_id: UUID,
    tenant_id: UUID,
    reviewer_id: UUID,
    notes: str | None = None,
) -> RemediationRequest:
    """Reject a remediation request."""
    result = await service.db.execute(
        select(RemediationRequest)
        .where(RemediationRequest.id == request_id)
        .where(RemediationRequest.tenant_id == tenant_id)
        .with_for_update()
    )
    request = await service._scalar_one_or_none(result)

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

    await service.db.commit()
    await service.db.refresh(request)

    logger.info(
        "remediation_rejected",
        request_id=str(request_id),
        reviewer=str(reviewer_id),
    )

    return request
