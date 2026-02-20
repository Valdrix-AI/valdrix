from unittest.mock import MagicMock

import pytest

from app.modules.optimization.adapters.hybrid.detector import HybridZombieDetector
from app.modules.optimization.domain.factory import ZombieDetectorFactory


@pytest.mark.asyncio
async def test_hybrid_detector_finds_idle_hybrid_resources() -> None:
    conn = MagicMock()
    conn.provider = "hybrid"
    conn.spend_feed = [
        {
            "resource_id": "vm-host-12",
            "service": "OpenStack Compute",
            "cost_usd": 200.0,
            "allocated_cpu": 32,
            "used_cpu": 8,
        }
    ]

    detector = HybridZombieDetector(connection=conn)
    result = await detector.scan_all()

    assert result["provider"] == "hybrid"
    assert len(result["idle_hybrid_resources"]) == 1
    assert result["idle_hybrid_resources"][0]["resource_id"] == "vm-host-12"
    assert result["idle_hybrid_resources"][0]["monthly_cost"] > 0


def test_hybrid_detector_factory_wiring() -> None:
    conn = MagicMock()
    conn.provider = "hybrid"
    conn.vendor = "openstack"
    conn.auth_method = "api_key"
    conn.api_key = "hy_key"
    conn.api_secret = "hy_secret"
    conn.connector_config = {"auth_url": "https://openstack.example.com/v3"}
    conn.spend_feed = [{"cost_usd": 22.0}]

    detector = ZombieDetectorFactory.get_detector(conn)

    assert isinstance(detector, HybridZombieDetector)
    assert detector.provider_name == "hybrid"
