from __future__ import annotations

import asyncio  # noqa: F401
from datetime import datetime
from decimal import Decimal
import hashlib  # noqa: F401
import time  # noqa: F401
from typing import Any, Mapping, cast
from uuid import UUID

import jwt
import structlog
from sqlalchemy.exc import IntegrityError, SQLAlchemyError  # noqa: F401
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enforcement import (
    EnforcementApprovalRequest,
    EnforcementDecision,
    EnforcementMode,
    EnforcementPolicy,
    EnforcementSource,
)
from app.modules.enforcement.domain.policy_document import (
    POLICY_DOCUMENT_SCHEMA_VERSION,  # noqa: F401
    PolicyDocument,  # noqa: F401
    PolicyDocumentEntitlementMatrix,  # noqa: F401
    canonical_policy_document_payload,  # noqa: F401
    policy_document_sha256,  # noqa: F401
)
from app.modules.enforcement.domain.runtime_query_ops import (
    get_approval_by_decision as _get_approval_by_decision_impl,
    get_decision_by_idempotency as _get_decision_by_idempotency_impl,
    get_effective_budget as _get_effective_budget_impl,
    get_reserved_totals as _get_reserved_totals_impl,
)
from app.modules.enforcement.domain.approval_flow_ops import (
    approve_request as _approve_request_impl,
    consume_approval_token as _consume_approval_token_impl,
    create_or_get_approval_request as _create_or_get_approval_request_impl,
    deny_request as _deny_request_impl,
    list_pending_approvals as _list_pending_approvals_impl,
)
from app.modules.enforcement.domain.gate_evaluation_ops import (
    evaluate_gate as _evaluate_gate_impl,
    resolve_fail_safe_gate as _resolve_fail_safe_gate_impl,
)
from app.modules.enforcement.domain.reconciliation_flow_ops import (
    reconcile_overdue_reservations as _reconcile_overdue_reservations_impl,
    reconcile_reservation as _reconcile_reservation_impl,
)
from app.modules.enforcement.domain.policy_contract_ops import (
    get_or_create_policy as _get_or_create_policy_impl,
    update_policy as _update_policy_impl,
)
import app.modules.enforcement.domain.service_private_ops as _service_private_ops_module
from app.modules.enforcement.domain.service_private_ops import (
    EnforcementServicePrivateOps,
)
from app.modules.enforcement.domain.service_runtime_ops import (
    acquire_gate_evaluation_lock as _acquire_gate_evaluation_lock_impl,
    append_decision_ledger_entry as _append_decision_ledger_entry_impl,
    build_export_bundle as _build_export_bundle_impl,
    build_reservation_reconciliation_idempotent_replay as _build_reservation_reconciliation_idempotent_replay_impl,
    build_signed_export_manifest as _build_signed_export_manifest_impl,
    list_active_reservations as _list_active_reservations_impl,
    list_decision_ledger as _list_decision_ledger_impl,
    list_reconciliation_exceptions as _list_reconciliation_exceptions_impl,
    render_approvals_csv as _render_approvals_csv_runtime_impl,
    render_decisions_csv as _render_decisions_csv_runtime_impl,
    resolve_export_manifest_signing_key_id as _resolve_export_manifest_signing_key_id_runtime_impl,
    resolve_export_manifest_signing_secret as _resolve_export_manifest_signing_secret_runtime_impl,
)
from app.modules.enforcement.domain.service_models import (
    GateEvaluationResult,
    GateInput,
    OverdueReservationReconciliationResult,
    ReservationReconciliationResult,
)
from app.modules.enforcement.domain.service_utils import (
    _as_utc,
    _computed_context_snapshot,  # noqa: F401
    _default_required_permission_for_environment,  # noqa: F401
    _gate_lock_timeout_seconds as _gate_lock_timeout_seconds_impl,
    _is_production_environment,
    _json_default,  # noqa: F401
    _month_bounds,
    _normalize_allowed_reviewer_roles,  # noqa: F401
    _normalize_environment,
    _normalize_policy_document_schema_version,
    _normalize_policy_document_sha256,
    _normalize_string_list,  # noqa: F401
    _parse_iso_datetime,  # noqa: F401
    _payload_sha256,  # noqa: F401
    _quantize,
    _sanitize_csv_cell,  # noqa: F401
    _stable_fingerprint,
    _to_decimal,
    _unique_reason_codes,
    _iso_or_empty,  # noqa: F401
    _utcnow,
)
from app.shared.core.approval_permissions import user_has_approval_permission
from app.shared.core.auth import CurrentUser
from app.shared.core.config import get_settings
from app.shared.core.pricing import PricingTier, get_tenant_tier, get_tier_limit  # noqa: F401
from app.shared.core.ops_metrics import (
    ENFORCEMENT_APPROVAL_TOKEN_EVENTS_TOTAL,
    ENFORCEMENT_EXPORT_EVENTS_TOTAL,  # noqa: F401
    ENFORCEMENT_RESERVATION_DRIFT_USD_TOTAL,
    ENFORCEMENT_RESERVATION_RECONCILIATIONS_TOTAL,
)
from app.shared.core.ops_metrics import (  # noqa: F401
    ENFORCEMENT_GATE_LOCK_EVENTS_TOTAL,
    ENFORCEMENT_GATE_LOCK_WAIT_SECONDS,
)


