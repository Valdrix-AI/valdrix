from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from app.models.enforcement import (
    EnforcementApprovalRequest,
    EnforcementDecision,
    EnforcementDecisionLedger,
    EnforcementDecisionType,
    EnforcementMode,
    EnforcementSource,
)
from app.modules.enforcement.domain.service_utils import _as_utc, _quantize


@dataclass(frozen=True)
class GateInput:
    project_id: str
    environment: str
    action: str
    resource_reference: str
    estimated_monthly_delta_usd: Decimal
    estimated_hourly_delta_usd: Decimal
    metadata: dict[str, Any]
    idempotency_key: str | None = None
    dry_run: bool = False


@dataclass(frozen=True)
class GateEvaluationResult:
    decision: EnforcementDecision
    approval: EnforcementApprovalRequest | None
    approval_token: str | None
    ttl_seconds: int


@dataclass(frozen=True)
class ApprovalTokenContext:
    approval_id: UUID
    decision_id: UUID
    tenant_id: UUID
    project_id: str
    source: EnforcementSource
    environment: str
    request_fingerprint: str
    resource_reference: str
    max_monthly_delta_usd: Decimal
    max_hourly_delta_usd: Decimal
    expires_at: datetime


@dataclass(frozen=True)
class ReservationReconciliationResult:
    decision: EnforcementDecision
    released_reserved_usd: Decimal
    actual_monthly_delta_usd: Decimal
    drift_usd: Decimal
    status: str
    reconciled_at: datetime


@dataclass(frozen=True)
class OverdueReservationReconciliationResult:
    released_count: int
    total_released_usd: Decimal
    decision_ids: list[UUID]
    older_than_seconds: int


@dataclass(frozen=True)
class ReservationReconciliationException:
    decision: EnforcementDecision
    expected_reserved_usd: Decimal
    actual_monthly_delta_usd: Decimal
    drift_usd: Decimal
    status: str
    reconciled_at: datetime | None
    notes: str | None
    credit_settlement: list[dict[str, str]]


@dataclass(frozen=True)
class EnforcementExportBundle:
    generated_at: datetime
    window_start: datetime
    window_end: datetime
    decision_count_db: int
    decision_count_exported: int
    approval_count_db: int
    approval_count_exported: int
    decisions_sha256: str
    approvals_sha256: str
    policy_lineage_sha256: str
    policy_lineage: list[dict[str, Any]]
    computed_context_lineage_sha256: str
    computed_context_lineage: list[dict[str, Any]]
    decisions_csv: str
    approvals_csv: str
    parity_ok: bool


@dataclass(frozen=True)
class EnforcementSignedExportManifest:
    schema_version: str
    generated_at: datetime
    tenant_id: UUID
    window_start: datetime
    window_end: datetime
    decision_count_db: int
    decision_count_exported: int
    approval_count_db: int
    approval_count_exported: int
    decisions_sha256: str
    approvals_sha256: str
    policy_lineage_sha256: str
    policy_lineage: list[dict[str, Any]]
    computed_context_lineage_sha256: str
    computed_context_lineage: list[dict[str, Any]]
    parity_ok: bool
    content_sha256: str
    signature_algorithm: Literal["hmac-sha256"]
    signature_key_id: str
    signature: str
    canonical_content_json: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at.isoformat(),
            "tenant_id": str(self.tenant_id),
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "decision_count_db": self.decision_count_db,
            "decision_count_exported": self.decision_count_exported,
            "approval_count_db": self.approval_count_db,
            "approval_count_exported": self.approval_count_exported,
            "decisions_sha256": self.decisions_sha256,
            "approvals_sha256": self.approvals_sha256,
            "policy_lineage_sha256": self.policy_lineage_sha256,
            "policy_lineage": self.policy_lineage,
            "computed_context_lineage_sha256": self.computed_context_lineage_sha256,
            "computed_context_lineage": self.computed_context_lineage,
            "parity_ok": self.parity_ok,
            "manifest_content_sha256": self.content_sha256,
            "manifest_signature_algorithm": self.signature_algorithm,
            "manifest_signature_key_id": self.signature_key_id,
            "manifest_signature": self.signature,
        }


@dataclass(frozen=True)
class DecisionLedgerRecord:
    entry: EnforcementDecisionLedger


@dataclass(frozen=True)
class EntitlementWaterfallResult:
    decision: EnforcementDecisionType
    reserve_allocation_usd: Decimal
    reserve_reserved_credit_usd: Decimal
    reserve_emergency_credit_usd: Decimal
    reason_code: str | None
    stage_details: list[dict[str, str]]

    @property
    def reserve_credit_usd(self) -> Decimal:
        return _quantize(
            self.reserve_reserved_credit_usd + self.reserve_emergency_credit_usd,
            "0.0001",
        )


@dataclass(frozen=True)
class DecisionComputedContext:
    context_version: str
    generated_at: datetime
    policy_version: int
    month_start: date
    month_end: date
    month_elapsed_days: int
    month_total_days: int
    observed_cost_days: int
    latest_cost_date: date | None
    mtd_spend_usd: Decimal
    burn_rate_daily_usd: Decimal
    forecast_eom_usd: Decimal
    anomaly_signal: bool
    anomaly_kind: str | None
    anomaly_delta_usd: Decimal
    anomaly_percent: Decimal | None
    data_source_mode: str
    risk_class: str
    risk_score: int
    risk_factors: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "context_version": self.context_version,
            "generated_at": _as_utc(self.generated_at).isoformat(),
            "policy_version": int(self.policy_version),
            "month_start": self.month_start.isoformat(),
            "month_end": self.month_end.isoformat(),
            "month_elapsed_days": int(self.month_elapsed_days),
            "month_total_days": int(self.month_total_days),
            "observed_cost_days": int(self.observed_cost_days),
            "latest_cost_date": (
                self.latest_cost_date.isoformat()
                if self.latest_cost_date is not None
                else None
            ),
            "mtd_spend_usd": str(self.mtd_spend_usd),
            "burn_rate_daily_usd": str(self.burn_rate_daily_usd),
            "forecast_eom_usd": str(self.forecast_eom_usd),
            "anomaly_signal": bool(self.anomaly_signal),
            "anomaly_kind": self.anomaly_kind,
            "anomaly_delta_usd": str(self.anomaly_delta_usd),
            "anomaly_percent": (
                str(self.anomaly_percent)
                if self.anomaly_percent is not None
                else None
            ),
            "data_source_mode": self.data_source_mode,
            "risk_class": self.risk_class,
            "risk_score": int(self.risk_score),
            "risk_factors": list(self.risk_factors),
        }


@dataclass(frozen=True)
class PolicyContractMaterialization:
    terraform_mode: EnforcementMode
    terraform_mode_prod: EnforcementMode
    terraform_mode_nonprod: EnforcementMode
    k8s_admission_mode: EnforcementMode
    k8s_admission_mode_prod: EnforcementMode
    k8s_admission_mode_nonprod: EnforcementMode
    require_approval_for_prod: bool
    require_approval_for_nonprod: bool
    enforce_prod_requester_reviewer_separation: bool
    enforce_nonprod_requester_reviewer_separation: bool
    plan_monthly_ceiling_usd: Decimal | None
    enterprise_monthly_ceiling_usd: Decimal | None
    auto_approve_below_monthly_usd: Decimal
    hard_deny_above_monthly_usd: Decimal
    default_ttl_seconds: int
    approval_routing_rules: list[dict[str, Any]]
    policy_document_schema_version: str
    policy_document_sha256: str
    policy_document: dict[str, Any]
