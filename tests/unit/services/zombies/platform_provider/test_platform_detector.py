from unittest.mock import MagicMock

import pytest

from app.modules.optimization.adapters.platform.detector import PlatformZombieDetector
from app.modules.optimization.domain.factory import ZombieDetectorFactory


@pytest.mark.asyncio
async def test_platform_detector_finds_idle_platform_services() -> None:
    conn = MagicMock()
    conn.provider = "platform"
    conn.spend_feed = [
        {
            "service_id": "platform-api-gateway",
            "service": "Shared API Gateway",
            "cost_usd": 120.0,
            "allocated_units": 100,
            "active_units": 40,
        }
    ]

    detector = PlatformZombieDetector(connection=conn)
    result = await detector.scan_all()

    assert result["provider"] == "platform"
    assert len(result["idle_platform_services"]) == 1
    assert result["idle_platform_services"][0]["resource_id"] == "platform-api-gateway"
    assert result["idle_platform_services"][0]["monthly_cost"] > 0


def test_platform_detector_factory_wiring() -> None:
    conn = MagicMock()
    conn.provider = "platform"
    conn.vendor = "datadog"
    conn.auth_method = "api_key"
    conn.api_key = "dd_key"
    conn.api_secret = "dd_secret"
    conn.connector_config = {"site": "datadoghq.com"}
    conn.spend_feed = [{"cost_usd": 12.0}]

    detector = ZombieDetectorFactory.get_detector(conn)

    assert isinstance(detector, PlatformZombieDetector)
    assert detector.provider_name == "platform"
