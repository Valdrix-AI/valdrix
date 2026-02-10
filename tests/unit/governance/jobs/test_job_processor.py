import asyncio
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4
from datetime import datetime, timezone
from app.modules.governance.domain.jobs.processor import JobProcessor, JobStatus
from app.models.background_job import BackgroundJob

@pytest.fixture
def mock_db_session():
    session = AsyncMock()
    # Mock begin_nested to return an async context manager that yields the session
    nested_ctx = AsyncMock()
    nested_ctx.__aenter__.return_value = session
    nested_ctx.__aexit__.return_value = None
    
    # IMPORTANT: begin_nested must be a MagicMock (sync) that returns the context manager
    # If we leave it as AsyncMock method, it returns a coroutine, failing 'async with'
    session.begin_nested = MagicMock(return_value=nested_ctx)
    return session

@pytest.fixture
def job_processor(mock_db_session):
    return JobProcessor(mock_db_session)

@pytest.mark.asyncio
async def test_process_pending_jobs_batch(job_processor):
    """Test batch processing loop."""
    # Setup mock jobs
    job1 = BackgroundJob(id=uuid4(), job_type="test_job", attempts=0, max_attempts=3)
    job2 = BackgroundJob(id=uuid4(), job_type="test_job", attempts=0, max_attempts=3)
    
    # Mock fetching jobs
    job_processor._fetch_pending_jobs = AsyncMock(return_value=[job1, job2])
    
    # Mock individual processing to succeed
    async def mark_complete(job):
        job.status = JobStatus.COMPLETED.value

    job_processor._process_single_job = AsyncMock(side_effect=mark_complete)
    
    results = await job_processor.process_pending_jobs(limit=5)
    
    assert results["processed"] == 2
    assert results["succeeded"] == 2
    assert results["failed"] == 0
    # Use call from unittest.mock
    from unittest.mock import call
    job_processor._process_single_job.assert_has_awaits([
        call(job1),
        call(job2)
    ])


@pytest.mark.asyncio
async def test_process_pending_jobs_counts_failed(job_processor):
    job = BackgroundJob(id=uuid4(), job_type="test_job", attempts=0, max_attempts=3)
    job_processor._fetch_pending_jobs = AsyncMock(return_value=[job])

    async def mark_failed(job):
        job.status = JobStatus.FAILED.value
        job.error_message = "boom"

    job_processor._process_single_job = AsyncMock(side_effect=mark_failed)

    results = await job_processor.process_pending_jobs(limit=1)

    assert results["processed"] == 1
    assert results["succeeded"] == 0
    assert results["failed"] == 1
    assert results["errors"][0]["error"] == "boom"


@pytest.mark.asyncio
async def test_process_pending_jobs_config_error(job_processor):
    job = BackgroundJob(id=uuid4(), job_type="test_job", attempts=0, max_attempts=3)
    job_processor._fetch_pending_jobs = AsyncMock(return_value=[job])
    job_processor._process_single_job = AsyncMock(side_effect=KeyError("bad config"))

    results = await job_processor.process_pending_jobs(limit=1)

    assert results["processed"] == 1
    assert results["failed"] == 1
    assert results["errors"][0]["type"] == "config"


@pytest.mark.asyncio
async def test_process_pending_jobs_db_error(job_processor):
    from sqlalchemy.exc import SQLAlchemyError

    job_processor._fetch_pending_jobs = AsyncMock(side_effect=SQLAlchemyError("db error"))
    results = await job_processor.process_pending_jobs(limit=1)

    assert results["processed"] == 0
    assert results["failed"] == 0
    assert results["errors"]

