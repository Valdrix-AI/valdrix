from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enforcement import (
    EnforcementApprovalRequest,
    EnforcementDecision,
    EnforcementPolicy,
)
from app.shared.core.auth import CurrentUser
from app.shared.core.approval_permissions import normalize_approval_permission


def default_approval_routing_trace(
    *,
    policy: EnforcementPolicy,
    decision: EnforcementDecision,
    normalize_environment_fn: Callable[[str], str],
    is_production_environment_fn: Callable[[str], bool],
    default_required_permission_for_environment_fn: Callable[[str], str],
    default_allowed_reviewer_roles: tuple[str, ...],
) -> dict[str, Any]:
    environment = normalize_environment_fn(decision.environment)
    is_prod = is_production_environment_fn(environment)
    return {
        "rule_id": f"default-{environment}",
        "matched_rule": "default",
        "required_permission": default_required_permission_for_environment_fn(
            environment
        ),
        "allowed_reviewer_roles": list(default_allowed_reviewer_roles),
        "require_requester_reviewer_separation": bool(
            policy.enforce_prod_requester_reviewer_separation
            if is_prod
            else policy.enforce_nonprod_requester_reviewer_separation
        ),
        "routing_conditions": {
            "environment": environment,
        },
    }


def extract_decision_risk_level(
    decision: EnforcementDecision,
) -> str | None:
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


def resolve_approval_routing_trace(
    *,
    policy: EnforcementPolicy,
    decision: EnforcementDecision,
    default_approval_routing_trace_fn: Callable[..., dict[str, Any]],
    extract_decision_risk_level_fn: Callable[[EnforcementDecision], str | None],
    normalize_environment_fn: Callable[[str], str],
    normalize_string_list_fn: Callable[..., list[str]],
    normalize_allowed_reviewer_roles_fn: Callable[[Any], list[str]],
    quantize_fn: Callable[[Decimal, str], Decimal],
    to_decimal_fn: Callable[[Any], Decimal],
) -> dict[str, Any]:
    default_trace = default_approval_routing_trace_fn(policy=policy, decision=decision)
    rules = (
        list(policy.approval_routing_rules)
        if isinstance(policy.approval_routing_rules, list)
        else []
    )
    if not rules:
        return default_trace

    environment = normalize_environment_fn(decision.environment)
    action = str(decision.action or "").strip().lower()
    monthly_delta = quantize_fn(to_decimal_fn(decision.estimated_monthly_delta_usd), "0.0001")
    risk_level = extract_decision_risk_level_fn(decision)

    for index, raw_rule in enumerate(rules, start=1):
        if not isinstance(raw_rule, Mapping):
            continue
        if not bool(raw_rule.get("enabled", True)):
            continue

        environments = normalize_string_list_fn(
            raw_rule.get("environments"),
            normalizer=normalize_environment_fn,
        )
        if environments and environment not in environments:
            continue

        action_prefixes = normalize_string_list_fn(raw_rule.get("action_prefixes"))
        if action_prefixes and not any(action.startswith(prefix) for prefix in action_prefixes):
            continue

        min_monthly_delta_raw = raw_rule.get("min_monthly_delta_usd")
        max_monthly_delta_raw = raw_rule.get("max_monthly_delta_usd")
        if min_monthly_delta_raw is not None:
            min_monthly_delta = quantize_fn(to_decimal_fn(min_monthly_delta_raw), "0.0001")
            if monthly_delta < min_monthly_delta:
                continue
        if max_monthly_delta_raw is not None:
            max_monthly_delta = quantize_fn(to_decimal_fn(max_monthly_delta_raw), "0.0001")
            if monthly_delta > max_monthly_delta:
                continue

        risk_levels = normalize_string_list_fn(raw_rule.get("risk_levels"))
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
        allowed_reviewer_roles = normalize_allowed_reviewer_roles_fn(
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
                        quantize_fn(
                            to_decimal_fn(min_monthly_delta_raw),
                            "0.0001",
                        )
                    )
                    if min_monthly_delta_raw is not None
                    else None
                ),
                "max_monthly_delta_usd": (
                    str(
                        quantize_fn(
                            to_decimal_fn(max_monthly_delta_raw),
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


def routing_trace_or_default(
    *,
    policy: EnforcementPolicy,
    decision: EnforcementDecision,
    approval: EnforcementApprovalRequest,
    resolve_approval_routing_trace_fn: Callable[..., dict[str, Any]],
    normalize_allowed_reviewer_roles_fn: Callable[[Any], list[str]],
) -> dict[str, Any]:
    trace = approval.routing_trace if isinstance(approval.routing_trace, dict) else {}
    required_permission = normalize_approval_permission(trace.get("required_permission"))
    allowed_reviewer_roles = normalize_allowed_reviewer_roles_fn(
        trace.get("allowed_reviewer_roles")
        if isinstance(trace.get("allowed_reviewer_roles"), list)
        else None
    )
    has_rule_id = bool(str(trace.get("rule_id") or "").strip())
    has_separation_flag = isinstance(
        trace.get("require_requester_reviewer_separation"), bool
    )
    if required_permission is None or not has_rule_id or not has_separation_flag:
        return resolve_approval_routing_trace_fn(policy=policy, decision=decision)

    return {
        **trace,
        "required_permission": required_permission,
        "allowed_reviewer_roles": allowed_reviewer_roles,
        "rule_id": str(trace.get("rule_id")).strip()[:64],
        "require_requester_reviewer_separation": bool(
            trace.get("require_requester_reviewer_separation")
        ),
    }


async def enforce_reviewer_authority(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    policy: EnforcementPolicy,
    approval: EnforcementApprovalRequest,
    decision: EnforcementDecision,
    reviewer: CurrentUser,
    enforce_requester_separation: bool,
    routing_trace_or_default_fn: Callable[..., dict[str, Any]],
    normalize_role_value_fn: Callable[[Any], str],
    normalize_allowed_reviewer_roles_fn: Callable[[Any], list[str]],
    user_has_approval_permission_fn: Callable[[AsyncSession, CurrentUser, str], Awaitable[bool]],
) -> dict[str, Any]:
    routing_trace = routing_trace_or_default_fn(
        policy=policy,
        decision=decision,
        approval=approval,
    )
    if routing_trace != (approval.routing_trace or {}):
        approval.routing_rule_id = str(routing_trace.get("rule_id") or "").strip() or None
        approval.routing_trace = routing_trace

    reviewer_role = normalize_role_value_fn(reviewer.role)
    allowed_reviewer_roles = normalize_allowed_reviewer_roles_fn(
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

    has_permission = await user_has_approval_permission_fn(
        db,
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
