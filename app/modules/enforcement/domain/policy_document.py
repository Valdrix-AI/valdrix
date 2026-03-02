from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field

from app.models.enforcement import EnforcementMode

POLICY_DOCUMENT_SCHEMA_VERSION = "valdrics.enforcement.policy.v1"


class ApprovalRoutingRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(..., min_length=1, max_length=64)
    enabled: bool = Field(default=True)
    environments: list[str] = Field(default_factory=list)
    action_prefixes: list[str] = Field(default_factory=list)
    min_monthly_delta_usd: Decimal | None = Field(default=None, ge=0)
    max_monthly_delta_usd: Decimal | None = Field(default=None, ge=0)
    risk_levels: list[str] = Field(default_factory=list)
    required_permission: str | None = Field(default=None, min_length=1, max_length=128)
    allowed_reviewer_roles: list[str] = Field(default_factory=lambda: ["owner", "admin"])
    require_requester_reviewer_separation: bool | None = None


class PolicyDocumentModeMatrix(BaseModel):
    model_config = ConfigDict(extra="forbid")

    terraform_default: EnforcementMode = Field(default=EnforcementMode.SOFT)
    terraform_prod: EnforcementMode = Field(default=EnforcementMode.SOFT)
    terraform_nonprod: EnforcementMode = Field(default=EnforcementMode.SOFT)
    k8s_admission_default: EnforcementMode = Field(default=EnforcementMode.SOFT)
    k8s_admission_prod: EnforcementMode = Field(default=EnforcementMode.SOFT)
    k8s_admission_nonprod: EnforcementMode = Field(default=EnforcementMode.SOFT)


class PolicyDocumentApprovalMatrix(BaseModel):
    model_config = ConfigDict(extra="forbid")

    require_approval_prod: bool = Field(default=True)
    require_approval_nonprod: bool = Field(default=False)
    enforce_prod_requester_reviewer_separation: bool = Field(default=True)
    enforce_nonprod_requester_reviewer_separation: bool = Field(default=False)
    routing_rules: list[ApprovalRoutingRule] = Field(default_factory=list)


class PolicyDocumentEntitlementMatrix(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_monthly_ceiling_usd: Decimal | None = Field(default=None, ge=0)
    enterprise_monthly_ceiling_usd: Decimal | None = Field(default=None, ge=0)
    auto_approve_below_monthly_usd: Decimal = Field(default=Decimal("25"), ge=0)
    hard_deny_above_monthly_usd: Decimal = Field(default=Decimal("5000"), gt=0)


class PolicyDocumentExecutionMatrix(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_ttl_seconds: int = Field(default=900, ge=60, le=86400)
    action_max_attempts: int = Field(default=3, ge=1, le=10)
    action_retry_backoff_seconds: int = Field(default=60, ge=1, le=86400)
    action_lease_ttl_seconds: int = Field(default=300, ge=30, le=3600)


class PolicyDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["valdrics.enforcement.policy.v1"] = (
        "valdrics.enforcement.policy.v1"
    )
    mode_matrix: PolicyDocumentModeMatrix = Field(
        default_factory=PolicyDocumentModeMatrix
    )
    approval: PolicyDocumentApprovalMatrix = Field(
        default_factory=PolicyDocumentApprovalMatrix
    )
    entitlements: PolicyDocumentEntitlementMatrix = Field(
        default_factory=PolicyDocumentEntitlementMatrix
    )
    execution: PolicyDocumentExecutionMatrix = Field(
        default_factory=PolicyDocumentExecutionMatrix
    )


def _normalize_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_json_value(inner)
            for key, inner in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"Unsupported policy document value type: {type(value)}")


def canonical_policy_document_payload(
    document: PolicyDocument | Mapping[str, Any],
) -> dict[str, Any]:
    if isinstance(document, PolicyDocument):
        payload = document.model_dump(mode="json")
    elif isinstance(document, Mapping):
        payload = PolicyDocument.model_validate(document).model_dump(mode="json")
    else:
        raise TypeError(f"Unsupported policy document input type: {type(document)}")
    normalized = _normalize_json_value(payload)
    if not isinstance(normalized, dict):
        raise TypeError("Canonical policy document payload must be a mapping")
    return normalized


def policy_document_sha256(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
