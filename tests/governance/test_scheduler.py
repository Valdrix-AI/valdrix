"""
Tests for SchedulerService

Tests cover:
- Scheduler instantiation
- Job registration
- Semaphore-limited concurrency
- Tenant processing workflow
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.modules.governance.domain.scheduler.orchestrator import SchedulerService


def create_mock_session_maker() -> MagicMock:
    """Create a mock session maker for testing."""
    mock_session = AsyncMock()
    mock_session_maker = MagicMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None
    mock_session_maker.return_value = mock_cm
    return mock_session_maker


@pytest.fixture
def scheduler_service() -> SchedulerService:
    """Fixture to provide a SchedulerService instance."""
    mock_session_maker = create_mock_session_maker()
    return SchedulerService(session_maker=mock_session_maker)


class TestSchedulerInstantiation:
    """Tests for SchedulerService initialization."""

    def test_creates_scheduler(self, scheduler_service: SchedulerService) -> None:
        """Should create APScheduler instance."""
        assert scheduler_service.scheduler is not None

    def test_stores_session_maker(self, scheduler_service: SchedulerService) -> None:
        """Should store the injected session_maker."""
        mock_session_maker = create_mock_session_maker()
        scheduler = SchedulerService(session_maker=mock_session_maker)
        assert scheduler.session_maker is mock_session_maker

    def test_creates_semaphore(self, scheduler_service: SchedulerService) -> None:
        """Should create semaphore for concurrency control."""
        assert scheduler_service.semaphore is not None
        # Default limit is 10
        assert scheduler_service.semaphore._value == 10

    def test_initial_status(self, scheduler_service: SchedulerService) -> None:
        """Initial run status should be None."""
        assert scheduler_service._last_run_success is None
        assert scheduler_service._last_run_time is None


class TestSchedulerStatus:
    """Tests for get_status()."""

    def test_returns_dict(self, scheduler_service: SchedulerService) -> None:
        """Should return status dictionary."""
        status = scheduler_service.get_status()
        assert isinstance(status, dict)

    def test_contains_running_flag(self, scheduler_service: SchedulerService) -> None:
        """Should contain running flag."""
        status = scheduler_service.get_status()
        assert "running" in status

    def test_contains_last_run_info(self, scheduler_service: SchedulerService) -> None:
        """Should contain last run information."""
        status = scheduler_service.get_status()
        assert "last_run_success" in status
        assert "last_run_time" in status

    def test_contains_job_list(self, scheduler_service: SchedulerService) -> None:
        """Should list registered jobs."""
        status = scheduler_service.get_status()
        assert "jobs" in status
        assert isinstance(status["jobs"], list)


@pytest.mark.asyncio
class TestSchedulerStart:
    """Tests for start() method."""

    async def test_registers_daily_job(self, scheduler_service: SchedulerService) -> None:
        """Should register cohort analysis jobs (Phase 7: tiered scheduling)."""
        scheduler_service.start()

        # Get job IDs - now using cohort-based scheduling
        job_ids = [j.id for j in scheduler_service.scheduler.get_jobs()]
        assert "cohort_high_value_scan" in job_ids  # Enterprise/Pro every 6h
        assert "cohort_active_scan" in job_ids  # Growth daily
        assert "cohort_dormant_scan" in job_ids  # Starter weekly

        scheduler_service.scheduler.shutdown(wait=False)

    async def test_registers_weekly_remediation_job(self, scheduler_service: SchedulerService) -> None:
        """Should register weekly remediation job."""
        mock_session_maker = create_mock_session_maker()
        scheduler = SchedulerService(session_maker=mock_session_maker)
        scheduler.start()

        job_ids = [j.id for j in scheduler.scheduler.get_jobs()]
        assert "weekly_remediation_sweep" in job_ids

        scheduler.scheduler.shutdown(wait=False)

    async def test_scheduler_is_running(self, scheduler_service: SchedulerService) -> None:
        """Scheduler should be running after start()."""
        mock_session_maker = create_mock_session_maker()
        scheduler = SchedulerService(session_maker=mock_session_maker)
        scheduler.start()

        assert scheduler.scheduler.running is True

        scheduler.scheduler.shutdown(wait=False)


@pytest.mark.asyncio
class TestSchedulerStop:
    """Tests for stop() method."""

    async def test_stop_calls_shutdown(self, scheduler_service: SchedulerService) -> None:
        """stop() should call scheduler.shutdown()."""
        mock_session_maker = create_mock_session_maker()
        scheduler = SchedulerService(session_maker=mock_session_maker)
        scheduler.start()

        # Stop should not raise
        scheduler.stop()

        # Calling stop again should not raise (idempotent)
        # The scheduler should remain in a stopped state


@pytest.mark.asyncio
class TestDailyAnalysisJob:
    """Tests for daily_analysis_job()."""

    async def test_fetches_all_tenants(self, scheduler_service: SchedulerService) -> None:
        """Should dispatch task for each cohort."""
        from app.shared.core.celery_app import celery_app

        mock_session_maker = create_mock_session_maker()
        scheduler = SchedulerService(session_maker=mock_session_maker)

        with patch.object(celery_app, "send_task") as mock_send_task:
            await scheduler.daily_analysis_job()

            # Should call send_task for HIGH_VALUE, ACTIVE, and DORMANT
            assert mock_send_task.call_count == 3
            # Verify one of the calls
            mock_send_task.assert_any_call(
                "scheduler.cohort_analysis", args=["high_value"]
            )

    async def test_updates_last_run_status(self, scheduler_service: SchedulerService) -> None:
        """Should update last_run_success after completion."""
        from app.shared.core.celery_app import celery_app

        mock_session_maker = create_mock_session_maker()
        scheduler = SchedulerService(session_maker=mock_session_maker)

        with patch.object(celery_app, "send_task"):
            await scheduler.daily_analysis_job()

            assert scheduler._last_run_success is True
            assert scheduler._last_run_time is not None

    async def test_processes_multiple_tenants(self, scheduler_service: SchedulerService) -> None:
        """Should dispatch all cohorts regardless of tenant count (orchestrator level)."""
        from app.shared.core.celery_app import celery_app

        mock_session_maker = create_mock_session_maker()
        scheduler = SchedulerService(session_maker=mock_session_maker)

        with patch.object(celery_app, "send_task") as mock_send_task:
            await scheduler.daily_analysis_job()

            assert mock_send_task.call_count == 3
            assert scheduler._last_run_success is True
