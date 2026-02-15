import asyncio
import pytest
import uuid
from unittest.mock import MagicMock, AsyncMock, patch
from app.modules.optimization.domain.service import ZombieService


@pytest.mark.asyncio
async def test_high_concurrency_zombie_scans():
    """
    Stress Test: Simulate 100 concurrent tenant scans (Series-A scale).
    Verifies that the system handles concurrency without blocking or crashing.
    """
    # 1. Setup mock DB and dependencies
    mock_db = AsyncMock()
    service = ZombieService(mock_db)

    # 2. Mock the ZombieDetector to return fast but distinct results
    # We patch the Factory or the Detector itself
    mock_results = {
        "unattached_volumes": [{"id": "vol-1", "monthly_cost": 10.0}],
        "total_monthly_waste": 10.0,
    }

    with patch(
        "app.modules.optimization.domain.factory.ZombieDetectorFactory.get_detector"
    ) as mock_factory:
        mock_detector = AsyncMock()
        mock_detector.scan_all.return_value = mock_results
        mock_detector.provider_name = "aws"
        mock_factory.return_value = mock_detector

        # Mock connections fetching
        mock_conn = MagicMock()
        mock_conn.id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_conn]
        mock_db.execute = AsyncMock(return_value=mock_result)

        # 3. Fire 100 concurrent scans
        tasks = []
        for i in range(100):
            tenant_id = uuid.uuid4()
            user = MagicMock(tenant_id=tenant_id, tier="growth")
            tasks.append(service.scan_for_tenant(tenant_id, user, analyze=False))

        results = await asyncio.gather(*tasks)

        # 4. Assertions
        assert len(results) == 100
        for res in results:
            assert res["total_monthly_waste"] == 30.0
            assert "unattached_volumes" in res
            assert len(res["unattached_volumes"]) == 3


@pytest.mark.asyncio
async def test_zombie_scan_timeout_resilience():
    """
    Chaos Test: Simulate a hanging plugin/detector and verify timeout.
    """
    mock_db = AsyncMock()
    service = ZombieService(mock_db)

    with patch(
        "app.modules.optimization.domain.factory.ZombieDetectorFactory.get_detector"
    ) as mock_factory:
        # Create a detector that hangs forever
        mock_detector = AsyncMock()

        async def hang_forever(*args, **kwargs):
            await asyncio.sleep(1000)
            return {}

        mock_detector.scan_all.side_effect = hang_forever
        mock_factory.return_value = mock_detector

        # Mock connections
        mock_conn = MagicMock()
        mock_conn.id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_conn]
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Reduce timeout for test speed or mock asyncio.wait_for
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            result = await service.scan_for_tenant(uuid.uuid4(), MagicMock())

            assert result.get("scan_timeout") is True
            assert result.get("partial_results") is True
            assert result["total_monthly_waste"] == 0.0
