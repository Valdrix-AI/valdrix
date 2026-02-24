from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from typing import Any, Mapping, cast
from uuid import UUID

import jwt
import structlog
from fastapi import HTTPException
from sqlalchemy.engine import CursorResult
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enforcement import (
    EnforcementApprovalRequest,
    EnforcementApprovalStatus,
    EnforcementBudgetAllocation,
    EnforcementCreditGrant,
    EnforcementDecision,
    EnforcementDecisionLedger,
    EnforcementDecisionType,
    EnforcementMode,
    EnforcementPolicy,
    EnforcementSource,
)
from app.shared.core.approval_permissions import (
    APPROVAL_PERMISSION_REMEDIATION_APPROVE_NONPROD,
    APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD,
    user_has_approval_permission,
)
from app.shared.core.auth import CurrentUser
from app.shared.core.config import get_settings
from app.shared.core.ops_metrics import (
    ENFORCEMENT_APPROVAL_TOKEN_EVENTS_TOTAL,
    ENFORCEMENT_EXPORT_EVENTS_TOTAL,
    ENFORCEMENT_RESERVATION_DRIFT_USD_TOTAL,
    ENFORCEMENT_RESERVATION_RECONCILIATIONS_TOTAL,
)


logger = structlog.get_logger()


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
    source: EnforcementSource
    environment: str
    request_fingerprint: str
    resource_reference: str
    max_monthly_delta_usd: Decimal
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
    decisions_csv: str
    approvals_csv: str
    parity_ok: bool


@dataclass(frozen=True)
class DecisionLedgerRecord:
    entry: EnforcementDecisionLedger


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


def _sanitize_csv_cell(value: Any) -> str:
    if value is None:
        return ""
    normalized = str(value).replace("\r", " ").replace("\n", " ")
    if normalized[:1] in {"=", "+", "-", "@"}:
        return "'" + normalized
    return normalized


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


