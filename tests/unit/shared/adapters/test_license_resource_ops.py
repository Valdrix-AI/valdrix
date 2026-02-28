from __future__ import annotations

from datetime import datetime, timezone

from app.shared.adapters.license_resource_ops import (
    build_discovered_license_resources,
    build_license_usage_rows,
    supports_license_discovery_resource_type,
    supports_license_usage_service,
)


def test_supports_resource_and_usage_aliases() -> None:
    assert supports_license_discovery_resource_type("licenses") is True
    assert supports_license_discovery_resource_type("compute") is False
    assert supports_license_usage_service("license_seat") is True
    assert supports_license_usage_service("network") is False


def test_build_discovered_license_resources_deduplicates_and_merges() -> None:
    resources = build_discovered_license_resources(
        activity_rows=[
            {
                "user_id": "u-1",
                "email": "first@example.com",
                "full_name": "First User",
                "last_active_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
                "is_admin": False,
                "suspended": False,
            },
            {
                "user_id": "u-1",
                "last_active_at": datetime(2026, 1, 5, tzinfo=timezone.utc),
                "is_admin": True,
            },
            {"email": "second@example.com", "suspended": True},
        ],
        vendor="microsoft_365",
        resource_type="license",
        region="eu-west-1",
    )

    assert len(resources) == 2
    assert resources[0]["id"] == "second@example.com"
    assert resources[0]["status"] == "suspended"
    assert resources[1]["id"] == "u-1"
    assert resources[1]["metadata"]["is_admin"] is True
    assert resources[1]["metadata"]["last_active_at"] == "2026-01-05T00:00:00+00:00"


def test_build_license_usage_rows_filters_by_resource_and_normalizes_defaults() -> None:
    rows = build_license_usage_rows(
        activity_rows=[
            {
                "user_id": "u-1",
                "email": "first@example.com",
                "last_active_at": datetime(2026, 2, 1, tzinfo=timezone.utc),
            },
            {"email": "second@example.com"},
        ],
        vendor="google_workspace",
        service_name="license",
        resource_id="U-1",
        default_seat_price_usd=-10.0,
        currency="eur",
        now=datetime(2026, 2, 2, tzinfo=timezone.utc),
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["resource_id"] == "u-1"
    assert row["cost_usd"] == 0.0
    assert row["currency"] == "EUR"
    assert row["timestamp"] == datetime(2026, 2, 1, tzinfo=timezone.utc)
    assert row["tags"]["vendor"] == "google_workspace"
    assert row["tags"]["email"] == "first@example.com"


def test_build_license_usage_rows_returns_empty_for_unsupported_service() -> None:
    assert (
        build_license_usage_rows(
            activity_rows=[{"user_id": "u-1"}],
            vendor="github",
            service_name="compute",
            resource_id=None,
            default_seat_price_usd=10.0,
            currency="USD",
        )
        == []
    )
