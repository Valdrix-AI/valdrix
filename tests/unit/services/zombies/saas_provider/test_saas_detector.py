from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.modules.optimization.adapters.saas.detector import SaaSZombieDetector
from app.modules.optimization.domain.factory import ZombieDetectorFactory


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


@pytest.mark.asyncio
async def test_saas_detector_wires_connection_credentials_for_github_plugin() -> None:
    conn = MagicMock()
    conn.provider = "saas"
    conn.id = uuid4()
    conn.tenant_id = uuid4()
    conn.vendor = "github"
    conn.auth_method = "api_key"
    conn.api_key = "ghp_test_token"
    conn.spend_feed = []
    conn.connector_config = {
        "github_org": "valdrix-org",
        "unused_threshold_days": 30,
        "seat_cost_usd": 22.0,
    }

    now = datetime.now(timezone.utc)
    mock_members = [
        {"login": "active-user", "last_activity": (now - timedelta(days=7)).isoformat()},
        {"login": "inactive-user", "last_activity": (now - timedelta(days=60)).isoformat()},
    ]

    mock_client_ctx = AsyncMock()
    mock_client = AsyncMock()
    mock_client_ctx.__aenter__.return_value = mock_client
    mock_client_ctx.__aexit__.return_value = False
    mock_client.get = AsyncMock(
        return_value=MagicMock(status_code=200, json=lambda: mock_members)
    )

    detector = ZombieDetectorFactory.get_detector(conn)
    assert isinstance(detector, SaaSZombieDetector)

    with pytest.MonkeyPatch.context() as mp:
        import httpx

        mp.setattr(httpx, "AsyncClient", lambda *args, **kwargs: mock_client_ctx)
        result = await detector.scan_all()

    assert any(
        item.get("resource_id") == "inactive-user"
        for item in result.get("unused_license_seats", [])
    )
