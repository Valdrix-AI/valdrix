from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
import time
from typing import Any, Callable, Mapping, cast
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import SQLAlchemyError

from app.models.enforcement import (
    EnforcementApprovalRequest,
    EnforcementDecision,
    EnforcementDecisionLedger,
    EnforcementMode,
    EnforcementPolicy,
    EnforcementSource,
)
from app.modules.enforcement.domain.export_bundle_ops import (
    build_signed_export_manifest_payload as _build_signed_export_manifest_payload_impl,
    build_export_bundle_payload as _build_export_bundle_payload_impl,
    resolve_manifest_signing_key_id as _resolve_manifest_signing_key_id_impl,
    resolve_manifest_signing_secret as _resolve_manifest_signing_secret_impl,
    render_approvals_csv as _render_approvals_csv_impl,
    render_decisions_csv as _render_decisions_csv_impl,
)
from app.modules.enforcement.domain.reconciliation_ops import (
    build_reconciliation_exception_payloads as _build_reconciliation_exception_payloads_impl,
    build_reservation_reconciliation_replay_payload as _build_reservation_reconciliation_replay_payload_impl,
)
from app.modules.enforcement.domain.service_models import (
    DecisionLedgerRecord,
    EnforcementExportBundle,
    EnforcementSignedExportManifest,
    ReservationReconciliationException,
    ReservationReconciliationResult,
)
from app.modules.enforcement.domain.service_utils import (
    _as_utc,
    _canonical_json,
    _computed_context_snapshot,
    _iso_or_empty,
    _json_default,
    _normalize_allowed_reviewer_roles,
    _normalize_environment,
    _normalize_policy_document_schema_version,
    _normalize_policy_document_sha256,
    _normalize_string_list,
    _parse_iso_datetime,
    _payload_sha256,
    _quantize,
    _sanitize_csv_cell,
    _to_decimal,
    _utcnow,
)
from app.shared.core.approval_permissions import (
    APPROVAL_PERMISSION_REMEDIATION_APPROVE_NONPROD,
    APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD,
    normalize_approval_permission,
)
from app.shared.core.config import get_settings
from app.shared.core.ops_metrics import (
    ENFORCEMENT_EXPORT_EVENTS_TOTAL,
    ENFORCEMENT_GATE_LOCK_EVENTS_TOTAL,
    ENFORCEMENT_GATE_LOCK_WAIT_SECONDS,
)


