from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation
import time
from typing import Any
import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models.enforcement import EnforcementSource
from app.modules.enforcement.api.v1.actions import router as actions_router
from app.modules.enforcement.api.v1.approvals import router as approvals_router
from app.modules.enforcement.api.v1.common import (
    tenant_or_403,
    require_features_or_403,
)
from app.modules.enforcement.api.v1.exports import router as exports_router
from app.modules.enforcement.api.v1.ledger import router as ledger_router
from app.modules.enforcement.api.v1.policy_budget_credit import (
    router as policy_budget_credit_router,
)
from app.modules.enforcement.api.v1.reservations import router as reservations_router
from app.modules.enforcement.api.v1.schemas import (
    GateDecisionResponse,
    GateRequest,
    CloudEventGateRequest,
    K8sAdmissionReviewPayload,
    K8sAdmissionReviewResponse,
    K8sAdmissionReviewResult,
    K8sAdmissionReviewStatus,
    TerraformPreflightBinding,
    TerraformPreflightContinuation,
    TerraformPreflightRequest,
    TerraformPreflightResponse,
)
from app.modules.enforcement.domain.service import (
    EnforcementService,
    GateInput,
    gate_result_to_response,
)
from app.shared.core.auth import CurrentUser, requires_role_with_db_context
from app.shared.core.pricing import FeatureFlag
from app.shared.core.config import get_settings
from app.shared.core.ops_metrics import (
    ENFORCEMENT_GATE_DECISIONS_TOTAL,
    ENFORCEMENT_GATE_DECISION_REASONS_TOTAL,
    ENFORCEMENT_GATE_FAILURES_TOTAL,
    ENFORCEMENT_GATE_LATENCY_SECONDS,
)
from app.shared.core.rate_limit import global_rate_limit, rate_limit
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


def _enforcement_global_gate_limit(_: Request) -> str:
    settings = get_settings()
    if not bool(getattr(settings, "ENFORCEMENT_GLOBAL_ABUSE_GUARD_ENABLED", True)):
        return "1000000/minute"
    raw_cap = getattr(settings, "ENFORCEMENT_GLOBAL_GATE_PER_MINUTE_CAP", 1200)
    try:
        cap = int(raw_cap)
    except (TypeError, ValueError):
        cap = 1200
    cap = max(1, min(cap, 100000))
    return f"{cap}/minute"


def _metric_reason(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return "unknown"
    safe = "".join(
        ch if (ch.isalnum() or ch in {"_", "-", "."}) else "_" for ch in normalized
    )
    return safe[:64] or "unknown"


def _http_detail_mapping(detail: Any) -> dict[str, Any]:
    if not isinstance(detail, dict):
        return {}
    return {str(key): detail[key] for key in detail if str(key).strip()}


def _lock_failure_reason_from_http_exception(exc: HTTPException) -> str | None:
    detail = _http_detail_mapping(exc.detail)
    code = str(detail.get("code") or "").strip().lower()
    if code in {"gate_lock_timeout", "gate_lock_contended"}:
        return code
    return None


def _build_gate_input(
    *,
    payload: GateRequest,
    idempotency_key: str | None,
) -> GateInput:
    return GateInput(
        project_id=str(payload.project_id).strip().lower() or "default",
        environment=payload.environment,
        action=str(payload.action).strip().lower(),
        resource_reference=str(payload.resource_reference).strip(),
        estimated_monthly_delta_usd=payload.estimated_monthly_delta_usd,
        estimated_hourly_delta_usd=payload.estimated_hourly_delta_usd,
        metadata=dict(payload.metadata or {}),
        idempotency_key=idempotency_key,
        dry_run=bool(payload.dry_run),
    )


def _annotation_decimal(
    annotations: dict[str, str],
    *,
    key: str,
    default: Decimal,
) -> Decimal:
    raw = str(annotations.get(key, "")).strip()
    if not raw:
        return default
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid admission annotation '{key}'",
        ) from exc


