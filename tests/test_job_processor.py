"""
Tests for Background Job Processor

Covers:
- Job state machine (pending → running → completed/failed)
- Retry logic with exponential backoff
- Dead letter queue on max attempts
- Job enqueueing
"""

import pytest
from typing import Annotated, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from app.models.background_job import BackgroundJob, JobStatus, JobType
from app.services.jobs.processor import JobProcessor, enqueue_job, BACKOFF_BASE_SECONDS


def create_mock_job(
    job_type: str = JobType.FINOPS_ANALYSIS,
    status: str = JobStatus.PENDING,
    attempts: int = 0,
    max_attempts: int = 3,
    scheduled_for: Optional[datetime] = None
) -> BackgroundJob:
    """Create a mock job for testing."""
    job = MagicMock(spec=BackgroundJob)
    job.id = uuid4()
    job.job_type = job_type
    job.status = status.value if hasattr(status, "value") else status
    job.attempts = attempts
    job.max_attempts = max_attempts
    job.tenant_id = uuid4()
    job.payload = {}
    job.scheduled_for = scheduled_for or datetime.now(timezone.utc)
    job.created_at = datetime.now(timezone.utc)
    job.started_at = None
    job.completed_at = None
    job.error_message = None
    job.result = None
    return job


class TestJobProcessor:
    """Tests for JobProcessor class."""
    
    @pytest.mark.asyncio
    async def test_process_pending_jobs_empty_queue(self):
        """Should handle empty queue gracefully."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        
        processor = JobProcessor(mock_db)
        results = await processor.process_pending_jobs()
        
        assert results["processed"] == 0
        assert results["succeeded"] == 0
        assert results["failed"] == 0
    
    @pytest.mark.asyncio
    @patch('app.services.jobs.processor.get_handler_factory')
    async def test_marks_job_running_on_start(self, mock_factory):
        """Job status should change to RUNNING when processing starts."""
        mock_db = AsyncMock()
        mock_job = create_mock_job()
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_job]
        mock_db.execute.return_value = mock_result
        
        processor = JobProcessor(mock_db)
        
        # Mock handler to verify state
        mock_handler = MagicMock()
        async def verify_handler(job, db):
            assert job.status == JobStatus.RUNNING.value
            return {"status": "ok"}
        mock_handler.return_value.execute = verify_handler
        mock_factory.return_value = mock_handler
        
        await processor.process_pending_jobs()
    
    @pytest.mark.asyncio
    @patch('app.services.jobs.processor.get_handler_factory')
    async def test_marks_job_completed_on_success(self, mock_factory):
        """Job status should change to COMPLETED on success."""
        mock_db = AsyncMock()
        mock_db.begin_nested = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock()
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_db.begin_nested.return_value = mock_ctx
        
        mock_job = create_mock_job()
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_job]
        mock_db.execute.return_value = mock_result
        
        processor = JobProcessor(mock_db)
        
        mock_handler = MagicMock()
        mock_handler.return_value.execute = AsyncMock(return_value={"status": "completed"})
        mock_factory.return_value = mock_handler
        
        await processor.process_pending_jobs()
        
        assert mock_job.status == JobStatus.COMPLETED.value
        assert mock_job.completed_at is not None
    
    @pytest.mark.asyncio
    @patch('app.services.jobs.processor.get_handler_factory')
    async def test_retries_on_failure(self, mock_factory):
        """Job should be rescheduled on failure with backoff."""
        mock_db = AsyncMock()
        mock_db.begin_nested = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock()
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_db.begin_nested.return_value = mock_ctx
        
        mock_job = create_mock_job(attempts=0, max_attempts=3)
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_job]
        mock_db.execute.return_value = mock_result
        
        processor = JobProcessor(mock_db)
        
        mock_handler = MagicMock()
        mock_handler.return_value.execute = AsyncMock(side_effect=Exception("Simulated failure"))
        mock_factory.return_value = mock_handler
        
        await processor.process_pending_jobs()
        
        # Should be pending again for retry
        assert mock_job.status == JobStatus.PENDING.value
        assert mock_job.error_message == "Simulated failure"
        # Scheduled in the future
        assert mock_job.scheduled_for > datetime.now(timezone.utc) - timedelta(seconds=1)
    
    @pytest.mark.asyncio
    @patch('app.services.jobs.processor.get_handler_factory')
    async def test_dead_letter_on_max_attempts(self, mock_factory):
        """Job should go to dead letter after max attempts."""
        mock_db = AsyncMock()
        mock_db.begin_nested = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock()
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_db.begin_nested.return_value = mock_ctx
        
        mock_job = create_mock_job(attempts=2, max_attempts=3)  # This will be attempt 3
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_job]
        mock_db.execute.return_value = mock_result
        
        processor = JobProcessor(mock_db)
        
        mock_handler = MagicMock()
        mock_handler.return_value.execute = AsyncMock(side_effect=Exception("Final failure"))
        mock_factory.return_value = mock_handler
        
        await processor.process_pending_jobs()
        
        assert mock_job.status == JobStatus.DEAD_LETTER.value
        assert mock_job.completed_at is not None
    
    @pytest.mark.asyncio
    @patch('app.services.jobs.processor.get_handler_factory')
    async def test_increments_attempts(self, mock_factory):
        """Attempts should increment on each processing."""
        mock_db = AsyncMock()
        mock_job = create_mock_job(attempts=0)
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_job]
        mock_db.execute.return_value = mock_result
        
        processor = JobProcessor(mock_db)
        
        mock_handler = MagicMock()
        mock_handler.return_value.execute = AsyncMock(return_value={})
        mock_factory.return_value = mock_handler
        
        await processor.process_pending_jobs()
        
        assert mock_job.attempts == 1
    
    @pytest.mark.asyncio
    async def test_handles_missing_handler(self):
        """Should set error message if no handler for job type."""
        mock_db = AsyncMock()
        mock_job = create_mock_job(job_type="unknown_type")
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_job]
        mock_db.execute.return_value = mock_result
        
        processor = JobProcessor(mock_db)
        
        await processor.process_pending_jobs()
        
        # Error should be recorded on the job
        assert mock_job.error_message is not None
        assert "No handler" in mock_job.error_message


class TestEnqueueJob:
    """Tests for enqueue_job helper."""
    
    @pytest.mark.asyncio
    async def test_creates_job_with_defaults(self):
        """Should create job with default values."""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        
        with patch('app.services.jobs.processor.BackgroundJob') as MockJob:
            mock_instance = MagicMock()
            mock_instance.id = uuid4()
            MockJob.return_value = mock_instance
            
            await enqueue_job(
                db=mock_db,
                job_type=JobType.FINOPS_ANALYSIS,
                tenant_id=uuid4()
            )
            
            mock_db.add.assert_called_once()
            mock_db.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_respects_scheduled_for(self):
        """Should use provided scheduled_for time."""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        
        with patch('app.services.jobs.processor.BackgroundJob') as MockJob:
            mock_instance = MagicMock()
            mock_instance.id = uuid4()
            MockJob.return_value = mock_instance
            
            await enqueue_job(
                db=mock_db,
                job_type=JobType.ZOMBIE_SCAN,
                scheduled_for=future_time
            )
            
            # Verify scheduled_for was passed
            call_kwargs = MockJob.call_args[1]
            assert call_kwargs["scheduled_for"] == future_time


class TestJobBackoff:
    """Tests for exponential backoff logic."""
    
    def test_backoff_exponential(self):
        """Backoff should increase exponentially."""
        # Attempt 1: 60 seconds
        # Attempt 2: 120 seconds  
        # Attempt 3: 240 seconds
        assert BACKOFF_BASE_SECONDS * (2 ** 0) == 60
        assert BACKOFF_BASE_SECONDS * (2 ** 1) == 120
        assert BACKOFF_BASE_SECONDS * (2 ** 2) == 240
