from typing import Annotated, Optional, Dict, Any
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Request
from fastapi.params import Param
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import structlog

from app.shared.core.auth import CurrentUser, requires_role, require_tenant_access
from app.shared.db.session import get_db
from app.models.remediation import (
    RemediationAction,
    RemediationRequest,
    RemediationStatus,
)
from app.modules.optimization.domain import ZombieService, RemediationService
from app.shared.core.dependencies import requires_feature
from app.shared.core.pricing import FeatureFlag
from app.shared.core.rate_limit import rate_limit
from app.shared.core.exceptions import ResourceNotFoundError, ValdrixException
from app.shared.core.provider import normalize_provider
from app.shared.core.remediation_results import (
    normalize_remediation_status,
    parse_remediation_execution_error,
)
from app.models.background_job import JobType
from app.modules.governance.domain.jobs.processor import enqueue_job

router = APIRouter(tags=["Cloud Hygiene (Zombies)"])
logger = structlog.get_logger()
DEFAULT_REGION_HINT = "global"


def _coerce_region_hint(value: Any) -> str:
    if isinstance(value, Param):
        value = value.default
    normalized = str(value or "").strip().lower()
    return normalized or DEFAULT_REGION_HINT


def _coerce_query_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, Param):
        value = value.default
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _coerce_query_int(
    value: Any,
    *,
    default: int,
    minimum: int | None = None,
) -> int:
    if isinstance(value, Param):
        value = value.default
    if value is None:
        coerced = default
    else:
        try:
            coerced = int(value)
        except (TypeError, ValueError):
            coerced = default
    if minimum is not None and coerced < minimum:
        return minimum
    return coerced


def _parse_remediation_action(action: str) -> RemediationAction:
    try:
        return RemediationAction(action)
    except ValueError as exc:
        raise ValdrixException(
            message=f"Invalid action: {action}",
            code="invalid_remediation_action",
            status_code=400,
        ) from exc


def _raise_if_failed_execution(executed_request: RemediationRequest) -> None:
    status_value = normalize_remediation_status(getattr(executed_request, "status", None))
    if status_value != RemediationStatus.FAILED.value:
        return

    failure = parse_remediation_execution_error(
        getattr(executed_request, "execution_error", None)
    )

    raise ValdrixException(
        message=failure.message,
        code=failure.reason,
        status_code=failure.status_code or 400,
    )


# --- Schemas ---
class RemediationRequestCreate(BaseModel):
    resource_id: str
    resource_type: str
    action: str
    provider: str
    connection_id: Optional[UUID] = None
    estimated_savings: float
    create_backup: bool = False
    backup_retention_days: int = 30
    backup_cost_estimate: float = 0
    parameters: Optional[Dict[str, Any]] = None


class ReviewRequest(BaseModel):
    notes: Optional[str] = None


class PolicyPreviewResponse(BaseModel):
    decision: str
    summary: str
    tier: str
    rule_hits: list[dict[str, Any]]
    config: dict[str, Any]


class PolicyPreviewCreate(BaseModel):
    resource_id: str
    resource_type: str
    action: str
    provider: str
    connection_id: Optional[UUID] = None
    confidence_score: float | None = None
    explainability_notes: str | None = None
    review_notes: str | None = None
    parameters: Optional[Dict[str, Any]] = None


# --- Endpoints ---


@router.get("")
@rate_limit("10/minute")
async def scan_zombies(
    request: Request,
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
    region: str = Query(default=DEFAULT_REGION_HINT),
    analyze: bool = Query(
        default=False, description="Enable AI-powered analysis of detected zombies"
    ),
    background: bool = Query(default=False, description="Run scan as a background job"),
) -> Any:
    """
    Scan cloud accounts for zombie resources.
    If background=True, returns a job_id immediately.
    """
    region_hint = _coerce_region_hint(region)
    analyze_enabled = _coerce_query_bool(analyze, default=False)
    run_in_background = _coerce_query_bool(background, default=False)
    if run_in_background:
        logger.info(
            "enqueuing_zombie_scan",
            tenant_id=str(tenant_id),
            region=region_hint,
        )
        job = await enqueue_job(
            db=db,
            job_type=JobType.ZOMBIE_SCAN,
            tenant_id=tenant_id,
            payload={"region": region_hint, "analyze": analyze_enabled},
        )
        return {"status": "pending", "job_id": str(job.id)}

    service = ZombieService(db=db)
    return await service.scan_for_tenant(
        tenant_id=tenant_id,
        region=region_hint,
        analyze=analyze_enabled,
    )


