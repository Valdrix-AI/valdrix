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
    app.dependency_overrides.clear()

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

@pytest.mark.skip(reason="SSE stream test hangs in CI/CD environments with sse-starlette")
@pytest.mark.asyncio
async def test_stream_jobs_sse(async_client: AsyncClient):
    """Test SSE streaming endpoint connectivity."""
    pass
