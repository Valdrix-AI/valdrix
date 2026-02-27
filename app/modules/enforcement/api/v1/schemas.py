from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.enforcement.domain.policy_document import (
    ApprovalRoutingRule,
    PolicyDocument,
)
from app.models.enforcement import (
    EnforcementActionStatus,
    EnforcementCreditPoolType,
    EnforcementMode,
    EnforcementSource,
)


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
    approval_token_contract: Literal["approval_flow_only"] = "approval_flow_only"
    ttl_seconds: int
    request_fingerprint: str
    reservation_active: bool
    computed_context: dict[str, Any] | None = None


class TerraformPreflightRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(..., min_length=1, max_length=128)
    stage: str = Field(default="pre_plan", min_length=1, max_length=64)
    workspace_id: str | None = Field(default=None, min_length=1, max_length=128)
    workspace_name: str | None = Field(default=None, min_length=1, max_length=256)
    callback_url: str | None = Field(default=None, min_length=1, max_length=2048)
    run_url: str | None = Field(default=None, min_length=1, max_length=2048)
    project_id: str = Field(default="default", min_length=1, max_length=128)
    environment: str = Field(default="nonprod", min_length=1, max_length=32)
    action: str = Field(default="terraform.apply", min_length=1, max_length=64)
    resource_reference: str = Field(..., min_length=1, max_length=512)
    estimated_monthly_delta_usd: Decimal = Field(..., ge=0)
    estimated_hourly_delta_usd: Decimal = Field(default=Decimal("0"), ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, min_length=4, max_length=128)
    expected_request_fingerprint: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
    )
    dry_run: bool = Field(default=False)


class TerraformPreflightBinding(BaseModel):
    expected_source: EnforcementSource
    expected_project_id: str
    expected_environment: str
    expected_request_fingerprint: str
    expected_resource_reference: str


class TerraformPreflightContinuation(BaseModel):
    approval_consume_endpoint: str
    binding: TerraformPreflightBinding


class TerraformPreflightResponse(BaseModel):
    run_id: str
    stage: str
    decision: str
    reason_codes: list[str]
    decision_id: UUID
    policy_version: int
    approval_required: bool
    approval_request_id: UUID | None = None
    approval_token_contract: Literal["approval_flow_only"] = "approval_flow_only"
    ttl_seconds: int
    request_fingerprint: str
    reservation_active: bool
    computed_context: dict[str, Any] | None = None
    continuation: TerraformPreflightContinuation


