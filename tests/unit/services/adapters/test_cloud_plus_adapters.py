from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.shared.adapters.license import LicenseAdapter
from app.shared.adapters.saas import SaaSAdapter


@pytest.mark.asyncio
async def test_saas_adapter_normalizes_feed() -> None:
    conn = MagicMock()
    conn.spend_feed = [
        {
            "date": "2026-01-10T00:00:00Z",
            "vendor": "Slack",
            "amount_usd": 25.5,
            "tags": {"team": "platform"},
        }
    ]
    adapter = SaaSAdapter(conn)
    rows = await adapter.get_cost_and_usage(
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
    )

    assert len(rows) == 1
    assert rows[0]["provider"] == "saas"
    assert rows[0]["service"] == "Slack"
    assert rows[0]["cost_usd"] == 25.5


@pytest.mark.asyncio
async def test_license_adapter_normalizes_feed() -> None:
    conn = MagicMock()
    conn.license_feed = [
        {
            "timestamp": "2026-01-15T00:00:00+00:00",
            "service": "Microsoft E5",
            "cost_usd": 120.0,
        }
    ]
    adapter = LicenseAdapter(conn)
    rows = await adapter.get_cost_and_usage(
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
    )

    assert len(rows) == 1
    assert rows[0]["provider"] == "license"
    assert rows[0]["service"] == "Microsoft E5"
    assert rows[0]["cost_usd"] == 120.0