def normalize_policy_approval_routing_rules(
    service: Any,
    rules: list[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not rules:
        return []

    if len(rules) > 64:
        raise HTTPException(
            status_code=422,
            detail="approval_routing_rules cannot exceed 64 rules",
        )

    normalized_rules: list[dict[str, Any]] = []
    seen_rule_ids: set[str] = set()
    for index, raw_rule in enumerate(rules, start=1):
        if not isinstance(raw_rule, Mapping):
            raise HTTPException(
                status_code=422,
                detail=f"approval_routing_rules[{index}] must be an object",
            )

        rule_id = str(raw_rule.get("rule_id") or "").strip()
        if not rule_id:
            raise HTTPException(
                status_code=422,
                detail=f"approval_routing_rules[{index}].rule_id is required",
            )
        if len(rule_id) > 64:
            raise HTTPException(
                status_code=422,
                detail=f"approval_routing_rules[{index}].rule_id exceeds 64 chars",
            )
        rule_key = rule_id.lower()
        if rule_key in seen_rule_ids:
            raise HTTPException(
                status_code=422,
                detail=f"Duplicate approval routing rule_id: {rule_id}",
            )
        seen_rule_ids.add(rule_key)

        min_delta_raw = raw_rule.get("min_monthly_delta_usd")
        max_delta_raw = raw_rule.get("max_monthly_delta_usd")
        min_delta = (
            _quantize(_to_decimal(min_delta_raw), "0.0001")
            if min_delta_raw is not None
            else None
        )
        max_delta = (
            _quantize(_to_decimal(max_delta_raw), "0.0001")
            if max_delta_raw is not None
            else None
        )
        if min_delta is not None and min_delta < Decimal("0"):
            raise HTTPException(
                status_code=422,
                detail=f"approval_routing_rules[{index}].min_monthly_delta_usd must be >= 0",
            )
        if max_delta is not None and max_delta < Decimal("0"):
            raise HTTPException(
                status_code=422,
                detail=f"approval_routing_rules[{index}].max_monthly_delta_usd must be >= 0",
            )
        if min_delta is not None and max_delta is not None and min_delta > max_delta:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"approval_routing_rules[{index}] min_monthly_delta_usd "
                    "cannot exceed max_monthly_delta_usd"
                ),
            )

        raw_required_permission = raw_rule.get("required_permission")
        required_permission = None
        if raw_required_permission is not None:
            required_permission = normalize_approval_permission(raw_required_permission)
            if required_permission is None:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"approval_routing_rules[{index}].required_permission must be one of "
                        f"{APPROVAL_PERMISSION_REMEDIATION_APPROVE_NONPROD}, "
                        f"{APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD}"
                    ),
                )

        raw_separation = raw_rule.get("require_requester_reviewer_separation")
        if raw_separation is not None and not isinstance(raw_separation, bool):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"approval_routing_rules[{index}].require_requester_reviewer_separation "
                    "must be a boolean when provided"
                ),
            )

        normalized_rules.append(
            {
                "rule_id": rule_id,
                "enabled": bool(raw_rule.get("enabled", True)),
                "environments": _normalize_string_list(
                    raw_rule.get("environments"),
                    normalizer=_normalize_environment,
                ),
                "action_prefixes": _normalize_string_list(raw_rule.get("action_prefixes")),
                "min_monthly_delta_usd": str(min_delta) if min_delta is not None else None,
                "max_monthly_delta_usd": str(max_delta) if max_delta is not None else None,
                "risk_levels": _normalize_string_list(raw_rule.get("risk_levels")),
                "required_permission": required_permission,
                "allowed_reviewer_roles": _normalize_allowed_reviewer_roles(
                    raw_rule.get("allowed_reviewer_roles")
                ),
                "require_requester_reviewer_separation": raw_separation,
            }
        )

    return normalized_rules


def resolve_policy_mode(
    _service: Any,
    *,
    policy: EnforcementPolicy,
    source: EnforcementSource,
    environment: str,
) -> tuple[EnforcementMode, str]:
    normalized_env = _normalize_environment(environment)
    if source == EnforcementSource.TERRAFORM:
        if normalized_env == "prod":
            return policy.terraform_mode_prod, "terraform:prod"
        if normalized_env == "nonprod":
            return policy.terraform_mode_nonprod, "terraform:nonprod"
        return policy.terraform_mode, "terraform:default"

    if source == EnforcementSource.K8S_ADMISSION:
        if normalized_env == "prod":
            return policy.k8s_admission_mode_prod, "k8s_admission:prod"
        if normalized_env == "nonprod":
            return policy.k8s_admission_mode_nonprod, "k8s_admission:nonprod"
        return policy.k8s_admission_mode, "k8s_admission:default"

    return policy.k8s_admission_mode, "fallback:k8s_admission_default"


async def list_active_reservations(
    service: Any,
    *,
    tenant_id: UUID,
    limit: int,
) -> list[EnforcementDecision]:
    rows = await service.db.execute(
        select(EnforcementDecision)
        .where(EnforcementDecision.tenant_id == tenant_id)
        .where(EnforcementDecision.reservation_active.is_(True))
        .order_by(EnforcementDecision.created_at.asc())
        .limit(max(1, min(limit, 1000)))
    )
    return list(rows.scalars().all())


