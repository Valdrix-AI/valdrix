from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.shared.adapters.platform import PlatformAdapter
from app.shared.adapters.hybrid import HybridAdapter


@pytest.mark.asyncio
async def test_platform_adapter_normalizes_feed() -> None:
    conn = MagicMock()
    conn.auth_method = "manual"
    conn.spend_feed = [
        {
            "date": "2026-02-10T00:00:00Z",
            "service": "Shared Cluster",
            "amount_usd": 42.5,
            "tags": {"team": "platform"},
        }
    ]
    adapter = PlatformAdapter(conn)
    rows = await adapter.get_cost_and_usage(
        start_date=datetime(2026, 2, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 2, 28, tzinfo=timezone.utc),
    )

    assert len(rows) == 1
    assert rows[0]["provider"] == "platform"
    assert rows[0]["service"] == "Shared Cluster"
    assert rows[0]["cost_usd"] == 42.5


@pytest.mark.asyncio
async def test_platform_adapter_manual_requires_non_empty_feed() -> None:
    conn = MagicMock()
    conn.auth_method = "manual"
    conn.spend_feed = []

    adapter = PlatformAdapter(conn)
    success = await adapter.verify_connection()

    assert success is False
    assert "at least one record" in (adapter.last_error or "").lower()


@pytest.mark.asyncio
async def test_hybrid_adapter_normalizes_feed() -> None:
    conn = MagicMock()
    conn.auth_method = "manual"
    conn.spend_feed = [
        {
            "timestamp": "2026-02-12T00:00:00+00:00",
            "service": "Datacenter Core",
            "cost_usd": 5120.0,
        }
    ]
    adapter = HybridAdapter(conn)
    rows = await adapter.get_cost_and_usage(
        start_date=datetime(2026, 2, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 2, 28, tzinfo=timezone.utc),
    )

    assert len(rows) == 1
    assert rows[0]["provider"] == "hybrid"
    assert rows[0]["service"] == "Datacenter Core"
    assert rows[0]["cost_usd"] == 5120.0


@pytest.mark.asyncio
async def test_hybrid_adapter_manual_requires_non_empty_feed() -> None:
    conn = MagicMock()
    conn.auth_method = "manual"
    conn.spend_feed = []

    adapter = HybridAdapter(conn)
    success = await adapter.verify_connection()

    assert success is False
    assert "at least one record" in (adapter.last_error or "").lower()
