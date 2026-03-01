from __future__ import annotations

import asyncio
import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import calendar
import hmac
import hashlib
import io
import json
import time
from typing import Any, Callable, Iterable, Literal, Mapping, cast
from uuid import UUID

import jwt
from pydantic import ValidationError
import structlog
from fastapi import HTTPException
from sqlalchemy.engine import CursorResult
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enforcement import (
    EnforcementApprovalRequest,
    EnforcementApprovalStatus,
    EnforcementBudgetAllocation,
    EnforcementCreditGrant,
    EnforcementCreditPoolType,
    EnforcementCreditReservationAllocation,
    EnforcementDecision,
    EnforcementDecisionLedger,
    EnforcementDecisionType,
    EnforcementMode,
    EnforcementPolicy,
    EnforcementSource,
)
from app.models.cloud import CostRecord
from app.modules.enforcement.domain.policy_document import (
    ApprovalRoutingRule,
    POLICY_DOCUMENT_SCHEMA_VERSION,
    PolicyDocument,
    PolicyDocumentApprovalMatrix,
    PolicyDocumentEntitlementMatrix,
    PolicyDocumentExecutionMatrix,
    PolicyDocumentModeMatrix,
    canonical_policy_document_payload,
    policy_document_sha256,
)
from app.shared.core.pricing import PricingTier, get_tenant_tier, get_tier_limit
from app.shared.core.approval_permissions import (
    APPROVAL_PERMISSION_REMEDIATION_APPROVE_NONPROD,
    APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD,
    normalize_approval_permission,
    user_has_approval_permission,
)
from app.shared.core.auth import CurrentUser
from app.shared.core.config import get_settings
from app.shared.core.ops_metrics import (
    ENFORCEMENT_APPROVAL_TOKEN_EVENTS_TOTAL,
    ENFORCEMENT_EXPORT_EVENTS_TOTAL,
    ENFORCEMENT_GATE_LOCK_EVENTS_TOTAL,
    ENFORCEMENT_GATE_LOCK_WAIT_SECONDS,
    ENFORCEMENT_RESERVATION_DRIFT_USD_TOTAL,
    ENFORCEMENT_RESERVATION_RECONCILIATIONS_TOTAL,
)


logger = structlog.get_logger()


_POLICY_DOCUMENT_SCHEMA_VERSION_DEFAULT = "valdrix.enforcement.policy.v1"
_POLICY_DOCUMENT_SHA256_EMPTY = "0" * 64


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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_iso_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _as_utc(value)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return _as_utc(parsed)


def _iso_or_empty(value: datetime | None) -> str:
    if value is None:
        return ""
    return _as_utc(value).isoformat()


def _to_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _quantize(value: Decimal, places: str) -> Decimal:
    return value.quantize(Decimal(places))


def _normalize_environment(value: str) -> str:
    env = str(value or "").strip().lower()
    if env in {"prod", "production", "live"}:
        return "prod"
    if env in {"nonprod", "non-prod", "dev", "test", "stage", "staging"}:
        return "nonprod"
    return env or "nonprod"


def _is_production_environment(value: str) -> bool:
    return _normalize_environment(value) == "prod"


_SUPPORTED_REVIEWER_ROLES = ("owner", "admin", "member")
_DEFAULT_ALLOWED_REVIEWER_ROLES = ("owner", "admin")


def _normalize_role_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _normalize_string_list(
    values: Iterable[Any] | None,
    *,
    normalizer: Callable[[str], str] | None = None,
) -> list[str]:
    normalized: list[str] = []
    if values is None:
        return normalized

    for raw in values:
        value = str(raw or "").strip()
        if not value:
            continue
        key = normalizer(value) if normalizer is not None else value.lower()
        if key not in normalized:
            normalized.append(key)
    return normalized


def _normalize_allowed_reviewer_roles(values: Iterable[Any] | None) -> list[str]:
    roles: list[str] = []
    if values is None:
        return list(_DEFAULT_ALLOWED_REVIEWER_ROLES)

    for raw in values:
        role = _normalize_role_value(raw)
        if role not in _SUPPORTED_REVIEWER_ROLES:
            continue
        if role not in roles:
            roles.append(role)
    if not roles:
        return list(_DEFAULT_ALLOWED_REVIEWER_ROLES)
    return roles


def _default_required_permission_for_environment(environment: str) -> str:
    if _is_production_environment(environment):
        return APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD
    return APPROVAL_PERMISSION_REMEDIATION_APPROVE_NONPROD


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Unsupported type for canonical json: {type(value)}")