@router.post("/request")
async def create_remediation_request(
    request: RemediationRequestCreate,
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[
        CurrentUser, Depends(requires_feature(FeatureFlag.AUTO_REMEDIATION))
    ],
    db: AsyncSession = Depends(get_db),
    region: str = Query(default=DEFAULT_REGION_HINT),
) -> Dict[str, str]:
    """Create a remediation request. Requires Pro tier or higher."""
    region_hint = _coerce_region_hint(region)
    action_enum = _parse_remediation_action(request.action)

    service = RemediationService(db=db, region=region_hint)
    result = await service.create_request(
        tenant_id=tenant_id,
        user_id=user.id,
        resource_id=request.resource_id,
        resource_type=request.resource_type,
        action=action_enum,
        estimated_savings=request.estimated_savings,
        create_backup=request.create_backup,
        backup_retention_days=request.backup_retention_days,
        backup_cost_estimate=request.backup_cost_estimate,
        provider=request.provider,
        connection_id=request.connection_id,
        parameters=request.parameters,
    )
    return {"status": "pending", "request_id": str(result.id)}


@router.get("/pending")
async def list_pending_requests(
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
    region: str = Query(default=DEFAULT_REGION_HINT),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Dict[str, Any]:
    """List open remediation requests (approval + execution queue)."""
    region_hint = _coerce_region_hint(region)
    page_limit = _coerce_query_int(limit, default=50, minimum=1)
    page_offset = _coerce_query_int(offset, default=0, minimum=0)
    service = RemediationService(db=db, region=region_hint)
    pending = await service.list_pending(
        tenant_id,
        limit=page_limit,
        offset=page_offset,
    )
    return {
        "pending_count": len(pending),
        "requests": [
            {
                "id": str(r.id),
                "status": r.status.value,
                "resource_id": r.resource_id,
                "resource_type": r.resource_type,
                "action": r.action.value,
                "provider": normalize_provider(getattr(r, "provider", None))
                or "unknown",
                "region": getattr(r, "region", region_hint),
                "connection_id": str(r.connection_id)
                if getattr(r, "connection_id", None)
                else None,
                "estimated_savings": float(r.estimated_monthly_savings or 0),
                "scheduled_execution_at": (
                    r.scheduled_execution_at.isoformat()
                    if r.scheduled_execution_at is not None
                    else None
                ),
                "escalation_required": bool(getattr(r, "escalation_required", False)),
                "escalation_reason": getattr(r, "escalation_reason", None),
                "escalated_at": escalated_at.isoformat()
                if (escalated_at := getattr(r, "escalated_at", None))
                else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in pending
        ],
    }


@router.post("/approve/{request_id}")
async def approve_remediation(
    request_id: UUID,
    review: ReviewRequest,
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db),
    region: str = Query(default=DEFAULT_REGION_HINT),
) -> Dict[str, str]:
    """Approve a request."""
    region_hint = _coerce_region_hint(region)
    service = RemediationService(db=db, region=region_hint)
    try:
        result = await service.approve(
            request_id,
            tenant_id,
            user.id,
            notes=review.notes,
            reviewer_role=user.role.value
            if hasattr(user.role, "value")
            else str(user.role),
        )
        return {"status": "approved", "request_id": str(result.id)}
    except ValueError as e:
        raise ResourceNotFoundError(str(e), code="remediation_request_not_found")


@router.get(
    "/policy-preview/{request_id}",
    response_model=PolicyPreviewResponse,
)
async def preview_remediation_policy(
    request_id: UUID,
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_feature(FeatureFlag.POLICY_PREVIEW))],
    db: AsyncSession = Depends(get_db),
    region: str = Query(default=DEFAULT_REGION_HINT),
) -> PolicyPreviewResponse:
    """Preview deterministic remediation policy outcome before execution."""
    region_hint = _coerce_region_hint(region)
    service = RemediationService(db=db, region=region_hint)
    remediation_request = await service.get_by_id(
        RemediationRequest, request_id, tenant_id
    )
    if not remediation_request:
        raise ResourceNotFoundError(f"Remediation request {request_id} not found")
    preview = await service.preview_policy(remediation_request, tenant_id)
    return PolicyPreviewResponse(**preview)