@pytest.mark.asyncio
async def test_process_single_job_success(job_processor, mock_db_session):
    """Test successful job execution."""
    job = BackgroundJob(id=uuid4(), job_type="test_job", attempts=0, max_attempts=3, status=JobStatus.PENDING.value)
    
    # Mock handler factory/execution
    with patch("app.modules.governance.domain.jobs.processor.get_handler_factory") as mock_factory:
        mock_handler = AsyncMock()
        mock_handler.execute.return_value = {"status": "ok"}
        mock_factory.return_value.return_value = mock_handler
        
        await job_processor._process_single_job(job)
        
        # Verify status update
        assert job.status == JobStatus.COMPLETED.value
        assert job.result == {"status": "ok"}
        assert job.attempts == 1
        mock_db_session.commit.assert_awaited()

@pytest.mark.asyncio
async def test_process_single_job_retry(job_processor, mock_db_session):
    """Test job failure and backoff."""
    job = BackgroundJob(id=uuid4(), job_type="test_job", attempts=0, max_attempts=3, status=JobStatus.PENDING.value)
    
    # Mock handler to raise exception
    with patch("app.modules.governance.domain.jobs.processor.get_handler_factory") as mock_factory:
        mock_handler = AsyncMock()
        # Side effect must be an exception, not an async mock raising it in a weird way?
        # AsyncMock side_effect can be an exception
        mock_handler.execute.side_effect = Exception("Processing Error")
        
        mock_factory.return_value.return_value = mock_handler
        
        await job_processor._process_single_job(job)
        
        # Verify pending with backoff
        assert job.status == JobStatus.PENDING.value
        assert job.attempts == 1
        assert "Processing Error" in job.error_message
        assert job.scheduled_for > datetime.now(timezone.utc)
        mock_db_session.commit.assert_awaited()

@pytest.mark.asyncio
async def test_process_single_job_dead_letter(job_processor, mock_db_session):
    """Test job exhaustion to dead letter."""
    job = BackgroundJob(id=uuid4(), job_type="test_job", attempts=2, max_attempts=3)
    
    with patch("app.modules.governance.domain.jobs.processor.get_handler_factory") as mock_factory:
        mock_handler = AsyncMock()
        mock_handler.execute.side_effect = Exception("Final Error")
        mock_factory.return_value.return_value = mock_handler
        
        await job_processor._process_single_job(job)
        
        # Verify dead letter (attempts incremented to 3, which is >= max_attempts if we increment first?
        # Logic says: attempts += 1 (so becomes 3). Then if attempts >= max (3>=3), DEAD_LETTER
        assert job.status == JobStatus.DEAD_LETTER.value
        assert job.attempts == 3
        mock_db_session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_process_single_job_timeout(job_processor, mock_db_session):
    job = BackgroundJob(id=uuid4(), job_type="test_job", attempts=0, max_attempts=2, status=JobStatus.PENDING.value)

    async def fake_wait_for(coro, timeout):
        await coro
        raise asyncio.TimeoutError

    with patch("app.modules.governance.domain.jobs.processor.get_handler_factory") as mock_factory, \
         patch("app.modules.governance.domain.jobs.processor.asyncio.wait_for", new=fake_wait_for):
        mock_handler = AsyncMock()
        mock_handler.execute = AsyncMock(return_value=None)
        mock_factory.return_value.return_value = mock_handler

        await job_processor._process_single_job(job)

        assert job.status == JobStatus.PENDING.value
        assert job.attempts == 1
        assert "timed out" in job.error_message
        assert job.scheduled_for > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_process_single_job_cancelled(job_processor, mock_db_session):
    job = BackgroundJob(id=uuid4(), job_type="test_job", attempts=0, max_attempts=3, status=JobStatus.PENDING.value)

    with patch("app.modules.governance.domain.jobs.processor.get_handler_factory") as mock_factory:
        mock_handler = AsyncMock()
        mock_handler.execute = AsyncMock(side_effect=asyncio.CancelledError)
        mock_factory.return_value.return_value = mock_handler

        await job_processor._process_single_job(job)

        assert job.status == JobStatus.PENDING.value
        assert job.error_message == "Job was cancelled"
        assert job.scheduled_for > datetime.now(timezone.utc)
