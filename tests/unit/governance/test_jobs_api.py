import pytest
import uuid
from httpx import AsyncClient
from unittest.mock import patch, MagicMock
from app.main import app
from app.models.background_job import BackgroundJob, JobStatus, JobType
from app.shared.core.auth import get_current_user
from datetime import datetime, timezone

@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.tenant_id = uuid.uuid4()
    user.role = "admin"
    return user

@pytest.fixture(autouse=True)
def override_auth(mock_user):
    app.dependency_overrides[get_current_user] = lambda: mock_user
    yield
    yield
    from app.shared.core.auth import get_current_user
    app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.asyncio
async def test_get_queue_status(async_client: AsyncClient, db_session, mock_user):
    """Test GET /api/v1/jobs/status."""
    now = datetime.now(timezone.utc)
    job1 = BackgroundJob(
        id=uuid.uuid4(),
        tenant_id=mock_user.tenant_id,
        job_type=JobType.ZOMBIE_SCAN.value,
        status=JobStatus.PENDING.value,
        scheduled_for=now,
        created_at=now
    )
    db_session.add(job1)
    await db_session.commit()
    
    response = await async_client.get("/api/v1/jobs/status")
    assert response.status_code == 200
    data = response.json()
    assert data["pending"] == 1

@pytest.mark.asyncio
async def test_process_jobs_manual(async_client: AsyncClient):
    """Test manual job processing trigger."""
    with patch("app.modules.governance.api.v1.jobs.JobProcessor.process_pending_jobs") as mock_proc:
        mock_proc.return_value = {"processed": 1, "succeeded": 1, "failed": 0}
        response = await async_client.post("/api/v1/jobs/process")
        assert response.status_code == 200
        assert response.json()["processed"] == 1

@pytest.mark.asyncio
async def test_process_jobs_internal_unauthorized(async_client: AsyncClient):
    """Test internal pg_cron trigger fails with invalid secret."""
    response = await async_client.post("/api/v1/jobs/internal/process", params={"secret": "wrong"})
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_process_jobs_internal_success(async_client: AsyncClient):
    """Test internal pg_cron trigger success."""
    # Patch globally since it's a local import in jobs.py
    with patch("app.shared.core.config.get_settings") as mock_get_settings:
        mock_settings = MagicMock()
        mock_settings.INTERNAL_JOB_SECRET = "super-secret"
        mock_get_settings.return_value = mock_settings
        
        response = await async_client.post(
            "/api/v1/jobs/internal/process", 
            params={"secret": "super-secret"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "accepted"

@pytest.mark.asyncio
async def test_stream_jobs_sse(async_client: AsyncClient):
    """Test SSE streaming endpoint connectivity."""
    from sse_starlette.sse import EventSourceResponse
    import asyncio

    async def mock_generator():
        yield {"event": "ping", "data": "heartbeat"}

    # Patch EventSourceResponse to use our finite generator
    with patch("app.modules.governance.api.v1.jobs.EventSourceResponse") as mock_sse_class:
        mock_sse_class.side_effect = lambda gen: EventSourceResponse(mock_generator())

        try:
            # Use a strict timeout for the streaming request
            async with asyncio.timeout(5):
                async with async_client.stream("GET", "/api/v1/jobs/stream") as response:
                    assert response.status_code == 200
                    
                    found_heartbeat = False
                    async for line in response.aiter_lines():
                        if "heartbeat" in line:
                            found_heartbeat = True
                            break
                    
                    assert found_heartbeat, "Heartbeat not found in SSE stream"
        except TimeoutError:
            pytest.fail("SSE stream test timed out after 5 seconds")
