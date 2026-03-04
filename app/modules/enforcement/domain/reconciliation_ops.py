from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException


def build_reconciliation_exception_payloads(
    *,
    decisions: Iterable[Any],
    bounded_limit: int,
    quantize_fn: Callable[[Decimal, str], Decimal],
    to_decimal_fn: Callable[[Any], Decimal],
    parse_iso_datetime_fn: Callable[[Any], datetime | None],
) -> list[dict[str, Any]]:
    exceptions: list[dict[str, Any]] = []
    for decision in decisions:
        response_payload = decision.response_payload or {}
        reconciliation = response_payload.get("reservation_reconciliation")
        if not isinstance(reconciliation, dict):
            continue

        drift_usd = quantize_fn(to_decimal_fn(reconciliation.get("drift_usd")), "0.0001")
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
                    {str(k): str(v) for k, v in raw_item.items() if str(k).strip()}
                )

        exceptions.append(
            {
                "decision": decision,
                "expected_reserved_usd": quantize_fn(
                    to_decimal_fn(reconciliation.get("expected_reserved_usd")),
                    "0.0001",
                ),
                "actual_monthly_delta_usd": quantize_fn(
                    to_decimal_fn(reconciliation.get("actual_monthly_delta_usd")),
                    "0.0001",
                ),
                "drift_usd": drift_usd,
                "status": status,
                "reconciled_at": parse_iso_datetime_fn(reconciliation.get("reconciled_at")),
                "notes": (
                    str(reconciliation.get("notes")).strip() or None
                    if reconciliation.get("notes") is not None
                    else None
                ),
                "credit_settlement": credit_settlement_rows,
            }
        )
        if len(exceptions) >= bounded_limit:
            break

    return exceptions


def build_reservation_reconciliation_replay_payload(
    *,
    decision: Any,
    actual_monthly_delta_usd: Decimal,
    notes: str | None,
    idempotency_key: str | None,
    quantize_fn: Callable[[Decimal, str], Decimal],
    to_decimal_fn: Callable[[Any], Decimal],
    parse_iso_datetime_fn: Callable[[Any], datetime | None],
    utcnow_fn: Callable[[], datetime],
) -> dict[str, Any] | None:
    normalized_key = str(idempotency_key or "").strip()
    if not normalized_key:
        return None

    response_payload = (
        decision.response_payload if isinstance(decision.response_payload, dict) else {}
    )
    reconciliation = response_payload.get("reservation_reconciliation")
    if not isinstance(reconciliation, dict):
        return None

    stored_key = str(reconciliation.get("idempotency_key") or "").strip()
    if not stored_key or stored_key != normalized_key:
        return None

    expected_actual = quantize_fn(
        to_decimal_fn(reconciliation.get("actual_monthly_delta_usd")),
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

    drift = quantize_fn(to_decimal_fn(reconciliation.get("drift_usd")), "0.0001")
    released_reserved = quantize_fn(
        to_decimal_fn(reconciliation.get("expected_reserved_usd")),
        "0.0001",
    )
    reconciled_at = parse_iso_datetime_fn(reconciliation.get("reconciled_at")) or utcnow_fn()
    return {
        "released_reserved_usd": released_reserved,
        "actual_monthly_delta_usd": expected_actual,
        "drift_usd": drift,
        "status": status,
        "reconciled_at": reconciled_at,
    }

