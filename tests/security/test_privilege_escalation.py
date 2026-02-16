import pytest
from uuid import uuid4
from httpx import AsyncClient
from app.main import app
from app.shared.core.auth import get_current_user, CurrentUser
from datetime import datetime, timezone
from app.models.tenant import Tenant, UserRole
from app.models.background_job import BackgroundJob, JobStatus
from app.shared.core.pricing import PricingTier
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Request

# Mock user data
TENANT_A = uuid4()
TENANT_B = uuid4()

MEMBER_A = CurrentUser(
    id=uuid4(),
    email="member-a@example.com",
    tenant_id=TENANT_A,
    role=UserRole.MEMBER,
    tier=PricingTier.PRO,
)

ADMIN_A = CurrentUser(
    id=uuid4(),
    email="admin-a@example.com",
    tenant_id=TENANT_A,
    role=UserRole.ADMIN,
    tier=PricingTier.PRO,
)

OWNER_A = CurrentUser(
    id=uuid4(),
    email="owner-a@example.com",
    tenant_id=TENANT_A,
    role=UserRole.OWNER,
    tier=PricingTier.PRO,
)

MEMBER_B = CurrentUser(
    id=uuid4(),
    email="member-b@example.com",
    tenant_id=TENANT_B,
    role=UserRole.MEMBER,
    tier=PricingTier.PRO,
)


def mock_user(user: CurrentUser):
    return user


@pytest.mark.asyncio
async def test_member_cannot_process_jobs(ac: AsyncClient):
    """Verify that a user with 'member' role cannot trigger job processing."""

    def override_member_a(request: Request):
        request.state.tenant_id = MEMBER_A.tenant_id
        request.state.user_id = MEMBER_A.id
        request.state.tier = MEMBER_A.tier
        return MEMBER_A

    app.dependency_overrides[get_current_user] = override_member_a

    response = await ac.post("/api/v1/jobs/process")

    assert response.status_code == 403
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_admin_can_process_jobs(ac: AsyncClient):
    """Verify that an admin CAN trigger job processing."""

    def override_admin_a(request: Request):
        request.state.tenant_id = ADMIN_A.tenant_id
        request.state.user_id = ADMIN_A.id
        request.state.tier = ADMIN_A.tier
        return ADMIN_A

    app.dependency_overrides[get_current_user] = override_admin_a

    response = await ac.post("/api/v1/jobs/process")

    # Might be 200 or 500 depending on DB, but should NOT be 403
    assert response.status_code != 403
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_owner_bypasses_role_check(ac: AsyncClient):
    """Verify that an owner can access admin endpoints."""

    def override_owner_a(request: Request):
        request.state.tenant_id = OWNER_A.tenant_id
        request.state.user_id = OWNER_A.id
        request.state.tier = OWNER_A.tier
        return OWNER_A

    app.dependency_overrides[get_current_user] = override_owner_a

    response = await ac.get("/api/v1/jobs/status")  # Status is admin-only (GET)

    assert response.status_code != 403
    app.dependency_overrides.pop(get_current_user, None)


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
        created_at=datetime.now(timezone.utc),
    )
    db.add(job_b)
    await db.commit()

    # 2. Access as User A
    def override_member_a(request: Request):
        request.state.tenant_id = MEMBER_A.tenant_id
        request.state.user_id = MEMBER_A.id
        request.state.tier = MEMBER_A.tier
        return MEMBER_A

    app.dependency_overrides[get_current_user] = override_member_a

    response = await ac.get("/api/v1/jobs/list")

    assert response.status_code == 200
    jobs = response.json()

    # User A should NOT see Job B
    job_ids = [j["id"] for j in jobs]
    assert str(job_b.id) not in job_ids
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_member_cannot_enqueue_restricted_jobs(ac: AsyncClient):
    """Verify that valid users cannot enqueue system-level jobs (SEC-N1)."""

    def override_member_a(request: Request):
        request.state.tenant_id = MEMBER_A.tenant_id
        request.state.user_id = MEMBER_A.id
        request.state.tier = MEMBER_A.tier
        return MEMBER_A

    app.dependency_overrides[get_current_user] = override_member_a

    payload = {
        "job_type": "recurring_billing",  # Internal only
        "payload": {},
    }

    resp = await ac.post("/api/v1/jobs/enqueue", json=payload)

    # Changed to 403 because role check (RequireRole) or endpoint validation happens before Pydantic.
    # The endpoint explicitly raises 403 for unauthorized job types.
    assert resp.status_code == 403
    # In Pydantic 2, the error message for Forbidden job type (literal) might be more structured
    assert "Input should be" in resp.text or "Unauthorized job type" in resp.text
    app.dependency_overrides.pop(get_current_user, None)