def _cloud_event_data_sha256(value: Any) -> str:
    serialized = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _build_cloud_event_gate_input(
    *,
    payload: CloudEventGateRequest,
    idempotency_key: str | None,
) -> GateInput:
    cloud_event = payload.cloud_event
    resource_reference = (
        str(payload.resource_reference or "").strip()
        or str(cloud_event.subject or "").strip()
        or str(cloud_event.source).strip()
    )
    if not resource_reference:
        raise HTTPException(
            status_code=422,
            detail="CloudEvent resource reference could not be derived",
        )
    metadata = {
        **dict(payload.metadata or {}),
        "cloud_event_id": cloud_event.id,
        "cloud_event_source": cloud_event.source,
        "cloud_event_type": cloud_event.type,
        "cloud_event_specversion": cloud_event.specversion,
        "cloud_event_subject": cloud_event.subject,
        "cloud_event_time": (
            cloud_event.time.isoformat()
            if cloud_event.time is not None
            else None
        ),
        "cloud_event_datacontenttype": cloud_event.datacontenttype,
        "cloud_event_dataschema": cloud_event.dataschema,
        "cloud_event_data_sha256": _cloud_event_data_sha256(cloud_event.data),
    }
    extra_attrs = dict(cloud_event.model_extra or {})
    if extra_attrs:
        metadata["cloud_event_extensions"] = {
            str(key): extra_attrs[key] for key in sorted(extra_attrs.keys())
        }

    return GateInput(
        project_id=str(payload.project_id).strip().lower() or "default",
        environment=payload.environment,
        action=str(payload.action).strip().lower(),
        resource_reference=resource_reference,
        estimated_monthly_delta_usd=payload.estimated_monthly_delta_usd,
        estimated_hourly_delta_usd=payload.estimated_hourly_delta_usd,
        metadata=metadata,
        idempotency_key=idempotency_key,
        dry_run=bool(payload.dry_run),
    )


def _extract_k8s_labels_annotations(obj: dict[str, Any] | None) -> tuple[dict[str, str], dict[str, str], str, str]:
    metadata = obj.get("metadata") if isinstance(obj, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}
    labels_raw = metadata.get("labels")
    annotations_raw = metadata.get("annotations")
    labels = labels_raw if isinstance(labels_raw, dict) else {}
    annotations = annotations_raw if isinstance(annotations_raw, dict) else {}
    name = str(metadata.get("name") or "").strip()
    namespace = str(metadata.get("namespace") or "").strip()
    return (
        {str(k): str(v) for k, v in labels.items()},
        {str(k): str(v) for k, v in annotations.items()},
        name,
        namespace,
    )


async def _run_gate_input(
    *,
    source: EnforcementSource,
    gate_input: GateInput,
    expected_request_fingerprint: str | None,
    current_user: CurrentUser,
    db: AsyncSession,
) -> GateDecisionResponse:
    tenant_id = tenant_or_403(current_user)
    started_at = time.perf_counter()
    metric_path = "normal"

    service = EnforcementService(db)
    normalized_expected_fingerprint = str(expected_request_fingerprint or "").strip().lower()
    if normalized_expected_fingerprint:
        computed_fingerprint = service.compute_request_fingerprint(
            source=source,
            gate_input=gate_input,
        )
        if normalized_expected_fingerprint != computed_fingerprint:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Terraform preflight fingerprint mismatch; "
                    "retry payload does not match expected request fingerprint"
                ),
            )

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
    except HTTPException as exc:
        lock_reason_code = _lock_failure_reason_from_http_exception(exc)
        if lock_reason_code is None:
            raise

        metric_path = "failsafe"
        ENFORCEMENT_GATE_FAILURES_TOTAL.labels(
            source=source.value,
            failure_type=(
                "lock_timeout"
                if lock_reason_code == "gate_lock_timeout"
                else "lock_contended"
            ),
        ).inc()
        detail = _http_detail_mapping(exc.detail)
        logger.warning(
            "enforcement_gate_lock_fallback",
            tenant_id=str(tenant_id),
            source=source.value,
            reason=lock_reason_code,
            http_status_code=int(exc.status_code),
            lock_timeout_seconds=detail.get("lock_timeout_seconds"),
            lock_wait_seconds=detail.get("lock_wait_seconds"),
        )
        result = await service.resolve_fail_safe_gate(
            tenant_id=tenant_id,
            actor_id=current_user.id,
            source=source,
            gate_input=gate_input,
            failure_reason_code=lock_reason_code,
            failure_metadata={
                "http_status_code": int(exc.status_code),
                **detail,
            },
        )
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


async def _run_gate(
    *,
    request: Request,
    payload: GateRequest,
    source: EnforcementSource,
    current_user: CurrentUser,
    db: AsyncSession,
) -> GateDecisionResponse:
    idempotency_header = request.headers.get("Idempotency-Key")
    gate_input = _build_gate_input(
        payload=payload,
        idempotency_key=(idempotency_header or payload.idempotency_key),
    )
    return await _run_gate_input(
        source=source,
        gate_input=gate_input,
        expected_request_fingerprint=None,
        current_user=current_user,
        db=db,
    )


