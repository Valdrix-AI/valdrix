
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.governance.domain.jobs.handlers.base import BaseJobHandler, JobTimeoutError
from app.models.background_job import BackgroundJob, JobStatus
from app.shared.core.exceptions import ValdrixException
import asyncio

# Concrete implementation for testing
class TestHandler(BaseJobHandler):
    timeout_seconds = 1  # Short timeout for testing
    
    async def execute(self, job: BackgroundJob, db: AsyncSession):
        # Default behavior: success
        return {"status": "success"}

class SlowHandler(BaseJobHandler):
    timeout_seconds = 0.1
    
    async def execute(self, job: BackgroundJob, db: AsyncSession):
        await asyncio.sleep(0.5) # Sleep longer than timeout
        return {"status": "too_slow"}

class ErrorHandler(BaseJobHandler):
    async def execute(self, job: BackgroundJob, db: AsyncSession):
        raise ValueError("Unexpected boom")

class ValdrixErrorHandler(BaseJobHandler):
    async def execute(self, job: BackgroundJob, db: AsyncSession):
        raise ValdrixException("Expected boom", code="test_error", status_code=400)

@pytest.fixture
def mock_db():
    db = AsyncMock(spec=AsyncSession)
    db.add = MagicMock()
    # db.commit is already an AsyncMock
    return db

@pytest.fixture
def job():
    return BackgroundJob(
        id=uuid4(),
        tenant_id=uuid4(),
        job_type="TEST_JOB",
        status=JobStatus.PENDING,
        attempts=0,
        payload={}
    )

@pytest.mark.asyncio
async def test_process_success(mock_db, job):
    handler = TestHandler()
    result = await handler.process(job, mock_db)
    
    assert result == {"status": "success"}
    assert job.status == JobStatus.COMPLETED
    assert job.result == {"status": "success"}
    assert job.started_at is not None
    assert job.completed_at is not None
    assert mock_db.commit.call_count >= 2 # Once for running, once for completed

@pytest.mark.asyncio
async def test_process_timeout(mock_db, job):
    handler = SlowHandler()
    
    with pytest.raises(JobTimeoutError):
        await handler.process(job, mock_db)
    
    # Check DLQ transition
    assert job.status == JobStatus.DEAD_LETTER
    assert "Job exceeded" in job.error_message
    assert mock_db.commit.call_count >= 2

@pytest.mark.asyncio
async def test_process_retry_valdrix_exception(mock_db, job):
    handler = ValdrixErrorHandler()
    handler.max_retries = 3
    
    with pytest.raises(ValdrixException):
        await handler.process(job, mock_db)
        
    assert job.status == JobStatus.FAILED
    assert job.attempts == 1
    assert "test_error" in job.error_message

@pytest.mark.asyncio
async def test_process_max_retries_exceeded(mock_db, job):
    handler = ValdrixErrorHandler()
    handler.max_retries = 1
    job.attempts = 1 # Already tried once
    
    with pytest.raises(ValdrixException):
        await handler.process(job, mock_db)
        
    assert job.status == JobStatus.DEAD_LETTER
    assert "Exceeded 1 retries" in job.error_message

@pytest.mark.asyncio
async def test_process_unexpected_error(mock_db, job):
    handler = ErrorHandler()
    
    with pytest.raises(ValueError):
        await handler.process(job, mock_db)
        
    assert job.status == JobStatus.DEAD_LETTER
    assert "Unexpected error" in job.error_message
