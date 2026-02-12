from unittest.mock import MagicMock

import pytest

from app.modules.optimization.adapters.license.detector import LicenseZombieDetector


@pytest.mark.asyncio
async def test_license_detector_finds_unused_license_seats() -> None:
    conn = MagicMock()
    conn.provider = "license"
    conn.license_feed = [
        {
            "license_id": "lic_456",
            "service": "Microsoft E5",
            "cost_usd": 240.0,
            "purchased_seats": 120,
            "assigned_seats": 90,
        }
    ]

    detector = LicenseZombieDetector(connection=conn)
    result = await detector.scan_all()

    assert result["provider"] == "license"
    assert len(result["unused_license_seats"]) == 1
    assert result["unused_license_seats"][0]["resource_id"] == "lic_456"
    assert result["unused_license_seats"][0]["monthly_cost"] > 0
