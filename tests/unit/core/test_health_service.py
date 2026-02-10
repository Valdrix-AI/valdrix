import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.shared.core.health import HealthCheckService


@pytest.mark.asyncio
async def test_calculate_overall_health():
    service = HealthCheckService()

    assert service._calculate_overall_health([{"status": "healthy"}]) == "healthy"
    assert service._calculate_overall_health([{"status": "up"}, {"status": "disabled"}]) == "healthy"
    assert service._calculate_overall_health([{"status": "degraded"}]) == "degraded"
    assert service._calculate_overall_health([{"status": "healthy"}, {"status": "degraded"}]) == "degraded"
    assert service._calculate_overall_health([{"status": "down"}]) == "unhealthy"
    assert service._calculate_overall_health([{"status": "unknown"}]) == "unknown"


@pytest.mark.asyncio
async def test_check_system_resources_degraded():
    service = HealthCheckService()

    mem = MagicMock(percent=90, used=8 * 1024**3, available=2 * 1024**3)
    disk = MagicMock(percent=95, free=10 * 1024**3)

    with patch("app.shared.core.health.psutil.virtual_memory", return_value=mem), \
         patch("app.shared.core.health.psutil.cpu_percent", return_value=92), \
         patch("app.shared.core.health.psutil.disk_usage", return_value=disk):
        result = await service._check_system_resources()

    assert result["status"] == "degraded"
    assert set(result["warnings"]) == {"memory_high", "cpu_high", "disk_high"}


@pytest.mark.asyncio
async def test_check_cache_disabled():
    service = HealthCheckService()
    cache = MagicMock()
    cache.enabled = False

    with patch("app.shared.core.health.get_cache_service", return_value=cache):
        result = await service._check_cache()

    assert result["status"] == "disabled"


@pytest.mark.asyncio
async def test_check_cache_success():
    service = HealthCheckService()
    cache = MagicMock()
    cache.enabled = True
    cache.set = AsyncMock(return_value=True)
    cache.get = AsyncMock(return_value="ok")

    with patch("app.shared.core.health.get_cache_service", return_value=cache):
        result = await service._check_cache()

    assert result["status"] == "healthy"


@pytest.mark.asyncio
async def test_check_circuit_breakers_open():
    service = HealthCheckService()

    breakers = {"cb1": {"state": "open"}, "cb2": {"state": "closed"}}
    with patch("app.shared.core.health.get_all_circuit_breakers", return_value=breakers):
        result = await service._check_circuit_breakers()

    assert result["status"] == "degraded"
    assert "cb1" in result["open_breakers"]


@pytest.mark.asyncio
async def test_check_circuit_breakers_empty():
    service = HealthCheckService()

    with patch("app.shared.core.health.get_all_circuit_breakers", return_value={}):
        result = await service._check_circuit_breakers()

    assert result["status"] == "healthy"


@pytest.mark.asyncio
async def test_check_background_jobs_no_db():
    service = HealthCheckService(db=None)
    result = await service._check_background_jobs()
    assert result["status"] == "unknown"


@pytest.mark.asyncio
async def test_check_background_jobs_stuck():
    db = AsyncMock()
    service = HealthCheckService(db=db)

    stuck_result = MagicMock()
    stuck_result.scalar.return_value = 3
    db.execute = AsyncMock(return_value=stuck_result)

    result = await service._check_background_jobs()
    assert result["status"] == "degraded"
    assert result["stuck_jobs"] == 3


@pytest.mark.asyncio
async def test_check_background_jobs_stats():
    db = AsyncMock()
    service = HealthCheckService(db=db)

    stuck_result = MagicMock()
    stuck_result.scalar.return_value = 0

    stats_row = MagicMock(total=5, pending=2, running=1, failed=0)
    stats_result = MagicMock()
    stats_result.first.return_value = stats_row

    db.execute = AsyncMock(side_effect=[stuck_result, stats_result])

    result = await service._check_background_jobs()
    assert result["status"] == "healthy"
    assert result["queue_stats"]["total_jobs"] == 5
    assert result["queue_stats"]["pending_jobs"] == 2
    assert result["queue_stats"]["running_jobs"] == 1
    assert result["queue_stats"]["failed_jobs"] == 0