@router.post("/gate/terraform", response_model=GateDecisionResponse)
@global_rate_limit(_enforcement_global_gate_limit, namespace="enforcement_gate")
@rate_limit("120/minute")
async def gate_terraform(
    request: Request,
    payload: GateRequest,
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> GateDecisionResponse:
    await require_features_or_403(
        user=current_user,
        db=db,
        features=(FeatureFlag.API_ACCESS, FeatureFlag.POLICY_CONFIGURATION),
    )
    return await _run_gate(
        request=request,
        payload=payload,
        source=EnforcementSource.TERRAFORM,
        current_user=current_user,
        db=db,
    )


@router.post("/gate/k8s/admission", response_model=GateDecisionResponse)
@global_rate_limit(_enforcement_global_gate_limit, namespace="enforcement_gate")
@rate_limit("120/minute")
async def gate_k8s_admission(
    request: Request,
    payload: GateRequest,
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> GateDecisionResponse:
    await require_features_or_403(
        user=current_user,
        db=db,
        features=(FeatureFlag.API_ACCESS, FeatureFlag.POLICY_CONFIGURATION),
    )
    return await _run_gate(
        request=request,
        payload=payload,
        source=EnforcementSource.K8S_ADMISSION,
        current_user=current_user,
        db=db,
    )


@router.post("/gate/terraform/preflight", response_model=TerraformPreflightResponse)
@global_rate_limit(_enforcement_global_gate_limit, namespace="enforcement_gate")
@rate_limit("120/minute")
async def gate_terraform_preflight(
    request: Request,
    payload: TerraformPreflightRequest,
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> TerraformPreflightResponse:
    await require_features_or_403(
        user=current_user,
        db=db,
        features=(FeatureFlag.API_ACCESS, FeatureFlag.POLICY_CONFIGURATION),
    )
    idempotency_header = request.headers.get("Idempotency-Key")
    default_idempotency_key = f"terraform:{payload.run_id}:{payload.stage}"[:128]
    gate_metadata = {
        **dict(payload.metadata or {}),
        "terraform_run_id": payload.run_id,
        "terraform_stage": payload.stage,
    }
    if payload.workspace_id:
        gate_metadata["terraform_workspace_id"] = payload.workspace_id
    if payload.workspace_name:
        gate_metadata["terraform_workspace_name"] = payload.workspace_name
    if payload.callback_url:
        gate_metadata["terraform_callback_url"] = payload.callback_url
    if payload.run_url:
        gate_metadata["terraform_run_url"] = payload.run_url

    gate_input = GateInput(
        project_id=str(payload.project_id).strip().lower() or "default",
        environment=payload.environment,
        action=str(payload.action).strip().lower(),
        resource_reference=str(payload.resource_reference).strip(),
        estimated_monthly_delta_usd=payload.estimated_monthly_delta_usd,
        estimated_hourly_delta_usd=payload.estimated_hourly_delta_usd,
        metadata=gate_metadata,
        idempotency_key=(
            idempotency_header or payload.idempotency_key or default_idempotency_key
        ),
        dry_run=bool(payload.dry_run),
    )

    gate_response = await _run_gate_input(
        source=EnforcementSource.TERRAFORM,
        gate_input=gate_input,
        expected_request_fingerprint=payload.expected_request_fingerprint,
        current_user=current_user,
        db=db,
    )
    binding = TerraformPreflightBinding(
        expected_source=EnforcementSource.TERRAFORM,
        expected_project_id=gate_input.project_id,
        expected_environment=gate_input.environment,
        expected_request_fingerprint=gate_response.request_fingerprint,
        expected_resource_reference=gate_input.resource_reference,
    )
    continuation = TerraformPreflightContinuation(
        approval_consume_endpoint="/api/v1/enforcement/approvals/consume",
        binding=binding,
    )
    return TerraformPreflightResponse(
        run_id=payload.run_id,
        stage=payload.stage,
        decision=gate_response.decision,
        reason_codes=list(gate_response.reason_codes or []),
        decision_id=gate_response.decision_id,
        policy_version=gate_response.policy_version,
        approval_required=gate_response.approval_required,
        approval_request_id=gate_response.approval_request_id,
        approval_token_contract=gate_response.approval_token_contract,
        ttl_seconds=gate_response.ttl_seconds,
        request_fingerprint=gate_response.request_fingerprint,
        reservation_active=gate_response.reservation_active,
        computed_context=gate_response.computed_context,
        continuation=continuation,
    )


@router.post("/gate/k8s/admission/review", response_model=K8sAdmissionReviewResponse)
@global_rate_limit(_enforcement_global_gate_limit, namespace="enforcement_gate")
@rate_limit("120/minute")
async def gate_k8s_admission_review(
    request: Request,
    payload: K8sAdmissionReviewPayload,
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> K8sAdmissionReviewResponse:
    await require_features_or_403(
        user=current_user,
        db=db,
        features=(FeatureFlag.API_ACCESS, FeatureFlag.POLICY_CONFIGURATION),
    )
    review_request = payload.request
    labels, annotations, metadata_name, metadata_namespace = _extract_k8s_labels_annotations(
        review_request.obj
    )
    namespace = (
        str(review_request.namespace or "").strip()
        or metadata_namespace
        or "default"
    )
    name = str(review_request.name or "").strip() or metadata_name or "unnamed"
    project_id = (
        str(
            annotations.get("valdrix.io/project-id")
            or labels.get("valdrix.io/project-id")
            or namespace
        )
        .strip()
        .lower()
        or "default"
    )
    environment = (
        str(
            annotations.get("valdrix.io/environment")
            or labels.get("valdrix.io/environment")
            or "nonprod"
        )
        .strip()
        .lower()
        or "nonprod"
    )
    resource_type = str(review_request.resource.resource).strip().lower()
    action = f"admission.{review_request.operation.lower()}"
    resource_reference = f"{resource_type}/{namespace}/{name}"
    estimated_monthly_delta_usd = _annotation_decimal(
        annotations,
        key="valdrix.io/estimated-monthly-delta-usd",
        default=Decimal("0"),
    )
    estimated_hourly_delta_usd = _annotation_decimal(
        annotations,
        key="valdrix.io/estimated-hourly-delta-usd",
        default=Decimal("0"),
    )
    gate_input = GateInput(
        project_id=project_id,
        environment=environment,
        action=action,
        resource_reference=resource_reference,
        estimated_monthly_delta_usd=estimated_monthly_delta_usd,
        estimated_hourly_delta_usd=estimated_hourly_delta_usd,
        metadata={
            "resource_type": str(review_request.kind.kind).strip().lower(),
            "admission_operation": review_request.operation,
            "admission_namespace": namespace,
            "admission_name": name,
            "admission_labels": labels,
            "admission_annotations": annotations,
            "admission_kind": review_request.kind.kind,
            "admission_resource": review_request.resource.resource,
            "admission_user": str(review_request.user_info.get("username") or ""),
        },
        idempotency_key=(request.headers.get("Idempotency-Key") or review_request.uid),
        dry_run=bool(review_request.dry_run),
    )
    gate_response = await _run_gate_input(
        source=EnforcementSource.K8S_ADMISSION,
        gate_input=gate_input,
        expected_request_fingerprint=None,
        current_user=current_user,
        db=db,
    )
    decision = str(gate_response.decision).strip().upper()
    allowed = decision in {"ALLOW", "ALLOW_WITH_CREDITS"}
    reason_codes = [str(reason).strip().lower() for reason in gate_response.reason_codes or []]

    status: K8sAdmissionReviewStatus | None = None
    if not allowed:
        status = K8sAdmissionReviewStatus(
            code=403,
            reason="Forbidden",
            message=(
                f"Valdrix admission decision={decision}; "
                f"reason_codes={','.join(reason_codes) or 'none'}"
            ),
        )

    response = K8sAdmissionReviewResult(
        uid=review_request.uid,
        allowed=allowed,
        status=status,
        warnings=[f"valdrix:{reason}" for reason in reason_codes[:8]],
        audit_annotations={
            "valdrix.io/decision-id": str(gate_response.decision_id),
            "valdrix.io/decision": decision,
            "valdrix.io/policy-version": str(gate_response.policy_version),
            "valdrix.io/request-fingerprint": gate_response.request_fingerprint,
            "valdrix.io/approval-required": str(bool(gate_response.approval_required)).lower(),
            "valdrix.io/approval-request-id": (
                str(gate_response.approval_request_id)
                if gate_response.approval_request_id is not None
                else ""
            ),
        },
    )
    return K8sAdmissionReviewResponse(
        api_version=payload.api_version,
        kind="AdmissionReview",
        response=response,
    )


@router.post("/gate/cloud-event", response_model=GateDecisionResponse)
@global_rate_limit(_enforcement_global_gate_limit, namespace="enforcement_gate")
@rate_limit("120/minute")
async def gate_cloud_event(
    request: Request,
    payload: CloudEventGateRequest,
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> GateDecisionResponse:
    await require_features_or_403(
        user=current_user,
        db=db,
        features=(FeatureFlag.API_ACCESS, FeatureFlag.POLICY_CONFIGURATION),
    )
    idempotency_header = request.headers.get("Idempotency-Key")
    cloud_event_default_idempotency = (
        f"cloudevent:{payload.cloud_event.id}"[:128]
    )
    gate_input = _build_cloud_event_gate_input(
        payload=payload,
        idempotency_key=(
            idempotency_header
            or payload.idempotency_key
            or cloud_event_default_idempotency
        ),
    )
    return await _run_gate_input(
        source=EnforcementSource.CLOUD_EVENT,
        gate_input=gate_input,
        expected_request_fingerprint=payload.expected_request_fingerprint,
        current_user=current_user,
        db=db,
    )


router.include_router(policy_budget_credit_router)
router.include_router(approvals_router)
router.include_router(reservations_router)
router.include_router(actions_router)
router.include_router(exports_router)
router.include_router(ledger_router)
