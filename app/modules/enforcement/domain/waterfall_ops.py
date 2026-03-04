from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any


def mode_violation_decision(
    *,
    mode: Any,
    shadow_mode: Any,
    soft_mode: Any,
    shadow_decision: Any,
    soft_decision: Any,
    hard_decision: Any,
) -> Any:
    if mode == shadow_mode:
        return shadow_decision
    if mode == soft_mode:
        return soft_decision
    return hard_decision


def mode_violation_reason_suffix(
    *,
    mode: Any,
    subject: str,
    shadow_mode: Any,
    soft_mode: Any,
) -> str:
    if mode == shadow_mode:
        return f"shadow_mode_{subject}_override"
    if mode == soft_mode:
        return f"soft_mode_{subject}_escalation"
    return f"hard_mode_{subject}_closed"


def evaluate_entitlement_waterfall(
    *,
    mode: Any,
    monthly_delta: Decimal,
    plan_headroom: Decimal | None,
    allocation_headroom: Decimal | None,
    reserved_credit_headroom: Decimal,
    emergency_credit_headroom: Decimal,
    enterprise_headroom: Decimal | None,
    quantize_fn: Callable[[Decimal, str], Decimal],
    to_decimal_fn: Callable[[Any], Decimal],
    mode_violation_decision_fn: Callable[[Any], Any],
    allow_decision: Any,
    allow_with_credits_decision: Any,
    soft_mode: Any,
) -> dict[str, Any]:
    requested = quantize_fn(to_decimal_fn(monthly_delta), "0.0001")
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
                str(quantize_fn(available, "0.0001"))
                if available is not None
                else "unbounded"
            ),
            "consumed_usd": str(quantize_fn(consumed, "0.0001")),
            "remaining_after_stage_usd": str(quantize_fn(remaining_after, "0.0001")),
        }

    if plan_headroom is not None:
        normalized_plan = max(Decimal("0.0000"), quantize_fn(plan_headroom, "0.0001"))
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
            return {
                "decision": mode_violation_decision_fn(mode),
                "reserve_allocation_usd": Decimal("0"),
                "reserve_reserved_credit_usd": Decimal("0"),
                "reserve_emergency_credit_usd": Decimal("0"),
                "reason_code": "plan_limit_exceeded",
                "stage_details": stage_details,
            }

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
            Decimal("0.0000"), quantize_fn(enterprise_headroom, "0.0001")
        )
        funding_target = min(requested, normalized_enterprise)
    else:
        normalized_enterprise = None

    remaining = funding_target
    if allocation_headroom is None:
        consumed_unbounded = quantize_fn(remaining, "0.0001")
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
        alloc_available = max(Decimal("0.0000"), quantize_fn(allocation_headroom, "0.0001"))
        reserved_alloc = quantize_fn(min(remaining, alloc_available), "0.0001")
        remaining = quantize_fn(remaining - reserved_alloc, "0.0001")
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
        Decimal("0.0000"), quantize_fn(reserved_credit_headroom, "0.0001")
    )
    reserved_credit = quantize_fn(min(remaining, reserved_available), "0.0001")
    remaining = quantize_fn(remaining - reserved_credit, "0.0001")
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
        Decimal("0.0000"), quantize_fn(emergency_credit_headroom, "0.0001")
    )
    emergency_credit = quantize_fn(min(remaining, emergency_available), "0.0001")
    remaining = quantize_fn(remaining - emergency_credit, "0.0001")
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
    enterprise_remaining = quantize_fn(requested - enterprise_consumable, "0.0001")
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
        return {
            "decision": mode_violation_decision_fn(mode),
            "reserve_allocation_usd": (
                reserved_alloc if mode == soft_mode else Decimal("0")
            ),
            "reserve_reserved_credit_usd": (
                reserved_credit if mode == soft_mode else Decimal("0")
            ),
            "reserve_emergency_credit_usd": (
                emergency_credit if mode == soft_mode else Decimal("0")
            ),
            "reason_code": "budget_exceeded",
            "stage_details": stage_details,
        }

    if enterprise_failed:
        return {
            "decision": mode_violation_decision_fn(mode),
            "reserve_allocation_usd": (
                reserved_alloc if mode == soft_mode else Decimal("0")
            ),
            "reserve_reserved_credit_usd": (
                reserved_credit if mode == soft_mode else Decimal("0")
            ),
            "reserve_emergency_credit_usd": (
                emergency_credit if mode == soft_mode else Decimal("0")
            ),
            "reason_code": "enterprise_ceiling_exceeded",
            "stage_details": stage_details,
        }

    return {
        "decision": (
            allow_decision
            if (reserved_credit + emergency_credit) == Decimal("0.0000")
            else allow_with_credits_decision
        ),
        "reserve_allocation_usd": reserved_alloc,
        "reserve_reserved_credit_usd": reserved_credit,
        "reserve_emergency_credit_usd": emergency_credit,
        "reason_code": None,
        "stage_details": stage_details,
    }


def evaluate_budget_waterfall(
    *,
    mode: Any,
    monthly_delta: Decimal,
    allocation_headroom: Decimal | None,
    credits_headroom: Decimal,
    reasons: list[str],
    evaluate_entitlement_waterfall_fn: Callable[..., Any],
    shadow_mode: Any,
    soft_mode: Any,
) -> tuple[Any, Decimal, Decimal]:
    result = evaluate_entitlement_waterfall_fn(
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
        if mode == shadow_mode:
            reasons.append("shadow_mode_budget_override")
        elif mode == soft_mode:
            reasons.append("soft_mode_budget_escalation")
    if (result.reserve_reserved_credit_usd + result.reserve_emergency_credit_usd) > Decimal(
        "0.0000"
    ):
        reasons.append("credit_waterfall_used")

    return (
        result.decision,
        result.reserve_allocation_usd,
        result.reserve_reserved_credit_usd,
    )

