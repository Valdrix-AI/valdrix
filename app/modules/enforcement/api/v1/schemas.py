from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enforcement import EnforcementMode, EnforcementSource


class GateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(default="default", min_length=1, max_length=128)
    environment: str = Field(default="nonprod", min_length=1, max_length=32)
    action: str = Field(..., min_length=1, max_length=64)
    resource_reference: str = Field(..., min_length=1, max_length=512)
    estimated_monthly_delta_usd: Decimal = Field(..., ge=0)
    estimated_hourly_delta_usd: Decimal = Field(default=Decimal("0"), ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, min_length=4, max_length=128)
    dry_run: bool = Field(default=False)


class GateDecisionResponse(BaseModel):
    decision: str
    reason_codes: list[str]
    decision_id: UUID
    policy_version: int
    approval_required: bool
    approval_request_id: UUID | None = None
    approval_token: str | None = None
    ttl_seconds: int
    request_fingerprint: str
    reservation_active: bool


class PolicyResponse(BaseModel):
    terraform_mode: EnforcementMode
    k8s_admission_mode: EnforcementMode
    require_approval_for_prod: bool
    require_approval_for_nonprod: bool
    auto_approve_below_monthly_usd: Decimal
    hard_deny_above_monthly_usd: Decimal
    default_ttl_seconds: int
    policy_version: int
    updated_at: datetime


class PolicyUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    terraform_mode: EnforcementMode = Field(default=EnforcementMode.SOFT)
    k8s_admission_mode: EnforcementMode = Field(default=EnforcementMode.SOFT)
    require_approval_for_prod: bool = Field(default=True)
    require_approval_for_nonprod: bool = Field(default=False)
    auto_approve_below_monthly_usd: Decimal = Field(default=Decimal("25"), ge=0)
    hard_deny_above_monthly_usd: Decimal = Field(default=Decimal("5000"), gt=0)
    default_ttl_seconds: int = Field(default=900, ge=60, le=86400)


class BudgetUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_key: str = Field(default="default", min_length=1, max_length=128)
    monthly_limit_usd: Decimal = Field(..., ge=0)
    active: bool = Field(default=True)


class BudgetResponse(BaseModel):
    id: UUID
    scope_key: str
    monthly_limit_usd: Decimal
    active: bool
    created_at: datetime
    updated_at: datetime


class CreditCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_key: str = Field(default="default", min_length=1, max_length=128)
    total_amount_usd: Decimal = Field(..., gt=0)
    expires_at: datetime | None = None
    reason: str | None = Field(default=None, max_length=500)


class CreditResponse(BaseModel):
    id: UUID
    scope_key: str
    total_amount_usd: Decimal
    remaining_amount_usd: Decimal
    expires_at: datetime | None
    reason: str | None
    active: bool
    created_at: datetime


class ApprovalCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: UUID
    notes: str | None = Field(default=None, max_length=1000)


class ApprovalReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notes: str | None = Field(default=None, max_length=1000)


class ApprovalTokenConsumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_token: str = Field(..., min_length=32, max_length=8192)
    expected_source: EnforcementSource | None = None
    expected_environment: str | None = Field(default=None, min_length=1, max_length=32)
    expected_request_fingerprint: str | None = Field(
        default=None,
        min_length=32,
        max_length=64,
    )
    expected_resource_reference: str | None = Field(
        default=None,
        min_length=1,
        max_length=512,
    )


class ReservationReconcileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actual_monthly_delta_usd: Decimal = Field(..., ge=0)
    notes: str | None = Field(default=None, max_length=1000)


class ReservationReconcileOverdueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    older_than_seconds: int | None = Field(default=None, ge=60, le=604800)
    limit: int = Field(default=200, ge=1, le=1000)


class ApprovalQueueItem(BaseModel):
    approval_id: UUID
    decision_id: UUID
    status: str
    source: str
    environment: str
    project_id: str
    action: str
    resource_reference: str
    estimated_monthly_delta_usd: Decimal
    reason_codes: list[str]
    expires_at: datetime
    created_at: datetime


class ApprovalReviewResponse(BaseModel):
    status: str
    approval_id: UUID
    decision_id: UUID
    approval_token: str | None = None
    token_expires_at: datetime | None = None


class ApprovalTokenConsumeResponse(BaseModel):
    status: str
    approval_id: UUID
    decision_id: UUID
    source: str
    environment: str
    project_id: str
    action: str
    resource_reference: str
    request_fingerprint: str
    max_monthly_delta_usd: Decimal
    token_expires_at: datetime
    consumed_at: datetime


class ActiveReservationItem(BaseModel):
    decision_id: UUID
    source: str
    environment: str
    project_id: str
    action: str
    resource_reference: str
    reason_codes: list[str]
    reserved_allocation_usd: Decimal
    reserved_credit_usd: Decimal
    reserved_total_usd: Decimal
    created_at: datetime
    age_seconds: int


class ReservationReconcileResponse(BaseModel):
    decision_id: UUID
    status: str
    released_reserved_usd: Decimal
    actual_monthly_delta_usd: Decimal
    drift_usd: Decimal
    reservation_active: bool
    reconciled_at: datetime


class ReservationReconcileOverdueResponse(BaseModel):
    released_count: int
    total_released_usd: Decimal
    decision_ids: list[UUID]
    older_than_seconds: int


class ReservationReconciliationExceptionItem(BaseModel):
    decision_id: UUID
    source: str
    environment: str
    project_id: str
    action: str
    resource_reference: str
    expected_reserved_usd: Decimal
    actual_monthly_delta_usd: Decimal
    drift_usd: Decimal
    status: str
    reconciled_at: datetime | None
    notes: str | None


class EnforcementExportParityResponse(BaseModel):
    generated_at: datetime
    window_start: datetime
    window_end: datetime
    decision_count_db: int = Field(..., ge=0)
    decision_count_exported: int = Field(..., ge=0)
    approval_count_db: int = Field(..., ge=0)
    approval_count_exported: int = Field(..., ge=0)
    decisions_sha256: str = Field(..., min_length=64, max_length=64)
    approvals_sha256: str = Field(..., min_length=64, max_length=64)
    parity_ok: bool


class DecisionLedgerItem(BaseModel):
    ledger_id: UUID
    decision_id: UUID
    source: str
    environment: str
    project_id: str
    action: str
    resource_reference: str
    decision: str
    reason_codes: list[str]
    policy_version: int
    request_fingerprint: str
    idempotency_key: str
    estimated_monthly_delta_usd: Decimal
    estimated_hourly_delta_usd: Decimal
    reserved_total_usd: Decimal
    approval_required: bool
    request_payload_sha256: str
    response_payload_sha256: str
    decision_created_at: datetime
    recorded_at: datetime
