from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models.enforcement import EnforcementSource
from app.modules.enforcement.api.v1.approvals import router as approvals_router
from app.modules.enforcement.api.v1.common import tenant_or_403
from app.modules.enforcement.api.v1.exports import router as exports_router
from app.modules.enforcement.api.v1.ledger import router as ledger_router
from app.modules.enforcement.api.v1.policy_budget_credit import (
    router as policy_budget_credit_router,
)
from app.modules.enforcement.api.v1.reservations import router as reservations_router
from app.modules.enforcement.api.v1.schemas import GateDecisionResponse, GateRequest
from app.modules.enforcement.domain.service import (
    EnforcementService,
    GateInput,
    gate_result_to_response,
)
from app.shared.core.auth import CurrentUser, requires_role_with_db_context
from app.shared.core.config import get_settings
from app.shared.core.ops_metrics import (
    ENFORCEMENT_GATE_DECISIONS_TOTAL,
    ENFORCEMENT_GATE_DECISION_REASONS_TOTAL,
    ENFORCEMENT_GATE_FAILURES_TOTAL,
    ENFORCEMENT_GATE_LATENCY_SECONDS,
)
from app.shared.core.rate_limit import rate_limit
from app.shared.db.session import get_db


router = APIRouter(tags=["Enforcement"])
logger = structlog.get_logger()


def _gate_timeout_seconds() -> float:
    raw = getattr(get_settings(), "ENFORCEMENT_GATE_TIMEOUT_SECONDS", 2.0)
    try:
        timeout_seconds = float(raw)
    except (TypeError, ValueError):
        timeout_seconds = 2.0
    return max(0.05, min(timeout_seconds, 30.0))


def _metric_reason(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return "unknown"
    safe = "".join(
        ch if (ch.isalnum() or ch in {"_", "-", "."}) else "_" for ch in normalized
    )
    return safe[:64] or "unknown"


async def _run_gate(
    *,
    request: Request,
    payload: GateRequest,
    source: EnforcementSource,
    current_user: CurrentUser,
    db: AsyncSession,
) -> GateDecisionResponse:
    tenant_id = tenant_or_403(current_user)
    idempotency_header = request.headers.get("Idempotency-Key")
    started_at = time.perf_counter()
    metric_path = "normal"

    gate_input = GateInput(
        project_id=str(payload.project_id).strip().lower() or "default",
        environment=payload.environment,
        action=str(payload.action).strip().lower(),
        resource_reference=str(payload.resource_reference).strip(),
        estimated_monthly_delta_usd=payload.estimated_monthly_delta_usd,
        estimated_hourly_delta_usd=payload.estimated_hourly_delta_usd,
        metadata=payload.metadata,
        idempotency_key=(idempotency_header or payload.idempotency_key),
        dry_run=bool(payload.dry_run),
    )

    service = EnforcementService(db)
    timeout_seconds = _gate_timeout_seconds()
    try:
        result = await asyncio.wait_for(
            service.evaluate_gate(
                tenant_id=tenant_id,
                actor_id=current_user.id,
                source=source,
                gate_input=gate_input,
            ),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        metric_path = "failsafe"
        ENFORCEMENT_GATE_FAILURES_TOTAL.labels(
            source=source.value,
            failure_type="timeout",
        ).inc()
        logger.warning(
            "enforcement_gate_timeout_fallback",
            tenant_id=str(tenant_id),
            source=source.value,
            timeout_seconds=timeout_seconds,
        )
        result = await service.resolve_fail_safe_gate(
            tenant_id=tenant_id,
            actor_id=current_user.id,
            source=source,
            gate_input=gate_input,
            failure_reason_code="gate_timeout",
            failure_metadata={"timeout_seconds": f"{timeout_seconds:.3f}"},
        )
    except HTTPException:
        raise
    except Exception as exc:
        metric_path = "failsafe"
        ENFORCEMENT_GATE_FAILURES_TOTAL.labels(
            source=source.value,
            failure_type="evaluation_error",
        ).inc()
        logger.exception(
            "enforcement_gate_failure_fallback",
            tenant_id=str(tenant_id),
            source=source.value,
            error_type=type(exc).__name__,
        )
        result = await service.resolve_fail_safe_gate(
            tenant_id=tenant_id,
            actor_id=current_user.id,
            source=source,
            gate_input=gate_input,
            failure_reason_code="gate_evaluation_error",
            failure_metadata={"error_type": type(exc).__name__},
        )

    ENFORCEMENT_GATE_DECISIONS_TOTAL.labels(
        source=source.value,
        decision=result.decision.decision.value,
        path=metric_path,
    ).inc()
    for reason in list(result.decision.reason_codes or [])[:8]:
        ENFORCEMENT_GATE_DECISION_REASONS_TOTAL.labels(
            source=source.value,
            reason=_metric_reason(reason),
        ).inc()
    ENFORCEMENT_GATE_LATENCY_SECONDS.labels(
        source=source.value,
        path=metric_path,
    ).observe(max(0.0, time.perf_counter() - started_at))

    return GateDecisionResponse(**gate_result_to_response(result))


@router.post("/gate/terraform", response_model=GateDecisionResponse)
@rate_limit("120/minute")
async def gate_terraform(
    request: Request,
    payload: GateRequest,
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> GateDecisionResponse:
    return await _run_gate(
        request=request,
        payload=payload,
        source=EnforcementSource.TERRAFORM,
        current_user=current_user,
        db=db,
    )


@router.post("/gate/k8s/admission", response_model=GateDecisionResponse)
@rate_limit("120/minute")
async def gate_k8s_admission(
    request: Request,
    payload: GateRequest,
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> GateDecisionResponse:
    return await _run_gate(
        request=request,
        payload=payload,
        source=EnforcementSource.K8S_ADMISSION,
        current_user=current_user,
        db=db,
    )

router.include_router(policy_budget_credit_router)
router.include_router(approvals_router)
router.include_router(reservations_router)
router.include_router(exports_router)
router.include_router(ledger_router)