@router.post(
    "/policy-preview",
    response_model=PolicyPreviewResponse,
)
async def preview_remediation_policy_payload(
    payload: PolicyPreviewCreate,
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_feature(FeatureFlag.POLICY_PREVIEW))],
    db: AsyncSession = Depends(get_db),
    region: str = Query(default=DEFAULT_REGION_HINT),
) -> PolicyPreviewResponse:
    """Preview deterministic policy outcome before a remediation request is created."""
    region_hint = _coerce_region_hint(region)
    action_enum = _parse_remediation_action(payload.action)

    service = RemediationService(db=db, region=region_hint)
    preview = await service.preview_policy_input(
        tenant_id=tenant_id,
        user_id=user.id,
        resource_id=payload.resource_id,
        resource_type=payload.resource_type,
        action=action_enum,
        provider=payload.provider,
        connection_id=payload.connection_id,
        confidence_score=payload.confidence_score,
        explainability_notes=payload.explainability_notes,
        review_notes=payload.review_notes,
        parameters=payload.parameters,
    )
    return PolicyPreviewResponse(**preview)


@router.post("/execute/{request_id}")
@rate_limit("50/hour")
async def execute_remediation(
    request: Request,
    request_id: UUID,
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[
        CurrentUser,
        Depends(requires_feature(FeatureFlag.AUTO_REMEDIATION, required_role="admin")),
    ],
    db: AsyncSession = Depends(get_db),
    region: str = Query(default=DEFAULT_REGION_HINT),
    bypass_grace_period: bool = Query(
        default=False, description="Bypass 24h grace period (emergency use)"
    ),
) -> Dict[str, str]:
    """Execute a remediation request. Requires Pro tier or higher and Admin role."""
    region_hint = _coerce_region_hint(region)
    bypass_grace = _coerce_query_bool(bypass_grace_period, default=False)
    service = RemediationService(db=db, region=region_hint)

    try:
        executed_request = await service.execute(
            request_id,
            tenant_id,
            bypass_grace_period=bypass_grace,
        )
        _raise_if_failed_execution(executed_request)
        return {
            "status": executed_request.status.value,
            "request_id": str(executed_request.id),
        }
    except ResourceNotFoundError:
        raise
    except ValdrixException:
        raise
    except ValueError as exc:
        raise ValdrixException(
            message=str(exc),
            code="remediation_execution_failed",
            status_code=400,
        ) from exc
    except Exception:
        logger.exception("remediation_api_execution_failed", request_id=str(request_id))
        raise ValdrixException(
            message="Failed to execute remediation request.",
            code="remediation_execution_failed",
            status_code=500,
        ) from None


@router.get("/plan/{request_id}")
async def get_remediation_plan(
    request_id: UUID,
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[
        CurrentUser, Depends(requires_feature(FeatureFlag.GITOPS_REMEDIATION))
    ],
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Generate and return a Terraform decommissioning plan for a remediation request.
    Requires Pro tier or higher.
    """
    service = RemediationService(db=db)

    # Fetch the request using centralized scoping
    remediation_request = await service.get_by_id(
        RemediationRequest, request_id, tenant_id
    )

    if not remediation_request:
        raise ResourceNotFoundError(f"Remediation request {request_id} not found")

    plan = await service.generate_iac_plan(remediation_request, tenant_id)

    return {
        "status": "success",
        "plan": plan,
        "resource_id": remediation_request.resource_id,
        "provider": remediation_request.provider,
    }
