import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy import select
from app.shared.core.auth import CurrentUser, get_current_user_from_jwt, UserRole
from app.models.tenant import User

@pytest.fixture
def mock_user():
    user_id = uuid.uuid4()
    return CurrentUser(id=user_id, tenant_id=None, email=f"onboard_{uuid.uuid4().hex[:8]}@test.io", role=UserRole.MEMBER)

@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    # Mock the return value chain for sqlalchemy execute
    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock()
    db.execute.return_value = mock_result
    
    def add_side_effect(obj):
        # Set ID if it's a Tenant model
        if hasattr(obj, "id") and obj.id is None:
            obj.id = uuid.uuid4()
            
    db.add = MagicMock(side_effect=add_side_effect)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db

@pytest.mark.asyncio
async def test_onboard_lifecycle(async_client: AsyncClient, db, app):
    """Deep test for the Onboarding API using real DB fixture."""
    user_id = uuid.uuid4()
    email = f"onboard_{uuid.uuid4().hex[:8]}@test.io"
    mock_user = CurrentUser(id=user_id, tenant_id=None, email=email, role=UserRole.MEMBER)
    
    app.dependency_overrides[get_current_user_from_jwt] = lambda: mock_user
    
    try:
        onboard_data = {
            "tenant_name": "Test Tenant Corp",
            "admin_email": email
        }
        response = await async_client.post("/api/v1/settings/onboard", json=onboard_data)
        assert response.status_code == 200
        assert response.json()["status"] == "onboarded"
        generated_tenant_id = response.json()["tenant_id"]
        
        response = await async_client.post("/api/v1/settings/onboard", json=onboard_data)
        assert response.status_code == 400
        
        result = await db.execute(select(User).where(User.id == user_id))
        db_user = result.scalar_one_or_none()
        assert db_user is not None
        assert str(db_user.tenant_id) == generated_tenant_id
        
    finally:
        app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_onboard_endpoint(mock_db, mock_user):
    from app.main import app
    from app.shared.db.session import get_db
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user_from_jwt] = lambda: mock_user
    
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/v1/settings/onboard", json={"tenant_name": "TestTenant"})
        assert response.status_code == 200
        assert "tenant_id" in response.json()
    
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_onboard_duplicate(mock_db, mock_user):
    from app.main import app
    from app.shared.db.session import get_db
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user_from_jwt] = lambda: mock_user
    
    mock_db.execute.return_value.scalar_one_or_none.return_value = MagicMock()
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/v1/settings/onboard", json={"tenant_name": "DuplicateTenant"})
        assert response.status_code == 400
        # Check either 'error' or 'message' field based on custom handler
        data = response.json()
        assert "Already onboarded" in (data.get("error") or data.get("message") or "")

    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_onboard_with_cloud_config_multi(mock_db, mock_user):
    from app.main import app
    from app.shared.db.session import get_db
    
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user_from_jwt] = lambda: mock_user
    
    platforms = [
        ("aws", {"role_arn": "arn:aws:iam::...", "external_id": "123"}),
        ("azure", {"client_id": "...", "client_secret": "...", "azure_tenant_id": "...", "subscription_id": "..."}),
        ("gcp", {"project_id": "...", "service_account_json": "{}"})
    ]
    
    for platform, config in platforms:
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        mock_adapter = AsyncMock()
        mock_adapter.verify_connection.return_value = True
        
        with patch("app.shared.adapters.factory.AdapterFactory.get_adapter", return_value=mock_adapter):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                payload = {
                    "tenant_name": f"Tenant-{platform}",
                    "cloud_config": {"platform": platform, **config}
                }
                response = await ac.post("/api/v1/settings/onboard", json=payload)
                assert response.status_code == 200, f"Failed for {platform}: {response.json()}"
    
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_onboard_invalid_platform(mock_db, mock_user):
    from app.main import app
    from app.shared.db.session import get_db
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user_from_jwt] = lambda: mock_user
    mock_db.execute.return_value.scalar_one_or_none.return_value = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "tenant_name": "NewTenant",
            "cloud_config": {"platform": "unknown"}
        }
        response = await ac.post("/api/v1/settings/onboard", json=payload)
        assert response.status_code == 400
        data = response.json()
        assert "Unsupported platform" in (data.get("error") or data.get("message") or "")

    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_onboard_connection_fail(mock_db, mock_user):
    from app.main import app
    from app.shared.db.session import get_db
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user_from_jwt] = lambda: mock_user
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    
    mock_adapter = AsyncMock()
    mock_adapter.verify_connection.return_value = False
    
    with patch("app.shared.adapters.factory.AdapterFactory.get_adapter", return_value=mock_adapter):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            payload = {
                "tenant_name": "FailTenant",
                "cloud_config": {"platform": "aws", "role_arn": "arn:aws:iam::..."}
            }
            response = await ac.post("/api/v1/settings/onboard", json=payload)
            assert response.status_code == 400
            data = response.json()
            assert "verification failed" in (data.get("error") or data.get("message") or "")

    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_onboard_exception_handler(mock_db, mock_user):
    from app.main import app
    from app.shared.db.session import get_db
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user_from_jwt] = lambda: mock_user
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    
    with patch("app.shared.adapters.factory.AdapterFactory.get_adapter", side_effect=Exception("Unexpected crash")):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            payload = {
                "tenant_name": "CrashTenant",
                "cloud_config": {"platform": "aws", "role_arn": "arn:aws:iam::..."}
            }
            response = await ac.post("/api/v1/settings/onboard", json=payload)
            assert response.status_code == 400
            assert "Unexpected crash" in str(response.json())

    app.dependency_overrides.clear()
