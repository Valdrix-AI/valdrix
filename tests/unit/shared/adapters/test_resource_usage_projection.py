from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.shared.adapters.resource_usage_projection import (
    discover_resources_from_cost_rows,
)


def test_discover_resources_from_cost_rows_rejects_unsupported_resource_type() -> None:
    rows = [
        {
            "timestamp": "2026-01-10T00:00:00Z",
            "service": "Example",
            "resource_id": "res-1",
            "cost_usd": 1.0,
        }
    ]
    discovered = discover_resources_from_cost_rows(
        cost_rows=rows,
        resource_type="unsupported",
        supported_resource_types={"all", "saas"},
        default_provider="saas",
        default_resource_type="saas_subscription",
    )
    assert discovered == []


def test_discover_resources_from_cost_rows_aggregates_and_filters_region() -> None:
    rows = [
        {
            "timestamp": datetime(2026, 1, 10, tzinfo=timezone.utc),
            "provider": "saas",
            "service": "GitHub",
            "resource_id": "seat-1",
            "usage_type": "subscription",
            "cost_usd": 4.0,
            "region": "us-east-1",
            "source_adapter": "saas_feed",
        },
        {
            "timestamp": "2026-01-11T00:00:00Z",
            "provider": "saas",
            "service": "GitHub",
            "resource_id": "seat-1",
            "usage_type": "subscription",
            "cost_usd": 6.0,
            "region": "us-east-1",
            "source_adapter": "saas_feed",
        },
        {
            "timestamp": "2026-01-09T00:00:00Z",
            "provider": "saas",
            "service": "GitHub",
            "resource_id": "seat-2",
            "usage_type": "subscription",
            "cost_usd": 1.5,
            "region": "eu-west-1",
            "source_adapter": "saas_feed",
        },
    ]

    discovered = discover_resources_from_cost_rows(
        cost_rows=rows,
        resource_type="saas",
        supported_resource_types={"all", "saas"},
        default_provider="saas",
        default_resource_type="saas_subscription",
        region="us-east-1",
    )

    assert len(discovered) == 1
    assert discovered[0]["id"] == "seat-1"
    assert discovered[0]["provider"] == "saas"
    assert discovered[0]["type"] == "saas_subscription"
    assert discovered[0]["region"] == "us-east-1"
    assert discovered[0]["metadata"]["record_count"] == 2
    assert discovered[0]["metadata"]["total_cost_usd"] == pytest.approx(10.0)
    assert discovered[0]["metadata"]["last_seen_at"] == "2026-01-11T00:00:00+00:00"
