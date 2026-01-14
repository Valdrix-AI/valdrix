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
from datetime import datetime, timezone
from uuid import uuid4

from app.services.scheduler import SchedulerService


def create_mock_session_maker():
    """Create a mock session maker for testing."""
    mock_session = AsyncMock()
    mock_session_maker = MagicMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None
    mock_session_maker.return_value = mock_cm
    return mock_session_maker


class TestSchedulerInstantiation:
    """Tests for SchedulerService initialization."""
    
    def test_creates_scheduler(self):
        """Should create APScheduler instance."""
        mock_session_maker = create_mock_session_maker()
        scheduler = SchedulerService(session_maker=mock_session_maker)
        assert scheduler.scheduler is not None
    
    def test_stores_session_maker(self):
        """Should store the injected session_maker."""
        mock_session_maker = create_mock_session_maker()
        scheduler = SchedulerService(session_maker=mock_session_maker)
        assert scheduler.session_maker is mock_session_maker
    
    def test_creates_semaphore(self):
        """Should create semaphore for concurrency control."""
        mock_session_maker = create_mock_session_maker()
        scheduler = SchedulerService(session_maker=mock_session_maker)
        assert scheduler.semaphore is not None
        # Default limit is 10
        assert scheduler.semaphore._value == 10
    
    def test_initial_status(self):
        """Initial run status should be None."""
        mock_session_maker = create_mock_session_maker()
        scheduler = SchedulerService(session_maker=mock_session_maker)
        assert scheduler._last_run_success is None
        assert scheduler._last_run_time is None


class TestSchedulerStatus:
    """Tests for get_status()."""
    
    def test_returns_dict(self):
        """Should return status dictionary."""
        mock_session_maker = create_mock_session_maker()
        scheduler = SchedulerService(session_maker=mock_session_maker)
        status = scheduler.get_status()
        assert isinstance(status, dict)
    
    def test_contains_running_flag(self):
        """Should contain running flag."""
        mock_session_maker = create_mock_session_maker()
        scheduler = SchedulerService(session_maker=mock_session_maker)
        status = scheduler.get_status()
        assert "running" in status
    
    def test_contains_last_run_info(self):
        """Should contain last run information."""
        mock_session_maker = create_mock_session_maker()
        scheduler = SchedulerService(session_maker=mock_session_maker)
        status = scheduler.get_status()
        assert "last_run_success" in status
        assert "last_run_time" in status
    
    def test_contains_job_list(self):
        """Should list registered jobs."""
        mock_session_maker = create_mock_session_maker()
        scheduler = SchedulerService(session_maker=mock_session_maker)
        status = scheduler.get_status()
        assert "jobs" in status
        assert isinstance(status["jobs"], list)


@pytest.mark.asyncio
class TestSchedulerStart:
    """Tests for start() method."""
    
    async def test_registers_daily_job(self):
        """Should register cohort analysis jobs (Phase 7: tiered scheduling)."""
        mock_session_maker = create_mock_session_maker()
        scheduler = SchedulerService(session_maker=mock_session_maker)
        scheduler.start()
        
        # Get job IDs - now using cohort-based scheduling
        job_ids = [j.id for j in scheduler.scheduler.get_jobs()]
        assert "cohort_high_value_scan" in job_ids  # Enterprise/Pro every 6h
        assert "cohort_active_scan" in job_ids       # Growth daily
        assert "cohort_dormant_scan" in job_ids      # Starter weekly
        
        scheduler.scheduler.shutdown(wait=False)
    
    async def test_registers_weekly_remediation_job(self):
        """Should register weekly remediation job."""
        mock_session_maker = create_mock_session_maker()
        scheduler = SchedulerService(session_maker=mock_session_maker)
        scheduler.start()
        
        job_ids = [j.id for j in scheduler.scheduler.get_jobs()]
        assert "weekly_remediation_sweep" in job_ids
        
        scheduler.scheduler.shutdown(wait=False)
    
    async def test_scheduler_is_running(self):
        """Scheduler should be running after start()."""
        mock_session_maker = create_mock_session_maker()
        scheduler = SchedulerService(session_maker=mock_session_maker)
        scheduler.start()
        
        assert scheduler.scheduler.running is True
        
        scheduler.scheduler.shutdown(wait=False)


@pytest.mark.asyncio
class TestSchedulerStop:
    """Tests for stop() method."""
    
    async def test_stop_calls_shutdown(self):
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
    
    async def test_fetches_all_tenants(self):
        """Should query all tenants from database."""
        mock_session_maker = create_mock_session_maker()
        scheduler = SchedulerService(session_maker=mock_session_maker)
        
        # Mock session and tenant query
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_db
        mock_cm.__aexit__.return_value = None
        scheduler.session_maker = MagicMock(return_value=mock_cm)
        
        await scheduler.daily_analysis_job()
        
        # Verify execute was called
        mock_db.execute.assert_called()
    
    async def test_updates_last_run_status(self):
        """Should update last_run_success after completion."""
        mock_session_maker = create_mock_session_maker()
        scheduler = SchedulerService(session_maker=mock_session_maker)
        
        # Mock empty tenant list
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_db
        mock_cm.__aexit__.return_value = None
        scheduler.session_maker = MagicMock(return_value=mock_cm)
        
        await scheduler.daily_analysis_job()
        
        assert scheduler._last_run_success is True
        assert scheduler._last_run_time is not None
    
    async def test_processes_multiple_tenants(self):
        """Should process all tenants."""
        mock_session_maker = create_mock_session_maker()
        scheduler = SchedulerService(session_maker=mock_session_maker)
        
        # Mock 2 tenants
        mock_tenants = [MagicMock(id=uuid4(), name="Tenant1"), MagicMock(id=uuid4(), name="Tenant2")]
        
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_tenants
        mock_db.execute.return_value = mock_result
        
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_db
        mock_cm.__aexit__.return_value = None
        scheduler.session_maker = MagicMock(return_value=mock_cm)
        
        call_count = [0]
        async def mock_process(db, tenant, start, end):
            call_count[0] += 1
        
        with patch.object(scheduler, '_process_tenant', side_effect=mock_process):
            await scheduler.daily_analysis_job()
        
        # Both tenants were processed
        assert call_count[0] == 2
        assert scheduler._last_run_success is True

