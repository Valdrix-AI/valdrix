import pytest
import uuid
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch
from app.main import app
from app.models.background_job import BackgroundJob, JobStatus, JobType
from app.shared.core.auth import get_current_user
from datetime import datetime, timezone, timedelta


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.tenant_id = uuid.uuid4()
    user.role = "admin"
    user.tier = "pro"
    return user


@pytest.fixture(autouse=True)
def override_auth(mock_user):
    app.dependency_overrides[get_current_user] = lambda: mock_user
    yield
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
        created_at=now,
    )
    db_session.add(job1)
    await db_session.commit()

    response = await async_client.get("/api/v1/jobs/status")
    assert response.status_code == 200
    data = response.json()
    assert data["pending"] == 1


@pytest.mark.asyncio
async def test_get_job_slo(async_client: AsyncClient, db_session, mock_user):
    """Test GET /api/v1/jobs/slo returns per-job-type reliability metrics."""
    now = datetime.now(timezone.utc)
    completed = BackgroundJob(
        id=uuid.uuid4(),
        tenant_id=mock_user.tenant_id,
        job_type=JobType.COST_INGESTION.value,
        status=JobStatus.COMPLETED.value,
        attempts=0,
        scheduled_for=now,
        created_at=now,
        started_at=now - timedelta(seconds=30),
        completed_at=now,
        is_deleted=False,
    )
    failed = BackgroundJob(
        id=uuid.uuid4(),
        tenant_id=mock_user.tenant_id,
        job_type=JobType.COST_INGESTION.value,
        status=JobStatus.FAILED.value,
        attempts=1,
        scheduled_for=now,
        created_at=now,
        started_at=now - timedelta(seconds=10),
        completed_at=now,
        error_message="boom",
        is_deleted=False,
    )
    db_session.add_all([completed, failed])
    await db_session.commit()

    response = await async_client.get(
        "/api/v1/jobs/slo",
        params={"window_hours": 1, "target_success_rate_percent": 50},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["window_hours"] == 1
    assert payload["target_success_rate_percent"] == 50.0
    assert isinstance(payload["metrics"], list)
    assert any(
        metric["job_type"] == JobType.COST_INGESTION.value
        for metric in payload["metrics"]
    )


@pytest.mark.asyncio
async def test_process_jobs_manual(async_client: AsyncClient):
    """Test manual job processing trigger."""
    with patch(
        "app.modules.governance.api.v1.jobs.JobProcessor.process_pending_jobs"
    ) as mock_proc:
        mock_proc.return_value = {"processed": 1, "succeeded": 1, "failed": 0}
        response = await async_client.post("/api/v1/jobs/process")
        assert response.status_code == 200
        assert response.json()["processed"] == 1


@pytest.mark.asyncio
async def test_process_jobs_internal_unauthorized(async_client: AsyncClient):
    """Test internal pg_cron trigger fails with invalid secret."""
    secret = "a" * 32
    with patch("app.shared.core.config.get_settings") as mock_get_settings:
        mock_settings = MagicMock()
        mock_settings.INTERNAL_JOB_SECRET = secret
        mock_get_settings.return_value = mock_settings

        response = await async_client.post(
            "/api/v1/jobs/internal/process", params={"secret": "wrong"}
        )
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_process_jobs_internal_success(async_client: AsyncClient):
    """Test internal pg_cron trigger success."""
    # Patch globally since it's a local import in jobs.py
    with patch("app.shared.core.config.get_settings") as mock_get_settings:
        mock_settings = MagicMock()
        mock_settings.INTERNAL_JOB_SECRET = "s" * 32
        mock_get_settings.return_value = mock_settings

        response = await async_client.post(
            "/api/v1/jobs/internal/process", params={"secret": "s" * 32}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "accepted"


@pytest.mark.asyncio
async def test_process_jobs_internal_insecure_secret_rejected(
    async_client: AsyncClient,
):
    with patch("app.shared.core.config.get_settings") as mock_get_settings:
        mock_settings = MagicMock()
        mock_settings.INTERNAL_JOB_SECRET = "short-secret"
        mock_get_settings.return_value = mock_settings

        response = await async_client.post(
            "/api/v1/jobs/internal/process", params={"secret": "short-secret"}
        )
        assert response.status_code == 503


@pytest.mark.asyncio
async def test_process_jobs_internal_insecure_secret_rejected(
    async_client: AsyncClient,
):
    with patch("app.shared.core.config.get_settings") as mock_get_settings:
        mock_settings = MagicMock()
        mock_settings.INTERNAL_JOB_SECRET = "short-secret"
        mock_get_settings.return_value = mock_settings

        response = await async_client.post(
            "/api/v1/jobs/internal/process", params={"secret": "short-secret"}
        )
        assert response.status_code == 503


@pytest.mark.asyncio
async def test_stream_jobs_sse(async_client: AsyncClient):
    """Test SSE streaming endpoint connectivity."""
    from sse_starlette.sse import EventSourceResponse
    import asyncio

    async def mock_generator():
        yield {"event": "ping", "data": "heartbeat"}

    # Patch EventSourceResponse to use our finite generator
    with patch(
        "app.modules.governance.api.v1.jobs.EventSourceResponse"
    ) as mock_sse_class:
        mock_sse_class.side_effect = lambda gen: EventSourceResponse(mock_generator())

        try:
            # Use a strict timeout for the streaming request
            async with asyncio.timeout(5):
                async with async_client.stream(
                    "GET", "/api/v1/jobs/stream"
                ) as response:
                    assert response.status_code == 200

                    found_heartbeat = False
                    async for line in response.aiter_lines():
                        if "heartbeat" in line:
                            found_heartbeat = True
                            break

                    assert found_heartbeat, "Heartbeat not found in SSE stream"
        except TimeoutError:
            pytest.fail("SSE stream test timed out after 5 seconds")


@pytest.mark.asyncio
async def test_stream_jobs_sse_rejects_when_tenant_connection_limit_reached(
    async_client: AsyncClient, mock_user
):
    from app.modules.governance.api.v1 import jobs as jobs_api

    tenant_key = str(mock_user.tenant_id)
    jobs_api._active_sse_connections[tenant_key] = 1
    try:
        with patch("app.shared.core.config.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.SSE_MAX_CONNECTIONS_PER_TENANT = 1
            mock_settings.SSE_POLL_INTERVAL_SECONDS = 3
            mock_get_settings.return_value = mock_settings

            response = await async_client.get("/api/v1/jobs/stream")
            assert response.status_code == 429
    finally:
        jobs_api._active_sse_connections.clear()


@pytest.mark.asyncio
async def test_enqueue_new_job_rejects_internal_job_type(async_client: AsyncClient):
    response = await async_client.post(
        "/api/v1/jobs/enqueue",
        json={"job_type": JobType.COST_INGESTION.value, "payload": {"k": "v"}},
    )
    assert response.status_code == 403
    assert "Unauthorized job type" in response.json()["error"]


@pytest.mark.asyncio
async def test_enqueue_new_job_success(async_client: AsyncClient):
    now = datetime.now(timezone.utc)
    mock_job = MagicMock()
    mock_job.id = uuid.uuid4()
    mock_job.job_type = JobType.NOTIFICATION.value
    mock_job.status = JobStatus.PENDING.value
    mock_job.attempts = 0
    mock_job.scheduled_for = now
    mock_job.created_at = now
    with patch(
        "app.modules.governance.api.v1.jobs.enqueue_job",
        new=AsyncMock(return_value=mock_job),
    ):
        response = await async_client.post(
            "/api/v1/jobs/enqueue",
            json={"job_type": JobType.NOTIFICATION.value, "payload": {"msg": "hello"}},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(mock_job.id)
    assert body["job_type"] == JobType.NOTIFICATION.value
    assert body["status"] == JobStatus.PENDING.value


@pytest.mark.asyncio
async def test_list_jobs_filters_status_and_sanitizes_error(
    async_client: AsyncClient, db_session, mock_user
):
    now = datetime.now(timezone.utc)
    pending_job = BackgroundJob(
        id=uuid.uuid4(),
        tenant_id=mock_user.tenant_id,
        job_type=JobType.ZOMBIE_SCAN.value,
        status=JobStatus.PENDING.value,
        attempts=0,
        scheduled_for=now,
        created_at=now,
        updated_at=now,
        is_deleted=False,
    )
    failed_job = BackgroundJob(
        id=uuid.uuid4(),
        tenant_id=mock_user.tenant_id,
        job_type=JobType.NOTIFICATION.value,
        status=JobStatus.FAILED.value,
        attempts=1,
        scheduled_for=now,
        created_at=now,
        updated_at=now,
        error_message="traceback:secret-details",
        is_deleted=False,
    )
    db_session.add_all([pending_job, failed_job])
    await db_session.commit()

    response = await async_client.get(
        "/api/v1/jobs/list",
        params={
            "status": JobStatus.FAILED.value,
            "sort_by": "created_at",
            "order": "asc",
            "limit": 20,
        },
    )
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 1
    assert jobs[0]["id"] == str(failed_job.id)
    assert jobs[0]["error_message"] == "traceback"
