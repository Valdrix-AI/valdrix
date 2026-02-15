import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.shared.core.health import HealthService


@pytest.mark.asyncio
async def test_check_cache_disabled():
    service = HealthService()
    cache = MagicMock()
    cache.enabled = False

    with patch("app.shared.core.health.get_cache_service", return_value=cache):
        result = await service._check_cache()

    assert result["status"] == "disabled"
    assert "not configured" in result["message"]


@pytest.mark.asyncio
async def test_check_cache_set_get_failed():
    service = HealthService()
    cache = MagicMock()
    cache.enabled = True
    cache.set = AsyncMock(return_value=True)
    cache.get = AsyncMock(return_value="wrong")

    with patch("app.shared.core.health.get_cache_service", return_value=cache):
        result = await service._check_cache()

    assert result["status"] == "unhealthy"
    assert "Cache set/get failed" in result["message"]


@pytest.mark.asyncio
async def test_check_external_services_exception():
    service = HealthService()
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(side_effect=Exception("boom"))

    with patch("app.shared.core.health.httpx.AsyncClient", return_value=mock_client):
        result = await service._check_external_services()

    assert result["status"] == "degraded"
    assert result["services"]["aws_sts"]["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_check_circuit_breakers_none():
    service = HealthService()
    with patch("app.shared.core.health.get_all_circuit_breakers", return_value={}):
        result = await service._check_circuit_breakers()

    assert result["status"] == "healthy"
    assert "No circuit breakers configured" in result["message"]


@pytest.mark.asyncio
async def test_check_circuit_breakers_open():
    service = HealthService()
    breakers = {"aws": {"state": "open"}, "db": {"state": "closed"}}
    with patch(
        "app.shared.core.health.get_all_circuit_breakers", return_value=breakers
    ):
        result = await service._check_circuit_breakers()

    assert result["status"] == "degraded"
    assert "aws" in result["open_breakers"]


@pytest.mark.asyncio
async def test_check_circuit_breakers_exception():
    service = HealthService()
    with patch(
        "app.shared.core.health.get_all_circuit_breakers", side_effect=Exception("oops")
    ):
        result = await service._check_circuit_breakers()

    assert result["status"] == "unknown"
    assert "oops" in result["error"]


@pytest.mark.asyncio
async def test_check_system_resources_degraded():
    service = HealthService()
    memory = SimpleNamespace(percent=90, used=5 * 1024**3, available=1 * 1024**3)
    disk = SimpleNamespace(percent=92, free=2 * 1024**3)

    with (
        patch("app.shared.core.health.safe_virtual_memory", return_value=memory),
        patch("app.shared.core.health.safe_cpu_percent", return_value=95) as mock_cpu,
        patch("app.shared.core.health.safe_disk_usage", return_value=disk) as mock_disk,
    ):
        result = await service._check_system_resources()

    assert result["status"] == "degraded"
    assert "memory_high" in result["warnings"]
    assert "cpu_high" in result["warnings"]
    assert "disk_high" in result["warnings"]
    mock_cpu.assert_called_once_with()
    mock_disk.assert_any_call("/")


@pytest.mark.asyncio
async def test_check_system_resources_exception():
    service = HealthService()
    with patch(
        "app.shared.core.health.psutil.virtual_memory",
        side_effect=Exception("psutil fail"),
    ):
        result = await service._check_system_resources()

    assert result["status"] == "unknown"
    assert "psutil fail" in result["error"]


@pytest.mark.asyncio
async def test_check_background_jobs_no_db():
    service = HealthService(db=None)
    result = await service._check_background_jobs()

    assert result["status"] == "unknown"
    assert "Database session not available" in result["message"]


@pytest.mark.asyncio
async def test_check_background_jobs_stuck_jobs():
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = 2
    db.execute.return_value = mock_result

    service = HealthService(db=db)
    result = await service._check_background_jobs()

    assert result["status"] == "degraded"
    assert result["stuck_jobs"] == 2


@pytest.mark.asyncio
async def test_check_background_jobs_queue_stats():
    db = AsyncMock()
    res_stuck = MagicMock()
    res_stuck.scalar.return_value = 0

    stats = SimpleNamespace(total=5, pending=2, running=1, failed=2)
    res_stats = MagicMock()
    res_stats.first.return_value = stats

    db.execute.side_effect = [res_stuck, res_stats]

    service = HealthService(db=db)
    result = await service._check_background_jobs()

    assert result["status"] == "healthy"
    assert result["queue_stats"]["total_jobs"] == 5
    assert result["queue_stats"]["pending_jobs"] == 2


@pytest.mark.asyncio
async def test_check_background_jobs_exception():
    db = AsyncMock()
    db.execute.side_effect = Exception("db fail")
    service = HealthService(db=db)

    result = await service._check_background_jobs()

    assert result["status"] == "unknown"
    assert "db fail" in result["error"]


def test_calculate_overall_health_unknown():
    service = HealthService()
    status = service._calculate_overall_health([{"status": "unknown"}])
    assert status == "unknown"


@pytest.mark.asyncio
async def test_handle_check_errors():
    service = HealthService()

    async def boom():
        raise Exception("boom")

    result = await service._handle_check_errors(boom())
    assert result["status"] == "error"
    assert "boom" in result["error"]
