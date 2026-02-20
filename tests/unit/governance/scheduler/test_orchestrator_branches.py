from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.modules.governance.domain.scheduler.cohorts import TenantCohort
from app.modules.governance.domain.scheduler.orchestrator import (
    SchedulerOrchestrator,
    SchedulerService,
)


@pytest.fixture
def orchestrator() -> SchedulerOrchestrator:
    session_maker = MagicMock()
    return SchedulerOrchestrator(session_maker)


@pytest.mark.asyncio
async def test_acquire_dispatch_lock_paths(
    orchestrator: SchedulerOrchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.governance.domain.scheduler.orchestrator as orchestrator_module

    monkeypatch.setattr(orchestrator_module.settings, "TESTING", False, raising=False)
    monkeypatch.setattr(
        orchestrator_module.settings, "SCHEDULER_LOCK_FAIL_OPEN", False, raising=False
    )
    monkeypatch.setattr(orchestrator_module.os, "getenv", lambda _: None)

    with patch(
        "app.modules.governance.domain.scheduler.orchestrator.get_redis_client",
        return_value=None,
    ):
        assert await orchestrator._acquire_dispatch_lock("demo") is False

    redis = MagicMock()
    redis.set = AsyncMock(return_value=False)
    with patch(
        "app.modules.governance.domain.scheduler.orchestrator.get_redis_client",
        return_value=redis,
    ):
        assert await orchestrator._acquire_dispatch_lock("demo") is False

    redis.set = AsyncMock(side_effect=RuntimeError("redis down"))
    with patch(
        "app.modules.governance.domain.scheduler.orchestrator.get_redis_client",
        return_value=redis,
    ):
        assert await orchestrator._acquire_dispatch_lock("demo") is False

    monkeypatch.setattr(
        orchestrator_module.settings, "SCHEDULER_LOCK_FAIL_OPEN", True, raising=False
    )
    with patch(
        "app.modules.governance.domain.scheduler.orchestrator.get_redis_client",
        return_value=redis,
    ):
        assert await orchestrator._acquire_dispatch_lock("demo") is True


@pytest.mark.asyncio
async def test_cohort_analysis_job_lock_held_skips_dispatch(
    orchestrator: SchedulerOrchestrator,
) -> None:
    orchestrator._acquire_dispatch_lock = AsyncMock(return_value=False)  # type: ignore[method-assign]
    with patch("app.shared.core.celery_app.celery_app.send_task") as mock_send:
        await orchestrator.cohort_analysis_job(TenantCohort.ACTIVE)
    mock_send.assert_not_called()
    assert orchestrator._last_run_success is None


@pytest.mark.asyncio
async def test_cohort_analysis_job_celery_error_still_updates_last_run(
    orchestrator: SchedulerOrchestrator,
) -> None:
    orchestrator._acquire_dispatch_lock = AsyncMock(return_value=True)  # type: ignore[method-assign]
    with patch(
        "app.shared.core.celery_app.celery_app.send_task",
        side_effect=RuntimeError("down"),
    ):
        await orchestrator.cohort_analysis_job(TenantCohort.HIGH_VALUE)
    assert orchestrator._last_run_success is True
    assert orchestrator._last_run_time is not None


@pytest.mark.asyncio
async def test_fetch_live_carbon_intensity_success_and_cache(
    orchestrator: SchedulerOrchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.modules.governance.domain.scheduler.orchestrator as orchestrator_module

    monkeypatch.setattr(
        orchestrator_module.settings,
        "ELECTRICITY_MAPS_API_KEY",
        "abc123",
        raising=False,
    )
    monkeypatch.setattr(
        orchestrator_module.settings,
        "CARBON_INTENSITY_API_TIMEOUT_SECONDS",
        3,
        raising=False,
    )

    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"carbonIntensity": 97}

    client = AsyncMock()
    client.get = AsyncMock(return_value=response)

    with patch(
        "app.shared.core.http.get_http_client",
        return_value=client,
    ):
        value = await orchestrator._fetch_live_carbon_intensity("us-east-1")
        assert value == 97.0

    with patch(
        "app.shared.core.http.get_http_client"
    ) as get_http_client:
        cached_value = await orchestrator._fetch_live_carbon_intensity("us-east-1")
        assert cached_value == 97.0
        get_http_client.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_live_carbon_intensity_none_and_exception_paths(
    orchestrator: SchedulerOrchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.modules.governance.domain.scheduler.orchestrator as orchestrator_module

    monkeypatch.setattr(
        orchestrator_module.settings, "ELECTRICITY_MAPS_API_KEY", None, raising=False
    )
    assert await orchestrator._fetch_live_carbon_intensity("us-east-1") is None

    monkeypatch.setattr(
        orchestrator_module.settings,
        "ELECTRICITY_MAPS_API_KEY",
        "abc123",
        raising=False,
    )
    assert await orchestrator._fetch_live_carbon_intensity("unknown-region") is None

    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {}
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    with patch(
        "app.shared.core.http.get_http_client",
        return_value=client,
    ):
        assert await orchestrator._fetch_live_carbon_intensity("us-east-1") is None

    client = AsyncMock()
    client.get = AsyncMock(side_effect=httpx.HTTPError("boom"))
    with patch(
        "app.shared.core.http.get_http_client",
        return_value=client,
    ):
        assert await orchestrator._fetch_live_carbon_intensity("us-east-1") is None


@pytest.mark.asyncio
async def test_is_low_carbon_window_uses_live_intensity_threshold(
    orchestrator: SchedulerOrchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.modules.governance.domain.scheduler.orchestrator as orchestrator_module

    monkeypatch.setattr(
        orchestrator_module.settings,
        "CARBON_LOW_INTENSITY_THRESHOLD",
        150.0,
        raising=False,
    )
    with patch.object(
        orchestrator, "_fetch_live_carbon_intensity", AsyncMock(return_value=120.0)
    ):
        assert await orchestrator.is_low_carbon_window("us-east-1") is True
    with patch.object(
        orchestrator, "_fetch_live_carbon_intensity", AsyncMock(return_value=180.0)
    ):
        assert await orchestrator.is_low_carbon_window("us-east-1") is False


@pytest.mark.asyncio
async def test_sweep_jobs_skip_when_lock_not_acquired(
    orchestrator: SchedulerOrchestrator,
) -> None:
    orchestrator._acquire_dispatch_lock = AsyncMock(return_value=False)  # type: ignore[method-assign]
    with patch("app.shared.core.celery_app.celery_app.send_task") as mock_send:
        await orchestrator.auto_remediation_job()
        await orchestrator.billing_sweep_job()
        await orchestrator.license_governance_sweep_job()
        await orchestrator.maintenance_sweep_job()
    mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_detect_stuck_jobs_no_results_no_commit(
    orchestrator: SchedulerOrchestrator,
) -> None:
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute.return_value = result
    orchestrator.session_maker.return_value.__aenter__.return_value = db
    orchestrator.session_maker.return_value.__aexit__.return_value = None

    with patch(
        "app.modules.governance.domain.scheduler.orchestrator.STUCK_JOB_COUNT"
    ) as metric:
        await orchestrator.detect_stuck_jobs()

    metric.set.assert_called_once_with(0)
    db.commit.assert_not_awaited()


def test_start_stop_and_status(orchestrator: SchedulerOrchestrator) -> None:
    scheduler = MagicMock()
    scheduler.running = True
    scheduler.get_jobs.return_value = [
        SimpleNamespace(id="job-1"),
        SimpleNamespace(id="job-2"),
    ]
    orchestrator.scheduler = scheduler

    orchestrator.start()
    assert scheduler.add_job.call_count == 9
    scheduler.start.assert_called_once()

    status = orchestrator.get_status()
    assert status["running"] is True
    assert status["jobs"] == ["job-1", "job-2"]

    orchestrator.stop()
    scheduler.shutdown.assert_called_once_with(wait=True)


def test_stop_skips_when_not_running(orchestrator: SchedulerOrchestrator) -> None:
    scheduler = MagicMock()
    scheduler.running = False
    orchestrator.scheduler = scheduler
    orchestrator.stop()
    scheduler.shutdown.assert_not_called()


@pytest.mark.asyncio
async def test_scheduler_service_daily_analysis_job_runs_all_cohorts() -> None:
    service = SchedulerService(MagicMock())
    service.cohort_analysis_job = AsyncMock()  # type: ignore[method-assign]

    await service.daily_analysis_job()

    assert service.cohort_analysis_job.await_count == 3
    service.cohort_analysis_job.assert_any_await(TenantCohort.HIGH_VALUE)
    service.cohort_analysis_job.assert_any_await(TenantCohort.ACTIVE)
    service.cohort_analysis_job.assert_any_await(TenantCohort.DORMANT)
    assert service._last_run_success is True
    assert service._last_run_time is not None