class K8sAdmissionReviewKind(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group: str = Field(default="")
    version: str = Field(default="v1")
    kind: str = Field(..., min_length=1, max_length=128)


class K8sAdmissionReviewResource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group: str = Field(default="")
    version: str = Field(default="v1")
    resource: str = Field(..., min_length=1, max_length=128)


class K8sAdmissionReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    uid: str = Field(..., min_length=1, max_length=256)
    kind: K8sAdmissionReviewKind
    resource: K8sAdmissionReviewResource
    sub_resource: str | None = Field(default=None, alias="subResource", max_length=128)
    request_kind: K8sAdmissionReviewKind | None = Field(
        default=None,
        alias="requestKind",
    )
    request_resource: K8sAdmissionReviewResource | None = Field(
        default=None,
        alias="requestResource",
    )
    request_sub_resource: str | None = Field(
        default=None,
        alias="requestSubResource",
        max_length=128,
    )
    name: str | None = Field(default=None, max_length=256)
    namespace: str | None = Field(default=None, max_length=256)
    operation: Literal["CREATE", "UPDATE", "DELETE", "CONNECT"]
    user_info: dict[str, Any] = Field(default_factory=dict, alias="userInfo")
    obj: dict[str, Any] | None = Field(default=None, alias="object")
    old_object: dict[str, Any] | None = Field(default=None, alias="oldObject")
    dry_run: bool | None = Field(default=None, alias="dryRun")
    options: dict[str, Any] | None = None


class K8sAdmissionReviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    api_version: str = Field(default="admission.k8s.io/v1", alias="apiVersion")
    kind: str = Field(default="AdmissionReview", min_length=1, max_length=64)
    request: K8sAdmissionReviewRequest


class K8sAdmissionReviewStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: int | None = None
    reason: str | None = None
    message: str | None = None


class K8sAdmissionReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    uid: str
    allowed: bool
    status: K8sAdmissionReviewStatus | None = None
    warnings: list[str] = Field(default_factory=list)
    audit_annotations: dict[str, str] = Field(default_factory=dict, alias="auditAnnotations")


class K8sAdmissionReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    api_version: str = Field(default="admission.k8s.io/v1", alias="apiVersion")
    kind: str = Field(default="AdmissionReview", min_length=1, max_length=64)
    response: K8sAdmissionReviewResult


class CloudEventEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow")

    specversion: Literal["1.0"] = "1.0"
    id: str = Field(..., min_length=1, max_length=256)
    source: str = Field(..., min_length=1, max_length=1024)
    type: str = Field(..., min_length=1, max_length=512)
    subject: str | None = Field(default=None, max_length=1024)
    time: datetime | None = None
    datacontenttype: str | None = Field(default=None, max_length=256)
    dataschema: str | None = Field(default=None, max_length=2048)
    data: Any = None


class CloudEventGateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cloud_event: CloudEventEnvelope
    project_id: str = Field(default="default", min_length=1, max_length=128)
    environment: str = Field(default="nonprod", min_length=1, max_length=32)
    action: str = Field(default="cloud_event.observe", min_length=1, max_length=64)
    resource_reference: str | None = Field(default=None, min_length=1, max_length=512)
    estimated_monthly_delta_usd: Decimal = Field(default=Decimal("0"), ge=0)
    estimated_hourly_delta_usd: Decimal = Field(default=Decimal("0"), ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, min_length=4, max_length=128)
    expected_request_fingerprint: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
    )
    dry_run: bool = Field(default=False)


class PolicyResponse(BaseModel):
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
    approval_routing_rules: list[ApprovalRoutingRule]
    policy_document_schema_version: str
    policy_document_sha256: str
    policy_document: PolicyDocument
    policy_version: int
    updated_at: datetime


class PolicyUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    terraform_mode: EnforcementMode = Field(default=EnforcementMode.SOFT)
    terraform_mode_prod: EnforcementMode | None = None
    terraform_mode_nonprod: EnforcementMode | None = None
    k8s_admission_mode: EnforcementMode = Field(default=EnforcementMode.SOFT)
    k8s_admission_mode_prod: EnforcementMode | None = None
    k8s_admission_mode_nonprod: EnforcementMode | None = None
    require_approval_for_prod: bool = Field(default=True)
    require_approval_for_nonprod: bool = Field(default=False)
    enforce_prod_requester_reviewer_separation: bool = Field(default=True)
    enforce_nonprod_requester_reviewer_separation: bool = Field(default=False)
    plan_monthly_ceiling_usd: Decimal | None = Field(default=None, ge=0)
    enterprise_monthly_ceiling_usd: Decimal | None = Field(default=None, ge=0)
    auto_approve_below_monthly_usd: Decimal = Field(default=Decimal("25"), ge=0)
    hard_deny_above_monthly_usd: Decimal = Field(default=Decimal("5000"), gt=0)
    default_ttl_seconds: int = Field(default=900, ge=60, le=86400)
    approval_routing_rules: list[ApprovalRoutingRule] = Field(default_factory=list)
    policy_document: PolicyDocument | None = None


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

    pool_type: EnforcementCreditPoolType = Field(
        default=EnforcementCreditPoolType.RESERVED
    )
    scope_key: str = Field(default="default", min_length=1, max_length=128)
    total_amount_usd: Decimal = Field(..., gt=0)
    expires_at: datetime | None = None
    reason: str | None = Field(default=None, max_length=500)


