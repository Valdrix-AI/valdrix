import pytest
import pytest_asyncio
import uuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.azure_connection import AzureConnection
from app.main import app
from app.shared.core.auth import get_current_user, CurrentUser
from app.models.tenant import Tenant

# Mocks
TENANT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()

MOCK_USER = CurrentUser(
    id=USER_ID,
    email="test@example.com",
    tenant_id=TENANT_ID,
    role="admin",
    tier="pro"
)

@pytest_asyncio.fixture
async def mock_auth(db: AsyncSession):
    # Ensure tenant exists to avoid ForeignKeyViolation
    tenant = Tenant(id=TENANT_ID, name="Test Tenant", plan="pro")
    await db.merge(tenant)
    await db.commit()
    
    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    yield
    app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.asyncio
async def test_duplicate_azure_connection_fails(ac: AsyncClient, db: AsyncSession, mock_auth):
    """Verify B1: UniqueConstraint on Azure connections."""
    sub_id = "sub-123"
    
    # 1. Create first connection
    conn1 = AzureConnection(
        tenant_id=TENANT_ID,
        name="Conn 1",
        azure_tenant_id="tenant-123",
        client_id="client-123",
        subscription_id=sub_id
    )
    db.add(conn1)
    await db.commit()

    # 2. Try creating duplicate
    conn2 = AzureConnection(
        tenant_id=TENANT_ID,
        name="Conn 2",
        azure_tenant_id="tenant-123",
        client_id="client-456",
        subscription_id=sub_id
    )
    db.add(conn2)
    with pytest.raises(Exception): # Should raise IntegrityError
        await db.commit()
    await db.rollback()

@pytest.mark.asyncio
async def test_pagination_bounds_m4(ac: AsyncClient, mock_auth):
    """Verify M4: limit must be >= 1."""
    # Test on audit list
    response = await ac.get("/api/v1/audit/logs?limit=0")
    assert response.status_code == 422
    assert "greater than or equal to 1" in response.text
    
    response = await ac.get("/api/v1/audit/logs?limit=-1")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_audit_logs_reject_sort_by_actor_email(ac: AsyncClient, mock_auth):
    response = await ac.get("/api/v1/audit/logs?sort_by=actor_email")
    assert response.status_code == 400
    assert "actor_email" in response.text.lower()

@pytest.mark.asyncio
async def test_job_type_hardening_m5(ac: AsyncClient, mock_auth):
    """Verify M5: EnqueueJobRequest uses Literal for job_type."""
    payload = {
        "job_type": "invalid_type",
        "payload": {}
    }
    response = await ac.post("/api/v1/jobs/enqueue", json=payload)
    assert response.status_code == 422
    # Pydantic validation error
    err_text = response.text.lower()
    assert any(x in err_text for x in ["literal", "pattern", "input_value", "validation_error"])

@pytest.mark.asyncio
async def test_startup_validation_q1():
    """Verify Q1: Startup validation for critical keys."""
    # This is hard to test in-process, but we can verify the logic in Settings
    from app.shared.core.config import Settings
    
    # Missing database URL in prod
    with pytest.raises(ValueError) as exc:
        # Provide valid CSRF to reach DATABASE_URL check
        # Instantiation triggers validate_security_config model_validator
        Settings(
            DATABASE_URL="", 
            ENVIRONMENT="production",
            DEBUG=False, 
            TESTING=False, 
            SUPABASE_JWT_SECRET="too-short-but-different",
            CSRF_SECRET_KEY="a-very-long-and-secure-csrf-secret-key-12345"
        )
    assert "DATABASE_URL" in str(exc.value) or "validation error" in str(exc.value).lower()
