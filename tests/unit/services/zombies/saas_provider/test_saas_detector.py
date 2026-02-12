from unittest.mock import MagicMock

import pytest

from app.modules.optimization.adapters.saas.detector import SaaSZombieDetector


@pytest.mark.asyncio
async def test_saas_detector_finds_idle_subscriptions_from_unused_seats() -> None:
    conn = MagicMock()
    conn.provider = "saas"
    conn.spend_feed = [
        {
            "subscription_id": "sub_123",
            "vendor": "Slack",
            "cost_usd": 100.0,
            "purchased_seats": 50,
            "active_seats": 30,
        }
    ]

    detector = SaaSZombieDetector(connection=conn)
    result = await detector.scan_all()

    assert result["provider"] == "saas"
    assert len(result["idle_saas_subscriptions"]) == 1
    assert result["idle_saas_subscriptions"][0]["resource_id"] == "sub_123"
    assert result["idle_saas_subscriptions"][0]["monthly_cost"] > 0