class CreditResponse(BaseModel):
    id: UUID
    pool_type: EnforcementCreditPoolType
    scope_key: str
    total_amount_usd: Decimal
    remaining_amount_usd: Decimal
    expires_at: datetime | None
    reason: str | None
    active: bool
    created_at: datetime


class ActionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: UUID
    action_type: str = Field(..., min_length=1, max_length=64)
    target_reference: str = Field(..., min_length=1, max_length=512)
    request_payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, min_length=4, max_length=128)
    max_attempts: int | None = Field(default=None, ge=1, le=10)
    retry_backoff_seconds: int | None = Field(default=None, ge=1, le=86400)
    lease_ttl_seconds: int | None = Field(default=None, ge=30, le=3600)


class ActionListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: EnforcementActionStatus | None = None
    decision_id: UUID | None = None
    limit: int = Field(default=100, ge=1, le=500)


class ActionLeaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_type: str | None = Field(default=None, min_length=1, max_length=64)


class ActionCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_payload: dict[str, Any] = Field(default_factory=dict)


class ActionFailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_code: str = Field(..., min_length=1, max_length=64)
    error_message: str = Field(..., min_length=1, max_length=1000)
    retryable: bool = Field(default=True)
    result_payload: dict[str, Any] = Field(default_factory=dict)


class ActionCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=1000)


class ActionExecutionResponse(BaseModel):
    action_id: UUID
    decision_id: UUID
    approval_request_id: UUID | None = None
    action_type: str
    target_reference: str
    idempotency_key: str
    request_payload: dict[str, Any]
    request_payload_sha256: str
    status: EnforcementActionStatus
    attempt_count: int
    max_attempts: int
    retry_backoff_seconds: int
    lease_ttl_seconds: int
    next_retry_at: datetime
    locked_by_worker_id: UUID | None = None
    lease_expires_at: datetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    result_payload: dict[str, Any] | None = None
    result_payload_sha256: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


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
    expected_project_id: str | None = Field(default=None, min_length=1, max_length=128)
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
    idempotency_key: str | None = Field(default=None, min_length=4, max_length=128)


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
    routing_rule_id: str | None = None
    expires_at: datetime
    created_at: datetime


class ApprovalReviewResponse(BaseModel):
    status: str
    approval_id: UUID
    decision_id: UUID
    routing_rule_id: str | None = None
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
    max_hourly_delta_usd: Decimal
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
    credit_settlement: list[dict[str, str]] = Field(default_factory=list)


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
    policy_lineage_sha256: str = Field(..., min_length=64, max_length=64)
    policy_lineage_entries: int = Field(..., ge=0)
    computed_context_lineage_sha256: str = Field(..., min_length=64, max_length=64)
    computed_context_lineage_entries: int = Field(..., ge=0)
    parity_ok: bool
    manifest_content_sha256: str = Field(..., min_length=64, max_length=64)
    manifest_signature: str = Field(..., min_length=64, max_length=64)
    manifest_signature_algorithm: Literal["hmac-sha256"]
    manifest_signature_key_id: str = Field(..., min_length=1, max_length=64)


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
    policy_document_schema_version: str
    policy_document_sha256: str = Field(..., min_length=64, max_length=64)
    request_fingerprint: str
    idempotency_key: str
    estimated_monthly_delta_usd: Decimal
    estimated_hourly_delta_usd: Decimal
    burn_rate_daily_usd: Decimal | None = None
    forecast_eom_usd: Decimal | None = None
    risk_class: str | None = None
    risk_score: int | None = None
    anomaly_signal: bool | None = None
    reserved_total_usd: Decimal
    approval_required: bool
    approval_request_id: UUID | None = None
    approval_status: str | None = None
    request_payload_sha256: str
    response_payload_sha256: str
    decision_created_at: datetime
    recorded_at: datetime