class EnforcementService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_policy(self, tenant_id: UUID) -> EnforcementPolicy:
        policy = (
            await self.db.execute(
                select(EnforcementPolicy).where(EnforcementPolicy.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if policy is not None:
            return policy

        policy = EnforcementPolicy(tenant_id=tenant_id)
        self.db.add(policy)
        await self.db.flush()
        return policy

    async def update_policy(
        self,
        *,
        tenant_id: UUID,
        terraform_mode: EnforcementMode,
        k8s_admission_mode: EnforcementMode,
        require_approval_for_prod: bool,
        require_approval_for_nonprod: bool,
        auto_approve_below_monthly_usd: Decimal,
        hard_deny_above_monthly_usd: Decimal,
        default_ttl_seconds: int,
    ) -> EnforcementPolicy:
        if hard_deny_above_monthly_usd <= Decimal("0"):
            raise HTTPException(
                status_code=422,
                detail="hard_deny_above_monthly_usd must be greater than 0",
            )
        if auto_approve_below_monthly_usd < Decimal("0"):
            raise HTTPException(
                status_code=422,
                detail="auto_approve_below_monthly_usd must be >= 0",
            )
        if auto_approve_below_monthly_usd > hard_deny_above_monthly_usd:
            raise HTTPException(
                status_code=422,
                detail=(
                    "auto_approve_below_monthly_usd cannot exceed "
                    "hard_deny_above_monthly_usd"
                ),
            )

        policy = await self.get_or_create_policy(tenant_id)
        policy.terraform_mode = terraform_mode
        policy.k8s_admission_mode = k8s_admission_mode
        policy.require_approval_for_prod = require_approval_for_prod
        policy.require_approval_for_nonprod = require_approval_for_nonprod
        policy.auto_approve_below_monthly_usd = _quantize(
            auto_approve_below_monthly_usd, "0.0001"
        )
        policy.hard_deny_above_monthly_usd = _quantize(
            hard_deny_above_monthly_usd, "0.0001"
        )
        policy.default_ttl_seconds = max(60, min(int(default_ttl_seconds), 86400))
        policy.policy_version += 1
        await self.db.commit()
        await self.db.refresh(policy)
        return policy

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

    async def evaluate_gate(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        source: EnforcementSource,
        gate_input: GateInput,
    ) -> GateEvaluationResult:
        now = _utcnow()
        month_start, month_end = _month_bounds(now)
        normalized_env = _normalize_environment(gate_input.environment)

        policy = await self.get_or_create_policy(tenant_id)
        mode = (
            policy.terraform_mode
            if source == EnforcementSource.TERRAFORM
            else policy.k8s_admission_mode
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

        monthly_delta = _quantize(gate_input.estimated_monthly_delta_usd, "0.0001")
        hourly_delta = _quantize(gate_input.estimated_hourly_delta_usd, "0.000001")
        reasons: list[str] = []

        reserved_alloc, reserved_credit = await self._get_reserved_totals(
            tenant_id=tenant_id,
            month_start=month_start,
            month_end=month_end,
        )

        budget = await self._get_effective_budget(
            tenant_id=tenant_id,
            scope_key=gate_input.project_id,
        )
        credits_available = await self._get_active_credit_headroom(
            tenant_id=tenant_id,
            scope_key=gate_input.project_id,
            now=now,
            reserved_credit=reserved_credit,
        )

        if budget is None:
            allocation_headroom: Decimal | None = None
            reasons.append("no_budget_configured")
        else:
            allocation_headroom = max(
                Decimal("0"),
                _to_decimal(budget.monthly_limit_usd) - reserved_alloc,
            )

        is_prod = _is_production_environment(normalized_env)
        approval_required = (
            policy.require_approval_for_prod if is_prod else policy.require_approval_for_nonprod
        )
        if monthly_delta <= _to_decimal(policy.auto_approve_below_monthly_usd):
            approval_required = False

        reserve_allocation = Decimal("0")
        reserve_credit = Decimal("0")
        reservation_active = False

        decision = EnforcementDecisionType.ALLOW
        hard_deny_threshold = _to_decimal(policy.hard_deny_above_monthly_usd)
        if monthly_delta > hard_deny_threshold:
            reasons.append("hard_deny_threshold_exceeded")
            decision = self._mode_violation_decision(mode)
            if mode == EnforcementMode.SOFT:
                reasons.append("soft_mode_escalation")
            if mode == EnforcementMode.SHADOW:
                reasons.append("shadow_mode_override")
        else:
            decision, reserve_allocation, reserve_credit = self._evaluate_budget_waterfall(
                mode=mode,
                monthly_delta=monthly_delta,
                allocation_headroom=allocation_headroom,
                credits_headroom=credits_available,
                reasons=reasons,
            )

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
            reserve_credit = Decimal("0")
            reservation_active = False
        elif decision != EnforcementDecisionType.DENY and mode != EnforcementMode.SHADOW:
            reservation_active = (reserve_allocation + reserve_credit) > Decimal("0")

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
            request_fingerprint=fingerprint,
            idempotency_key=idempotency_key,
            request_payload={
                "project_id": gate_input.project_id,
                "environment": normalized_env,
                "action": gate_input.action,
                "resource_reference": gate_input.resource_reference,
                "estimated_monthly_delta_usd": str(monthly_delta),
                "estimated_hourly_delta_usd": str(hourly_delta),
                "metadata": gate_input.metadata,
                "dry_run": gate_input.dry_run,
            },
            response_payload={
                "mode": mode.value,
                "is_production": is_prod,
                "allocation_headroom_usd": (
                    str(allocation_headroom) if allocation_headroom is not None else None
                ),
                "credits_headroom_usd": str(credits_available),
            },
            estimated_monthly_delta_usd=monthly_delta,
            estimated_hourly_delta_usd=hourly_delta,
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

            if (
                decision == EnforcementDecisionType.REQUIRE_APPROVAL
                and not gate_input.dry_run
                and mode != EnforcementMode.SHADOW
            ):
                approval = EnforcementApprovalRequest(
                    tenant_id=tenant_id,
                    decision_id=decision_row.id,
                    status=EnforcementApprovalStatus.PENDING,
                    requested_by_user_id=actor_id,
                    expires_at=now + timedelta(seconds=ttl_seconds),
                )
                self.db.add(approval)

            self._append_decision_ledger_entry(decision_row=decision_row)
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
        mode = (
            policy.terraform_mode
            if source == EnforcementSource.TERRAFORM
            else policy.k8s_admission_mode
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

        fail_safe_details: dict[str, Any] | None = None
        if failure_metadata:
            fail_safe_details = {
                str(key): value
                for key, value in failure_metadata.items()
                if str(key).strip()
            } or None

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
            request_fingerprint=fingerprint,
            idempotency_key=idempotency_key,
            request_payload={
                "project_id": gate_input.project_id,
                "environment": normalized_env,
                "action": gate_input.action,
                "resource_reference": gate_input.resource_reference,
                "estimated_monthly_delta_usd": str(monthly_delta),
                "estimated_hourly_delta_usd": str(hourly_delta),
                "metadata": gate_input.metadata,
                "dry_run": gate_input.dry_run,
            },
            response_payload={
                "mode": mode.value,
                "is_production": _is_production_environment(normalized_env),
                "fail_safe_trigger": normalized_reason,
                "fail_safe_details": fail_safe_details,
            },
            estimated_monthly_delta_usd=monthly_delta,
            estimated_hourly_delta_usd=hourly_delta,
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
                approval = EnforcementApprovalRequest(
                    tenant_id=tenant_id,
                    decision_id=decision_row.id,
                    status=EnforcementApprovalStatus.PENDING,
                    requested_by_user_id=actor_id,
                    expires_at=now + timedelta(seconds=ttl_seconds),
                )
                self.db.add(approval)

            self._append_decision_ledger_entry(decision_row=decision_row)
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

        approval = EnforcementApprovalRequest(
            tenant_id=tenant_id,
            decision_id=decision_id,
            status=EnforcementApprovalStatus.PENDING,
            requested_by_user_id=actor_id,
            review_notes=(str(notes).strip() if notes else None),
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        self.db.add(approval)
        await self.db.commit()
        await self.db.refresh(approval)
        return approval

    async def list_pending_approvals(
        self,
        *,
        tenant_id: UUID,
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
        return [(row[0], row[1]) for row in rows.all()]

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
            decision.reservation_active = False
            decision.reserved_allocation_usd = Decimal("0")
            decision.reserved_credit_usd = Decimal("0")
            await self.db.commit()
            raise HTTPException(status_code=409, detail="Approval request has expired")

        required_permission = (
            APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD
            if _is_production_environment(decision.environment)
            else APPROVAL_PERMISSION_REMEDIATION_APPROVE_NONPROD
        )
        has_permission = await user_has_approval_permission(
            self.db,
            reviewer,
            required_permission,
        )
        if not has_permission:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Insufficient approval permission: {required_permission}"
                ),
            )

        policy = await self.get_or_create_policy(tenant_id)
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
            "approved_by_user_id": str(reviewer.id),
            "approved_at": now.isoformat(),
        }

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

        now = _utcnow()
        approval.status = EnforcementApprovalStatus.DENIED
        approval.reviewed_by_user_id = reviewer.id
        approval.review_notes = (str(notes).strip() if notes else None)
        approval.denied_at = now
        approval.updated_at = now

        # Release reservation after denial.
        decision.reservation_active = False
        decision.reserved_allocation_usd = Decimal("0")
        decision.reserved_credit_usd = Decimal("0")
        decision.response_payload = {
            **(decision.response_payload or {}),
            "approval_id": str(approval.id),
            "denied_by_user_id": str(reviewer.id),
            "denied_at": now.isoformat(),
        }

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

        if expected_source is not None and expected_source != decision.source:
            _token_reject(
                event="expected_source_mismatch",
                status_code=409,
                detail="Expected source mismatch",
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
                )
            )
            if len(exceptions) >= bounded_limit:
                break

        return exceptions

    async def reconcile_reservation(
        self,
        *,
        tenant_id: UUID,
        decision_id: UUID,
        actor_id: UUID,
        actual_monthly_delta_usd: Decimal,
        notes: str | None,
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
        if not decision.reservation_active:
            raise HTTPException(status_code=409, detail="Reservation is not active")

        actual = _quantize(_to_decimal(actual_monthly_delta_usd), "0.0001")
        if actual < Decimal("0"):
            raise HTTPException(
                status_code=422,
                detail="actual_monthly_delta_usd must be >= 0",
            )

        released_total = _quantize(
            _to_decimal(decision.reserved_allocation_usd)
            + _to_decimal(decision.reserved_credit_usd),
            "0.0001",
        )
        drift = _quantize(actual - released_total, "0.0001")
        status = (
            "matched"
            if drift == Decimal("0.0000")
            else ("overage" if drift > Decimal("0") else "savings")
        )
        now = _utcnow()

        reasons = list(decision.reason_codes or [])
        reasons.append("reservation_reconciled")
        if drift != Decimal("0.0000"):
            reasons.append("reservation_reconciliation_drift")
        decision.reason_codes = _unique_reason_codes(reasons)
        decision.reservation_active = False
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
                "notes": (str(notes).strip() if notes else None),
            },
        }

        await self.db.commit()
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
            .with_for_update()
        )
        decisions = list(rows.scalars().all())
        if not decisions:
            return OverdueReservationReconciliationResult(
                released_count=0,
                total_released_usd=Decimal("0.0000"),
                decision_ids=[],
                older_than_seconds=bounded_age,
            )

        total_released = Decimal("0.0000")
        decision_ids: list[UUID] = []
        for decision in decisions:
            released = _quantize(
                _to_decimal(decision.reserved_allocation_usd)
                + _to_decimal(decision.reserved_credit_usd),
                "0.0001",
            )
            total_released = _quantize(total_released + released, "0.0001")
            decision_ids.append(decision.id)

            reasons = list(decision.reason_codes or [])
            reasons.append("reservation_auto_released_sla")
            decision.reason_codes = _unique_reason_codes(reasons)
            decision.reservation_active = False
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
                },
            }

        await self.db.commit()
        ENFORCEMENT_RESERVATION_RECONCILIATIONS_TOTAL.labels(
            trigger="auto",
            status="auto_release",
        ).inc(len(decisions))
        return OverdueReservationReconciliationResult(
            released_count=len(decisions),
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
            decisions_csv=decisions_csv,
            approvals_csv=approvals_csv,
            parity_ok=parity_ok,
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
            writer.writerow(
                [
                    _sanitize_csv_cell(approval.id),
                    _sanitize_csv_cell(approval.decision_id),
                    _sanitize_csv_cell(approval.status.value),
                    _sanitize_csv_cell(approval.requested_by_user_id or ""),
                    _sanitize_csv_cell(approval.reviewed_by_user_id or ""),
                    _sanitize_csv_cell(approval.review_notes or ""),
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
            reserved_total_usd=reserved_total,
            approval_required=bool(decision_row.approval_required),
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

    async def _get_active_credit_headroom(
        self,
        *,
        tenant_id: UUID,
        scope_key: str,
        now: datetime,
        reserved_credit: Decimal,
    ) -> Decimal:
        normalized_scope = str(scope_key or "default").strip().lower() or "default"
        total = (
            await self.db.execute(
                select(func.coalesce(func.sum(EnforcementCreditGrant.remaining_amount_usd), 0))
                .where(EnforcementCreditGrant.tenant_id == tenant_id)
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

        return max(Decimal("0"), _to_decimal(total) - reserved_credit)

    def _mode_violation_decision(self, mode: EnforcementMode) -> EnforcementDecisionType:
        if mode == EnforcementMode.SHADOW:
            return EnforcementDecisionType.ALLOW
        if mode == EnforcementMode.SOFT:
            return EnforcementDecisionType.REQUIRE_APPROVAL
        return EnforcementDecisionType.DENY

    def _evaluate_budget_waterfall(
        self,
        *,
        mode: EnforcementMode,
        monthly_delta: Decimal,
        allocation_headroom: Decimal | None,
        credits_headroom: Decimal,
        reasons: list[str],
    ) -> tuple[EnforcementDecisionType, Decimal, Decimal]:
        if allocation_headroom is None:
            return EnforcementDecisionType.ALLOW, Decimal("0"), Decimal("0")

        available_alloc = max(Decimal("0"), allocation_headroom)
        available_credits = max(Decimal("0"), credits_headroom)

        if monthly_delta <= available_alloc:
            return EnforcementDecisionType.ALLOW, monthly_delta, Decimal("0")

        if monthly_delta <= (available_alloc + available_credits):
            reasons.append("credit_waterfall_used")
            return (
                EnforcementDecisionType.ALLOW_WITH_CREDITS,
                available_alloc,
                monthly_delta - available_alloc,
            )

        reasons.append("budget_exceeded")
        if mode == EnforcementMode.SHADOW:
            reasons.append("shadow_mode_budget_override")
            return EnforcementDecisionType.ALLOW, Decimal("0"), Decimal("0")
        if mode == EnforcementMode.SOFT:
            reasons.append("soft_mode_budget_escalation")
            return EnforcementDecisionType.REQUIRE_APPROVAL, available_alloc, available_credits
        return EnforcementDecisionType.DENY, Decimal("0"), Decimal("0")

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
                )
            )
        ).scalar_one_or_none()
        if approval is None:
            raise HTTPException(status_code=404, detail="Approval request not found")

        decision = (
            await self.db.execute(
                select(EnforcementDecision).where(
                    EnforcementDecision.id == approval.decision_id,
                    EnforcementDecision.tenant_id == tenant_id,
                )
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
                            "decision_id",
                            "approval_id",
                            "source",
                            "environment",
                            "request_fingerprint",
                            "max_monthly_delta_usd",
                            "resource_reference",
                        ]
                    },
                )
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

        return ApprovalTokenContext(
            approval_id=_uuid_claim("approval_id"),
            decision_id=_uuid_claim("decision_id"),
            tenant_id=_uuid_claim("tenant_id"),
            source=source,
            environment=str(payload.get("environment", "")).strip(),
            request_fingerprint=request_fingerprint,
            resource_reference=resource_reference,
            max_monthly_delta_usd=max_monthly_delta,
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
            "decision_id": str(decision.id),
            "approval_id": str(approval.id),
            "source": decision.source.value,
            "environment": decision.environment,
            "request_fingerprint": decision.request_fingerprint,
            "max_monthly_delta_usd": str(
                _to_decimal(decision.estimated_monthly_delta_usd)
            ),
            "resource_reference": decision.resource_reference,
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

    return {
        "decision": decision.decision.value,
        "reason_codes": list(decision.reason_codes or []),
        "decision_id": decision.id,
        "policy_version": int(decision.policy_version),
        "approval_required": bool(decision.approval_required),
        "approval_request_id": approval.id if approval is not None else None,
        "approval_token": result.approval_token,
        "ttl_seconds": int(result.ttl_seconds),
        "request_fingerprint": decision.request_fingerprint,
        "reservation_active": bool(decision.reservation_active),
    }
