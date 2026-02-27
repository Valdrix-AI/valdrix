from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.modules.enforcement.api.v1 import exports, reservations


def test_resolve_idempotency_key_prefers_header_and_validates_length() -> None:
    assert (
        reservations._resolve_idempotency_key(
            header_value="header-key",
            body_value="body-key",
        )
        == "header-key"
    )
    assert (
        reservations._resolve_idempotency_key(
            header_value=None,
            body_value="body-key",
        )
        == "body-key"
    )
    assert (
        reservations._resolve_idempotency_key(
            header_value=None,
            body_value="   ",
        )
        is None
    )

    with pytest.raises(HTTPException):
        reservations._resolve_idempotency_key(
            header_value="abc",
            body_value=None,
        )
    with pytest.raises(HTTPException):
        reservations._resolve_idempotency_key(
            header_value="x" * 129,
            body_value=None,
        )


def test_reservation_reconcile_sla_seconds_bounds_and_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        reservations,
        "get_settings",
        lambda: SimpleNamespace(
            ENFORCEMENT_RESERVATION_RECONCILIATION_SLA_SECONDS="bad"
        ),
    )
    assert reservations._reservation_reconcile_sla_seconds() == 86400

    monkeypatch.setattr(
        reservations,
        "get_settings",
        lambda: SimpleNamespace(ENFORCEMENT_RESERVATION_RECONCILIATION_SLA_SECONDS=1),
    )
    assert reservations._reservation_reconcile_sla_seconds() == 60

    monkeypatch.setattr(
        reservations,
        "get_settings",
        lambda: SimpleNamespace(
            ENFORCEMENT_RESERVATION_RECONCILIATION_SLA_SECONDS=10_000_000
        ),
    )
    assert reservations._reservation_reconcile_sla_seconds() == 604800


def test_exports_resolve_window_validates_order_and_max_days(monkeypatch) -> None:
    monkeypatch.setattr(
        exports,
        "get_settings",
        lambda: SimpleNamespace(ENFORCEMENT_EXPORT_MAX_DAYS=30),
    )

    start, end = exports._resolve_window(
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 28),
    )
    assert start.date() == date(2026, 2, 1)
    assert end.date() == date(2026, 2, 28)

    with pytest.raises(HTTPException):
        exports._resolve_window(
            start_date=date(2026, 2, 10),
            end_date=date(2026, 2, 9),
        )

    with pytest.raises(HTTPException):
        exports._resolve_window(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 2, 15),
        )


def test_exports_resolve_max_rows_validates_bounds(monkeypatch) -> None:
    monkeypatch.setattr(
        exports,
        "get_settings",
        lambda: SimpleNamespace(ENFORCEMENT_EXPORT_MAX_ROWS=500),
    )

    assert exports._resolve_max_rows(None) == 500
    assert exports._resolve_max_rows(50) == 50

    with pytest.raises(HTTPException):
        exports._resolve_max_rows(0)

    with pytest.raises(HTTPException):
        exports._resolve_max_rows(501)
