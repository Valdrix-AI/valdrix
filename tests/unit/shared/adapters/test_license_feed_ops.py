from __future__ import annotations

from datetime import datetime, timezone

from app.shared.adapters.license_feed_ops import (
    coerce_bool,
    iter_manual_cost_rows,
    list_manual_feed_activity,
    normalize_email,
    normalize_text,
    validate_manual_feed,
)


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise TypeError("invalid timestamp")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_normalization_helpers() -> None:
    assert normalize_text(" hi ") == "hi"
    assert normalize_text("   ") is None
    assert normalize_email(" USER@Example.com ") == "user@example.com"
    assert normalize_email("invalid") is None
    assert coerce_bool("true") is True
    assert coerce_bool("off") is False


def test_validate_manual_feed_contract() -> None:
    assert (
        validate_manual_feed(
            [{"timestamp": "2026-01-01T00:00:00Z", "cost_usd": 1.0}],
            is_number_fn=lambda value: isinstance(value, (int, float)),
        )
        is None
    )
    assert "at least one record" in str(
        validate_manual_feed([], is_number_fn=lambda _: True)
    )


def test_iter_manual_cost_rows_filters_by_window_and_shapes() -> None:
    rows = list(
        iter_manual_cost_rows(
            feed=[
                {"timestamp": "2026-01-01T00:00:00Z", "cost_usd": 2.5, "service": "A"},
                {"timestamp": "2025-12-01T00:00:00Z", "cost_usd": 10.0, "service": "B"},
            ],
            start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
            parse_timestamp_fn=_parse_timestamp,
            as_float_fn=lambda value, default=0.0: float(value) if value is not None else default,
            is_number_fn=lambda value: isinstance(value, (int, float)),
        )
    )
    assert len(rows) == 1
    assert rows[0]["service"] == "A"
    assert rows[0]["cost_usd"] == 2.5


def test_list_manual_feed_activity_consolidates_records() -> None:
    rows = list_manual_feed_activity(
        feed=[
            {
                "email": "u1@example.com",
                "last_login_at": "2026-01-01T00:00:00Z",
                "full_name": "User One",
            },
            {
                "email": "u1@example.com",
                "last_active_at": "2026-01-05T00:00:00Z",
                "is_admin": True,
            },
        ],
        parse_timestamp_fn=_parse_timestamp,
    )
    assert len(rows) == 1
    assert rows[0]["email"] == "u1@example.com"
    assert rows[0]["is_admin"] is True
    assert rows[0]["last_active_at"] == datetime(2026, 1, 5, tzinfo=timezone.utc)
