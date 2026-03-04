from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Callable, Mapping
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.models.enforcement import (
    EnforcementApprovalRequest,
    EnforcementApprovalStatus,
    EnforcementDecision,
    EnforcementDecisionType,
    EnforcementMode,
    EnforcementSource,
)


async def evaluate_gate(
    *,
    service: Any,
    tenant_id: UUID,
    actor_id: UUID,
    source: EnforcementSource,
    gate_input: Any,
    gate_evaluation_result_cls: type[Any],
    stable_fingerprint_fn: Callable[[EnforcementSource, Any], str],
    normalize_environment_fn: Callable[[str], str],
    month_bounds_fn: Callable[[datetime], tuple[datetime, datetime]],
    quantize_fn: Callable[[Decimal, str], Decimal],
    to_decimal_fn: Callable[[Any], Decimal],
    is_production_environment_fn: Callable[[str], bool],
    unique_reason_codes_fn: Callable[[list[str]], list[str]],
    normalize_policy_document_schema_version_fn: Callable[[str | None], str],
    normalize_policy_document_sha256_fn: Callable[[str | None], str],
    utcnow_fn: Callable[[], datetime],
) -> Any:
    policy = await service.get_or_create_policy(tenant_id)
    normalized_env = normalize_environment_fn(gate_input.environment)
    mode, mode_scope = service._resolve_policy_mode(
        policy=policy,
        source=source,
        environment=normalized_env,
    )
    ttl_seconds = max(60, min(int(policy.default_ttl_seconds), 86400))

    fingerprint = stable_fingerprint_fn(source, gate_input)
    raw_idempotency_key = (gate_input.idempotency_key or fingerprint).strip()
    idempotency_key = raw_idempotency_key[:128] if raw_idempotency_key else fingerprint

    existing = await service._get_decision_by_idempotency(
        tenant_id=tenant_id,
        source=source,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        existing_approval = await service._get_approval_by_decision(existing.id)
        return gate_evaluation_result_cls(
            decision=existing,
            approval=existing_approval,
            approval_token=None,
            ttl_seconds=ttl_seconds,
        )

    await service._acquire_gate_evaluation_lock(policy=policy, source=source)

    # Re-check idempotency after lock acquisition to avoid duplicate work when
    # another worker commits while this request waits on the serialization lock.
    existing = await service._get_decision_by_idempotency(
        tenant_id=tenant_id,
        source=source,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        existing_approval = await service._get_approval_by_decision(existing.id)
        return gate_evaluation_result_cls(
            decision=existing,
            approval=existing_approval,
            approval_token=None,
            ttl_seconds=ttl_seconds,
        )

    now = utcnow_fn()
    month_start, month_end = month_bounds_fn(now)
    monthly_delta = quantize_fn(gate_input.estimated_monthly_delta_usd, "0.0001")
    hourly_delta = quantize_fn(gate_input.estimated_hourly_delta_usd, "0.000001")
    reasons: list[str] = []

    reserved_alloc_total, reserved_credit_total = await service._get_reserved_totals(
        tenant_id=tenant_id,
        month_start=month_start,
        month_end=month_end,
    )
    reserved_total_monthly = quantize_fn(
        to_decimal_fn(reserved_alloc_total) + to_decimal_fn(reserved_credit_total),
        "0.0001",
    )
    tenant_tier = await service._resolve_tenant_tier(tenant_id)
    plan_ceiling = await service._resolve_plan_monthly_ceiling_usd(
        policy=policy,
        tenant_tier=tenant_tier,
    )
    enterprise_ceiling = await service._resolve_enterprise_monthly_ceiling_usd(
        policy=policy,
        tenant_tier=tenant_tier,
    )
    plan_headroom = (
        quantize_fn(
            max(Decimal("0.0000"), to_decimal_fn(plan_ceiling) - reserved_total_monthly),
            "0.0001",
        )
        if plan_ceiling is not None
        else None
    )
    enterprise_headroom = (
        quantize_fn(
            max(Decimal("0.0000"), to_decimal_fn(enterprise_ceiling) - reserved_total_monthly),
            "0.0001",
        )
        if enterprise_ceiling is not None
        else None
    )

    budget = await service._get_effective_budget(
        tenant_id=tenant_id,
        scope_key=gate_input.project_id,
    )
    reserved_credit_headroom, emergency_credit_headroom = await service._get_credit_headrooms(
        tenant_id=tenant_id,
        scope_key=gate_input.project_id,
        now=now,
    )
    credits_available = quantize_fn(
        reserved_credit_headroom + emergency_credit_headroom,
        "0.0001",
    )

    if budget is None:
        allocation_headroom: Decimal | None = None
        reasons.append("no_budget_configured")
    else:
        allocation_headroom = max(
            Decimal("0"),
            to_decimal_fn(budget.monthly_limit_usd) - reserved_alloc_total,
        )

    is_prod = is_production_environment_fn(normalized_env)
    computed_context = await service._build_decision_computed_context(
        tenant_id=tenant_id,
        policy_version=int(policy.policy_version),
        gate_input=gate_input,
        now=now,
        is_production=is_prod,
    )
    approval_required = (
        policy.require_approval_for_prod if is_prod else policy.require_approval_for_nonprod
    )
    if monthly_delta <= to_decimal_fn(policy.auto_approve_below_monthly_usd):
        approval_required = False

    reserve_allocation = Decimal("0")
    reserve_reserved_credit = Decimal("0")
    reserve_emergency_credit = Decimal("0")
    reserve_credit = Decimal("0")
    reservation_active = False
    entitlement_result = None

    decision = EnforcementDecisionType.ALLOW
    computed_context_unavailable = (
        computed_context.data_source_mode == "unavailable"
        and monthly_delta > Decimal("0.0000")
    )
    if computed_context_unavailable:
        reasons.append("computed_context_unavailable")
        reasons.append(service._mode_violation_reason_suffix(mode, subject="cost_context"))
        decision = service._mode_violation_decision(mode)
    else:
        hard_deny_threshold = to_decimal_fn(policy.hard_deny_above_monthly_usd)
        if monthly_delta > hard_deny_threshold:
            reasons.append("hard_deny_threshold_exceeded")
            decision = service._mode_violation_decision(mode)
            if mode == EnforcementMode.SOFT:
                reasons.append("soft_mode_escalation")
            if mode == EnforcementMode.SHADOW:
                reasons.append("shadow_mode_override")
        else:
            entitlement_result = service._evaluate_entitlement_waterfall(
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
                        service._mode_violation_reason_suffix(
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
        reason_codes=unique_reason_codes_fn(reasons),
        policy_version=int(policy.policy_version),
        policy_document_schema_version=normalize_policy_document_schema_version_fn(
            policy.policy_document_schema_version
        ),
        policy_document_sha256=normalize_policy_document_sha256_fn(
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
                str(quantize_fn(to_decimal_fn(plan_ceiling), "0.0001"))
                if plan_ceiling is not None
                else None
            ),
            "plan_headroom_usd": (
                str(quantize_fn(to_decimal_fn(plan_headroom), "0.0001"))
                if plan_headroom is not None
                else None
            ),
            "enterprise_monthly_ceiling_usd": (
                str(quantize_fn(to_decimal_fn(enterprise_ceiling), "0.0001"))
                if enterprise_ceiling is not None
                else None
            ),
            "enterprise_headroom_usd": (
                str(quantize_fn(to_decimal_fn(enterprise_headroom), "0.0001"))
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
    service.db.add(decision_row)

    approval: EnforcementApprovalRequest | None = None
    try:
        # Ensure the decision id is materialized before creating approval rows.
        await service.db.flush()

        credit_allocations_payload: list[dict[str, str]] = []
        if reservation_active and reserve_credit > Decimal("0"):
            credit_allocations_payload = await service._reserve_credit_for_decision(
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
            approval_routing_trace = service._resolve_approval_routing_trace(
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
            service.db.add(approval)
            await service.db.flush()

        service._append_decision_ledger_entry(
            decision_row=decision_row,
            approval_row=approval,
        )
        await service.db.commit()
    except IntegrityError:
        await service.db.rollback()
        existing = await service._get_decision_by_idempotency(
            tenant_id=tenant_id,
            source=source,
            idempotency_key=idempotency_key,
        )
        if existing is None:
            raise
        existing_approval = await service._get_approval_by_decision(existing.id)
        return gate_evaluation_result_cls(
            decision=existing,
            approval=existing_approval,
            approval_token=None,
            ttl_seconds=ttl_seconds,
        )

    await service.db.refresh(decision_row)
    if approval is not None:
        await service.db.refresh(approval)

    return gate_evaluation_result_cls(
        decision=decision_row,
        approval=approval,
        approval_token=None,
        ttl_seconds=ttl_seconds,
    )


async def resolve_fail_safe_gate(
    *,
    service: Any,
    tenant_id: UUID,
    actor_id: UUID,
    source: EnforcementSource,
    gate_input: Any,
    failure_reason_code: str,
    failure_metadata: Mapping[str, Any] | None,
    gate_evaluation_result_cls: type[Any],
    stable_fingerprint_fn: Callable[[EnforcementSource, Any], str],
    normalize_environment_fn: Callable[[str], str],
    quantize_fn: Callable[[Decimal, str], Decimal],
    mode_violation_decision_fn: Callable[[EnforcementMode], EnforcementDecisionType],
    is_production_environment_fn: Callable[[str], bool],
    unique_reason_codes_fn: Callable[[list[str]], list[str]],
    normalize_policy_document_schema_version_fn: Callable[[str | None], str],
    normalize_policy_document_sha256_fn: Callable[[str | None], str],
    utcnow_fn: Callable[[], datetime],
) -> Any:
    now = utcnow_fn()
    normalized_env = normalize_environment_fn(gate_input.environment)
    policy = await service.get_or_create_policy(tenant_id)
    mode, mode_scope = service._resolve_policy_mode(
        policy=policy,
        source=source,
        environment=normalized_env,
    )
    ttl_seconds = max(60, min(int(policy.default_ttl_seconds), 86400))

    fingerprint = stable_fingerprint_fn(source, gate_input)
    raw_idempotency_key = (gate_input.idempotency_key or fingerprint).strip()
    idempotency_key = raw_idempotency_key[:128] if raw_idempotency_key else fingerprint

    existing = await service._get_decision_by_idempotency(
        tenant_id=tenant_id,
        source=source,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        existing_approval = await service._get_approval_by_decision(existing.id)
        return gate_evaluation_result_cls(
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

    monthly_delta = quantize_fn(gate_input.estimated_monthly_delta_usd, "0.0001")
    hourly_delta = quantize_fn(gate_input.estimated_hourly_delta_usd, "0.000001")
    decision = mode_violation_decision_fn(mode)
    is_prod = is_production_environment_fn(normalized_env)
    computed_context = await service._build_decision_computed_context(
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
        reason_codes=unique_reason_codes_fn(reasons),
        policy_version=int(policy.policy_version),
        policy_document_schema_version=normalize_policy_document_schema_version_fn(
            policy.policy_document_schema_version
        ),
        policy_document_sha256=normalize_policy_document_sha256_fn(
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
    service.db.add(decision_row)

    approval: EnforcementApprovalRequest | None = None
    try:
        await service.db.flush()

        if (
            decision == EnforcementDecisionType.REQUIRE_APPROVAL
            and not gate_input.dry_run
            and mode != EnforcementMode.SHADOW
        ):
            approval_routing_trace = service._resolve_approval_routing_trace(
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
            service.db.add(approval)
            await service.db.flush()

        service._append_decision_ledger_entry(
            decision_row=decision_row,
            approval_row=approval,
        )
        await service.db.commit()
    except IntegrityError:
        await service.db.rollback()
        existing = await service._get_decision_by_idempotency(
            tenant_id=tenant_id,
            source=source,
            idempotency_key=idempotency_key,
        )
        if existing is None:
            raise
        existing_approval = await service._get_approval_by_decision(existing.id)
        return gate_evaluation_result_cls(
            decision=existing,
            approval=existing_approval,
            approval_token=None,
            ttl_seconds=ttl_seconds,
        )

    await service.db.refresh(decision_row)
    if approval is not None:
        await service.db.refresh(approval)

    return gate_evaluation_result_cls(
        decision=decision_row,
        approval=approval,
        approval_token=None,
        ttl_seconds=ttl_seconds,
    )
