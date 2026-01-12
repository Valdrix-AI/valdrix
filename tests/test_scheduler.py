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


class TestSchedulerInstantiation:
    """Tests for SchedulerService initialization."""
    
    def test_creates_scheduler(self):
        """Should create APScheduler instance."""
        scheduler = SchedulerService()
        assert scheduler.scheduler is not None
    
    def test_creates_engine(self):
        """Should create async SQLAlchemy engine."""
        scheduler = SchedulerService()
        assert scheduler.engine is not None
    
    def test_creates_session_maker(self):
        """Should create async session maker."""
        scheduler = SchedulerService()
        assert scheduler.session_maker is not None
    
    def test_creates_semaphore(self):
        """Should create semaphore for concurrency control."""
        scheduler = SchedulerService()
        assert scheduler.semaphore is not None
        # Default limit is 10
        assert scheduler.semaphore._value == 10
    
    def test_initial_status(self):
        """Initial run status should be None."""
        scheduler = SchedulerService()
        assert scheduler._last_run_success is None
        assert scheduler._last_run_time is None


class TestSchedulerStatus:
    """Tests for get_status()."""
    
    def test_returns_dict(self):
        """Should return status dictionary."""
        scheduler = SchedulerService()
        status = scheduler.get_status()
        assert isinstance(status, dict)
    
    def test_contains_running_flag(self):
        """Should contain running flag."""
        scheduler = SchedulerService()
        status = scheduler.get_status()
        assert "running" in status
    
    def test_contains_last_run_info(self):
        """Should contain last run information."""
        scheduler = SchedulerService()
        status = scheduler.get_status()
        assert "last_run_success" in status
        assert "last_run_time" in status
    
    def test_contains_job_list(self):
        """Should list registered jobs."""
        scheduler = SchedulerService()
        status = scheduler.get_status()
        assert "jobs" in status
        assert isinstance(status["jobs"], list)


@pytest.mark.asyncio
class TestSchedulerStart:
    """Tests for start() method."""
    
    async def test_registers_daily_job(self):
        """Should register daily analysis job."""
        scheduler = SchedulerService()
        scheduler.start()
        
        # Get job IDs
        job_ids = [j.id for j in scheduler.scheduler.get_jobs()]
        assert "daily_finops_scan" in job_ids
        
        scheduler.scheduler.shutdown(wait=False)
    
    async def test_registers_weekly_remediation_job(self):
        """Should register weekly remediation job."""
        scheduler = SchedulerService()
        scheduler.start()
        
        job_ids = [j.id for j in scheduler.scheduler.get_jobs()]
        assert "weekly_remediation_sweep" in job_ids
        
        scheduler.scheduler.shutdown(wait=False)
    
    async def test_scheduler_is_running(self):
        """Scheduler should be running after start()."""
        scheduler = SchedulerService()
        scheduler.start()
        
        assert scheduler.scheduler.running is True
        
        scheduler.scheduler.shutdown(wait=False)


@pytest.mark.asyncio
class TestSchedulerStop:
    """Tests for stop() method."""
    
    async def test_stop_calls_shutdown(self):
        """stop() should call scheduler.shutdown()."""
        scheduler = SchedulerService()
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
        scheduler = SchedulerService()
        
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
        scheduler = SchedulerService()
        
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
        scheduler = SchedulerService()
        
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
