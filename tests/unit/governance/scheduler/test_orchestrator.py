import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone, timedelta
from app.modules.governance.domain.scheduler.orchestrator import SchedulerOrchestrator
from app.modules.governance.domain.scheduler.cohorts import TenantCohort
from app.models.background_job import BackgroundJob, JobStatus
import uuid

@pytest.fixture
def mock_session_maker():
    # session_maker() is called synchronously to return a session (which is async context manager)
    maker = MagicMock()
    return maker

@pytest.fixture
def orchestrator(mock_session_maker):
    return SchedulerOrchestrator(mock_session_maker)

@pytest.mark.asyncio
async def test_cohort_analysis_job_dispatch(orchestrator):
    """Test dispatching cohort analysis to Celery."""
    with patch("app.shared.core.celery_app.celery_app.send_task") as mock_send:
        await orchestrator.cohort_analysis_job(TenantCohort.HIGH_VALUE)
        mock_send.assert_called_with("scheduler.cohort_analysis", args=["high_value"])
        assert orchestrator._last_run_success is True

@pytest.mark.asyncio
async def test_low_carbon_window(orchestrator):
    """Test Green Window logic."""
    # Test Green Window (e.g., 12:00 UTC)
    with patch("app.modules.governance.domain.scheduler.orchestrator.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        is_green = await orchestrator._is_low_carbon_window("us-east-1")
        assert is_green is True
        
    # Test Non-Green Window (e.g., 18:00 UTC)
    with patch("app.modules.governance.domain.scheduler.orchestrator.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 1, 1, 18, 0, 0, tzinfo=timezone.utc)
        is_green = await orchestrator._is_low_carbon_window("us-east-1")
        assert is_green is False

@pytest.mark.asyncio
async def test_detect_stuck_jobs(orchestrator, mock_session_maker):
    """Test detection and mitigation of stuck jobs."""
    # Setup mock DB session
    mock_db = AsyncMock()
    # session_maker() returns an object that can be used in 'async with'
    # So mock_session_maker.return_value should be the context manager
    mock_session_maker.return_value.__aenter__.return_value = mock_db
    mock_session_maker.return_value.__aexit__.return_value = None
    
    stuck_job = BackgroundJob(
        id=uuid.uuid4(),
        status=JobStatus.PENDING,
        created_at=datetime.now(timezone.utc) - timedelta(hours=2)
    )
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [stuck_job]
    mock_db.execute.return_value = mock_result
    
    await orchestrator.detect_stuck_jobs()
    
    assert stuck_job.status == JobStatus.FAILED
    assert "Stuck in PENDING" in stuck_job.error_message
    mock_db.commit.assert_awaited_once()

@pytest.mark.asyncio
async def test_billing_sweep_job(orchestrator):
    """Test billing sweep dispatch."""
    with patch("app.shared.core.celery_app.celery_app.send_task") as mock_send:
        await orchestrator.billing_sweep_job()
        mock_send.assert_called_with("scheduler.billing_sweep")

@pytest.mark.asyncio
async def test_maintenance_sweep_job(orchestrator):
    """Test maintenance sweep dispatch."""
    with patch("app.shared.core.celery_app.celery_app.send_task") as mock_send:
        await orchestrator.maintenance_sweep_job()
        mock_send.assert_called_with("scheduler.maintenance_sweep")
