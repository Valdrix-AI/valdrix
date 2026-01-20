import pytest
from uuid import uuid4
from httpx import AsyncClient
from app.main import app
from app.core.auth import get_current_user, CurrentUser
from datetime import datetime, timezone
from app.models.tenant import Tenant
from app.models.background_job import BackgroundJob, JobStatus
from sqlalchemy.ext.asyncio import AsyncSession

# Mock user data
TENANT_A = uuid4()
TENANT_B = uuid4()

MEMBER_A = CurrentUser(
    id=uuid4(),
    email="member-a@example.com",
    tenant_id=TENANT_A,
    role="member",
    tier="pro"
)

ADMIN_A = CurrentUser(
    id=uuid4(),
    email="admin-a@example.com",
    tenant_id=TENANT_A,
    role="admin",
    tier="pro"
)

OWNER_A = CurrentUser(
    id=uuid4(),
    email="owner-a@example.com",
    tenant_id=TENANT_A,
    role="owner",
    tier="pro"
)

MEMBER_B = CurrentUser(
    id=uuid4(),
    email="member-b@example.com",
    tenant_id=TENANT_B,
    role="member",
    tier="pro"
)

def mock_user(user: CurrentUser):
    return user

@pytest.mark.asyncio
async def test_member_cannot_process_jobs(ac: AsyncClient):
    """Verify that a user with 'member' role cannot trigger job processing."""
    app.dependency_overrides[get_current_user] = lambda: mock_user(MEMBER_A)
    
    response = await ac.post("/api/v1/jobs/process")
    
    assert response.status_code == 403
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_admin_can_process_jobs(ac: AsyncClient):
    """Verify that an admin CAN trigger job processing."""
    app.dependency_overrides[get_current_user] = lambda: mock_user(ADMIN_A)
    
    response = await ac.post("/api/v1/jobs/process")
    
    # Might be 200 or 500 depending on DB, but should NOT be 403
    assert response.status_code != 403
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_owner_bypasses_role_check(ac: AsyncClient):
    """Verify that an owner can access admin endpoints."""
    app.dependency_overrides[get_current_user] = lambda: mock_user(OWNER_A)
    
    response = await ac.get("/api/v1/jobs/status") # Status is admin-only (GET)
    
    assert response.status_code != 403
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_cross_tenant_isolation(ac: AsyncClient, db: AsyncSession):
    """Verify that User A cannot see Job B (broken RLS/Tenant filtering)."""
    # 0. Create tenants
    tenant_a = Tenant(id=TENANT_A, name="Tenant A", plan="pro")
    tenant_b = Tenant(id=TENANT_B, name="Tenant B", plan="pro")
    db.add_all([tenant_a, tenant_b])
    await db.commit()

    # 1. Create a job for Tenant B
    job_b = BackgroundJob(
        id=uuid4(),
        tenant_id=TENANT_B,
        job_type="zombie_scan",
        status=JobStatus.PENDING,
        scheduled_for=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc)
    )
    db.add(job_b)
    await db.commit()

    # 2. Access as User A
    app.dependency_overrides[get_current_user] = lambda: mock_user(MEMBER_A)
    
    response = await ac.get("/api/v1/jobs/list")
    
    assert response.status_code == 200
    jobs = response.json()
    
    # User A should NOT see Job B
    job_ids = [j["id"] for j in jobs]
    assert str(job_b.id) not in job_ids
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_member_cannot_enqueue_restricted_jobs(ac: AsyncClient):
    """Verify that valid users cannot enqueue system-level jobs (SEC-N1)."""
    app.dependency_overrides[get_current_user] = lambda: mock_user(MEMBER_A)
    
    payload = {
        "job_type": "recurring_billing", # Internal only
        "payload": {}
    }
    
    resp = await ac.post("/api/v1/jobs/enqueue", json=payload)
    
    # Changed from 403 to 422 because Literal schema hardening (M5) catches this at validation layer
    assert resp.status_code == 422
    # In Pydantic 2, the error message for Forbidden job type (literal) might be more structured
    assert "Input should be" in resp.text or "Unauthorized job type" in resp.text
    app.dependency_overrides.clear()
