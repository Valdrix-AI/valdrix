import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy import select
from unittest.mock import MagicMock, patch, AsyncMock
from app.main import app
from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.tenant import Tenant
from app.models.tenant import UserRole
from app.shared.core.auth import get_current_user
from app.shared.core.pricing import PricingTier

@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.tenant_id = uuid.uuid4()
    user.role = UserRole.MEMBER
    return user

@pytest.fixture(autouse=True)
def disable_cache():
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=True)
    with patch("app.shared.core.cache.get_cache_service", return_value=cache):
        yield

@pytest.fixture(autouse=True)
def override_auth(mock_user):
    app.dependency_overrides[get_current_user] = lambda: mock_user
    yield
    app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.asyncio
async def test_get_aws_setup_templates(async_client: AsyncClient):
    """Test AWS setup template generation."""
    response = await async_client.post("/api/v1/settings/connections/aws/setup")
    assert response.status_code == 200
    data = response.json()
    assert "cloudformation_yaml" in data
    assert "terraform_hcl" in data


@pytest.mark.asyncio
async def test_get_cloud_plus_setup_templates(async_client: AsyncClient):
    """Test SaaS and license setup snippet endpoints."""
    saas_res = await async_client.post("/api/v1/settings/connections/saas/setup")
    assert saas_res.status_code == 200
    assert "snippet" in saas_res.json()
    assert "sample_feed" in saas_res.json()
    assert "native_connectors" in saas_res.json()

    license_res = await async_client.post("/api/v1/settings/connections/license/setup")
    assert license_res.status_code == 200
    assert "snippet" in license_res.json()
    assert "sample_feed" in license_res.json()
    assert "native_connectors" in license_res.json()

@pytest.mark.asyncio
async def test_create_aws_connection(async_client: AsyncClient, db_session, mock_user):
    """Test creating an AWS connection (all tiers)."""
    payload = {
        "aws_account_id": "123456789012",
        "role_arn": "arn:aws:iam::123456789012:role/Valdrix",
        "external_id": "vx-" + "a" * 32,
        "region": "us-east-1"
    }
    response = await async_client.post("/api/v1/settings/connections/aws", json=payload)
    assert response.status_code == 201
    
    result = await db_session.execute(select(AWSConnection))
    conn = result.scalar_one()
    assert conn.aws_account_id == "123456789012"
    assert conn.tenant_id == mock_user.tenant_id

@pytest.mark.asyncio
async def test_create_azure_connection_denied_on_free_tier(async_client: AsyncClient, db_session, mock_user):
    """Test Azure connection denied for Free tier."""
    # Ensure tenant is on FREE plan
    tenant = Tenant(id=mock_user.tenant_id, name="Free Tenant", plan=PricingTier.FREE_TRIAL.value)
    db_session.add(tenant)
    await db_session.commit()
    
    payload = {
        "name": "Azure Sub",
        "subscription_id": str(uuid.uuid4()),
        "azure_tenant_id": str(uuid.uuid4()),
        "client_id": str(uuid.uuid4()),
        "client_secret": "secret"
    }
    response = await async_client.post("/api/v1/settings/connections/azure", json=payload)
    assert response.status_code == 403
    assert "requires 'Growth' plan or higher" in response.json()["error"]

@pytest.mark.asyncio
async def test_create_azure_connection_allowed_on_pro_tier(async_client: AsyncClient, db_session, mock_user):
    """Test Azure connection allowed for Pro tier."""
    tenant = Tenant(id=mock_user.tenant_id, name="Pro Tenant", plan=PricingTier.PRO.value)
    db_session.add(tenant)
    await db_session.commit()
    
    sub_id = str(uuid.uuid4())
    payload = {
        "name": "Azure Sub",
        "subscription_id": sub_id,
        "azure_tenant_id": str(uuid.uuid4()),
        "client_id": str(uuid.uuid4()),
        "client_secret": "secret"
    }
    response = await async_client.post("/api/v1/settings/connections/azure", json=payload)
    assert response.status_code == 201
    
    result = await db_session.execute(select(AzureConnection).where(AzureConnection.subscription_id == sub_id))
    assert result.scalar_one_or_none() is not None

@pytest.mark.asyncio
async def test_verify_aws_connection(async_client: AsyncClient, db_session, mock_user):
    """Test calling AWS connection verification."""
    conn = AWSConnection(
        tenant_id=mock_user.tenant_id,
        aws_account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/Valdrix",
        external_id="ext-id"
    )
    db_session.add(conn)
    await db_session.commit()
    
    with patch("app.shared.connections.aws.AWSConnectionService.verify_connection") as mock_verify:
        mock_verify.return_value = {"status": "verified"}
        response = await async_client.post(f"/api/v1/settings/connections/aws/{conn.id}/verify")
        assert response.status_code == 200
        assert response.json()["status"] == "verified"