async def list_decision_ledger(
    service: Any,
    *,
    tenant_id: UUID,
    limit: int,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> list[DecisionLedgerRecord]:
    bounded_limit = max(1, min(int(limit), 1000))
    stmt = (
        select(EnforcementDecisionLedger)
        .where(EnforcementDecisionLedger.tenant_id == tenant_id)
        .order_by(
            EnforcementDecisionLedger.recorded_at.desc(),
            EnforcementDecisionLedger.id.desc(),
        )
        .limit(bounded_limit)
    )

    if start_at is not None:
        stmt = stmt.where(EnforcementDecisionLedger.recorded_at >= _as_utc(start_at))
    if end_at is not None:
        stmt = stmt.where(EnforcementDecisionLedger.recorded_at <= _as_utc(end_at))

    rows = await service.db.execute(stmt)
    return [DecisionLedgerRecord(entry=item) for item in rows.scalars().all()]


async def list_reconciliation_exceptions(
    service: Any,
    *,
    tenant_id: UUID,
    limit: int,
) -> list[ReservationReconciliationException]:
    bounded_limit = max(1, min(int(limit), 1000))
    scan_limit = max(100, min(bounded_limit * 10, 5000))

    rows = await service.db.execute(
        select(EnforcementDecision)
        .where(EnforcementDecision.tenant_id == tenant_id)
        .where(EnforcementDecision.reservation_active.is_(False))
        .order_by(EnforcementDecision.created_at.desc())
        .limit(scan_limit)
    )
    decisions = list(rows.scalars().all())

    payloads = _build_reconciliation_exception_payloads_impl(
        decisions=decisions,
        bounded_limit=bounded_limit,
        quantize_fn=_quantize,
        to_decimal_fn=_to_decimal,
        parse_iso_datetime_fn=_parse_iso_datetime,
    )
    return [ReservationReconciliationException(**payload) for payload in payloads]


def build_reservation_reconciliation_idempotent_replay(
    _service: Any,
    *,
    decision: EnforcementDecision,
    actual_monthly_delta_usd: Decimal,
    notes: str | None,
    idempotency_key: str | None,
) -> ReservationReconciliationResult | None:
    payload = _build_reservation_reconciliation_replay_payload_impl(
        decision=decision,
        actual_monthly_delta_usd=actual_monthly_delta_usd,
        notes=notes,
        idempotency_key=idempotency_key,
        quantize_fn=_quantize,
        to_decimal_fn=_to_decimal,
        parse_iso_datetime_fn=_parse_iso_datetime,
        utcnow_fn=_utcnow,
    )
    if payload is None:
        return None
    return ReservationReconciliationResult(
        decision=decision,
        **payload,
    )


async def build_export_bundle(
    service: Any,
    *,
    tenant_id: UUID,
    window_start: datetime,
    window_end: datetime,
    max_rows: int,
) -> EnforcementExportBundle:
    payload = await _build_export_bundle_payload_impl(
        db=service.db,
        tenant_id=tenant_id,
        window_start=window_start,
        window_end=window_end,
        max_rows=max_rows,
        as_utc_fn=_as_utc,
        normalize_policy_document_schema_version_fn=_normalize_policy_document_schema_version,
        normalize_policy_document_sha256_fn=_normalize_policy_document_sha256,
        computed_context_snapshot_fn=_computed_context_snapshot,
        json_default_fn=_json_default,
        render_decisions_csv_fn=service._render_decisions_csv,
        render_approvals_csv_fn=service._render_approvals_csv,
        export_events_counter=ENFORCEMENT_EXPORT_EVENTS_TOTAL,
        utcnow_fn=_utcnow,
    )
    return EnforcementExportBundle(**payload)


def resolve_export_manifest_signing_secret(
    _service: Any,
    *,
    get_settings_fn: Callable[[], Any] | None = None,
) -> str:
    resolved_get_settings_fn = get_settings_fn
    if resolved_get_settings_fn is None:
        from app.modules.enforcement.domain import service as enforcement_service_module

        resolved_get_settings_fn = cast(
            Callable[[], Any],
            getattr(
                enforcement_service_module,
                "get_settings",
                get_settings,
            ),
        )
    settings = resolved_get_settings_fn()
    return _resolve_manifest_signing_secret_impl(
        configured_secret=str(
            getattr(settings, "ENFORCEMENT_EXPORT_SIGNING_SECRET", "") or ""
        ),
        fallback_secret=str(getattr(settings, "SUPABASE_JWT_SECRET", "") or ""),
    )


def resolve_export_manifest_signing_key_id(
    _service: Any,
    *,
    get_settings_fn: Callable[[], Any] | None = None,
) -> str:
    resolved_get_settings_fn = get_settings_fn
    if resolved_get_settings_fn is None:
        from app.modules.enforcement.domain import service as enforcement_service_module

        resolved_get_settings_fn = cast(
            Callable[[], Any],
            getattr(
                enforcement_service_module,
                "get_settings",
                get_settings,
            ),
        )
    settings = resolved_get_settings_fn()
    return _resolve_manifest_signing_key_id_impl(
        explicit_key_id=str(getattr(settings, "ENFORCEMENT_EXPORT_SIGNING_KID", "") or ""),
        jwt_signing_key_id=str(getattr(settings, "JWT_SIGNING_KID", "") or ""),
    )


def build_signed_export_manifest(
    service: Any,
    *,
    tenant_id: UUID,
    bundle: EnforcementExportBundle,
) -> EnforcementSignedExportManifest:
    payload = _build_signed_export_manifest_payload_impl(
        tenant_id=tenant_id,
        bundle=bundle,
        resolve_signing_secret_fn=service._resolve_export_manifest_signing_secret,
        resolve_signing_key_id_fn=service._resolve_export_manifest_signing_key_id,
        canonical_json_fn=_canonical_json,
    )
    return EnforcementSignedExportManifest(**payload)


def render_decisions_csv(
    _service: Any,
    decisions: list[EnforcementDecision],
) -> str:
    return _render_decisions_csv_impl(
        decisions,
        computed_context_snapshot_fn=_computed_context_snapshot,
        sanitize_csv_cell_fn=_sanitize_csv_cell,
        normalize_policy_document_schema_version_fn=_normalize_policy_document_schema_version,
        normalize_policy_document_sha256_fn=_normalize_policy_document_sha256,
        to_decimal_fn=_to_decimal,
        iso_or_empty_fn=_iso_or_empty,
        json_default_fn=_json_default,
    )


def render_approvals_csv(
    _service: Any,
    approvals: list[EnforcementApprovalRequest],
) -> str:
    return _render_approvals_csv_impl(
        approvals,
        sanitize_csv_cell_fn=_sanitize_csv_cell,
        iso_or_empty_fn=_iso_or_empty,
    )


def append_decision_ledger_entry(
    service: Any,
    *,
    decision_row: EnforcementDecision,
    approval_row: EnforcementApprovalRequest | None = None,
) -> None:
    reserved_total = _quantize(
        _to_decimal(decision_row.reserved_allocation_usd)
        + _to_decimal(decision_row.reserved_credit_usd),
        "0.0001",
    )
    ledger_entry = EnforcementDecisionLedger(
        tenant_id=decision_row.tenant_id,
        decision_id=decision_row.id,
        source=decision_row.source,
        environment=decision_row.environment,
        project_id=decision_row.project_id,
        action=decision_row.action,
        resource_reference=decision_row.resource_reference,
        decision=decision_row.decision,
        reason_codes=list(decision_row.reason_codes or []),
        policy_version=int(decision_row.policy_version),
        policy_document_schema_version=_normalize_policy_document_schema_version(
            decision_row.policy_document_schema_version
        ),
        policy_document_sha256=_normalize_policy_document_sha256(
            decision_row.policy_document_sha256
        ),
        request_fingerprint=decision_row.request_fingerprint,
        idempotency_key=decision_row.idempotency_key,
        estimated_monthly_delta_usd=_quantize(
            _to_decimal(decision_row.estimated_monthly_delta_usd),
            "0.0001",
        ),
        estimated_hourly_delta_usd=_quantize(
            _to_decimal(decision_row.estimated_hourly_delta_usd),
            "0.000001",
        ),
        burn_rate_daily_usd=(
            _quantize(_to_decimal(decision_row.burn_rate_daily_usd), "0.0001")
            if decision_row.burn_rate_daily_usd is not None
            else None
        ),
        forecast_eom_usd=(
            _quantize(_to_decimal(decision_row.forecast_eom_usd), "0.0001")
            if decision_row.forecast_eom_usd is not None
            else None
        ),
        risk_class=(
            str(decision_row.risk_class).strip().lower()
            if decision_row.risk_class is not None
            else None
        ),
        risk_score=(
            int(decision_row.risk_score)
            if decision_row.risk_score is not None
            else None
        ),
        anomaly_signal=(
            bool(decision_row.anomaly_signal)
            if decision_row.anomaly_signal is not None
            else None
        ),
        reserved_total_usd=reserved_total,
        approval_required=bool(decision_row.approval_required),
        approval_request_id=approval_row.id if approval_row is not None else None,
        approval_status=approval_row.status if approval_row is not None else None,
        request_payload_sha256=_payload_sha256(decision_row.request_payload or {}),
        response_payload_sha256=_payload_sha256(decision_row.response_payload or {}),
        created_by_user_id=decision_row.created_by_user_id,
        decision_created_at=decision_row.created_at or _utcnow(),
    )
    service.db.add(ledger_entry)


async def acquire_gate_evaluation_lock(
    service: Any,
    *,
    policy: EnforcementPolicy,
    source: EnforcementSource,
) -> None:
    from app.modules.enforcement.domain import service as enforcement_service_module

    service_asyncio = getattr(enforcement_service_module, "asyncio", asyncio)
    service_time = getattr(enforcement_service_module, "time", time)
    wait_for_fn = getattr(service_asyncio, "wait_for", asyncio.wait_for)
    perf_counter_fn = getattr(service_time, "perf_counter", time.perf_counter)
    lock_events_total = getattr(
        enforcement_service_module,
        "ENFORCEMENT_GATE_LOCK_EVENTS_TOTAL",
        ENFORCEMENT_GATE_LOCK_EVENTS_TOTAL,
    )
    lock_wait_seconds = getattr(
        enforcement_service_module,
        "ENFORCEMENT_GATE_LOCK_WAIT_SECONDS",
        ENFORCEMENT_GATE_LOCK_WAIT_SECONDS,
    )

    lock_timeout_seconds = service._gate_lock_timeout_seconds()
    started_at = perf_counter_fn()
    try:
        result = cast(
            CursorResult[Any],
            await wait_for_fn(
                service.db.execute(
                    update(EnforcementPolicy)
                    .where(EnforcementPolicy.id == policy.id)
                    .where(EnforcementPolicy.tenant_id == policy.tenant_id)
                    .values(policy_version=EnforcementPolicy.policy_version)
                ),
                timeout=lock_timeout_seconds,
            ),
        )
    except TimeoutError as exc:
        wait_seconds = max(0.0, perf_counter_fn() - started_at)
        lock_wait_seconds.labels(
            source=source.value,
            outcome="timeout",
        ).observe(wait_seconds)
        lock_events_total.labels(
            source=source.value,
            event="timeout",
        ).inc()
        lock_events_total.labels(
            source=source.value,
            event="contended",
        ).inc()
        await service.db.rollback()
        raise HTTPException(
            status_code=503,
            detail={
                "code": "gate_lock_timeout",
                "message": "Enforcement gate evaluation lock timeout",
                "lock_timeout_seconds": f"{lock_timeout_seconds:.3f}",
                "lock_wait_seconds": f"{wait_seconds:.3f}",
            },
        ) from exc
    except (SQLAlchemyError, RuntimeError):
        wait_seconds = max(0.0, perf_counter_fn() - started_at)
        lock_wait_seconds.labels(
            source=source.value,
            outcome="error",
        ).observe(wait_seconds)
        lock_events_total.labels(
            source=source.value,
            event="error",
        ).inc()
        raise

    wait_seconds = max(0.0, perf_counter_fn() - started_at)
    lock_wait_seconds.labels(
        source=source.value,
        outcome="acquired",
    ).observe(wait_seconds)
    lock_events_total.labels(
        source=source.value,
        event="acquired",
    ).inc()
    if wait_seconds >= 0.05:
        lock_events_total.labels(
            source=source.value,
            event="contended",
        ).inc()
    if result.rowcount == 0:
        lock_events_total.labels(
            source=source.value,
            event="not_acquired",
        ).inc()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "gate_lock_contended",
                "message": "Unable to acquire enforcement gate evaluation lock",
                "lock_wait_seconds": f"{wait_seconds:.3f}",
            },
        )