logger = structlog.get_logger()

# Keep private-op dependencies bound to service-module symbols so helper tests
# that monkeypatch this module continue to validate behavior across the split.
setattr(_service_private_ops_module, "get_settings", lambda: get_settings())
setattr(
    _service_private_ops_module,
    "user_has_approval_permission",
    lambda *args, **kwargs: user_has_approval_permission(*args, **kwargs),
)
setattr(
    _service_private_ops_module,
    "_quantize",
    lambda value, quantum: _quantize(value, quantum),
)
setattr(_service_private_ops_module, "_to_decimal", lambda value: _to_decimal(value))
setattr(_service_private_ops_module, "jwt", jwt)


def _gate_lock_timeout_seconds() -> float:
    # Preserve service-module monkeypatch seam used in helper tests.
    raw = getattr(get_settings(), "ENFORCEMENT_GATE_TIMEOUT_SECONDS", 2.0)
    try:
        gate_timeout = float(raw)
    except (TypeError, ValueError):
        return _gate_lock_timeout_seconds_impl()
    gate_timeout = max(0.05, min(gate_timeout, 30.0))
    return max(0.05, min(gate_timeout * 0.8, 5.0))


class EnforcementService(EnforcementServicePrivateOps):
    def __init__(self, db: AsyncSession):
        self.db = db

    def compute_request_fingerprint(
        self,
        *,
        source: EnforcementSource,
        gate_input: GateInput,
    ) -> str:
        return _stable_fingerprint(source, gate_input)

    async def get_or_create_policy(self, tenant_id: UUID) -> EnforcementPolicy:
        return await _get_or_create_policy_impl(
            db=self.db,
            tenant_id=tenant_id,
            policy_document_contract_backfill_required_fn=(
                self._policy_document_contract_backfill_required
            ),
            materialize_policy_contract_fn=self._materialize_policy_contract,
            apply_policy_contract_materialization_fn=(
                self._apply_policy_contract_materialization
            ),
            to_decimal_fn=_to_decimal,
        )

    async def update_policy(
        self,
        *,
        tenant_id: UUID,
        terraform_mode: EnforcementMode,
        terraform_mode_prod: EnforcementMode | None = None,
        terraform_mode_nonprod: EnforcementMode | None = None,
        k8s_admission_mode: EnforcementMode,
        k8s_admission_mode_prod: EnforcementMode | None = None,
        k8s_admission_mode_nonprod: EnforcementMode | None = None,
        require_approval_for_prod: bool,
        require_approval_for_nonprod: bool,
        plan_monthly_ceiling_usd: Decimal | None = None,
        enterprise_monthly_ceiling_usd: Decimal | None = None,
        auto_approve_below_monthly_usd: Decimal,
        hard_deny_above_monthly_usd: Decimal,
        default_ttl_seconds: int,
        enforce_prod_requester_reviewer_separation: bool = True,
        enforce_nonprod_requester_reviewer_separation: bool = False,
        approval_routing_rules: list[Mapping[str, Any]] | None = None,
        policy_document: Mapping[str, Any] | None = None,
    ) -> EnforcementPolicy:
        return await _update_policy_impl(
            db=self.db,
            tenant_id=tenant_id,
            terraform_mode=terraform_mode,
            terraform_mode_prod=terraform_mode_prod,
            terraform_mode_nonprod=terraform_mode_nonprod,
            k8s_admission_mode=k8s_admission_mode,
            k8s_admission_mode_prod=k8s_admission_mode_prod,
            k8s_admission_mode_nonprod=k8s_admission_mode_nonprod,
            require_approval_for_prod=require_approval_for_prod,
            require_approval_for_nonprod=require_approval_for_nonprod,
            plan_monthly_ceiling_usd=plan_monthly_ceiling_usd,
            enterprise_monthly_ceiling_usd=enterprise_monthly_ceiling_usd,
            auto_approve_below_monthly_usd=auto_approve_below_monthly_usd,
            hard_deny_above_monthly_usd=hard_deny_above_monthly_usd,
            default_ttl_seconds=default_ttl_seconds,
            enforce_prod_requester_reviewer_separation=(
                enforce_prod_requester_reviewer_separation
            ),
            enforce_nonprod_requester_reviewer_separation=(
                enforce_nonprod_requester_reviewer_separation
            ),
            approval_routing_rules=approval_routing_rules,
            policy_document=policy_document,
            get_or_create_policy_fn=self.get_or_create_policy,
            materialize_policy_contract_fn=self._materialize_policy_contract,
            apply_policy_contract_materialization_fn=(
                self._apply_policy_contract_materialization
            ),
        )

    async def evaluate_gate(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        source: EnforcementSource,
        gate_input: GateInput,
    ) -> GateEvaluationResult:
        return cast(
            GateEvaluationResult,
            await _evaluate_gate_impl(
                service=self,
                tenant_id=tenant_id,
                actor_id=actor_id,
                source=source,
                gate_input=gate_input,
                gate_evaluation_result_cls=GateEvaluationResult,
                stable_fingerprint_fn=_stable_fingerprint,
                normalize_environment_fn=_normalize_environment,
                month_bounds_fn=_month_bounds,
                quantize_fn=_quantize,
                to_decimal_fn=_to_decimal,
                is_production_environment_fn=_is_production_environment,
                unique_reason_codes_fn=_unique_reason_codes,
                normalize_policy_document_schema_version_fn=(
                    _normalize_policy_document_schema_version
                ),
                normalize_policy_document_sha256_fn=_normalize_policy_document_sha256,
                utcnow_fn=_utcnow,
            ),
        )

    async def resolve_fail_safe_gate(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        source: EnforcementSource,
        gate_input: GateInput,
        failure_reason_code: str,
        failure_metadata: Mapping[str, Any] | None = None,
    ) -> GateEvaluationResult:
        return cast(
            GateEvaluationResult,
            await _resolve_fail_safe_gate_impl(
                service=self,
                tenant_id=tenant_id,
                actor_id=actor_id,
                source=source,
                gate_input=gate_input,
                failure_reason_code=failure_reason_code,
                failure_metadata=failure_metadata,
                gate_evaluation_result_cls=GateEvaluationResult,
                stable_fingerprint_fn=_stable_fingerprint,
                normalize_environment_fn=_normalize_environment,
                quantize_fn=_quantize,
                mode_violation_decision_fn=self._mode_violation_decision,
                is_production_environment_fn=_is_production_environment,
                unique_reason_codes_fn=_unique_reason_codes,
                normalize_policy_document_schema_version_fn=(
                    _normalize_policy_document_schema_version
                ),
                normalize_policy_document_sha256_fn=_normalize_policy_document_sha256,
                utcnow_fn=_utcnow,
            ),
        )

    async def create_or_get_approval_request(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        decision_id: UUID,
        notes: str | None,
    ) -> EnforcementApprovalRequest:
        return await _create_or_get_approval_request_impl(
            db=self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            decision_id=decision_id,
            notes=notes,
            get_or_create_policy_fn=self.get_or_create_policy,
            get_approval_by_decision_fn=self._get_approval_by_decision,
            resolve_approval_routing_trace_fn=self._resolve_approval_routing_trace,
            append_decision_ledger_entry_fn=self._append_decision_ledger_entry,
            utcnow_fn=_utcnow,
        )

    async def list_pending_approvals(
        self,
        *,
        tenant_id: UUID,
        reviewer: CurrentUser | None,
        limit: int,
    ) -> list[tuple[EnforcementApprovalRequest, EnforcementDecision]]:
        return await _list_pending_approvals_impl(
            db=self.db,
            tenant_id=tenant_id,
            reviewer=reviewer,
            limit=limit,
            get_or_create_policy_fn=self.get_or_create_policy,
            enforce_reviewer_authority_fn=self._enforce_reviewer_authority,
            utcnow_fn=_utcnow,
        )

    async def approve_request(
        self,
        *,
        tenant_id: UUID,
        approval_id: UUID,
        reviewer: CurrentUser,
        notes: str | None,
    ) -> tuple[EnforcementApprovalRequest, EnforcementDecision, str, datetime]:
        return await _approve_request_impl(
            db=self.db,
            tenant_id=tenant_id,
            approval_id=approval_id,
            reviewer=reviewer,
            notes=notes,
            load_approval_with_decision_fn=self._load_approval_with_decision,
            assert_pending_fn=self._assert_pending,
            settle_credit_reservations_for_decision_fn=self._settle_credit_reservations_for_decision,
            get_or_create_policy_fn=self.get_or_create_policy,
            enforce_reviewer_authority_fn=self._enforce_reviewer_authority,
            build_approval_token_fn=self._build_approval_token,
            append_decision_ledger_entry_fn=self._append_decision_ledger_entry,
            utcnow_fn=_utcnow,
            as_utc_fn=_as_utc,
        )

    async def deny_request(
        self,
        *,
        tenant_id: UUID,
        approval_id: UUID,
        reviewer: CurrentUser,
        notes: str | None,
    ) -> tuple[EnforcementApprovalRequest, EnforcementDecision]:
        return await _deny_request_impl(
            db=self.db,
            tenant_id=tenant_id,
            approval_id=approval_id,
            reviewer=reviewer,
            notes=notes,
            load_approval_with_decision_fn=self._load_approval_with_decision,
            assert_pending_fn=self._assert_pending,
            get_or_create_policy_fn=self.get_or_create_policy,
            enforce_reviewer_authority_fn=self._enforce_reviewer_authority,
            settle_credit_reservations_for_decision_fn=self._settle_credit_reservations_for_decision,
            append_decision_ledger_entry_fn=self._append_decision_ledger_entry,
            utcnow_fn=_utcnow,
        )

    async def consume_approval_token(
        self,
        *,
        tenant_id: UUID,
        approval_token: str,
        actor_id: UUID | None = None,
        expected_source: EnforcementSource | None = None,
        expected_project_id: str | None = None,
        expected_environment: str | None = None,
        expected_request_fingerprint: str | None = None,
        expected_resource_reference: str | None = None,
    ) -> tuple[EnforcementApprovalRequest, EnforcementDecision]:
        return await _consume_approval_token_impl(
            db=self.db,
            tenant_id=tenant_id,
            approval_token=approval_token,
            actor_id=actor_id,
            expected_source=expected_source,
            expected_project_id=expected_project_id,
            expected_environment=expected_environment,
            expected_request_fingerprint=expected_request_fingerprint,
            expected_resource_reference=expected_resource_reference,
            decode_approval_token_fn=self._decode_approval_token,
            extract_token_context_fn=self._extract_token_context,
            load_approval_with_decision_fn=self._load_approval_with_decision,
            utcnow_fn=_utcnow,
            as_utc_fn=_as_utc,
            normalize_environment_fn=_normalize_environment,
            quantize_fn=_quantize,
            to_decimal_fn=_to_decimal,
            approval_token_events_counter=ENFORCEMENT_APPROVAL_TOKEN_EVENTS_TOTAL,
        )

    list_active_reservations = _list_active_reservations_impl
    list_decision_ledger = _list_decision_ledger_impl
    list_reconciliation_exceptions = _list_reconciliation_exceptions_impl
    _build_reservation_reconciliation_idempotent_replay = (
        _build_reservation_reconciliation_idempotent_replay_impl
    )

    async def reconcile_reservation(
        self,
        *,
        tenant_id: UUID,
        decision_id: UUID,
        actor_id: UUID,
        actual_monthly_delta_usd: Decimal,
        notes: str | None,
        idempotency_key: str | None = None,
    ) -> ReservationReconciliationResult:
        return cast(
            ReservationReconciliationResult,
            await _reconcile_reservation_impl(
                service=self,
                tenant_id=tenant_id,
                decision_id=decision_id,
                actor_id=actor_id,
                actual_monthly_delta_usd=actual_monthly_delta_usd,
                notes=notes,
                idempotency_key=idempotency_key,
                reservation_reconciliation_result_cls=ReservationReconciliationResult,
                quantize_fn=_quantize,
                to_decimal_fn=_to_decimal,
                unique_reason_codes_fn=_unique_reason_codes,
                utcnow_fn=_utcnow,
                reservation_reconciliations_total_metric=(
                    ENFORCEMENT_RESERVATION_RECONCILIATIONS_TOTAL
                ),
                reservation_drift_usd_total_metric=(
                    ENFORCEMENT_RESERVATION_DRIFT_USD_TOTAL
                ),
            ),
        )

    async def reconcile_overdue_reservations(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        older_than_seconds: int,
        limit: int,
    ) -> OverdueReservationReconciliationResult:
        return cast(
            OverdueReservationReconciliationResult,
            await _reconcile_overdue_reservations_impl(
                service=self,
                tenant_id=tenant_id,
                actor_id=actor_id,
                older_than_seconds=older_than_seconds,
                limit=limit,
                overdue_reservation_reconciliation_result_cls=(
                    OverdueReservationReconciliationResult
                ),
                quantize_fn=_quantize,
                to_decimal_fn=_to_decimal,
                unique_reason_codes_fn=_unique_reason_codes,
                utcnow_fn=_utcnow,
                reservation_reconciliations_total_metric=(
                    ENFORCEMENT_RESERVATION_RECONCILIATIONS_TOTAL
                ),
            ),
        )

    build_export_bundle = _build_export_bundle_impl
    _resolve_export_manifest_signing_secret = (
        _resolve_export_manifest_signing_secret_runtime_impl
    )
    _resolve_export_manifest_signing_key_id = (
        _resolve_export_manifest_signing_key_id_runtime_impl
    )
    build_signed_export_manifest = _build_signed_export_manifest_impl
    _render_decisions_csv = _render_decisions_csv_runtime_impl
    _render_approvals_csv = _render_approvals_csv_runtime_impl
    _append_decision_ledger_entry = _append_decision_ledger_entry_impl

    _get_decision_by_idempotency = _get_decision_by_idempotency_impl
    _get_approval_by_decision = _get_approval_by_decision_impl
    _get_reserved_totals = _get_reserved_totals_impl
    _get_effective_budget = _get_effective_budget_impl

    def _gate_lock_timeout_seconds(self) -> float:
        return _gate_lock_timeout_seconds()

    _acquire_gate_evaluation_lock = _acquire_gate_evaluation_lock_impl


def gate_result_to_response(
    result: GateEvaluationResult,
) -> Mapping[str, Any]:
    decision = result.decision
    approval = result.approval
    response_payload = decision.response_payload if isinstance(decision.response_payload, dict) else {}
    computed_context = response_payload.get("computed_context")

    return {
        "decision": decision.decision.value,
        "reason_codes": list(decision.reason_codes or []),
        "decision_id": decision.id,
        "policy_version": int(decision.policy_version),
        "approval_required": bool(decision.approval_required),
        "approval_request_id": approval.id if approval is not None else None,
        "approval_token": result.approval_token,
        "approval_token_contract": "approval_flow_only",
        "ttl_seconds": int(result.ttl_seconds),
        "request_fingerprint": decision.request_fingerprint,
        "reservation_active": bool(decision.reservation_active),
        "computed_context": computed_context if isinstance(computed_context, dict) else None,
    }