def _payload_sha256(payload: Mapping[str, Any] | None) -> str:
    serialized = json.dumps(
        dict(payload or {}),
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def _sanitize_csv_cell(value: Any) -> str:
    if value is None:
        return ""
    normalized = str(value).replace("\r", " ").replace("\n", " ")
    if normalized[:1] in {"=", "+", "-", "@"}:
        return "'" + normalized
    return normalized


def _computed_context_snapshot(
    response_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    computed_context_raw = (
        response_payload.get("computed_context")
        if isinstance(response_payload, Mapping)
        else None
    )
    computed_context = (
        cast(Mapping[str, Any], computed_context_raw)
        if isinstance(computed_context_raw, Mapping)
        else {}
    )

    def _ctx_str(key: str) -> str:
        return str(computed_context.get(key) or "").strip()

    def _ctx_int(key: str) -> int:
        raw = computed_context.get(key)
        if raw is None:
            return 0
        if isinstance(raw, bool):
            return int(raw)
        if not isinstance(raw, (int, float, Decimal, str)):
            return 0
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0

    return {
        "context_version": _ctx_str("context_version"),
        "generated_at": _ctx_str("generated_at"),
        "month_start": _ctx_str("month_start"),
        "month_end": _ctx_str("month_end"),
        "month_elapsed_days": _ctx_int("month_elapsed_days"),
        "month_total_days": _ctx_int("month_total_days"),
        "observed_cost_days": _ctx_int("observed_cost_days"),
        "latest_cost_date": _ctx_str("latest_cost_date"),
        "data_source_mode": _ctx_str("data_source_mode"),
    }


def _stable_fingerprint(source: EnforcementSource, gate_input: GateInput) -> str:
    canonical = {
        "source": source.value,
        "project_id": gate_input.project_id,
        "environment": _normalize_environment(gate_input.environment),
        "action": gate_input.action,
        "resource_reference": gate_input.resource_reference,
        "estimated_monthly_delta_usd": str(
            _quantize(gate_input.estimated_monthly_delta_usd, "0.0001")
        ),
        "estimated_hourly_delta_usd": str(
            _quantize(gate_input.estimated_hourly_delta_usd, "0.000001")
        ),
        "metadata": gate_input.metadata,
    }
    serialized = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _month_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def _unique_reason_codes(values: list[str]) -> list[str]:
    ordered: list[str] = []
    for value in values:
        key = str(value or "").strip().lower()
        if not key:
            continue
        if key not in ordered:
            ordered.append(key)
    return ordered


def _normalize_policy_document_schema_version(value: str | None) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return _POLICY_DOCUMENT_SCHEMA_VERSION_DEFAULT
    return normalized[:64]


def _normalize_policy_document_sha256(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if len(normalized) != 64:
        return _POLICY_DOCUMENT_SHA256_EMPTY
    if any(ch not in "0123456789abcdef" for ch in normalized):
        return _POLICY_DOCUMENT_SHA256_EMPTY
    return normalized


def _gate_lock_timeout_seconds() -> float:
    raw = getattr(get_settings(), "ENFORCEMENT_GATE_TIMEOUT_SECONDS", 2.0)
    try:
        gate_timeout = float(raw)
    except (TypeError, ValueError):
        gate_timeout = 2.0
    gate_timeout = max(0.05, min(gate_timeout, 30.0))
    return max(0.05, min(gate_timeout * 0.8, 5.0))


class EnforcementService:
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
        policy = (
            await self.db.execute(
                select(EnforcementPolicy).where(EnforcementPolicy.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if policy is None:
            policy = EnforcementPolicy(tenant_id=tenant_id)
            self.db.add(policy)
            # Ensure ORM/defaulted fields are available for contract backfill.
            await self.db.flush()

        if self._policy_document_contract_backfill_required(policy):
            materialized = self._materialize_policy_contract(
                terraform_mode=policy.terraform_mode or EnforcementMode.SOFT,
                terraform_mode_prod=policy.terraform_mode_prod or EnforcementMode.SOFT,
                terraform_mode_nonprod=policy.terraform_mode_nonprod
                or EnforcementMode.SOFT,
                k8s_admission_mode=policy.k8s_admission_mode or EnforcementMode.SOFT,
                k8s_admission_mode_prod=policy.k8s_admission_mode_prod
                or EnforcementMode.SOFT,
                k8s_admission_mode_nonprod=policy.k8s_admission_mode_nonprod
                or EnforcementMode.SOFT,
                require_approval_for_prod=bool(policy.require_approval_for_prod),
                require_approval_for_nonprod=bool(policy.require_approval_for_nonprod),
                plan_monthly_ceiling_usd=policy.plan_monthly_ceiling_usd,
                enterprise_monthly_ceiling_usd=policy.enterprise_monthly_ceiling_usd,
                auto_approve_below_monthly_usd=_to_decimal(
                    policy.auto_approve_below_monthly_usd,
                    default=Decimal("25"),
                ),
                hard_deny_above_monthly_usd=_to_decimal(
                    policy.hard_deny_above_monthly_usd,
                    default=Decimal("5000"),
                ),
                default_ttl_seconds=int(policy.default_ttl_seconds or 900),
                enforce_prod_requester_reviewer_separation=bool(
                    policy.enforce_prod_requester_reviewer_separation
                ),
                enforce_nonprod_requester_reviewer_separation=bool(
                    policy.enforce_nonprod_requester_reviewer_separation
                ),
                approval_routing_rules=(
                    list(policy.approval_routing_rules)
                    if isinstance(policy.approval_routing_rules, list)
                    else []
                ),
                policy_document=(
                    cast(Mapping[str, Any], policy.policy_document)
                    if isinstance(policy.policy_document, Mapping)
                    else None
                ),
            )
            self._apply_policy_contract_materialization(
                policy,
                materialized,
                increment_policy_version=False,
            )

        await self.db.flush()
        return policy

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
        materialized = self._materialize_policy_contract(
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
            enforce_prod_requester_reviewer_separation=enforce_prod_requester_reviewer_separation,
            enforce_nonprod_requester_reviewer_separation=enforce_nonprod_requester_reviewer_separation,
            approval_routing_rules=approval_routing_rules,
            policy_document=policy_document,
        )

        policy = await self.get_or_create_policy(tenant_id)
        self._apply_policy_contract_materialization(
            policy,
            materialized,
            increment_policy_version=True,
        )
        await self.db.commit()
        await self.db.refresh(policy)
        return policy

    def _policy_document_contract_backfill_required(
        self,
        policy: EnforcementPolicy,
    ) -> bool:
        schema_version = str(getattr(policy, "policy_document_schema_version", "")).strip()
        if schema_version != POLICY_DOCUMENT_SCHEMA_VERSION:
            return True

        policy_document_raw = getattr(policy, "policy_document", None)
        if not isinstance(policy_document_raw, Mapping):
            return True

        try:
            canonical_payload = canonical_policy_document_payload(policy_document_raw)
        except (ValidationError, TypeError):
            return True

        hash_raw = str(getattr(policy, "policy_document_sha256", "")).strip().lower()
        if len(hash_raw) != 64 or any(ch not in "0123456789abcdef" for ch in hash_raw):
            return True
        return hash_raw != policy_document_sha256(canonical_payload)

    def _materialize_policy_contract(
        self,
        *,
        terraform_mode: EnforcementMode,
        terraform_mode_prod: EnforcementMode | None,
        terraform_mode_nonprod: EnforcementMode | None,
        k8s_admission_mode: EnforcementMode,
        k8s_admission_mode_prod: EnforcementMode | None,
        k8s_admission_mode_nonprod: EnforcementMode | None,
        require_approval_for_prod: bool,
        require_approval_for_nonprod: bool,
        plan_monthly_ceiling_usd: Decimal | None,
        enterprise_monthly_ceiling_usd: Decimal | None,
        auto_approve_below_monthly_usd: Decimal,
        hard_deny_above_monthly_usd: Decimal,
        default_ttl_seconds: int,
        enforce_prod_requester_reviewer_separation: bool,
        enforce_nonprod_requester_reviewer_separation: bool,
        approval_routing_rules: list[Mapping[str, Any]] | None,
        policy_document: Mapping[str, Any] | None,
    ) -> PolicyContractMaterialization:
        if policy_document is not None:
            try:
                document_model = PolicyDocument.model_validate(policy_document)
            except ValidationError as exc:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "message": "policy_document is invalid",
                        "errors": exc.errors(),
                    },
                ) from exc

            normalized_routing_rules = self._normalize_policy_approval_routing_rules(
                [
                    rule.model_dump(mode="json")
                    for rule in document_model.approval.routing_rules
                ]
            )
        else:
            normalized_routing_rules = self._normalize_policy_approval_routing_rules(
                approval_routing_rules
            )
            document_model = PolicyDocument(
                mode_matrix=PolicyDocumentModeMatrix(
                    terraform_default=terraform_mode,
                    terraform_prod=terraform_mode_prod or terraform_mode,
                    terraform_nonprod=terraform_mode_nonprod or terraform_mode,
                    k8s_admission_default=k8s_admission_mode,
                    k8s_admission_prod=k8s_admission_mode_prod or k8s_admission_mode,
                    k8s_admission_nonprod=(
                        k8s_admission_mode_nonprod or k8s_admission_mode
                    ),
                ),
                approval=PolicyDocumentApprovalMatrix(
                    require_approval_prod=bool(require_approval_for_prod),
                    require_approval_nonprod=bool(require_approval_for_nonprod),
                    enforce_prod_requester_reviewer_separation=bool(
                        enforce_prod_requester_reviewer_separation
                    ),
                    enforce_nonprod_requester_reviewer_separation=bool(
                        enforce_nonprod_requester_reviewer_separation
                    ),
                    routing_rules=[
                        ApprovalRoutingRule.model_validate(rule)
                        for rule in normalized_routing_rules
                    ],
                ),
                entitlements=PolicyDocumentEntitlementMatrix(
                    plan_monthly_ceiling_usd=plan_monthly_ceiling_usd,
                    enterprise_monthly_ceiling_usd=enterprise_monthly_ceiling_usd,
                    auto_approve_below_monthly_usd=auto_approve_below_monthly_usd,
                    hard_deny_above_monthly_usd=hard_deny_above_monthly_usd,
                ),
                execution=PolicyDocumentExecutionMatrix(
                    default_ttl_seconds=max(
                        60,
                        min(int(default_ttl_seconds), 86400),
                    )
                ),
            )

        auto_approve_threshold = _quantize(
            _to_decimal(document_model.entitlements.auto_approve_below_monthly_usd),
            "0.0001",
        )
        hard_deny_threshold = _quantize(
            _to_decimal(document_model.entitlements.hard_deny_above_monthly_usd),
            "0.0001",
        )
        if hard_deny_threshold <= Decimal("0"):
            raise HTTPException(
                status_code=422,
                detail="hard_deny_above_monthly_usd must be greater than 0",
            )
        # Defensive invariant guard: negative values are rejected by
        # PolicyDocumentEntitlementMatrix(ge=0) before this helper runs. Keep this
        # check as a fail-safe for malformed/bypassed policy payloads.
        if auto_approve_threshold < Decimal("0"):
            raise HTTPException(
                status_code=422,
                detail="auto_approve_below_monthly_usd must be >= 0",
            )
        if auto_approve_threshold > hard_deny_threshold:
            raise HTTPException(
                status_code=422,
                detail=(
                    "auto_approve_below_monthly_usd cannot exceed "
                    "hard_deny_above_monthly_usd"
                ),
            )

        plan_ceiling = (
            _quantize(_to_decimal(document_model.entitlements.plan_monthly_ceiling_usd), "0.0001")
            if document_model.entitlements.plan_monthly_ceiling_usd is not None
            else None
        )
        enterprise_ceiling = (
            _quantize(
                _to_decimal(document_model.entitlements.enterprise_monthly_ceiling_usd),
                "0.0001",
            )
            if document_model.entitlements.enterprise_monthly_ceiling_usd is not None
            else None
        )
        # Defensive invariant guard: entitlement matrix enforces ge=0 for plan
        # ceiling during model validation.
        if plan_ceiling is not None and plan_ceiling < Decimal("0"):
            raise HTTPException(
                status_code=422,
                detail="plan_monthly_ceiling_usd must be >= 0 when provided",
            )
        # Defensive invariant guard: entitlement matrix enforces ge=0 for
        # enterprise ceiling during model validation.
        if enterprise_ceiling is not None and enterprise_ceiling < Decimal("0"):
            raise HTTPException(
                status_code=422,
                detail="enterprise_monthly_ceiling_usd must be >= 0 when provided",
            )

        materialized_document = PolicyDocument(
            mode_matrix=document_model.mode_matrix,
            approval=PolicyDocumentApprovalMatrix(
                require_approval_prod=bool(
                    document_model.approval.require_approval_prod
                ),
                require_approval_nonprod=bool(
                    document_model.approval.require_approval_nonprod
                ),
                enforce_prod_requester_reviewer_separation=bool(
                    document_model.approval.enforce_prod_requester_reviewer_separation
                ),
                enforce_nonprod_requester_reviewer_separation=bool(
                    document_model.approval.enforce_nonprod_requester_reviewer_separation
                ),
                routing_rules=[
                    ApprovalRoutingRule.model_validate(item)
                    for item in normalized_routing_rules
                ],
            ),
            entitlements=PolicyDocumentEntitlementMatrix(
                plan_monthly_ceiling_usd=plan_ceiling,
                enterprise_monthly_ceiling_usd=enterprise_ceiling,
                auto_approve_below_monthly_usd=auto_approve_threshold,
                hard_deny_above_monthly_usd=hard_deny_threshold,
            ),
            execution=PolicyDocumentExecutionMatrix(
                default_ttl_seconds=max(
                    60,
                    min(int(document_model.execution.default_ttl_seconds), 86400),
                ),
                action_max_attempts=max(
                    1,
                    min(int(document_model.execution.action_max_attempts), 10),
                ),
                action_retry_backoff_seconds=max(
                    1,
                    min(
                        int(document_model.execution.action_retry_backoff_seconds),
                        86400,
                    ),
                ),
                action_lease_ttl_seconds=max(
                    30,
                    min(int(document_model.execution.action_lease_ttl_seconds), 3600),
                ),
            ),
        )
        canonical_document = canonical_policy_document_payload(materialized_document)
        document_hash = policy_document_sha256(canonical_document)

        return PolicyContractMaterialization(
            terraform_mode=materialized_document.mode_matrix.terraform_default,
            terraform_mode_prod=materialized_document.mode_matrix.terraform_prod,
            terraform_mode_nonprod=materialized_document.mode_matrix.terraform_nonprod,
            k8s_admission_mode=materialized_document.mode_matrix.k8s_admission_default,
            k8s_admission_mode_prod=materialized_document.mode_matrix.k8s_admission_prod,
            k8s_admission_mode_nonprod=materialized_document.mode_matrix.k8s_admission_nonprod,
            require_approval_for_prod=bool(
                materialized_document.approval.require_approval_prod
            ),
            require_approval_for_nonprod=bool(
                materialized_document.approval.require_approval_nonprod
            ),
            enforce_prod_requester_reviewer_separation=bool(
                materialized_document.approval.enforce_prod_requester_reviewer_separation
            ),
            enforce_nonprod_requester_reviewer_separation=bool(
                materialized_document.approval.enforce_nonprod_requester_reviewer_separation
            ),
            plan_monthly_ceiling_usd=plan_ceiling,
            enterprise_monthly_ceiling_usd=enterprise_ceiling,
            auto_approve_below_monthly_usd=auto_approve_threshold,
            hard_deny_above_monthly_usd=hard_deny_threshold,
            default_ttl_seconds=max(
                60,
                min(int(materialized_document.execution.default_ttl_seconds), 86400),
            ),
            approval_routing_rules=normalized_routing_rules,
            policy_document_schema_version=POLICY_DOCUMENT_SCHEMA_VERSION,
            policy_document_sha256=document_hash,
            policy_document=canonical_document,
        )

    def _apply_policy_contract_materialization(
        self,
        policy: EnforcementPolicy,
        materialized: PolicyContractMaterialization,
        *,
        increment_policy_version: bool,
    ) -> None:
        policy.terraform_mode = materialized.terraform_mode
        policy.terraform_mode_prod = materialized.terraform_mode_prod
        policy.terraform_mode_nonprod = materialized.terraform_mode_nonprod
        policy.k8s_admission_mode = materialized.k8s_admission_mode
        policy.k8s_admission_mode_prod = materialized.k8s_admission_mode_prod
        policy.k8s_admission_mode_nonprod = materialized.k8s_admission_mode_nonprod
        policy.require_approval_for_prod = materialized.require_approval_for_prod
        policy.require_approval_for_nonprod = materialized.require_approval_for_nonprod
        policy.enforce_prod_requester_reviewer_separation = (
            materialized.enforce_prod_requester_reviewer_separation
        )
        policy.enforce_nonprod_requester_reviewer_separation = (
            materialized.enforce_nonprod_requester_reviewer_separation
        )
        policy.plan_monthly_ceiling_usd = materialized.plan_monthly_ceiling_usd
        policy.enterprise_monthly_ceiling_usd = materialized.enterprise_monthly_ceiling_usd
        policy.auto_approve_below_monthly_usd = (
            materialized.auto_approve_below_monthly_usd
        )
        policy.hard_deny_above_monthly_usd = materialized.hard_deny_above_monthly_usd
        policy.default_ttl_seconds = materialized.default_ttl_seconds
        policy.approval_routing_rules = materialized.approval_routing_rules
        policy.policy_document_schema_version = (
            materialized.policy_document_schema_version
        )
        policy.policy_document_sha256 = materialized.policy_document_sha256
        policy.policy_document = materialized.policy_document
        if increment_policy_version:
            policy.policy_version += 1

    def _normalize_policy_approval_routing_rules(
        self,
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

    def _resolve_policy_mode(
        self,
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

        # Cloud-event and any future source fall back to k8s/default semantics,
        # preserving prior behavior for non-terraform sources.
        return policy.k8s_admission_mode, "fallback:k8s_admission_default"

    async def _resolve_tenant_tier(self, tenant_id: UUID) -> PricingTier:
        tier = await get_tenant_tier(tenant_id, self.db)
        return tier if isinstance(tier, PricingTier) else PricingTier.FREE

    async def _resolve_plan_monthly_ceiling_usd(
        self,
        *,
        policy: EnforcementPolicy,
        tenant_tier: PricingTier,
    ) -> Decimal | None:
        configured = policy.plan_monthly_ceiling_usd
        if configured is not None:
            normalized = _quantize(_to_decimal(configured), "0.0001")
            return normalized if normalized > Decimal("0.0000") else None

        raw = get_tier_limit(tenant_tier, "enforcement_plan_monthly_ceiling_usd")
        if raw is None:
            return None
        ceiling = _quantize(_to_decimal(raw), "0.0001")
        if ceiling <= Decimal("0.0000"):
            return None
        return ceiling

    async def _resolve_enterprise_monthly_ceiling_usd(
        self,
        *,
        policy: EnforcementPolicy,
        tenant_tier: PricingTier,
    ) -> Decimal | None:
        configured = policy.enterprise_monthly_ceiling_usd
        if configured is not None:
            normalized = _quantize(_to_decimal(configured), "0.0001")
            return normalized if normalized > Decimal("0.0000") else None

        raw = get_tier_limit(tenant_tier, "enforcement_enterprise_monthly_ceiling_usd")
        if raw is None:
            return None
        ceiling = _quantize(_to_decimal(raw), "0.0001")
        if ceiling <= Decimal("0.0000"):
            return None
        return ceiling

    def _month_total_days(self, value: date) -> int:
        return int(calendar.monthrange(value.year, value.month)[1])

    async def _load_daily_cost_totals(
        self,
        *,
        tenant_id: UUID,
        start_date: date,
        end_date: date,
        final_only: bool,
    ) -> dict[date, Decimal]:
        stmt = (
            select(
                CostRecord.recorded_at.label("recorded_at"),
                func.coalesce(func.sum(CostRecord.cost_usd), 0).label("total_cost_usd"),
            )
            .where(CostRecord.tenant_id == tenant_id)
            .where(CostRecord.recorded_at >= start_date)
            .where(CostRecord.recorded_at <= end_date)
            .group_by(CostRecord.recorded_at)
        )
        if final_only:
            stmt = stmt.where(CostRecord.cost_status == "FINAL")

        rows = await self.db.execute(stmt)
        return {
            cast(date, item.recorded_at): _quantize(
                _to_decimal(item.total_cost_usd),
                "0.0001",
            )
            for item in rows.all()
        }

    def _derive_risk_assessment(
        self,
        *,
        gate_input: GateInput,
        is_production: bool,
        anomaly_signal: bool,
    ) -> tuple[str, int, tuple[str, ...]]:
        metadata = gate_input.metadata if isinstance(gate_input.metadata, dict) else {}
        action = str(gate_input.action or "").strip().lower()
        resource_reference = str(gate_input.resource_reference or "").strip().lower()
        resource_type = str(metadata.get("resource_type") or "").strip().lower()
        resource_class = str(metadata.get("resource_class") or resource_type).strip().lower()
        criticality = (
            str(
                metadata.get("criticality")
                or metadata.get("business_criticality")
                or metadata.get("service_criticality")
                or ""
            )
            .strip()
            .lower()
        )
        monthly_delta = _quantize(_to_decimal(gate_input.estimated_monthly_delta_usd), "0.0001")

        score = 0
        factors: list[str] = []

        if is_production:
            score += 3
            factors.append("production_environment")

        destructive_markers = (
            "destroy",
            "delete",
            "terminate",
            "remove",
            "revoke",
            "detach",
            "scale_down",
            "downscale",
        )
        if any(marker in action for marker in destructive_markers):
            score += 2
            factors.append("destructive_action")

        high_criticality_values = {"critical", "high", "tier0", "tier1", "p0", "sev0"}
        medium_criticality_values = {"medium", "tier2", "p1", "sev1"}
        if criticality in high_criticality_values:
            score += 2
            factors.append("criticality_high")
        elif criticality in medium_criticality_values:
            score += 1
            factors.append("criticality_medium")

        high_impact_markers = (
            "gpu",
            "db",
            "database",
            "cluster",
            "k8s",
            "kubernetes",
            "warehouse",
            "redshift",
            "bigquery",
            "rds",
            "postgres",
            "mysql",
            "elasticsearch",
        )
        impact_text = " ".join([resource_class, resource_type, resource_reference])
        if any(marker in impact_text for marker in high_impact_markers):
            score += 1
            factors.append("high_impact_resource_class")

        if monthly_delta >= Decimal("5000.0000"):
            score += 2
            factors.append("large_monthly_delta")
        elif monthly_delta >= Decimal("1000.0000"):
            score += 1
            factors.append("moderate_monthly_delta")

        if anomaly_signal:
            score += 1
            factors.append("anomaly_spike_signal")

        if score >= 6:
            risk_class = "high"
        elif score >= 3:
            risk_class = "medium"
        else:
            risk_class = "low"

        return risk_class, score, tuple(factors)

    async def _build_decision_computed_context(
        self,
        *,
        tenant_id: UUID,
        policy_version: int,
        gate_input: GateInput,
        now: datetime,
        is_production: bool,
    ) -> DecisionComputedContext:
        context_version = "enforcement_computed_context_v1"
        now_utc = _as_utc(now)
        today = now_utc.date()
        month_start = today.replace(day=1)
        month_total_days = self._month_total_days(today)
        month_end = today.replace(day=month_total_days)
        month_elapsed_days = max(1, (today - month_start).days + 1)

        lookback_start = today - timedelta(days=35)
        data_source_mode = "final"
        latest_cost_date: date | None = None
        mtd_spend_usd = Decimal("0.0000")
        observed_cost_days = 0
        burn_rate_daily_usd = Decimal("0.0000")
        forecast_eom_usd = Decimal("0.0000")
        anomaly_signal = False
        anomaly_kind: str | None = None
        anomaly_delta_usd = Decimal("0.0000")
        anomaly_percent: Decimal | None = None

        try:
            daily_totals = await self._load_daily_cost_totals(
                tenant_id=tenant_id,
                start_date=lookback_start,
                end_date=today,
                final_only=True,
            )
            if not daily_totals:
                daily_totals = await self._load_daily_cost_totals(
                    tenant_id=tenant_id,
                    start_date=lookback_start,
                    end_date=today,
                    final_only=False,
                )
                data_source_mode = "all_status" if daily_totals else "none"

            if daily_totals:
                latest_cost_date = max(daily_totals.keys())
                mtd_spend_usd = _quantize(
                    sum(
                        (
                            amount
                            for day, amount in daily_totals.items()
                            if month_start <= day <= today
                        ),
                        Decimal("0.0000"),
                    ),
                    "0.0001",
                )
                observed_cost_days = sum(
                    1
                    for day, amount in daily_totals.items()
                    if month_start <= day <= today and amount > Decimal("0.0000")
                )
                burn_rate_daily_usd = _quantize(
                    mtd_spend_usd / Decimal(month_elapsed_days),
                    "0.0001",
                )
                forecast_eom_usd = _quantize(
                    burn_rate_daily_usd * Decimal(month_total_days),
                    "0.0001",
                )

                today_total = _quantize(
                    _to_decimal(daily_totals.get(today, Decimal("0.0000"))),
                    "0.0001",
                )
                baseline_days = [today - timedelta(days=offset) for offset in range(1, 8)]
                baseline_total = _quantize(
                    sum(
                        (
                            _to_decimal(daily_totals.get(day, Decimal("0.0000")))
                            for day in baseline_days
                        ),
                        Decimal("0.0000"),
                    ),
                    "0.0001",
                )
                baseline_avg = _quantize(
                    baseline_total / Decimal("7"),
                    "0.0001",
                )

                anomaly_delta_usd = _quantize(today_total - baseline_avg, "0.0001")
                if baseline_avg > Decimal("0.0000"):
                    anomaly_percent = _quantize(
                        (anomaly_delta_usd / baseline_avg) * Decimal("100"),
                        "0.01",
                    )

                if baseline_avg <= Decimal("0.0000") and today_total >= Decimal("100.0000"):
                    anomaly_signal = True
                    anomaly_kind = "new_spend"
                elif (
                    anomaly_delta_usd >= Decimal("100.0000")
                    and anomaly_percent is not None
                    and anomaly_percent >= Decimal("30.00")
                ):
                    anomaly_signal = True
                    anomaly_kind = "spike"
        except Exception as exc:
            data_source_mode = "unavailable"
            logger.warning(
                "enforcement_computed_context_unavailable",
                tenant_id=str(tenant_id),
                error_type=type(exc).__name__,
            )

        risk_class, risk_score, risk_factors = self._derive_risk_assessment(
            gate_input=gate_input,
            is_production=is_production,
            anomaly_signal=anomaly_signal,
        )

        return DecisionComputedContext(
            context_version=context_version,
            generated_at=now_utc,
            policy_version=int(policy_version),
            month_start=month_start,
            month_end=month_end,
            month_elapsed_days=month_elapsed_days,
            month_total_days=month_total_days,
            observed_cost_days=observed_cost_days,
            latest_cost_date=latest_cost_date,
            mtd_spend_usd=mtd_spend_usd,
            burn_rate_daily_usd=burn_rate_daily_usd,
            forecast_eom_usd=forecast_eom_usd,
            anomaly_signal=anomaly_signal,
            anomaly_kind=anomaly_kind,
            anomaly_delta_usd=anomaly_delta_usd,
            anomaly_percent=anomaly_percent,
            data_source_mode=data_source_mode,
            risk_class=risk_class,
            risk_score=risk_score,
            risk_factors=risk_factors,
        )

    async def list_budgets(self, tenant_id: UUID) -> list[EnforcementBudgetAllocation]:
        rows = await self.db.execute(
            select(EnforcementBudgetAllocation)
            .where(EnforcementBudgetAllocation.tenant_id == tenant_id)
            .order_by(EnforcementBudgetAllocation.scope_key.asc())
        )
        return list(rows.scalars().all())

    async def upsert_budget(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        scope_key: str,
        monthly_limit_usd: Decimal,
        active: bool,
    ) -> EnforcementBudgetAllocation:
        normalized_scope = str(scope_key or "default").strip().lower() or "default"
        if monthly_limit_usd < Decimal("0"):
            raise HTTPException(
                status_code=422,
                detail="monthly_limit_usd must be >= 0",
            )

        budget = (
            await self.db.execute(
                select(EnforcementBudgetAllocation).where(
                    EnforcementBudgetAllocation.tenant_id == tenant_id,
                    EnforcementBudgetAllocation.scope_key == normalized_scope,
                )
            )
        ).scalar_one_or_none()

        if budget is None:
            budget = EnforcementBudgetAllocation(
                tenant_id=tenant_id,
                scope_key=normalized_scope,
                monthly_limit_usd=_quantize(monthly_limit_usd, "0.0001"),
                active=bool(active),
                created_by_user_id=actor_id,
            )
            self.db.add(budget)
        else:
            budget.monthly_limit_usd = _quantize(monthly_limit_usd, "0.0001")
            budget.active = bool(active)

        await self.db.commit()
        await self.db.refresh(budget)
        return budget

    async def list_credits(self, tenant_id: UUID) -> list[EnforcementCreditGrant]:
        rows = await self.db.execute(
            select(EnforcementCreditGrant)
            .where(EnforcementCreditGrant.tenant_id == tenant_id)
            .order_by(EnforcementCreditGrant.created_at.desc())
        )
        return list(rows.scalars().all())

    async def create_credit_grant(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        pool_type: EnforcementCreditPoolType = EnforcementCreditPoolType.RESERVED,
        scope_key: str,
        total_amount_usd: Decimal,
        expires_at: datetime | None,
        reason: str | None,
    ) -> EnforcementCreditGrant:
        normalized_scope = str(scope_key or "default").strip().lower() or "default"
        amount = _quantize(total_amount_usd, "0.0001")
        if amount <= Decimal("0"):
            raise HTTPException(
                status_code=422,
                detail="total_amount_usd must be > 0",
            )

        normalized_expires_at = _as_utc(expires_at) if expires_at is not None else None
        if normalized_expires_at is not None and normalized_expires_at <= _utcnow():
            raise HTTPException(
                status_code=422,
                detail="expires_at must be in the future",
            )

        credit = EnforcementCreditGrant(
            tenant_id=tenant_id,
            pool_type=pool_type,
            scope_key=normalized_scope,
            total_amount_usd=amount,
            remaining_amount_usd=amount,
            expires_at=normalized_expires_at,
            reason=(str(reason).strip() if reason else None),
            active=True,
            created_by_user_id=actor_id,
        )
        self.db.add(credit)
        await self.db.commit()
        await self.db.refresh(credit)
        return credit

    def _default_approval_routing_trace(
        self,
        *,
        policy: EnforcementPolicy,
        decision: EnforcementDecision,
    ) -> dict[str, Any]:
        environment = _normalize_environment(decision.environment)
        is_prod = _is_production_environment(environment)
        return {
            "rule_id": f"default-{environment}",
            "matched_rule": "default",
            "required_permission": _default_required_permission_for_environment(environment),
            "allowed_reviewer_roles": list(_DEFAULT_ALLOWED_REVIEWER_ROLES),
            "require_requester_reviewer_separation": bool(
                policy.enforce_prod_requester_reviewer_separation
                if is_prod
                else policy.enforce_nonprod_requester_reviewer_separation
            ),
            "routing_conditions": {
                "environment": environment,
            },
        }

    def _extract_decision_risk_level(self, decision: EnforcementDecision) -> str | None:
        payload = decision.request_payload if isinstance(decision.request_payload, dict) else {}
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            return None

        for key in ("risk_level", "risk", "criticality"):
            value = metadata.get(key)
            normalized = str(value or "").strip().lower()
            if normalized:
                return normalized
        return None

    def _resolve_approval_routing_trace(
        self,
        *,
        policy: EnforcementPolicy,
        decision: EnforcementDecision,
    ) -> dict[str, Any]:
        default_trace = self._default_approval_routing_trace(policy=policy, decision=decision)
        rules = (
            list(policy.approval_routing_rules)
            if isinstance(policy.approval_routing_rules, list)
            else []
        )
        if not rules:
            return default_trace

        environment = _normalize_environment(decision.environment)
        action = str(decision.action or "").strip().lower()
        monthly_delta = _quantize(_to_decimal(decision.estimated_monthly_delta_usd), "0.0001")
        risk_level = self._extract_decision_risk_level(decision)

        for index, raw_rule in enumerate(rules, start=1):
            if not isinstance(raw_rule, Mapping):
                continue
            if not bool(raw_rule.get("enabled", True)):
                continue

            environments = _normalize_string_list(
                raw_rule.get("environments"),
                normalizer=_normalize_environment,
            )
            if environments and environment not in environments:
                continue

            action_prefixes = _normalize_string_list(raw_rule.get("action_prefixes"))
            if action_prefixes and not any(action.startswith(prefix) for prefix in action_prefixes):
                continue

            min_monthly_delta_raw = raw_rule.get("min_monthly_delta_usd")
            max_monthly_delta_raw = raw_rule.get("max_monthly_delta_usd")
            if min_monthly_delta_raw is not None:
                min_monthly_delta = _quantize(_to_decimal(min_monthly_delta_raw), "0.0001")
                if monthly_delta < min_monthly_delta:
                    continue
            if max_monthly_delta_raw is not None:
                max_monthly_delta = _quantize(_to_decimal(max_monthly_delta_raw), "0.0001")
                if monthly_delta > max_monthly_delta:
                    continue

            risk_levels = _normalize_string_list(raw_rule.get("risk_levels"))
            if risk_levels:
                if risk_level is None or risk_level not in risk_levels:
                    continue

            required_permission = normalize_approval_permission(raw_rule.get("required_permission"))
            if required_permission is None:
                required_permission = str(default_trace["required_permission"])

            separation_override = raw_rule.get("require_requester_reviewer_separation")
            separation = (
                bool(separation_override)
                if isinstance(separation_override, bool)
                else bool(default_trace["require_requester_reviewer_separation"])
            )

            rule_id = str(raw_rule.get("rule_id") or "").strip() or f"rule-{index}"
            allowed_reviewer_roles = _normalize_allowed_reviewer_roles(
                raw_rule.get("allowed_reviewer_roles")
            )

            return {
                "rule_id": rule_id[:64],
                "matched_rule": "policy_rule",
                "required_permission": required_permission,
                "allowed_reviewer_roles": allowed_reviewer_roles,
                "require_requester_reviewer_separation": separation,
                "routing_conditions": {
                    "environment": environment,
                    "action_prefixes": action_prefixes,
                    "min_monthly_delta_usd": (
                        str(
                            _quantize(
                                _to_decimal(min_monthly_delta_raw),
                                "0.0001",
                            )
                        )
                        if min_monthly_delta_raw is not None
                        else None
                    ),
                    "max_monthly_delta_usd": (
                        str(
                            _quantize(
                                _to_decimal(max_monthly_delta_raw),
                                "0.0001",
                            )
                        )
                        if max_monthly_delta_raw is not None
                        else None
                    ),
                    "risk_levels": risk_levels,
                    "risk_level": risk_level,
                },
            }

        return default_trace

    def _routing_trace_or_default(
        self,
        *,
        policy: EnforcementPolicy,
        decision: EnforcementDecision,
        approval: EnforcementApprovalRequest,
    ) -> dict[str, Any]:
        trace = approval.routing_trace if isinstance(approval.routing_trace, dict) else {}
        required_permission = normalize_approval_permission(trace.get("required_permission"))
        allowed_reviewer_roles = _normalize_allowed_reviewer_roles(
            trace.get("allowed_reviewer_roles")
            if isinstance(trace.get("allowed_reviewer_roles"), list)
            else None
        )
        has_rule_id = bool(str(trace.get("rule_id") or "").strip())
        has_separation_flag = isinstance(
            trace.get("require_requester_reviewer_separation"), bool
        )
        if required_permission is None or not has_rule_id or not has_separation_flag:
            return self._resolve_approval_routing_trace(policy=policy, decision=decision)

        return {
            **trace,
            "required_permission": required_permission,
            "allowed_reviewer_roles": allowed_reviewer_roles,
            "rule_id": str(trace.get("rule_id")).strip()[:64],
            "require_requester_reviewer_separation": bool(
                trace.get("require_requester_reviewer_separation")
            ),
        }

    async def _enforce_reviewer_authority(
        self,
        *,
        tenant_id: UUID,
        policy: EnforcementPolicy,
        approval: EnforcementApprovalRequest,
        decision: EnforcementDecision,
        reviewer: CurrentUser,
        enforce_requester_separation: bool,
    ) -> dict[str, Any]:
        routing_trace = self._routing_trace_or_default(
            policy=policy,
            decision=decision,
            approval=approval,
        )
        if routing_trace != (approval.routing_trace or {}):
            approval.routing_rule_id = str(routing_trace.get("rule_id") or "").strip() or None
            approval.routing_trace = routing_trace

        reviewer_role = _normalize_role_value(reviewer.role)
        allowed_reviewer_roles = _normalize_allowed_reviewer_roles(
            routing_trace.get("allowed_reviewer_roles")
            if isinstance(routing_trace.get("allowed_reviewer_roles"), list)
            else None
        )
        if reviewer_role not in allowed_reviewer_roles:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Reviewer role '{reviewer_role}' is not allowed for "
                    f"routing rule '{routing_trace.get('rule_id')}'"
                ),
            )

        required_permission = normalize_approval_permission(
            routing_trace.get("required_permission")
        )
        if required_permission is None:
            raise HTTPException(
                status_code=409,
                detail="Approval routing trace is missing required_permission",
            )

        has_permission = await user_has_approval_permission(
            self.db,
            reviewer,
            required_permission,
        )
        if not has_permission:
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient approval permission: {required_permission}",
            )

        requires_separation = bool(
            routing_trace.get("require_requester_reviewer_separation")
        )
        requested_by_user_id = str(approval.requested_by_user_id or "").strip().lower()
        reviewer_user_id = str(reviewer.id).strip().lower()
        if (
            enforce_requester_separation
            and requires_separation
            and requested_by_user_id
            and requested_by_user_id == reviewer_user_id
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    "Requester/reviewer separation is enforced for this approval route"
                ),
            )

        return routing_trace

    async def evaluate_gate(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        source: EnforcementSource,
        gate_input: GateInput,
    ) -> GateEvaluationResult:
        policy = await self.get_or_create_policy(tenant_id)
        normalized_env = _normalize_environment(gate_input.environment)
        mode, mode_scope = self._resolve_policy_mode(
            policy=policy,
            source=source,
            environment=normalized_env,
        )
        ttl_seconds = max(60, min(int(policy.default_ttl_seconds), 86400))

        fingerprint = _stable_fingerprint(source, gate_input)
        raw_idempotency_key = (gate_input.idempotency_key or fingerprint).strip()
        idempotency_key = raw_idempotency_key[:128] if raw_idempotency_key else fingerprint

        existing = await self._get_decision_by_idempotency(
            tenant_id=tenant_id,
            source=source,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            existing_approval = await self._get_approval_by_decision(existing.id)
            return GateEvaluationResult(
                decision=existing,
                approval=existing_approval,
                approval_token=None,
                ttl_seconds=ttl_seconds,
            )

        await self._acquire_gate_evaluation_lock(policy=policy, source=source)

        # Re-check idempotency after lock acquisition to avoid duplicate work when
        # another worker commits while this request waits on the serialization lock.
        existing = await self._get_decision_by_idempotency(
            tenant_id=tenant_id,
            source=source,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            existing_approval = await self._get_approval_by_decision(existing.id)
            return GateEvaluationResult(
                decision=existing,
                approval=existing_approval,
                approval_token=None,
                ttl_seconds=ttl_seconds,
            )

        now = _utcnow()
        month_start, month_end = _month_bounds(now)
        monthly_delta = _quantize(gate_input.estimated_monthly_delta_usd, "0.0001")
        hourly_delta = _quantize(gate_input.estimated_hourly_delta_usd, "0.000001")
        reasons: list[str] = []

        reserved_alloc_total, reserved_credit_total = await self._get_reserved_totals(
            tenant_id=tenant_id,
            month_start=month_start,
            month_end=month_end,
        )
        reserved_total_monthly = _quantize(
            _to_decimal(reserved_alloc_total) + _to_decimal(reserved_credit_total),
            "0.0001",
        )
        tenant_tier = await self._resolve_tenant_tier(tenant_id)
        plan_ceiling = await self._resolve_plan_monthly_ceiling_usd(
            policy=policy,
            tenant_tier=tenant_tier,
        )
        enterprise_ceiling = await self._resolve_enterprise_monthly_ceiling_usd(
            policy=policy,
            tenant_tier=tenant_tier,
        )
        plan_headroom = (
            _quantize(
                max(Decimal("0.0000"), _to_decimal(plan_ceiling) - reserved_total_monthly),
                "0.0001",
            )
            if plan_ceiling is not None
            else None
        )
        enterprise_headroom = (
            _quantize(
                max(Decimal("0.0000"), _to_decimal(enterprise_ceiling) - reserved_total_monthly),
                "0.0001",
            )
            if enterprise_ceiling is not None
            else None
        )

        budget = await self._get_effective_budget(
            tenant_id=tenant_id,
            scope_key=gate_input.project_id,
        )
        reserved_credit_headroom, emergency_credit_headroom = await self._get_credit_headrooms(
            tenant_id=tenant_id,
            scope_key=gate_input.project_id,
            now=now,
        )
        credits_available = _quantize(
            reserved_credit_headroom + emergency_credit_headroom,
            "0.0001",
        )

        if budget is None:
            allocation_headroom: Decimal | None = None
            reasons.append("no_budget_configured")
        else:
            allocation_headroom = max(
                Decimal("0"),
                _to_decimal(budget.monthly_limit_usd) - reserved_alloc_total,
            )

        is_prod = _is_production_environment(normalized_env)
        computed_context = await self._build_decision_computed_context(
            tenant_id=tenant_id,
            policy_version=int(policy.policy_version),
            gate_input=gate_input,
            now=now,
            is_production=is_prod,
        )
        approval_required = (
            policy.require_approval_for_prod if is_prod else policy.require_approval_for_nonprod
        )
        if monthly_delta <= _to_decimal(policy.auto_approve_below_monthly_usd):
            approval_required = False

        reserve_allocation = Decimal("0")
        reserve_reserved_credit = Decimal("0")
        reserve_emergency_credit = Decimal("0")
        reserve_credit = Decimal("0")
        reservation_active = False
        entitlement_result: EntitlementWaterfallResult | None = None

        decision = EnforcementDecisionType.ALLOW
        computed_context_unavailable = (
            computed_context.data_source_mode == "unavailable"
            and monthly_delta > Decimal("0.0000")
        )
        if computed_context_unavailable:
            reasons.append("computed_context_unavailable")
            reasons.append(
                self._mode_violation_reason_suffix(mode, subject="cost_context")
            )
            decision = self._mode_violation_decision(mode)
        else:
            hard_deny_threshold = _to_decimal(policy.hard_deny_above_monthly_usd)
            if monthly_delta > hard_deny_threshold:
                reasons.append("hard_deny_threshold_exceeded")
                decision = self._mode_violation_decision(mode)
                if mode == EnforcementMode.SOFT:
                    reasons.append("soft_mode_escalation")
                if mode == EnforcementMode.SHADOW:
                    reasons.append("shadow_mode_override")
            else:
                entitlement_result = self._evaluate_entitlement_waterfall(
                    mode=mode,
                    monthly_delta=monthly_delta,
                    plan_headroom=plan_headroom,
                    allocation_headroom=allocation_headroom,
                    reserved_credit_headroom=reserved_credit_headroom,
                    emergency_credit_headroom=emergency_credit_headroom,
                    enterprise_headroom=enterprise_headroom,
                )
                decision = entitlement_result.decision
                reserve_allocation = entitlement_result.reserve_allocation_usd
                reserve_reserved_credit = entitlement_result.reserve_reserved_credit_usd
                reserve_emergency_credit = entitlement_result.reserve_emergency_credit_usd
                reserve_credit = entitlement_result.reserve_credit_usd

                if entitlement_result.reason_code is not None:
                    reasons.append(entitlement_result.reason_code)
                    reason_subject = {
                        "budget_exceeded": "budget",
                        "plan_limit_exceeded": "plan_limit",
                        "enterprise_ceiling_exceeded": "enterprise_ceiling",
                    }.get(entitlement_result.reason_code)
                    if reason_subject and mode in {
                        EnforcementMode.SHADOW,
                        EnforcementMode.SOFT,
                    }:
                        reasons.append(
                            self._mode_violation_reason_suffix(
                                mode,
                                subject=reason_subject,
                            )
                        )
                if reserve_credit > Decimal("0.0000"):
                    reasons.append("credit_waterfall_used")
                    if reserve_reserved_credit > Decimal("0.0000"):
                        reasons.append("reserved_credit_waterfall_used")
                    if reserve_emergency_credit > Decimal("0.0000"):
                        reasons.append("emergency_credit_waterfall_used")

        if decision in {
            EnforcementDecisionType.ALLOW,
            EnforcementDecisionType.ALLOW_WITH_CREDITS,
        } and approval_required:
            if mode == EnforcementMode.SHADOW:
                reasons.append("shadow_mode_approval_override")
            else:
                decision = EnforcementDecisionType.REQUIRE_APPROVAL
                reasons.append("approval_required")

        if gate_input.dry_run:
            reasons.append("dry_run")
            reserve_allocation = Decimal("0")
            reserve_reserved_credit = Decimal("0")
            reserve_emergency_credit = Decimal("0")
            reserve_credit = Decimal("0")
            reservation_active = False
        elif decision != EnforcementDecisionType.DENY and mode != EnforcementMode.SHADOW:
            reservation_active = (reserve_allocation + reserve_credit) > Decimal("0")

        metadata_payload = dict(gate_input.metadata)
        if "risk_level" not in metadata_payload:
            metadata_payload["risk_level"] = computed_context.risk_class
        metadata_payload["computed_risk_class"] = computed_context.risk_class
        metadata_payload["computed_risk_score"] = computed_context.risk_score

        decision_row = EnforcementDecision(
            tenant_id=tenant_id,
            source=source,
            environment=normalized_env,
            project_id=gate_input.project_id,
            action=gate_input.action,
            resource_reference=gate_input.resource_reference,
            decision=decision,
            reason_codes=_unique_reason_codes(reasons),
            policy_version=int(policy.policy_version),
            policy_document_schema_version=_normalize_policy_document_schema_version(
                policy.policy_document_schema_version
            ),
            policy_document_sha256=_normalize_policy_document_sha256(
                policy.policy_document_sha256
            ),
            request_fingerprint=fingerprint,
            idempotency_key=idempotency_key,
            request_payload={
                "project_id": gate_input.project_id,
                "environment": normalized_env,
                "action": gate_input.action,
                "resource_reference": gate_input.resource_reference,
                "estimated_monthly_delta_usd": str(monthly_delta),
                "estimated_hourly_delta_usd": str(hourly_delta),
                "metadata": metadata_payload,
                "dry_run": gate_input.dry_run,
            },
            response_payload={
                "mode": mode.value,
                "mode_scope": mode_scope,
                "is_production": is_prod,
                "allocation_headroom_usd": (
                    str(allocation_headroom) if allocation_headroom is not None else None
                ),
                "credits_headroom_usd": str(credits_available),
                "reserved_credits_headroom_usd": str(reserved_credit_headroom),
                "emergency_credits_headroom_usd": str(emergency_credit_headroom),
                "plan_monthly_ceiling_usd": (
                    str(_quantize(_to_decimal(plan_ceiling), "0.0001"))
                    if plan_ceiling is not None
                    else None
                ),
                "plan_headroom_usd": (
                    str(_quantize(_to_decimal(plan_headroom), "0.0001"))
                    if plan_headroom is not None
                    else None
                ),
                "enterprise_monthly_ceiling_usd": (
                    str(_quantize(_to_decimal(enterprise_ceiling), "0.0001"))
                    if enterprise_ceiling is not None
                    else None
                ),
                "enterprise_headroom_usd": (
                    str(_quantize(_to_decimal(enterprise_headroom), "0.0001"))
                    if enterprise_headroom is not None
                    else None
                ),
                "tenant_tier": tenant_tier.value,
                "entitlement_reason_code": (
                    entitlement_result.reason_code if entitlement_result is not None else None
                ),
                "entitlement_waterfall": (
                    entitlement_result.stage_details if entitlement_result is not None else None
                ),
                "reserved_credit_split_usd": {
                    "reserved": str(reserve_reserved_credit),
                    "emergency": str(reserve_emergency_credit),
                },
                "computed_context": computed_context.to_payload(),
            },
            estimated_monthly_delta_usd=monthly_delta,
            estimated_hourly_delta_usd=hourly_delta,
            burn_rate_daily_usd=computed_context.burn_rate_daily_usd,
            forecast_eom_usd=computed_context.forecast_eom_usd,
            risk_class=computed_context.risk_class,
            risk_score=int(computed_context.risk_score),
            anomaly_signal=bool(computed_context.anomaly_signal),
            allocation_available_usd=allocation_headroom,
            credits_available_usd=credits_available,
            reserved_allocation_usd=reserve_allocation,
            reserved_credit_usd=reserve_credit,
            reservation_active=reservation_active,
            approval_required=decision == EnforcementDecisionType.REQUIRE_APPROVAL,
            approval_token_issued=False,
            token_expires_at=None,
            created_by_user_id=actor_id,
        )
        self.db.add(decision_row)

        approval: EnforcementApprovalRequest | None = None
        try:
            # Ensure the decision id is materialized before creating approval rows.
            await self.db.flush()

            credit_allocations_payload: list[dict[str, str]] = []
            if reservation_active and reserve_credit > Decimal("0"):
                credit_allocations_payload = await self._reserve_credit_for_decision(
                    tenant_id=tenant_id,
                    decision_id=decision_row.id,
                    scope_key=gate_input.project_id,
                    reserve_reserved_credit_usd=reserve_reserved_credit,
                    reserve_emergency_credit_usd=reserve_emergency_credit,
                    now=now,
                )
                decision_row.response_payload = {
                    **(decision_row.response_payload or {}),
                    "credit_reservation_allocations": credit_allocations_payload,
                }

            if (
                decision == EnforcementDecisionType.REQUIRE_APPROVAL
                and not gate_input.dry_run
                and mode != EnforcementMode.SHADOW
            ):
                approval_routing_trace = self._resolve_approval_routing_trace(
                    policy=policy,
                    decision=decision_row,
                )
                approval = EnforcementApprovalRequest(
                    tenant_id=tenant_id,
                    decision_id=decision_row.id,
                    status=EnforcementApprovalStatus.PENDING,
                    requested_by_user_id=actor_id,
                    routing_rule_id=(
                        str(approval_routing_trace.get("rule_id") or "").strip() or None
                    ),
                    routing_trace=approval_routing_trace,
                    expires_at=now + timedelta(seconds=ttl_seconds),
                )
                self.db.add(approval)
                await self.db.flush()

            self._append_decision_ledger_entry(
                decision_row=decision_row,
                approval_row=approval,
            )
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            existing = await self._get_decision_by_idempotency(
                tenant_id=tenant_id,
                source=source,
                idempotency_key=idempotency_key,
            )
            if existing is None:
                raise
            existing_approval = await self._get_approval_by_decision(existing.id)
            return GateEvaluationResult(
                decision=existing,
                approval=existing_approval,
                approval_token=None,
                ttl_seconds=ttl_seconds,
            )

        await self.db.refresh(decision_row)
        if approval is not None:
            await self.db.refresh(approval)

        return GateEvaluationResult(
            decision=decision_row,
            approval=approval,
            approval_token=None,
            ttl_seconds=ttl_seconds,
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
        now = _utcnow()
        normalized_env = _normalize_environment(gate_input.environment)
        policy = await self.get_or_create_policy(tenant_id)
        mode, mode_scope = self._resolve_policy_mode(
            policy=policy,
            source=source,
            environment=normalized_env,
        )
        ttl_seconds = max(60, min(int(policy.default_ttl_seconds), 86400))

        fingerprint = _stable_fingerprint(source, gate_input)
        raw_idempotency_key = (gate_input.idempotency_key or fingerprint).strip()
        idempotency_key = raw_idempotency_key[:128] if raw_idempotency_key else fingerprint

        existing = await self._get_decision_by_idempotency(
            tenant_id=tenant_id,
            source=source,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            existing_approval = await self._get_approval_by_decision(existing.id)
            return GateEvaluationResult(
                decision=existing,
                approval=existing_approval,
                approval_token=None,
                ttl_seconds=ttl_seconds,
            )

        normalized_reason = str(failure_reason_code or "").strip().lower()
        if not normalized_reason:
            normalized_reason = "gate_evaluation_error"

        mode_reason = {
            EnforcementMode.SHADOW: "shadow_mode_fail_open",
            EnforcementMode.SOFT: "soft_mode_fail_safe_escalation",
            EnforcementMode.HARD: "hard_mode_fail_closed",
        }[mode]
        reasons = [normalized_reason, mode_reason]
        if gate_input.dry_run:
            reasons.append("dry_run")

        monthly_delta = _quantize(gate_input.estimated_monthly_delta_usd, "0.0001")
        hourly_delta = _quantize(gate_input.estimated_hourly_delta_usd, "0.000001")
        decision = self._mode_violation_decision(mode)
        is_prod = _is_production_environment(normalized_env)
        computed_context = await self._build_decision_computed_context(
            tenant_id=tenant_id,
            policy_version=int(policy.policy_version),
            gate_input=gate_input,
            now=now,
            is_production=is_prod,
        )

        fail_safe_details: dict[str, Any] | None = None
        if failure_metadata:
            fail_safe_details = {
                str(key): value
                for key, value in failure_metadata.items()
                if str(key).strip()
            } or None

        metadata_payload = dict(gate_input.metadata)
        if "risk_level" not in metadata_payload:
            metadata_payload["risk_level"] = computed_context.risk_class
        metadata_payload["computed_risk_class"] = computed_context.risk_class
        metadata_payload["computed_risk_score"] = computed_context.risk_score

        decision_row = EnforcementDecision(
            tenant_id=tenant_id,
            source=source,
            environment=normalized_env,
            project_id=gate_input.project_id,
            action=gate_input.action,
            resource_reference=gate_input.resource_reference,
            decision=decision,
            reason_codes=_unique_reason_codes(reasons),
            policy_version=int(policy.policy_version),
            policy_document_schema_version=_normalize_policy_document_schema_version(
                policy.policy_document_schema_version
            ),
            policy_document_sha256=_normalize_policy_document_sha256(
                policy.policy_document_sha256
            ),
            request_fingerprint=fingerprint,
            idempotency_key=idempotency_key,
            request_payload={
                "project_id": gate_input.project_id,
                "environment": normalized_env,
                "action": gate_input.action,
                "resource_reference": gate_input.resource_reference,
                "estimated_monthly_delta_usd": str(monthly_delta),
                "estimated_hourly_delta_usd": str(hourly_delta),
                "metadata": metadata_payload,
                "dry_run": gate_input.dry_run,
            },
            response_payload={
                "mode": mode.value,
                "mode_scope": mode_scope,
                "is_production": is_prod,
                "fail_safe_trigger": normalized_reason,
                "fail_safe_details": fail_safe_details,
                "computed_context": computed_context.to_payload(),
            },
            estimated_monthly_delta_usd=monthly_delta,
            estimated_hourly_delta_usd=hourly_delta,
            burn_rate_daily_usd=computed_context.burn_rate_daily_usd,
            forecast_eom_usd=computed_context.forecast_eom_usd,
            risk_class=computed_context.risk_class,
            risk_score=int(computed_context.risk_score),
            anomaly_signal=bool(computed_context.anomaly_signal),
            allocation_available_usd=None,
            credits_available_usd=None,
            reserved_allocation_usd=Decimal("0"),
            reserved_credit_usd=Decimal("0"),
            reservation_active=False,
            approval_required=decision == EnforcementDecisionType.REQUIRE_APPROVAL,
            approval_token_issued=False,
            token_expires_at=None,
            created_by_user_id=actor_id,
        )
        self.db.add(decision_row)

        approval: EnforcementApprovalRequest | None = None
        try:
            await self.db.flush()

            if (
                decision == EnforcementDecisionType.REQUIRE_APPROVAL
                and not gate_input.dry_run
                and mode != EnforcementMode.SHADOW
            ):
                approval_routing_trace = self._resolve_approval_routing_trace(
                    policy=policy,
                    decision=decision_row,
                )
                approval = EnforcementApprovalRequest(
                    tenant_id=tenant_id,
                    decision_id=decision_row.id,
                    status=EnforcementApprovalStatus.PENDING,
                    requested_by_user_id=actor_id,
                    routing_rule_id=(
                        str(approval_routing_trace.get("rule_id") or "").strip() or None
                    ),
                    routing_trace=approval_routing_trace,
                    expires_at=now + timedelta(seconds=ttl_seconds),
                )
                self.db.add(approval)
                await self.db.flush()

            self._append_decision_ledger_entry(
                decision_row=decision_row,
                approval_row=approval,
            )
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            existing = await self._get_decision_by_idempotency(
                tenant_id=tenant_id,
                source=source,
                idempotency_key=idempotency_key,
            )
            if existing is None:
                raise
            existing_approval = await self._get_approval_by_decision(existing.id)
            return GateEvaluationResult(
                decision=existing,
                approval=existing_approval,
                approval_token=None,
                ttl_seconds=ttl_seconds,
            )

        await self.db.refresh(decision_row)
        if approval is not None:
            await self.db.refresh(approval)

        return GateEvaluationResult(
            decision=decision_row,
            approval=approval,
            approval_token=None,
            ttl_seconds=ttl_seconds,
        )

    async def create_or_get_approval_request(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        decision_id: UUID,
        notes: str | None,
    ) -> EnforcementApprovalRequest:
        decision = (
            await self.db.execute(
                select(EnforcementDecision).where(
                    EnforcementDecision.id == decision_id,
                    EnforcementDecision.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()
        if decision is None:
            raise HTTPException(status_code=404, detail="Decision not found")

        if decision.decision != EnforcementDecisionType.REQUIRE_APPROVAL:
            raise HTTPException(
                status_code=409,
                detail="Approval request can only be created for REQUIRE_APPROVAL decisions",
            )

        existing = await self._get_approval_by_decision(decision_id)
        if existing is not None:
            return existing

        policy = await self.get_or_create_policy(tenant_id)
        ttl_seconds = max(60, min(int(policy.default_ttl_seconds), 86400))
        now = _utcnow()
        approval_routing_trace = self._resolve_approval_routing_trace(
            policy=policy,
            decision=decision,
        )

        approval = EnforcementApprovalRequest(
            tenant_id=tenant_id,
            decision_id=decision_id,
            status=EnforcementApprovalStatus.PENDING,
            requested_by_user_id=actor_id,
            review_notes=(str(notes).strip() if notes else None),
            routing_rule_id=(
                str(approval_routing_trace.get("rule_id") or "").strip() or None
            ),
            routing_trace=approval_routing_trace,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        self.db.add(approval)
        await self.db.flush()
        self._append_decision_ledger_entry(
            decision_row=decision,
            approval_row=approval,
        )
        await self.db.commit()
        await self.db.refresh(approval)
        return approval

    async def list_pending_approvals(
        self,
        *,
        tenant_id: UUID,
        reviewer: CurrentUser | None,
        limit: int,
    ) -> list[tuple[EnforcementApprovalRequest, EnforcementDecision]]:
        now = _utcnow()
        rows = await self.db.execute(
            select(EnforcementApprovalRequest, EnforcementDecision)
            .join(
                EnforcementDecision,
                EnforcementDecision.id == EnforcementApprovalRequest.decision_id,
            )
            .where(EnforcementApprovalRequest.tenant_id == tenant_id)
            .where(EnforcementApprovalRequest.status == EnforcementApprovalStatus.PENDING)
            .where(EnforcementApprovalRequest.expires_at >= now)
            .order_by(EnforcementApprovalRequest.created_at.asc())
            .limit(max(1, min(limit, 200)))
        )
        pending = [(row[0], row[1]) for row in rows.all()]
        if reviewer is None:
            return pending

        policy = await self.get_or_create_policy(tenant_id)
        allowed: list[tuple[EnforcementApprovalRequest, EnforcementDecision]] = []
        for approval, decision in pending:
            try:
                await self._enforce_reviewer_authority(
                    tenant_id=tenant_id,
                    policy=policy,
                    approval=approval,
                    decision=decision,
                    reviewer=reviewer,
                    enforce_requester_separation=False,
                )
            except HTTPException:
                continue
            allowed.append((approval, decision))
        return allowed

    async def approve_request(
        self,
        *,
        tenant_id: UUID,
        approval_id: UUID,
        reviewer: CurrentUser,
        notes: str | None,
    ) -> tuple[EnforcementApprovalRequest, EnforcementDecision, str, datetime]:
        approval, decision = await self._load_approval_with_decision(
            tenant_id=tenant_id,
            approval_id=approval_id,
        )
        self._assert_pending(approval)

        now = _utcnow()
        approval_expires_at = _as_utc(approval.expires_at)
        if approval_expires_at <= now:
            approval.status = EnforcementApprovalStatus.EXPIRED
            approval.updated_at = now
            credit_settlement = await self._settle_credit_reservations_for_decision(
                tenant_id=tenant_id,
                decision=decision,
                consumed_credit_usd=Decimal("0"),
                now=now,
            )
            decision.reservation_active = False
            decision.reserved_allocation_usd = Decimal("0")
            decision.reserved_credit_usd = Decimal("0")
            decision.response_payload = {
                **(decision.response_payload or {}),
                "approval_expired_at": now.isoformat(),
                "credit_settlement": credit_settlement,
            }
            self._append_decision_ledger_entry(
                decision_row=decision,
                approval_row=approval,
            )
            await self.db.commit()
            raise HTTPException(status_code=409, detail="Approval request has expired")

        policy = await self.get_or_create_policy(tenant_id)
        routing_trace = await self._enforce_reviewer_authority(
            tenant_id=tenant_id,
            policy=policy,
            approval=approval,
            decision=decision,
            reviewer=reviewer,
            enforce_requester_separation=True,
        )
        ttl_seconds = max(60, min(int(policy.default_ttl_seconds), 86400))
        token_expires_at = now + timedelta(seconds=ttl_seconds)
        approval_token = self._build_approval_token(
            decision=decision,
            approval=approval,
            expires_at=token_expires_at,
        )

        approval.status = EnforcementApprovalStatus.APPROVED
        approval.reviewed_by_user_id = reviewer.id
        approval.review_notes = (str(notes).strip() if notes else None)
        approval.approved_at = now
        approval.updated_at = now
        approval.approval_token_hash = hashlib.sha256(
            approval_token.encode("utf-8")
        ).hexdigest()
        approval.approval_token_expires_at = token_expires_at

        decision.approval_token_issued = True
        decision.token_expires_at = token_expires_at
        decision.response_payload = {
            **(decision.response_payload or {}),
            "approval_id": str(approval.id),
            "approval_routing_rule_id": str(routing_trace.get("rule_id") or ""),
            "approval_routing_trace": routing_trace,
            "approved_by_user_id": str(reviewer.id),
            "approved_at": now.isoformat(),
        }
        self._append_decision_ledger_entry(
            decision_row=decision,
            approval_row=approval,
        )

        await self.db.commit()
        await self.db.refresh(approval)
        await self.db.refresh(decision)

        return approval, decision, approval_token, token_expires_at

    async def deny_request(
        self,
        *,
        tenant_id: UUID,
        approval_id: UUID,
        reviewer: CurrentUser,
        notes: str | None,
    ) -> tuple[EnforcementApprovalRequest, EnforcementDecision]:
        approval, decision = await self._load_approval_with_decision(
            tenant_id=tenant_id,
            approval_id=approval_id,
        )
        self._assert_pending(approval)
        policy = await self.get_or_create_policy(tenant_id)
        routing_trace = await self._enforce_reviewer_authority(
            tenant_id=tenant_id,
            policy=policy,
            approval=approval,
            decision=decision,
            reviewer=reviewer,
            enforce_requester_separation=True,
        )

        now = _utcnow()
        approval.status = EnforcementApprovalStatus.DENIED
        approval.reviewed_by_user_id = reviewer.id
        approval.review_notes = (str(notes).strip() if notes else None)
        approval.denied_at = now
        approval.updated_at = now

        # Release reservation after denial.
        credit_settlement = await self._settle_credit_reservations_for_decision(
            tenant_id=tenant_id,
            decision=decision,
            consumed_credit_usd=Decimal("0"),
            now=now,
        )
        decision.reservation_active = False
        decision.reserved_allocation_usd = Decimal("0")
        decision.reserved_credit_usd = Decimal("0")
        decision.response_payload = {
            **(decision.response_payload or {}),
            "approval_id": str(approval.id),
            "approval_routing_rule_id": str(routing_trace.get("rule_id") or ""),
            "approval_routing_trace": routing_trace,
            "denied_by_user_id": str(reviewer.id),
            "denied_at": now.isoformat(),
            "credit_settlement": credit_settlement,
        }
        self._append_decision_ledger_entry(
            decision_row=decision,
            approval_row=approval,
        )

        await self.db.commit()
        await self.db.refresh(approval)
        await self.db.refresh(decision)

        return approval, decision

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
        def _token_reject(*, event: str, status_code: int, detail: str) -> None:
            ENFORCEMENT_APPROVAL_TOKEN_EVENTS_TOTAL.labels(event=event).inc()
            raise HTTPException(status_code=status_code, detail=detail)

        normalized_token = str(approval_token or "").strip()
        if not normalized_token:
            _token_reject(
                event="token_missing",
                status_code=422,
                detail="approval_token is required",
            )

        token_payload = self._decode_approval_token(normalized_token)
        token_context = self._extract_token_context(token_payload)
        if token_context.tenant_id != tenant_id:
            _token_reject(
                event="tenant_mismatch",
                status_code=403,
                detail="Approval token tenant mismatch",
            )

        approval, decision = await self._load_approval_with_decision(
            tenant_id=tenant_id,
            approval_id=token_context.approval_id,
        )
        if decision.id != token_context.decision_id:
            _token_reject(
                event="decision_binding_mismatch",
                status_code=409,
                detail="Approval token decision binding mismatch",
            )
        if approval.status != EnforcementApprovalStatus.APPROVED:
            _token_reject(
                event="status_not_active",
                status_code=409,
                detail=f"Approval token is not active ({approval.status.value})",
            )

        computed_hash = hashlib.sha256(normalized_token.encode("utf-8")).hexdigest()
        if not approval.approval_token_hash or approval.approval_token_hash != computed_hash:
            _token_reject(
                event="token_hash_mismatch",
                status_code=409,
                detail="Approval token mismatch",
            )

        now = _utcnow()
        effective_expiry = _as_utc(
            approval.approval_token_expires_at
            or decision.token_expires_at
            or token_context.expires_at
        )
        if effective_expiry <= now:
            _token_reject(
                event="token_expired",
                status_code=409,
                detail="Approval token has expired",
            )

        if token_context.source != decision.source:
            _token_reject(
                event="source_mismatch",
                status_code=409,
                detail="Approval token source mismatch",
            )
        if token_context.project_id != decision.project_id:
            _token_reject(
                event="project_binding_mismatch",
                status_code=409,
                detail="Approval token project binding mismatch",
            )
        if _normalize_environment(token_context.environment) != _normalize_environment(
            decision.environment
        ):
            _token_reject(
                event="environment_mismatch",
                status_code=409,
                detail="Approval token environment mismatch",
            )
        if token_context.request_fingerprint != decision.request_fingerprint:
            _token_reject(
                event="fingerprint_mismatch",
                status_code=409,
                detail="Approval token fingerprint mismatch",
            )
        if token_context.resource_reference != decision.resource_reference:
            _token_reject(
                event="resource_binding_mismatch",
                status_code=409,
                detail="Approval token resource binding mismatch",
            )
        if _quantize(token_context.max_monthly_delta_usd, "0.0001") != _quantize(
            _to_decimal(decision.estimated_monthly_delta_usd),
            "0.0001",
        ):
            _token_reject(
                event="cost_binding_mismatch",
                status_code=409,
                detail="Approval token cost binding mismatch",
            )
        if _quantize(token_context.max_hourly_delta_usd, "0.000001") != _quantize(
            _to_decimal(decision.estimated_hourly_delta_usd),
            "0.000001",
        ):
            _token_reject(
                event="cost_binding_mismatch",
                status_code=409,
                detail="Approval token cost binding mismatch",
            )

        if expected_source is not None and expected_source != decision.source:
            _token_reject(
                event="expected_source_mismatch",
                status_code=409,
                detail="Expected source mismatch",
            )
        if expected_project_id is not None and str(expected_project_id).strip() != str(
            decision.project_id
        ).strip():
            _token_reject(
                event="expected_project_mismatch",
                status_code=409,
                detail="Expected project mismatch",
            )
        if expected_environment is not None and _normalize_environment(
            expected_environment
        ) != _normalize_environment(decision.environment):
            _token_reject(
                event="expected_environment_mismatch",
                status_code=409,
                detail="Expected environment mismatch",
            )
        if expected_request_fingerprint is not None and str(
            expected_request_fingerprint
        ).strip() != decision.request_fingerprint:
            _token_reject(
                event="expected_fingerprint_mismatch",
                status_code=409,
                detail="Expected request fingerprint mismatch",
            )
        if expected_resource_reference is not None and str(
            expected_resource_reference
        ).strip() != decision.resource_reference:
            _token_reject(
                event="expected_resource_reference_mismatch",
                status_code=409,
                detail="Expected resource reference mismatch",
            )

        consume_result = cast(
            CursorResult[Any],
            await self.db.execute(
                update(EnforcementApprovalRequest)
                .where(EnforcementApprovalRequest.id == approval.id)
                .where(EnforcementApprovalRequest.tenant_id == tenant_id)
                .where(EnforcementApprovalRequest.approval_token_consumed_at.is_(None))
                .values(
                    approval_token_consumed_at=now,
                    updated_at=now,
                ),
            ),
        )
        consumed = int(consume_result.rowcount or 0)
        if consumed != 1:
            await self.db.rollback()
            _token_reject(
                event="replay_detected",
                status_code=409,
                detail="Approval token replay detected",
            )

        decision.response_payload = {
            **(decision.response_payload or {}),
            "approval_token_consumed_at": now.isoformat(),
            "approval_token_consumed_by_user_id": str(actor_id) if actor_id else None,
        }
        await self.db.commit()
        ENFORCEMENT_APPROVAL_TOKEN_EVENTS_TOTAL.labels(event="consumed").inc()
        await self.db.refresh(approval)
        await self.db.refresh(decision)
        return approval, decision

    async def list_active_reservations(
        self,
        *,
        tenant_id: UUID,
        limit: int,
    ) -> list[EnforcementDecision]:
        rows = await self.db.execute(
            select(EnforcementDecision)
            .where(EnforcementDecision.tenant_id == tenant_id)
            .where(EnforcementDecision.reservation_active.is_(True))
            .order_by(EnforcementDecision.created_at.asc())
            .limit(max(1, min(limit, 1000)))
        )
        return list(rows.scalars().all())

    async def list_decision_ledger(
        self,
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

        rows = await self.db.execute(stmt)
        return [DecisionLedgerRecord(entry=item) for item in rows.scalars().all()]

    async def list_reconciliation_exceptions(
        self,
        *,
        tenant_id: UUID,
        limit: int,
    ) -> list[ReservationReconciliationException]:
        bounded_limit = max(1, min(int(limit), 1000))
        scan_limit = max(100, min(bounded_limit * 10, 5000))

        rows = await self.db.execute(
            select(EnforcementDecision)
            .where(EnforcementDecision.tenant_id == tenant_id)
            .where(EnforcementDecision.reservation_active.is_(False))
            .order_by(EnforcementDecision.created_at.desc())
            .limit(scan_limit)
        )
        decisions = list(rows.scalars().all())

        exceptions: list[ReservationReconciliationException] = []
        for decision in decisions:
            response_payload = decision.response_payload or {}
            reconciliation = response_payload.get("reservation_reconciliation")
            if not isinstance(reconciliation, dict):
                continue

            drift_usd = _quantize(_to_decimal(reconciliation.get("drift_usd")), "0.0001")
            if drift_usd == Decimal("0.0000"):
                continue

            status = str(reconciliation.get("status") or "").strip().lower()
            if status not in {"overage", "savings"}:
                status = "overage" if drift_usd > Decimal("0") else "savings"

            credit_settlement_rows: list[dict[str, str]] = []
            raw_credit_settlement = reconciliation.get("credit_settlement")
            if isinstance(raw_credit_settlement, list):
                for raw_item in raw_credit_settlement:
                    if not isinstance(raw_item, dict):
                        continue
                    credit_settlement_rows.append(
                        {
                            str(k): str(v)
                            for k, v in raw_item.items()
                            if str(k).strip()
                        }
                    )

            exceptions.append(
                ReservationReconciliationException(
                    decision=decision,
                    expected_reserved_usd=_quantize(
                        _to_decimal(reconciliation.get("expected_reserved_usd")),
                        "0.0001",
                    ),
                    actual_monthly_delta_usd=_quantize(
                        _to_decimal(reconciliation.get("actual_monthly_delta_usd")),
                        "0.0001",
                    ),
                    drift_usd=drift_usd,
                    status=status,
                    reconciled_at=_parse_iso_datetime(
                        reconciliation.get("reconciled_at")
                    ),
                    notes=(
                        str(reconciliation.get("notes")).strip() or None
                        if reconciliation.get("notes") is not None
                        else None
                    ),
                    credit_settlement=credit_settlement_rows,
                )
            )
            if len(exceptions) >= bounded_limit:
                break

        return exceptions

    def _build_reservation_reconciliation_idempotent_replay(
        self,
        *,
        decision: EnforcementDecision,
        actual_monthly_delta_usd: Decimal,
        notes: str | None,
        idempotency_key: str | None,
    ) -> ReservationReconciliationResult | None:
        normalized_key = str(idempotency_key or "").strip()
        if not normalized_key:
            return None

        response_payload = decision.response_payload if isinstance(decision.response_payload, dict) else {}
        reconciliation = response_payload.get("reservation_reconciliation")
        if not isinstance(reconciliation, dict):
            return None

        stored_key = str(reconciliation.get("idempotency_key") or "").strip()
        if not stored_key or stored_key != normalized_key:
            return None

        expected_actual = _quantize(
            _to_decimal(reconciliation.get("actual_monthly_delta_usd")),
            "0.0001",
        )
        if expected_actual != actual_monthly_delta_usd:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Reservation reconciliation idempotency key replay payload mismatch "
                    "(actual_monthly_delta_usd)"
                ),
            )

        stored_notes = (
            str(reconciliation.get("notes")).strip() or None
            if reconciliation.get("notes") is not None
            else None
        )
        if notes is not None and notes != stored_notes:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Reservation reconciliation idempotency key replay payload mismatch "
                    "(notes)"
                ),
            )

        status = str(reconciliation.get("status") or "").strip().lower()
        if status not in {"matched", "overage", "savings"}:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Stored reservation reconciliation payload is invalid for "
                    "idempotent replay (status)"
                ),
            )

        drift = _quantize(_to_decimal(reconciliation.get("drift_usd")), "0.0001")
        released_reserved = _quantize(
            _to_decimal(reconciliation.get("expected_reserved_usd")),
            "0.0001",
        )
        reconciled_at = _parse_iso_datetime(reconciliation.get("reconciled_at")) or _utcnow()
        return ReservationReconciliationResult(
            decision=decision,
            released_reserved_usd=released_reserved,
            actual_monthly_delta_usd=expected_actual,
            drift_usd=drift,
            status=status,
            reconciled_at=reconciled_at,
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
        decision = (
            await self.db.execute(
                select(EnforcementDecision)
                .where(EnforcementDecision.id == decision_id)
                .where(EnforcementDecision.tenant_id == tenant_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if decision is None:
            raise HTTPException(status_code=404, detail="Decision not found")

        actual = _quantize(_to_decimal(actual_monthly_delta_usd), "0.0001")
        if actual < Decimal("0"):
            raise HTTPException(
                status_code=422,
                detail="actual_monthly_delta_usd must be >= 0",
            )
        normalized_notes = (str(notes).strip() if notes else None) or None
        normalized_idempotency_key = (str(idempotency_key).strip() if idempotency_key else None) or None

        if not decision.reservation_active:
            replay = self._build_reservation_reconciliation_idempotent_replay(
                decision=decision,
                actual_monthly_delta_usd=actual,
                notes=normalized_notes,
                idempotency_key=normalized_idempotency_key,
            )
            if replay is not None:
                ENFORCEMENT_RESERVATION_RECONCILIATIONS_TOTAL.labels(
                    trigger="manual_replay",
                    status=replay.status,
                ).inc()
                return replay
            raise HTTPException(status_code=409, detail="Reservation is not active")

        # Claim active reservation atomically to prevent double-settlement when
        # concurrent workers race and row-level locks are unavailable/degraded.
        claim = cast(
            CursorResult[Any],
            await self.db.execute(
                update(EnforcementDecision)
                .where(EnforcementDecision.id == decision_id)
                .where(EnforcementDecision.tenant_id == tenant_id)
                .where(EnforcementDecision.reservation_active.is_(True))
                .values(reservation_active=False)
            ),
        )
        claimed_rows = int(claim.rowcount or 0)
        if claimed_rows != 1:
            await self.db.rollback()
            refreshed = (
                await self.db.execute(
                    select(EnforcementDecision)
                    .where(EnforcementDecision.id == decision_id)
                    .where(EnforcementDecision.tenant_id == tenant_id)
                )
            ).scalar_one_or_none()
            if refreshed is None:
                raise HTTPException(status_code=404, detail="Decision not found")
            replay = self._build_reservation_reconciliation_idempotent_replay(
                decision=refreshed,
                actual_monthly_delta_usd=actual,
                notes=normalized_notes,
                idempotency_key=normalized_idempotency_key,
            )
            if replay is not None:
                ENFORCEMENT_RESERVATION_RECONCILIATIONS_TOTAL.labels(
                    trigger="manual_replay",
                    status=replay.status,
                ).inc()
                return replay
            raise HTTPException(status_code=409, detail="Reservation is not active")
        decision.reservation_active = False

        try:
            now = _utcnow()
            reserved_allocation = _quantize(
                _to_decimal(decision.reserved_allocation_usd),
                "0.0001",
            )
            reserved_credit = _quantize(
                _to_decimal(decision.reserved_credit_usd),
                "0.0001",
            )
            credit_needed = max(Decimal("0.0000"), actual - reserved_allocation)
            consumed_credit = _quantize(min(reserved_credit, credit_needed), "0.0001")
            released_credit = _quantize(reserved_credit - consumed_credit, "0.0001")
            credit_settlement = await self._settle_credit_reservations_for_decision(
                tenant_id=tenant_id,
                decision=decision,
                consumed_credit_usd=consumed_credit,
                now=now,
            )

            released_total = _quantize(
                reserved_allocation + reserved_credit,
                "0.0001",
            )
            drift = _quantize(actual - released_total, "0.0001")
            status = (
                "matched"
                if drift == Decimal("0.0000")
                else ("overage" if drift > Decimal("0") else "savings")
            )

            reasons = list(decision.reason_codes or [])
            reasons.append("reservation_reconciled")
            if drift != Decimal("0.0000"):
                reasons.append("reservation_reconciliation_drift")
            decision.reason_codes = _unique_reason_codes(reasons)
            decision.reserved_allocation_usd = Decimal("0")
            decision.reserved_credit_usd = Decimal("0")
            decision.response_payload = {
                **(decision.response_payload or {}),
                "reservation_reconciliation": {
                    "reconciled_at": now.isoformat(),
                    "reconciled_by_user_id": str(actor_id),
                    "expected_reserved_usd": str(released_total),
                    "actual_monthly_delta_usd": str(actual),
                    "drift_usd": str(drift),
                    "status": status,
                    "notes": normalized_notes,
                    "idempotency_key": normalized_idempotency_key,
                    "credit_reserved_usd": str(reserved_credit),
                    "credit_consumed_usd": str(consumed_credit),
                    "credit_released_usd": str(released_credit),
                    "credit_settlement": credit_settlement,
                },
            }
            approval = await self._get_approval_by_decision(decision.id)
            self._append_decision_ledger_entry(
                decision_row=decision,
                approval_row=approval,
            )

            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        ENFORCEMENT_RESERVATION_RECONCILIATIONS_TOTAL.labels(
            trigger="manual",
            status=status,
        ).inc()
        if drift > Decimal("0.0000"):
            ENFORCEMENT_RESERVATION_DRIFT_USD_TOTAL.labels(direction="overage").inc(
                float(drift)
            )
        elif drift < Decimal("0.0000"):
            ENFORCEMENT_RESERVATION_DRIFT_USD_TOTAL.labels(direction="savings").inc(
                float(abs(drift))
            )
        await self.db.refresh(decision)
        return ReservationReconciliationResult(
            decision=decision,
            released_reserved_usd=released_total,
            actual_monthly_delta_usd=actual,
            drift_usd=drift,
            status=status,
            reconciled_at=now,
        )

    async def reconcile_overdue_reservations(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        older_than_seconds: int,
        limit: int,
    ) -> OverdueReservationReconciliationResult:
        bounded_age = max(60, min(int(older_than_seconds), 604800))
        bounded_limit = max(1, min(int(limit), 1000))
        now = _utcnow()
        cutoff = now - timedelta(seconds=bounded_age)

        rows = await self.db.execute(
            select(EnforcementDecision)
            .where(EnforcementDecision.tenant_id == tenant_id)
            .where(EnforcementDecision.reservation_active.is_(True))
            .where(EnforcementDecision.created_at < cutoff)
            .order_by(EnforcementDecision.created_at.asc())
            .limit(bounded_limit)
            .with_for_update(skip_locked=True)
        )
        decisions = list(rows.scalars().all())
        if not decisions:
            return OverdueReservationReconciliationResult(
                released_count=0,
                total_released_usd=Decimal("0.0000"),
                decision_ids=[],
                older_than_seconds=bounded_age,
            )
        approval_rows = (
            await self.db.execute(
                select(EnforcementApprovalRequest).where(
                    EnforcementApprovalRequest.decision_id.in_(
                        [decision.id for decision in decisions]
                    )
                )
            )
        ).scalars().all()
        approval_by_decision: dict[UUID, EnforcementApprovalRequest] = {
            approval.decision_id: approval for approval in approval_rows
        }

        total_released = Decimal("0.0000")
        decision_ids: list[UUID] = []
        try:
            for decision in decisions:
                claim = cast(
                    CursorResult[Any],
                    await self.db.execute(
                        update(EnforcementDecision)
                        .where(EnforcementDecision.id == decision.id)
                        .where(EnforcementDecision.tenant_id == tenant_id)
                        .where(EnforcementDecision.reservation_active.is_(True))
                        .values(reservation_active=False)
                    ),
                )
                if int(claim.rowcount or 0) != 1:
                    continue
                decision.reservation_active = False

                released = _quantize(
                    _to_decimal(decision.reserved_allocation_usd)
                    + _to_decimal(decision.reserved_credit_usd),
                    "0.0001",
                )
                credit_settlement = await self._settle_credit_reservations_for_decision(
                    tenant_id=tenant_id,
                    decision=decision,
                    consumed_credit_usd=Decimal("0"),
                    now=now,
                )
                total_released = _quantize(total_released + released, "0.0001")
                decision_ids.append(decision.id)

                reasons = list(decision.reason_codes or [])
                reasons.append("reservation_auto_released_sla")
                decision.reason_codes = _unique_reason_codes(reasons)
                decision.reserved_allocation_usd = Decimal("0")
                decision.reserved_credit_usd = Decimal("0")
                decision.response_payload = {
                    **(decision.response_payload or {}),
                    "auto_reconciliation": {
                        "released_at": now.isoformat(),
                        "released_by_user_id": str(actor_id),
                        "released_reserved_usd": str(released),
                        "older_than_seconds": bounded_age,
                        "reason": "reservation_reconciliation_sla_expired",
                        "credit_settlement": credit_settlement,
                    },
                }
                self._append_decision_ledger_entry(
                    decision_row=decision,
                    approval_row=approval_by_decision.get(decision.id),
                )
        except Exception:
            await self.db.rollback()
            raise

        if not decision_ids:
            return OverdueReservationReconciliationResult(
                released_count=0,
                total_released_usd=Decimal("0.0000"),
                decision_ids=[],
                older_than_seconds=bounded_age,
            )

        await self.db.commit()
        ENFORCEMENT_RESERVATION_RECONCILIATIONS_TOTAL.labels(
            trigger="auto",
            status="auto_release",
        ).inc(len(decision_ids))
        return OverdueReservationReconciliationResult(
            released_count=len(decision_ids),
            total_released_usd=total_released,
            decision_ids=decision_ids,
            older_than_seconds=bounded_age,
        )

    async def build_export_bundle(
        self,
        *,
        tenant_id: UUID,
        window_start: datetime,
        window_end: datetime,
        max_rows: int,
    ) -> EnforcementExportBundle:
        bounded_max_rows = int(max_rows)
        if bounded_max_rows < 1:
            raise HTTPException(status_code=422, detail="max_rows must be >= 1")
        if bounded_max_rows > 50000:
            raise HTTPException(status_code=422, detail="max_rows must be <= 50000")

        normalized_start = _as_utc(window_start)
        normalized_end = _as_utc(window_end)
        if normalized_start >= normalized_end:
            raise HTTPException(
                status_code=422,
                detail="window_start must be before window_end",
            )

        decision_count_db = int(
            (
                await self.db.execute(
                    select(func.count(EnforcementDecision.id))
                    .where(EnforcementDecision.tenant_id == tenant_id)
                    .where(EnforcementDecision.created_at >= normalized_start)
                    .where(EnforcementDecision.created_at <= normalized_end)
                )
            ).scalar_one()
            or 0
        )
        if decision_count_db > bounded_max_rows:
            ENFORCEMENT_EXPORT_EVENTS_TOTAL.labels(
                artifact="bundle",
                outcome="rejected_limit",
            ).inc()
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Export window exceeds max_rows ({bounded_max_rows}). "
                    "Narrow the date range or increase max_rows."
                ),
            )

        decision_rows = await self.db.execute(
            select(EnforcementDecision)
            .where(EnforcementDecision.tenant_id == tenant_id)
            .where(EnforcementDecision.created_at >= normalized_start)
            .where(EnforcementDecision.created_at <= normalized_end)
            .order_by(EnforcementDecision.created_at.asc(), EnforcementDecision.id.asc())
        )
        decisions = list(decision_rows.scalars().all())
        decision_count_exported = len(decisions)

        approval_count_db = int(
            (
                await self.db.execute(
                    select(func.count(EnforcementApprovalRequest.id))
                    .select_from(EnforcementApprovalRequest)
                    .join(
                        EnforcementDecision,
                        EnforcementDecision.id
                        == EnforcementApprovalRequest.decision_id,
                    )
                    .where(EnforcementApprovalRequest.tenant_id == tenant_id)
                    .where(EnforcementDecision.tenant_id == tenant_id)
                    .where(EnforcementDecision.created_at >= normalized_start)
                    .where(EnforcementDecision.created_at <= normalized_end)
                )
            ).scalar_one()
            or 0
        )

        approvals: list[EnforcementApprovalRequest] = []
        if decisions:
            decision_ids = [decision.id for decision in decisions]
            approval_rows = await self.db.execute(
                select(EnforcementApprovalRequest)
                .where(EnforcementApprovalRequest.tenant_id == tenant_id)
                .where(EnforcementApprovalRequest.decision_id.in_(decision_ids))
                .order_by(
                    EnforcementApprovalRequest.created_at.asc(),
                    EnforcementApprovalRequest.id.asc(),
                )
            )
            approvals = list(approval_rows.scalars().all())

        policy_lineage_counts: dict[tuple[str, str], int] = {}
        for decision in decisions:
            schema_version = _normalize_policy_document_schema_version(
                getattr(decision, "policy_document_schema_version", None)
            )
            policy_hash = _normalize_policy_document_sha256(
                getattr(decision, "policy_document_sha256", None)
            )
            key = (schema_version, policy_hash)
            policy_lineage_counts[key] = int(policy_lineage_counts.get(key, 0)) + 1

        policy_lineage: list[dict[str, Any]] = []
        for schema_version, policy_hash in sorted(policy_lineage_counts.keys()):
            policy_lineage.append(
                {
                    "policy_document_schema_version": schema_version,
                    "policy_document_sha256": policy_hash,
                    "decision_count": int(policy_lineage_counts[(schema_version, policy_hash)]),
                }
            )
        policy_lineage_json = json.dumps(
            policy_lineage,
            sort_keys=True,
            separators=(",", ":"),
            default=_json_default,
        )
        policy_lineage_sha256 = hashlib.sha256(
            policy_lineage_json.encode("utf-8")
        ).hexdigest()

        computed_context_lineage_counts: dict[
            tuple[str, str, str, str, int, int, int, str, str],
            int,
        ] = {}
        for decision in decisions:
            snapshot = _computed_context_snapshot(decision.response_payload)
            context_key = (
                str(snapshot["context_version"]),
                str(snapshot["generated_at"]),
                str(snapshot["month_start"]),
                str(snapshot["month_end"]),
                int(snapshot["month_elapsed_days"]),
                int(snapshot["month_total_days"]),
                int(snapshot["observed_cost_days"]),
                str(snapshot["latest_cost_date"]),
                str(snapshot["data_source_mode"]),
            )
            computed_context_lineage_counts[context_key] = (
                int(computed_context_lineage_counts.get(context_key, 0)) + 1
            )

        computed_context_lineage: list[dict[str, Any]] = []
        for context_key in sorted(computed_context_lineage_counts.keys()):
            (
                context_version,
                generated_at,
                month_start,
                month_end,
                month_elapsed_days,
                month_total_days,
                observed_cost_days,
                latest_cost_date,
                data_source_mode,
            ) = context_key
            computed_context_lineage.append(
                {
                    "context_version": context_version,
                    "generated_at": generated_at,
                    "month_start": month_start,
                    "month_end": month_end,
                    "month_elapsed_days": month_elapsed_days,
                    "month_total_days": month_total_days,
                    "observed_cost_days": observed_cost_days,
                    "latest_cost_date": latest_cost_date,
                    "data_source_mode": data_source_mode,
                    "decision_count": int(computed_context_lineage_counts[context_key]),
                }
            )
        computed_context_lineage_json = json.dumps(
            computed_context_lineage,
            sort_keys=True,
            separators=(",", ":"),
            default=_json_default,
        )
        computed_context_lineage_sha256 = hashlib.sha256(
            computed_context_lineage_json.encode("utf-8")
        ).hexdigest()

        approval_count_exported = len(approvals)
        decisions_csv = self._render_decisions_csv(decisions)
        approvals_csv = self._render_approvals_csv(approvals)
        decisions_sha256 = hashlib.sha256(
            decisions_csv.encode("utf-8")
        ).hexdigest()
        approvals_sha256 = hashlib.sha256(
            approvals_csv.encode("utf-8")
        ).hexdigest()
        parity_ok = (
            decision_count_db == decision_count_exported
            and approval_count_db == approval_count_exported
        )
        ENFORCEMENT_EXPORT_EVENTS_TOTAL.labels(
            artifact="bundle",
            outcome=("success" if parity_ok else "mismatch"),
        ).inc()

        return EnforcementExportBundle(
            generated_at=_utcnow(),
            window_start=normalized_start,
            window_end=normalized_end,
            decision_count_db=decision_count_db,
            decision_count_exported=decision_count_exported,
            approval_count_db=approval_count_db,
            approval_count_exported=approval_count_exported,
            decisions_sha256=decisions_sha256,
            approvals_sha256=approvals_sha256,
            policy_lineage_sha256=policy_lineage_sha256,
            policy_lineage=policy_lineage,
            computed_context_lineage_sha256=computed_context_lineage_sha256,
            computed_context_lineage=computed_context_lineage,
            decisions_csv=decisions_csv,
            approvals_csv=approvals_csv,
            parity_ok=parity_ok,
        )

    def _resolve_export_manifest_signing_secret(self) -> str:
        settings = get_settings()
        configured = str(
            getattr(settings, "ENFORCEMENT_EXPORT_SIGNING_SECRET", "") or ""
        ).strip()
        if len(configured) >= 32:
            return configured

        fallback = str(getattr(settings, "SUPABASE_JWT_SECRET", "") or "").strip()
        if len(fallback) >= 32:
            return fallback

        raise HTTPException(
            status_code=503,
            detail="Export manifest signing key is not configured",
        )

    def _resolve_export_manifest_signing_key_id(self) -> str:
        settings = get_settings()
        explicit = str(
            getattr(settings, "ENFORCEMENT_EXPORT_SIGNING_KID", "") or ""
        ).strip()
        if explicit:
            return explicit[:64]
        jwt_kid = str(getattr(settings, "JWT_SIGNING_KID", "") or "").strip()
        if jwt_kid:
            return jwt_kid[:64]
        return "enforcement-export-hmac-v1"

    def build_signed_export_manifest(
        self,
        *,
        tenant_id: UUID,
        bundle: EnforcementExportBundle,
    ) -> EnforcementSignedExportManifest:
        content_payload: dict[str, Any] = {
            "schema_version": "valdrix.enforcement.export_manifest.v1",
            "tenant_id": str(tenant_id),
            "window_start": bundle.window_start,
            "window_end": bundle.window_end,
            "decision_count_db": int(bundle.decision_count_db),
            "decision_count_exported": int(bundle.decision_count_exported),
            "approval_count_db": int(bundle.approval_count_db),
            "approval_count_exported": int(bundle.approval_count_exported),
            "decisions_sha256": str(bundle.decisions_sha256),
            "approvals_sha256": str(bundle.approvals_sha256),
            "policy_lineage_sha256": str(bundle.policy_lineage_sha256),
            "policy_lineage": list(bundle.policy_lineage),
            "computed_context_lineage_sha256": str(
                bundle.computed_context_lineage_sha256
            ),
            "computed_context_lineage": list(bundle.computed_context_lineage),
            "parity_ok": bool(bundle.parity_ok),
        }
        canonical_content_json = _canonical_json(content_payload)
        content_sha256 = hashlib.sha256(
            canonical_content_json.encode("utf-8")
        ).hexdigest()
        signing_secret = self._resolve_export_manifest_signing_secret()
        signature = hmac.new(
            signing_secret.encode("utf-8"),
            canonical_content_json.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        signature_key_id = self._resolve_export_manifest_signing_key_id()

        return EnforcementSignedExportManifest(
            schema_version="valdrix.enforcement.export_manifest.v1",
            generated_at=bundle.generated_at,
            tenant_id=tenant_id,
            window_start=bundle.window_start,
            window_end=bundle.window_end,
            decision_count_db=bundle.decision_count_db,
            decision_count_exported=bundle.decision_count_exported,
            approval_count_db=bundle.approval_count_db,
            approval_count_exported=bundle.approval_count_exported,
            decisions_sha256=bundle.decisions_sha256,
            approvals_sha256=bundle.approvals_sha256,
            policy_lineage_sha256=bundle.policy_lineage_sha256,
            policy_lineage=list(bundle.policy_lineage),
            computed_context_lineage_sha256=bundle.computed_context_lineage_sha256,
            computed_context_lineage=list(bundle.computed_context_lineage),
            parity_ok=bundle.parity_ok,
            content_sha256=content_sha256,
            signature_algorithm="hmac-sha256",
            signature_key_id=signature_key_id,
            signature=signature,
            canonical_content_json=canonical_content_json,
        )

    def _render_decisions_csv(
        self,
        decisions: list[EnforcementDecision],
    ) -> str:
        headers = [
            "decision_id",
            "source",
            "environment",
            "project_id",
            "action",
            "resource_reference",
            "decision",
            "reason_codes",
            "policy_version",
            "policy_document_schema_version",
            "policy_document_sha256",
            "computed_context_version",
            "computed_context_generated_at",
            "computed_context_month_start",
            "computed_context_month_end",
            "computed_context_month_elapsed_days",
            "computed_context_month_total_days",
            "computed_context_observed_cost_days",
            "computed_context_latest_cost_date",
            "computed_context_data_source_mode",
            "request_fingerprint",
            "idempotency_key",
            "estimated_monthly_delta_usd",
            "estimated_hourly_delta_usd",
            "allocation_available_usd",
            "credits_available_usd",
            "reserved_allocation_usd",
            "reserved_credit_usd",
            "reservation_active",
            "approval_required",
            "approval_token_issued",
            "token_expires_at",
            "created_by_user_id",
            "created_at",
            "request_payload",
            "response_payload",
        ]
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(headers)
        for decision in decisions:
            context_snapshot = _computed_context_snapshot(decision.response_payload)
            writer.writerow(
                [
                    _sanitize_csv_cell(decision.id),
                    _sanitize_csv_cell(decision.source.value),
                    _sanitize_csv_cell(decision.environment),
                    _sanitize_csv_cell(decision.project_id),
                    _sanitize_csv_cell(decision.action),
                    _sanitize_csv_cell(decision.resource_reference),
                    _sanitize_csv_cell(decision.decision.value),
                    _sanitize_csv_cell(
                        json.dumps(
                            list(decision.reason_codes or []),
                            separators=(",", ":"),
                        )
                    ),
                    _sanitize_csv_cell(int(decision.policy_version)),
                    _sanitize_csv_cell(
                        _normalize_policy_document_schema_version(
                            decision.policy_document_schema_version
                        )
                    ),
                    _sanitize_csv_cell(
                        _normalize_policy_document_sha256(
                            decision.policy_document_sha256
                        )
                    ),
                    _sanitize_csv_cell(context_snapshot["context_version"]),
                    _sanitize_csv_cell(context_snapshot["generated_at"]),
                    _sanitize_csv_cell(context_snapshot["month_start"]),
                    _sanitize_csv_cell(context_snapshot["month_end"]),
                    _sanitize_csv_cell(context_snapshot["month_elapsed_days"]),
                    _sanitize_csv_cell(context_snapshot["month_total_days"]),
                    _sanitize_csv_cell(context_snapshot["observed_cost_days"]),
                    _sanitize_csv_cell(context_snapshot["latest_cost_date"]),
                    _sanitize_csv_cell(context_snapshot["data_source_mode"]),
                    _sanitize_csv_cell(decision.request_fingerprint),
                    _sanitize_csv_cell(decision.idempotency_key),
                    _sanitize_csv_cell(_to_decimal(decision.estimated_monthly_delta_usd)),
                    _sanitize_csv_cell(_to_decimal(decision.estimated_hourly_delta_usd)),
                    _sanitize_csv_cell(
                        _to_decimal(decision.allocation_available_usd)
                        if decision.allocation_available_usd is not None
                        else ""
                    ),
                    _sanitize_csv_cell(
                        _to_decimal(decision.credits_available_usd)
                        if decision.credits_available_usd is not None
                        else ""
                    ),
                    _sanitize_csv_cell(_to_decimal(decision.reserved_allocation_usd)),
                    _sanitize_csv_cell(_to_decimal(decision.reserved_credit_usd)),
                    _sanitize_csv_cell(bool(decision.reservation_active)),
                    _sanitize_csv_cell(bool(decision.approval_required)),
                    _sanitize_csv_cell(bool(decision.approval_token_issued)),
                    _sanitize_csv_cell(_iso_or_empty(decision.token_expires_at)),
                    _sanitize_csv_cell(decision.created_by_user_id or ""),
                    _sanitize_csv_cell(_iso_or_empty(decision.created_at)),
                    _sanitize_csv_cell(
                        json.dumps(
                            decision.request_payload or {},
                            sort_keys=True,
                            separators=(",", ":"),
                            default=_json_default,
                        )
                    ),
                    _sanitize_csv_cell(
                        json.dumps(
                            decision.response_payload or {},
                            sort_keys=True,
                            separators=(",", ":"),
                            default=_json_default,
                        )
                    ),
                ]
            )
        return out.getvalue()

    def _render_approvals_csv(
        self,
        approvals: list[EnforcementApprovalRequest],
    ) -> str:
        headers = [
            "approval_id",
            "decision_id",
            "status",
            "requested_by_user_id",
            "reviewed_by_user_id",
            "review_notes",
            "routing_rule_id",
            "routing_required_permission",
            "routing_allowed_reviewer_roles",
            "routing_require_requester_reviewer_separation",
            "approval_token_expires_at",
            "approval_token_consumed_at",
            "expires_at",
            "approved_at",
            "denied_at",
            "created_at",
            "updated_at",
        ]
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(headers)
        for approval in approvals:
            routing_trace = approval.routing_trace if isinstance(approval.routing_trace, dict) else {}
            routing_roles = routing_trace.get("allowed_reviewer_roles")
            if not isinstance(routing_roles, list):
                routing_roles = []
            writer.writerow(
                [
                    _sanitize_csv_cell(approval.id),
                    _sanitize_csv_cell(approval.decision_id),
                    _sanitize_csv_cell(approval.status.value),
                    _sanitize_csv_cell(approval.requested_by_user_id or ""),
                    _sanitize_csv_cell(approval.reviewed_by_user_id or ""),
                    _sanitize_csv_cell(approval.review_notes or ""),
                    _sanitize_csv_cell(approval.routing_rule_id or ""),
                    _sanitize_csv_cell(routing_trace.get("required_permission") or ""),
                    _sanitize_csv_cell(",".join(str(role) for role in routing_roles)),
                    _sanitize_csv_cell(
                        bool(routing_trace.get("require_requester_reviewer_separation"))
                    ),
                    _sanitize_csv_cell(_iso_or_empty(approval.approval_token_expires_at)),
                    _sanitize_csv_cell(_iso_or_empty(approval.approval_token_consumed_at)),
                    _sanitize_csv_cell(_iso_or_empty(approval.expires_at)),
                    _sanitize_csv_cell(_iso_or_empty(approval.approved_at)),
                    _sanitize_csv_cell(_iso_or_empty(approval.denied_at)),
                    _sanitize_csv_cell(_iso_or_empty(approval.created_at)),
                    _sanitize_csv_cell(_iso_or_empty(approval.updated_at)),
                ]
            )
        return out.getvalue()

    def _append_decision_ledger_entry(
        self,
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
        self.db.add(ledger_entry)

    async def _get_decision_by_idempotency(
        self,
        *,
        tenant_id: UUID,
        source: EnforcementSource,
        idempotency_key: str,
    ) -> EnforcementDecision | None:
        return (
            await self.db.execute(
                select(EnforcementDecision).where(
                    EnforcementDecision.tenant_id == tenant_id,
                    EnforcementDecision.source == source,
                    EnforcementDecision.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()

    async def _acquire_gate_evaluation_lock(
        self,
        *,
        policy: EnforcementPolicy,
        source: EnforcementSource,
    ) -> None:
        # Use a tenant-scoped no-op update as a cross-dialect serialization lock
        # for the reserve-critical section. This guarantees distinct idempotency
        # requests cannot evaluate against stale shared headroom concurrently.
        lock_timeout_seconds = _gate_lock_timeout_seconds()
        started_at = time.perf_counter()
        try:
            result = cast(
                CursorResult[Any],
                await asyncio.wait_for(
                    self.db.execute(
                        update(EnforcementPolicy)
                        .where(EnforcementPolicy.id == policy.id)
                        .where(EnforcementPolicy.tenant_id == policy.tenant_id)
                        .values(policy_version=EnforcementPolicy.policy_version)
                    ),
                    timeout=lock_timeout_seconds,
                ),
            )
        except TimeoutError as exc:
            wait_seconds = max(0.0, time.perf_counter() - started_at)
            ENFORCEMENT_GATE_LOCK_WAIT_SECONDS.labels(
                source=source.value,
                outcome="timeout",
            ).observe(wait_seconds)
            ENFORCEMENT_GATE_LOCK_EVENTS_TOTAL.labels(
                source=source.value,
                event="timeout",
            ).inc()
            ENFORCEMENT_GATE_LOCK_EVENTS_TOTAL.labels(
                source=source.value,
                event="contended",
            ).inc()
            await self.db.rollback()
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "gate_lock_timeout",
                    "message": "Enforcement gate evaluation lock timeout",
                    "lock_timeout_seconds": f"{lock_timeout_seconds:.3f}",
                    "lock_wait_seconds": f"{wait_seconds:.3f}",
                },
            ) from exc
        except Exception:
            wait_seconds = max(0.0, time.perf_counter() - started_at)
            ENFORCEMENT_GATE_LOCK_WAIT_SECONDS.labels(
                source=source.value,
                outcome="error",
            ).observe(wait_seconds)
            ENFORCEMENT_GATE_LOCK_EVENTS_TOTAL.labels(
                source=source.value,
                event="error",
            ).inc()
            raise

        wait_seconds = max(0.0, time.perf_counter() - started_at)
        ENFORCEMENT_GATE_LOCK_WAIT_SECONDS.labels(
            source=source.value,
            outcome="acquired",
        ).observe(wait_seconds)
        ENFORCEMENT_GATE_LOCK_EVENTS_TOTAL.labels(
            source=source.value,
            event="acquired",
        ).inc()
        if wait_seconds >= 0.05:
            ENFORCEMENT_GATE_LOCK_EVENTS_TOTAL.labels(
                source=source.value,
                event="contended",
            ).inc()
        if result.rowcount == 0:
            ENFORCEMENT_GATE_LOCK_EVENTS_TOTAL.labels(
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

    async def _get_approval_by_decision(
        self,
        decision_id: UUID,
    ) -> EnforcementApprovalRequest | None:
        return (
            await self.db.execute(
                select(EnforcementApprovalRequest).where(
                    EnforcementApprovalRequest.decision_id == decision_id,
                )
            )
        ).scalar_one_or_none()

    async def _get_reserved_totals(
        self,
        *,
        tenant_id: UUID,
        month_start: datetime,
        month_end: datetime,
    ) -> tuple[Decimal, Decimal]:
        row = (
            await self.db.execute(
                select(
                    func.coalesce(func.sum(EnforcementDecision.reserved_allocation_usd), 0),
                    func.coalesce(func.sum(EnforcementDecision.reserved_credit_usd), 0),
                )
                .where(EnforcementDecision.tenant_id == tenant_id)
                .where(EnforcementDecision.reservation_active.is_(True))
                .where(EnforcementDecision.created_at >= month_start)
                .where(EnforcementDecision.created_at < month_end)
            )
        ).one()
        return _to_decimal(row[0]), _to_decimal(row[1])

    async def _get_effective_budget(
        self,
        *,
        tenant_id: UUID,
        scope_key: str,
    ) -> EnforcementBudgetAllocation | None:
        normalized_scope = str(scope_key or "default").strip().lower() or "default"

        scoped = (
            await self.db.execute(
                select(EnforcementBudgetAllocation)
                .where(EnforcementBudgetAllocation.tenant_id == tenant_id)
                .where(EnforcementBudgetAllocation.scope_key == normalized_scope)
                .where(EnforcementBudgetAllocation.active.is_(True))
            )
        ).scalar_one_or_none()
        if scoped is not None:
            return scoped

        fallback = (
            await self.db.execute(
                select(EnforcementBudgetAllocation)
                .where(EnforcementBudgetAllocation.tenant_id == tenant_id)
                .where(EnforcementBudgetAllocation.scope_key == "default")
                .where(EnforcementBudgetAllocation.active.is_(True))
            )
        ).scalar_one_or_none()
        return fallback

    async def _get_credit_headrooms(
        self,
        *,
        tenant_id: UUID,
        scope_key: str,
        now: datetime,
    ) -> tuple[Decimal, Decimal]:
        normalized_scope = str(scope_key or "default").strip().lower() or "default"
        reserved_remaining = (
            await self.db.execute(
                select(func.coalesce(func.sum(EnforcementCreditGrant.remaining_amount_usd), 0))
                .where(EnforcementCreditGrant.tenant_id == tenant_id)
                .where(EnforcementCreditGrant.pool_type == EnforcementCreditPoolType.RESERVED)
                .where(EnforcementCreditGrant.active.is_(True))
                .where(
                    EnforcementCreditGrant.scope_key.in_(
                        [normalized_scope, "default"]
                    )
                )
                .where(
                    or_(
                        EnforcementCreditGrant.expires_at.is_(None),
                        EnforcementCreditGrant.expires_at > now,
                    )
                )
            )
        ).scalar_one()
        emergency_remaining = (
            await self.db.execute(
                select(func.coalesce(func.sum(EnforcementCreditGrant.remaining_amount_usd), 0))
                .where(EnforcementCreditGrant.tenant_id == tenant_id)
                .where(EnforcementCreditGrant.pool_type == EnforcementCreditPoolType.EMERGENCY)
                .where(EnforcementCreditGrant.active.is_(True))
                .where(
                    or_(
                        EnforcementCreditGrant.expires_at.is_(None),
                        EnforcementCreditGrant.expires_at > now,
                    )
                )
            )
        ).scalar_one()

        # Legacy safety guard:
        # older active reservation rows can exist without explicit grant-allocation
        # mappings. Subtract only the uncovered legacy amount to avoid double-counting
        # for new reservations that debit grant balances at reserve time. Apply this
        # adjustment to project-reserved pool first, then emergency pool.
        decisions_reserved_total = (
            await self.db.execute(
                select(func.coalesce(func.sum(EnforcementDecision.reserved_credit_usd), 0))
                .where(EnforcementDecision.tenant_id == tenant_id)
                .where(EnforcementDecision.reservation_active.is_(True))
            )
        ).scalar_one()
        mapped_active_total = (
            await self.db.execute(
                select(
                    func.coalesce(
                        func.sum(
                            EnforcementCreditReservationAllocation.reserved_amount_usd
                        ),
                        0,
                    )
                )
                .where(EnforcementCreditReservationAllocation.tenant_id == tenant_id)
                .where(EnforcementCreditReservationAllocation.active.is_(True))
            )
        ).scalar_one()

        uncovered_legacy_reserved = max(
            Decimal("0"),
            _to_decimal(decisions_reserved_total) - _to_decimal(mapped_active_total),
        )

        reserved_headroom = max(Decimal("0"), _to_decimal(reserved_remaining))
        emergency_headroom = max(Decimal("0"), _to_decimal(emergency_remaining))
        if uncovered_legacy_reserved > Decimal("0"):
            reserved_reduction = min(uncovered_legacy_reserved, reserved_headroom)
            reserved_headroom = _quantize(
                max(Decimal("0"), reserved_headroom - reserved_reduction),
                "0.0001",
            )
            remaining_uncovered = _quantize(
                uncovered_legacy_reserved - reserved_reduction,
                "0.0001",
            )
            if remaining_uncovered > Decimal("0"):
                emergency_headroom = _quantize(
                    max(Decimal("0"), emergency_headroom - remaining_uncovered),
                    "0.0001",
                )

        return (
            _quantize(reserved_headroom, "0.0001"),
            _quantize(emergency_headroom, "0.0001"),
        )

    async def _get_active_credit_headroom(
        self,
        *,
        tenant_id: UUID,
        scope_key: str,
        now: datetime,
    ) -> Decimal:
        reserved_headroom, emergency_headroom = await self._get_credit_headrooms(
            tenant_id=tenant_id,
            scope_key=scope_key,
            now=now,
        )
        return _quantize(reserved_headroom + emergency_headroom, "0.0001")

    async def _reserve_credit_for_decision(
        self,
        *,
        tenant_id: UUID,
        decision_id: UUID,
        scope_key: str,
        reserve_reserved_credit_usd: Decimal,
        reserve_emergency_credit_usd: Decimal,
        now: datetime,
    ) -> list[dict[str, str]]:
        reserved_target = _quantize(_to_decimal(reserve_reserved_credit_usd), "0.0001")
        emergency_target = _quantize(_to_decimal(reserve_emergency_credit_usd), "0.0001")
        normalized_scope = str(scope_key or "default").strip().lower() or "default"
        allocations: list[dict[str, str]] = []
        if reserved_target > Decimal("0.0000"):
            allocations.extend(
                await self._reserve_credit_from_grants(
                    tenant_id=tenant_id,
                    decision_id=decision_id,
                    scope_key=normalized_scope,
                    pool_type=EnforcementCreditPoolType.RESERVED,
                    reserve_target_usd=reserved_target,
                    now=now,
                )
            )
        if emergency_target > Decimal("0.0000"):
            allocations.extend(
                await self._reserve_credit_from_grants(
                    tenant_id=tenant_id,
                    decision_id=decision_id,
                    scope_key=normalized_scope,
                    pool_type=EnforcementCreditPoolType.EMERGENCY,
                    reserve_target_usd=emergency_target,
                    now=now,
                )
            )

        return allocations

    async def _reserve_credit_from_grants(
        self,
        *,
        tenant_id: UUID,
        decision_id: UUID,
        scope_key: str,
        pool_type: EnforcementCreditPoolType,
        reserve_target_usd: Decimal,
        now: datetime,
    ) -> list[dict[str, str]]:
        target = _quantize(_to_decimal(reserve_target_usd), "0.0001")
        if target <= Decimal("0.0000"):
            return []

        scope_priority = case(
            (EnforcementCreditGrant.scope_key == scope_key, 0),
            (EnforcementCreditGrant.scope_key == "default", 1),
            else_=2,
        )
        query = (
            select(EnforcementCreditGrant)
            .where(EnforcementCreditGrant.tenant_id == tenant_id)
            .where(EnforcementCreditGrant.active.is_(True))
            .where(EnforcementCreditGrant.pool_type == pool_type)
            .where(
                or_(
                    EnforcementCreditGrant.expires_at.is_(None),
                    EnforcementCreditGrant.expires_at > now,
                )
            )
            .with_for_update()
        )
        if pool_type == EnforcementCreditPoolType.RESERVED:
            query = query.where(EnforcementCreditGrant.scope_key.in_([scope_key, "default"]))
            query = query.order_by(
                scope_priority.asc(),
                case((EnforcementCreditGrant.expires_at.is_(None), 1), else_=0).asc(),
                EnforcementCreditGrant.expires_at.asc(),
                EnforcementCreditGrant.created_at.asc(),
                EnforcementCreditGrant.id.asc(),
            )
        else:
            query = query.order_by(
                case((EnforcementCreditGrant.expires_at.is_(None), 1), else_=0).asc(),
                EnforcementCreditGrant.expires_at.asc(),
                EnforcementCreditGrant.created_at.asc(),
                EnforcementCreditGrant.id.asc(),
            )

        rows = await self.db.execute(query)
        grants = list(rows.scalars().all())

        remaining = target
        allocations: list[dict[str, str]] = []
        for grant in grants:
            if remaining <= Decimal("0.0000"):
                break

            grant_remaining = _quantize(_to_decimal(grant.remaining_amount_usd), "0.0001")
            if grant_remaining <= Decimal("0.0000"):
                continue

            reserve_amount = _quantize(min(remaining, grant_remaining), "0.0001")
            # Defensive quantization guard: with 4dp quantization and the
            # grant_remaining <= 0 short-circuit above, this path should only be
            # reachable if decimal coercion semantics regress.
            if reserve_amount <= Decimal("0.0000"):
                continue

            grant.remaining_amount_usd = _quantize(grant_remaining - reserve_amount, "0.0001")
            if _to_decimal(grant.remaining_amount_usd) <= Decimal("0.0000"):
                grant.active = False

            self.db.add(
                EnforcementCreditReservationAllocation(
                    tenant_id=tenant_id,
                    decision_id=decision_id,
                    credit_grant_id=grant.id,
                    credit_pool_type=pool_type,
                    reserved_amount_usd=reserve_amount,
                    consumed_amount_usd=Decimal("0"),
                    released_amount_usd=Decimal("0"),
                    active=True,
                )
            )
            allocations.append(
                {
                    "credit_grant_id": str(grant.id),
                    "credit_pool_type": pool_type.value,
                    "scope_key": str(grant.scope_key),
                    "reserved_amount_usd": str(reserve_amount),
                }
            )
            remaining = _quantize(remaining - reserve_amount, "0.0001")

        if remaining > Decimal("0.0000"):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Insufficient credit grant headroom during reservation allocation "
                    f"(pool={pool_type.value}, missing={remaining})"
                ),
            )

        return allocations

    async def _settle_credit_reservations_for_decision(
        self,
        *,
        tenant_id: UUID,
        decision: EnforcementDecision,
        consumed_credit_usd: Decimal,
        now: datetime,
    ) -> list[dict[str, str]]:
        reserved_credit = _quantize(_to_decimal(decision.reserved_credit_usd), "0.0001")
        if reserved_credit <= Decimal("0.0000"):
            return []

        bounded_consumed = _quantize(
            min(max(Decimal("0.0000"), _to_decimal(consumed_credit_usd)), reserved_credit),
            "0.0001",
        )
        remaining_consume = bounded_consumed
        remaining_release = _quantize(reserved_credit - bounded_consumed, "0.0001")

        allocation_rows = await self.db.execute(
            select(EnforcementCreditReservationAllocation)
            .where(EnforcementCreditReservationAllocation.tenant_id == tenant_id)
            .where(EnforcementCreditReservationAllocation.decision_id == decision.id)
            .where(EnforcementCreditReservationAllocation.active.is_(True))
            .order_by(EnforcementCreditReservationAllocation.created_at.asc())
            .with_for_update()
        )
        allocations = list(allocation_rows.scalars().all())
        if not allocations:
            raise HTTPException(
                status_code=409,
                detail="Missing credit reservation allocation rows for decision settlement",
            )

        grant_ids = sorted({allocation.credit_grant_id for allocation in allocations})
        grant_rows = await self.db.execute(
            select(EnforcementCreditGrant)
            .where(EnforcementCreditGrant.tenant_id == tenant_id)
            .where(EnforcementCreditGrant.id.in_(grant_ids))
            .with_for_update()
        )
        grants_by_id = {grant.id: grant for grant in grant_rows.scalars().all()}

        diagnostics: list[dict[str, str]] = []
        for allocation in allocations:
            grant = grants_by_id.get(allocation.credit_grant_id)
            if grant is None:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Missing credit grant row for reservation allocation "
                        f"{allocation.id}"
                    ),
                )

            reserved_amount = _quantize(
                _to_decimal(allocation.reserved_amount_usd),
                "0.0001",
            )
            consume_amount = _quantize(
                min(reserved_amount, remaining_consume),
                "0.0001",
            )
            remaining_consume = _quantize(remaining_consume - consume_amount, "0.0001")

            release_amount = _quantize(reserved_amount - consume_amount, "0.0001")
            if release_amount > remaining_release:
                release_amount = remaining_release
            remaining_release = _quantize(remaining_release - release_amount, "0.0001")

            if release_amount > Decimal("0.0000"):
                new_remaining = _quantize(
                    _to_decimal(grant.remaining_amount_usd) + release_amount,
                    "0.0001",
                )
                grant_total = _quantize(_to_decimal(grant.total_amount_usd), "0.0001")
                if new_remaining > grant_total:
                    new_remaining = grant_total
                grant.remaining_amount_usd = new_remaining

            grant_active = _to_decimal(grant.remaining_amount_usd) > Decimal("0.0000")
            not_expired = grant.expires_at is None or _as_utc(grant.expires_at) > now
            grant.active = bool(grant_active and not_expired)

            allocation.consumed_amount_usd = _quantize(
                _to_decimal(allocation.consumed_amount_usd) + consume_amount,
                "0.0001",
            )
            allocation.released_amount_usd = _quantize(
                _to_decimal(allocation.released_amount_usd) + release_amount,
                "0.0001",
            )
            allocation.active = False
            allocation.settled_at = now

            diagnostics.append(
                {
                    "credit_grant_id": str(grant.id),
                    "credit_pool_type": allocation.credit_pool_type.value,
                    "scope_key": str(grant.scope_key),
                    "reserved_amount_usd": str(reserved_amount),
                    "consumed_amount_usd": str(consume_amount),
                    "released_amount_usd": str(release_amount),
                    "grant_remaining_amount_usd_after": str(
                        _quantize(_to_decimal(grant.remaining_amount_usd), "0.0001")
                    ),
                }
            )

        if remaining_consume > Decimal("0.0000") or remaining_release > Decimal("0.0000"):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Credit reservation settlement drift detected "
                    f"(remaining_consume={remaining_consume}, "
                    f"remaining_release={remaining_release})"
                ),
            )

        return diagnostics

    def _mode_violation_decision(self, mode: EnforcementMode) -> EnforcementDecisionType:
        if mode == EnforcementMode.SHADOW:
            return EnforcementDecisionType.ALLOW
        if mode == EnforcementMode.SOFT:
            return EnforcementDecisionType.REQUIRE_APPROVAL
        return EnforcementDecisionType.DENY

    def _mode_violation_reason_suffix(self, mode: EnforcementMode, *, subject: str) -> str:
        if mode == EnforcementMode.SHADOW:
            return f"shadow_mode_{subject}_override"
        if mode == EnforcementMode.SOFT:
            return f"soft_mode_{subject}_escalation"
        return f"hard_mode_{subject}_closed"

    def _evaluate_entitlement_waterfall(
        self,
        *,
        mode: EnforcementMode,
        monthly_delta: Decimal,
        plan_headroom: Decimal | None,
        allocation_headroom: Decimal | None,
        reserved_credit_headroom: Decimal,
        emergency_credit_headroom: Decimal,
        enterprise_headroom: Decimal | None,
    ) -> EntitlementWaterfallResult:
        requested = _quantize(_to_decimal(monthly_delta), "0.0001")
        reserved_alloc = Decimal("0.0000")
        reserved_credit = Decimal("0.0000")
        emergency_credit = Decimal("0.0000")
        remaining = requested
        stage_details: list[dict[str, str]] = []

        def _stage_row(
            *,
            stage: str,
            status: str,
            available: Decimal | None,
            consumed: Decimal,
            remaining_after: Decimal,
        ) -> dict[str, str]:
            return {
                "stage": stage,
                "status": status,
                "available_usd": (
                    str(_quantize(available, "0.0001")) if available is not None else "unbounded"
                ),
                "consumed_usd": str(_quantize(consumed, "0.0001")),
                "remaining_after_stage_usd": str(_quantize(remaining_after, "0.0001")),
            }

        if plan_headroom is not None:
            normalized_plan = max(Decimal("0.0000"), _quantize(plan_headroom, "0.0001"))
            if requested > normalized_plan:
                stage_details.append(
                    _stage_row(
                        stage="plan_limit",
                        status="fail",
                        available=normalized_plan,
                        consumed=Decimal("0"),
                        remaining_after=requested,
                    )
                )
                return EntitlementWaterfallResult(
                    decision=self._mode_violation_decision(mode),
                    reserve_allocation_usd=Decimal("0"),
                    reserve_reserved_credit_usd=Decimal("0"),
                    reserve_emergency_credit_usd=Decimal("0"),
                    reason_code="plan_limit_exceeded",
                    stage_details=stage_details,
                )

            stage_details.append(
                _stage_row(
                    stage="plan_limit",
                    status="pass",
                    available=normalized_plan,
                    consumed=requested,
                    remaining_after=remaining,
                )
            )
        else:
            stage_details.append(
                _stage_row(
                    stage="plan_limit",
                    status="skipped",
                    available=None,
                    consumed=requested,
                    remaining_after=remaining,
                )
            )

        funding_target = requested
        if enterprise_headroom is not None:
            normalized_enterprise = max(
                Decimal("0.0000"), _quantize(enterprise_headroom, "0.0001")
            )
            funding_target = min(requested, normalized_enterprise)
        else:
            normalized_enterprise = None

        remaining = funding_target
        if allocation_headroom is None:
            consumed_unbounded = _quantize(remaining, "0.0001")
            remaining = Decimal("0.0000")
            stage_details.append(
                _stage_row(
                    stage="project_allocation",
                    status="skipped",
                    available=None,
                    consumed=consumed_unbounded,
                    remaining_after=remaining,
                )
            )
        else:
            alloc_available = max(Decimal("0.0000"), _quantize(allocation_headroom, "0.0001"))
            reserved_alloc = _quantize(min(remaining, alloc_available), "0.0001")
            remaining = _quantize(remaining - reserved_alloc, "0.0001")
            alloc_status = "pass" if remaining == Decimal("0.0000") else "partial"
            stage_details.append(
                _stage_row(
                    stage="project_allocation",
                    status=alloc_status,
                    available=alloc_available,
                    consumed=reserved_alloc,
                    remaining_after=remaining,
                )
            )

        reserved_available = max(
            Decimal("0.0000"), _quantize(reserved_credit_headroom, "0.0001")
        )
        reserved_credit = _quantize(min(remaining, reserved_available), "0.0001")
        remaining = _quantize(remaining - reserved_credit, "0.0001")
        reserved_status = "pass" if remaining == Decimal("0.0000") else "partial"
        stage_details.append(
            _stage_row(
                stage="reserved_credits",
                status=reserved_status if reserved_available > Decimal("0") else "skipped",
                available=reserved_available,
                consumed=reserved_credit,
                remaining_after=remaining,
            )
        )

        emergency_available = max(
            Decimal("0.0000"), _quantize(emergency_credit_headroom, "0.0001")
        )
        emergency_credit = _quantize(min(remaining, emergency_available), "0.0001")
        remaining = _quantize(remaining - emergency_credit, "0.0001")
        emergency_status = "pass" if remaining == Decimal("0.0000") else "partial"
        stage_details.append(
            _stage_row(
                stage="org_emergency_credits",
                status=emergency_status if emergency_available > Decimal("0") else "skipped",
                available=emergency_available,
                consumed=emergency_credit,
                remaining_after=remaining,
            )
        )

        enterprise_consumable = (
            min(requested, normalized_enterprise)
            if normalized_enterprise is not None
            else requested
        )
        enterprise_remaining = _quantize(requested - enterprise_consumable, "0.0001")
        enterprise_failed = (
            normalized_enterprise is not None and requested > normalized_enterprise
        )
        stage_details.append(
            _stage_row(
                stage="enterprise_ceiling",
                status=(
                    "fail"
                    if enterprise_failed and remaining == Decimal("0.0000")
                    else ("pass" if normalized_enterprise is not None else "skipped")
                ),
                available=normalized_enterprise,
                consumed=enterprise_consumable,
                remaining_after=enterprise_remaining,
            )
        )

        if remaining > Decimal("0.0000"):
            return EntitlementWaterfallResult(
                decision=self._mode_violation_decision(mode),
                reserve_allocation_usd=(
                    reserved_alloc if mode == EnforcementMode.SOFT else Decimal("0")
                ),
                reserve_reserved_credit_usd=(
                    reserved_credit if mode == EnforcementMode.SOFT else Decimal("0")
                ),
                reserve_emergency_credit_usd=(
                    emergency_credit if mode == EnforcementMode.SOFT else Decimal("0")
                ),
                reason_code="budget_exceeded",
                stage_details=stage_details,
            )

        if enterprise_failed:
            return EntitlementWaterfallResult(
                decision=self._mode_violation_decision(mode),
                reserve_allocation_usd=(
                    reserved_alloc if mode == EnforcementMode.SOFT else Decimal("0")
                ),
                reserve_reserved_credit_usd=(
                    reserved_credit if mode == EnforcementMode.SOFT else Decimal("0")
                ),
                reserve_emergency_credit_usd=(
                    emergency_credit if mode == EnforcementMode.SOFT else Decimal("0")
                ),
                reason_code="enterprise_ceiling_exceeded",
                stage_details=stage_details,
            )

        return EntitlementWaterfallResult(
            decision=(
                EnforcementDecisionType.ALLOW
                if (reserved_credit + emergency_credit) == Decimal("0.0000")
                else EnforcementDecisionType.ALLOW_WITH_CREDITS
            ),
            reserve_allocation_usd=reserved_alloc,
            reserve_reserved_credit_usd=reserved_credit,
            reserve_emergency_credit_usd=emergency_credit,
            reason_code=None,
            stage_details=stage_details,
        )

    def _evaluate_budget_waterfall(
        self,
        *,
        mode: EnforcementMode,
        monthly_delta: Decimal,
        allocation_headroom: Decimal | None,
        credits_headroom: Decimal,
        reasons: list[str],
    ) -> tuple[EnforcementDecisionType, Decimal, Decimal]:
        result = self._evaluate_entitlement_waterfall(
            mode=mode,
            monthly_delta=monthly_delta,
            plan_headroom=None,
            allocation_headroom=allocation_headroom,
            reserved_credit_headroom=credits_headroom,
            emergency_credit_headroom=Decimal("0"),
            enterprise_headroom=None,
        )
        if result.reason_code == "budget_exceeded":
            reasons.append("budget_exceeded")
            if mode == EnforcementMode.SHADOW:
                reasons.append("shadow_mode_budget_override")
            elif mode == EnforcementMode.SOFT:
                reasons.append("soft_mode_budget_escalation")
        if (result.reserve_reserved_credit_usd + result.reserve_emergency_credit_usd) > Decimal(
            "0.0000"
        ):
            reasons.append("credit_waterfall_used")

        return (
            result.decision,
            result.reserve_allocation_usd,
            result.reserve_credit_usd,
        )

    async def _load_approval_with_decision(
        self,
        *,
        tenant_id: UUID,
        approval_id: UUID,
    ) -> tuple[EnforcementApprovalRequest, EnforcementDecision]:
        approval = (
            await self.db.execute(
                select(EnforcementApprovalRequest).where(
                    EnforcementApprovalRequest.id == approval_id,
                    EnforcementApprovalRequest.tenant_id == tenant_id,
                ).with_for_update()
            )
        ).scalar_one_or_none()
        if approval is None:
            raise HTTPException(status_code=404, detail="Approval request not found")

        decision = (
            await self.db.execute(
                select(EnforcementDecision).where(
                    EnforcementDecision.id == approval.decision_id,
                    EnforcementDecision.tenant_id == tenant_id,
                ).with_for_update()
            )
        ).scalar_one_or_none()
        if decision is None:
            raise HTTPException(status_code=404, detail="Approval decision not found")

        return approval, decision

    def _assert_pending(self, approval: EnforcementApprovalRequest) -> None:
        if approval.status != EnforcementApprovalStatus.PENDING:
            raise HTTPException(
                status_code=409,
                detail=f"Approval request is already {approval.status.value}",
            )

    def _decode_approval_token(self, approval_token: str) -> Mapping[str, Any]:
        settings = get_settings()
        primary_secret = str(getattr(settings, "SUPABASE_JWT_SECRET", "") or "").strip()
        if len(primary_secret) < 32:
            raise HTTPException(
                status_code=503,
                detail="Approval token signing key is not configured",
            )
        fallback_secrets = [
            str(value or "").strip()
            for value in list(
                getattr(settings, "ENFORCEMENT_APPROVAL_TOKEN_FALLBACK_SECRETS", []) or []
            )
            if len(str(value or "").strip()) >= 32
        ]
        candidate_secrets: list[str] = []
        for secret in [primary_secret, *fallback_secrets]:
            if secret and secret not in candidate_secrets:
                candidate_secrets.append(secret)

        issuer = str(getattr(settings, "API_URL", "")).rstrip("/")
        expired_error: jwt.ExpiredSignatureError | None = None
        for candidate_secret in candidate_secrets:
            try:
                payload = jwt.decode(
                    approval_token,
                    candidate_secret,
                    algorithms=["HS256"],
                    audience="enforcement_gate",
                    issuer=issuer,
                    options={
                        "require": [
                            "exp",
                            "iat",
                            "nbf",
                            "tenant_id",
                            "project_id",
                            "decision_id",
                            "approval_id",
                            "source",
                            "environment",
                            "request_fingerprint",
                            "max_monthly_delta_usd",
                            "max_hourly_delta_usd",
                            "resource_reference",
                            "token_type",
                        ]
                    },
                )
                token_type = str(payload.get("token_type", "")).strip()
                if token_type != "enforcement_approval":
                    continue
                return cast(Mapping[str, Any], payload)
            except jwt.ExpiredSignatureError as exc:
                expired_error = exc
                continue
            except jwt.InvalidTokenError:
                continue

        if expired_error is not None:
            raise HTTPException(
                status_code=409,
                detail="Approval token has expired",
            ) from expired_error
        raise HTTPException(
            status_code=401,
            detail="Invalid approval token",
        )

    def _extract_token_context(
        self,
        payload: Mapping[str, Any],
    ) -> ApprovalTokenContext:
        def _uuid_claim(key: str) -> UUID:
            raw = payload.get(key)
            try:
                return UUID(str(raw))
            except (TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid approval token",
                ) from exc

        source_raw = str(payload.get("source", "")).strip().lower()
        try:
            source = EnforcementSource(source_raw)
        except ValueError as exc:
            raise HTTPException(
                status_code=401,
                detail="Invalid approval token",
            ) from exc

        try:
            max_monthly_delta = _quantize(
                _to_decimal(payload.get("max_monthly_delta_usd")),
                "0.0001",
            )
            max_hourly_delta = _quantize(
                _to_decimal(payload.get("max_hourly_delta_usd")),
                "0.000001",
            )
        except InvalidOperation as exc:
            raise HTTPException(
                status_code=401,
                detail="Invalid approval token",
            ) from exc

        exp_raw = payload.get("exp")
        if not isinstance(exp_raw, (int, float, str)):
            raise HTTPException(status_code=401, detail="Invalid approval token")
        try:
            expires_at = datetime.fromtimestamp(int(exp_raw), tz=timezone.utc)
        except (TypeError, ValueError, OSError) as exc:
            raise HTTPException(
                status_code=401,
                detail="Invalid approval token",
            ) from exc

        request_fingerprint = str(payload.get("request_fingerprint", "")).strip()
        if len(request_fingerprint) != 64:
            raise HTTPException(status_code=401, detail="Invalid approval token")

        resource_reference = str(payload.get("resource_reference", "")).strip()
        if not resource_reference:
            raise HTTPException(status_code=401, detail="Invalid approval token")
        project_id = str(payload.get("project_id", "")).strip()
        if not project_id:
            raise HTTPException(status_code=401, detail="Invalid approval token")

        return ApprovalTokenContext(
            approval_id=_uuid_claim("approval_id"),
            decision_id=_uuid_claim("decision_id"),
            tenant_id=_uuid_claim("tenant_id"),
            project_id=project_id,
            source=source,
            environment=str(payload.get("environment", "")).strip(),
            request_fingerprint=request_fingerprint,
            resource_reference=resource_reference,
            max_monthly_delta_usd=max_monthly_delta,
            max_hourly_delta_usd=max_hourly_delta,
            expires_at=expires_at,
        )

    def _build_approval_token(
        self,
        *,
        decision: EnforcementDecision,
        approval: EnforcementApprovalRequest,
        expires_at: datetime,
    ) -> str:
        settings = get_settings()
        secret = str(getattr(settings, "SUPABASE_JWT_SECRET", "") or "").strip()
        if len(secret) < 32:
            raise HTTPException(
                status_code=503,
                detail="Approval token signing key is not configured",
            )

        now = _utcnow()
        payload: dict[str, Any] = {
            "iss": str(getattr(settings, "API_URL", "")).rstrip("/"),
            "aud": "enforcement_gate",
            "sub": f"enforcement_approval:{approval.id}",
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "tenant_id": str(decision.tenant_id),
            "project_id": decision.project_id,
            "decision_id": str(decision.id),
            "approval_id": str(approval.id),
            "source": decision.source.value,
            "environment": decision.environment,
            "request_fingerprint": decision.request_fingerprint,
            "max_monthly_delta_usd": str(
                _to_decimal(decision.estimated_monthly_delta_usd)
            ),
            "max_hourly_delta_usd": str(
                _to_decimal(decision.estimated_hourly_delta_usd)
            ),
            "resource_reference": decision.resource_reference,
            "token_type": "enforcement_approval",
        }

        headers: dict[str, str] | None = None
        signing_kid = str(getattr(settings, "JWT_SIGNING_KID", "") or "").strip()
        if signing_kid:
            headers = {"kid": signing_kid}

        return jwt.encode(
            payload,
            secret,
            algorithm="HS256",
            headers=headers,
        )


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
