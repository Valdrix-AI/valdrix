import pytest
import pytest_asyncio
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, AsyncMock
from app.shared.core.pricing import PricingTier
from app.shared.core.auth import CurrentUser, get_current_user
from app.models.tenant import Tenant, User, UserRole
from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.gcp_connection import GCPConnection
from app.models.saas_connection import SaaSConnection
from app.models.license_connection import LicenseConnection
from app.models.discovered_account import DiscoveredAccount
from sqlalchemy import select

# ==================== Fixtures ====================

@pytest_asyncio.fixture
async def test_tenant(db):
    tenant = Tenant(
        id=uuid4(),
        name="Test Tenant",
        plan=PricingTier.FREE_TRIAL.value
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant

@pytest_asyncio.fixture
async def test_user(db, test_tenant):
    user = User(
        id=uuid4(),
        email="test@valdrix.io",
        tenant_id=test_tenant.id,
        role=UserRole.ADMIN
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

@pytest_asyncio.fixture
def auth_user(test_user, test_tenant):
    return CurrentUser(
        id=test_user.id,
        email=test_user.email,
        tenant_id=test_tenant.id,
        role=test_user.role,
        tier=test_tenant.plan
    )

@pytest_asyncio.fixture
def override_auth(app, auth_user):
    app.dependency_overrides[get_current_user] = lambda: auth_user
    yield
    app.dependency_overrides.pop(get_current_user, None)

@pytest.fixture(autouse=True)
def disable_cache():
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=True)
    with patch("app.shared.core.cache.get_cache_service", return_value=cache):
        yield

# ==================== Helper Tests ====================

@pytest.mark.asyncio
async def test_check_growth_tier_logic(db, auth_user):
    from app.modules.governance.api.v1.settings.connections import check_growth_tier
    from fastapi import HTTPException
    
    # 1. Test Free (already set in fixture)
    with pytest.raises(HTTPException) as exc:
        await check_growth_tier(auth_user, db)
    assert exc.value.status_code == 403

    # 1b. Trial should also be denied for multi-cloud operations
    tenant = await db.get(Tenant, auth_user.tenant_id)
    tenant.plan = PricingTier.FREE_TRIAL.value
    await db.commit()
    auth_user.tier = PricingTier.FREE_TRIAL
    with pytest.raises(HTTPException) as trial_exc:
        await check_growth_tier(auth_user, db)
    assert trial_exc.value.status_code == 403
    
    # 2. Test Growth
    tenant = await db.get(Tenant, auth_user.tenant_id)
    tenant.plan = PricingTier.GROWTH.value
    await db.commit()
    
    auth_user.tier = PricingTier.GROWTH
    await check_growth_tier(auth_user, db) # Should not raise

@pytest.mark.asyncio
async def test_check_growth_tier_invalid_plan(db, auth_user):
    from app.modules.governance.api.v1.settings.connections import check_growth_tier
    from fastapi import HTTPException
    
    # Set invalid plan in DB
    tenant = await db.get(Tenant, auth_user.tenant_id)
    tenant.plan = "super_unknown_plan"
    await db.commit()
    
    # Should fall back to FREE and raise 403
    with pytest.raises(HTTPException) as exc:
        await check_growth_tier(auth_user, db)
    assert exc.value.status_code == 403
    assert "Free" in str(exc.value.detail) or "Growth" in str(exc.value.detail)

@pytest.mark.asyncio
async def test_check_growth_tier_cache_hit(auth_user):
    from app.modules.governance.api.v1.settings.connections import check_growth_tier
    db = MagicMock()
    db.execute = AsyncMock()
    cache = MagicMock()
    cache.get = AsyncMock(return_value=PricingTier.GROWTH.value)
    cache.set = AsyncMock()

    with patch("app.shared.core.cache.get_cache_service", return_value=cache):
        await check_growth_tier(auth_user, db)
        db.execute.assert_not_awaited()

@pytest.mark.asyncio
async def test_check_growth_tier_cache_invalid(auth_user):
    from app.modules.governance.api.v1.settings.connections import check_growth_tier
    db = MagicMock()
    tenant = MagicMock()
    tenant.plan = PricingTier.GROWTH.value
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=tenant)))
    cache = MagicMock()
    cache.get = AsyncMock(return_value="unknown-plan")
    cache.set = AsyncMock()

    with patch("app.shared.core.cache.get_cache_service", return_value=cache):
        await check_growth_tier(auth_user, db)
        db.execute.assert_awaited()

@pytest.mark.asyncio
async def test_check_growth_tier_cache_get_error_fallback(auth_user):
    from app.modules.governance.api.v1.settings.connections import check_growth_tier
    tenant = MagicMock()
    tenant.plan = PricingTier.GROWTH.value
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=tenant)))
    cache = MagicMock()
    cache.get = AsyncMock(side_effect=RuntimeError("redis down"))
    cache.set = AsyncMock(return_value=True)

    with patch("app.shared.core.cache.get_cache_service", return_value=cache):
        await check_growth_tier(auth_user, db)
        db.execute.assert_awaited()

@pytest.mark.asyncio
async def test_check_growth_tier_cache_set_error_nonfatal(auth_user):
    from app.modules.governance.api.v1.settings.connections import check_growth_tier
    tenant = MagicMock()
    tenant.plan = PricingTier.GROWTH.value
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=tenant)))
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(side_effect=RuntimeError("redis write down"))

    with patch("app.shared.core.cache.get_cache_service", return_value=cache):
        await check_growth_tier(auth_user, db)
        db.execute.assert_awaited()

@pytest.mark.asyncio
async def test_check_growth_tier_missing_tenant(auth_user):
    from app.modules.governance.api.v1.settings.connections import check_growth_tier
    from fastapi import HTTPException
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=True)

    with patch("app.shared.core.cache.get_cache_service", return_value=cache):
        with pytest.raises(HTTPException) as exc:
            await check_growth_tier(auth_user, db)
        assert exc.value.status_code == 404

# ==================== AWS API Tests ====================

@pytest.mark.asyncio
async def test_aws_setup_templates(ac):
    with patch("app.shared.connections.aws.AWSConnectionService.get_setup_templates") as mock_service:
        mock_service.return_value = {
            "external_id": "vx-123",
            "cloudformation_yaml": "---",
            "terraform_hcl": "resource...",
            "magic_link": "https://...",
            "instructions": "steps...",
            "permissions_summary": ["CostExplorer"]
        }
        resp = await ac.post("/api/v1/settings/connections/aws/setup")
        assert resp.status_code == 200
        data = resp.json()
        assert data["external_id"] == "vx-123"


@pytest.mark.asyncio
async def test_cloud_plus_setup_templates(ac, override_auth):
    saas = await ac.post("/api/v1/settings/connections/saas/setup")
    assert saas.status_code == 200
    saas_data = saas.json()
    assert "snippet" in saas_data
    assert "sample_feed" in saas_data

    license_res = await ac.post("/api/v1/settings/connections/license/setup")
    assert license_res.status_code == 200
    license_data = license_res.json()
    assert "snippet" in license_data
    assert "sample_feed" in license_data

@pytest.mark.asyncio
async def test_create_aws_connection(ac, override_auth, auth_user, db):
    payload = {
        "aws_account_id": "123456789012",
        "role_arn": "arn:aws:iam::123456789012:role/Valdrix",
        "external_id": "vx-12345678901234567890123456789012",
        "region": "us-east-1",
        "is_management_account": True,
        "organization_id": "o-123"
    }
    resp = await ac.post("/api/v1/settings/connections/aws", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["aws_account_id"] == "123456789012"
    assert "id" in data
    assert "created_at" in data

@pytest.mark.asyncio
async def test_duplicate_aws_connection(ac, db, override_auth, auth_user):
    # Pre-create a connection
    conn = AWSConnection(
        tenant_id=auth_user.tenant_id,
        aws_account_id="999999999999",
        role_arn="arn:aws:iam::999999999999:role/Valdrix",
        external_id="vx-99999999999999999999999999999999",
        status="pending"
    )
    db.add(conn)
    await db.commit()
    
    payload = {
        "aws_account_id": "999999999999",
        "role_arn": "arn:aws:iam::999999999999:role/Valdrix",
        "external_id": "vx-99999999999999999999999999999999",
        "region": "us-east-1"
    }
    resp = await ac.post("/api/v1/settings/connections/aws", json=payload)
    assert resp.status_code == 409

@pytest.mark.asyncio
async def test_sync_aws_org(ac, db, override_auth, auth_user):
    # Create management account
    conn = AWSConnection(
        tenant_id=auth_user.tenant_id,
        aws_account_id="112233445566",
        role_arn="arn:aws:iam::112233445566:role/Valdrix",
        external_id="vx-11223344556611223344556611223344",
        is_management_account=True,
        status="active"
    )
    db.add(conn)
    await db.commit()
    
    with patch("app.shared.connections.organizations.OrganizationsDiscoveryService.sync_accounts") as mock_sync:
        mock_sync.return_value = 5
        resp = await ac.post(f"/api/v1/settings/connections/aws/{conn.id}/sync-org")
        assert resp.status_code == 200
        assert resp.json()["count"] == 5

@pytest.mark.asyncio
async def test_sync_aws_org_not_management(ac, db, override_auth, auth_user):
    # Standard connection (not management)
    conn = AWSConnection(
        tenant_id=auth_user.tenant_id,
        aws_account_id="998877665544",
        role_arn="arn:aws:iam::998877665544:role/Valdrix",
        external_id="vx-998877665544",
        is_management_account=False,
        status="active"
    )
    db.add(conn)
    await db.commit()
    
    resp = await ac.post(f"/api/v1/settings/connections/aws/{conn.id}/sync-org")
    assert resp.status_code == 404

@pytest.mark.asyncio
async def test_list_aws_connections(ac, db, override_auth, auth_user):
    conn = AWSConnection(tenant_id=auth_user.tenant_id, aws_account_id="123", role_arn="arn", external_id="vx-123", status="active")
    db.add(conn)
    await db.commit()
    resp = await ac.get("/api/v1/settings/connections/aws")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1

@pytest.mark.asyncio
async def test_verify_aws_connection(ac, db, override_auth, auth_user):
    conn = AWSConnection(tenant_id=auth_user.tenant_id, aws_account_id="123", role_arn="arn", external_id="vx-123", status="active")
    db.add(conn)
    await db.commit()
    with patch("app.shared.connections.aws.AWSConnectionService.verify_connection") as mock_verify:
        mock_verify.return_value = {"status": "verified"}
        resp = await ac.post(f"/api/v1/settings/connections/aws/{conn.id}/verify")
        assert resp.status_code == 200

@pytest.mark.asyncio
async def test_delete_aws_connection(ac, db, override_auth, auth_user):
    conn = AWSConnection(tenant_id=auth_user.tenant_id, aws_account_id="delete-me", role_arn="arn", external_id="vx-123", status="active")
    db.add(conn)
    await db.commit()
    resp = await ac.delete(f"/api/v1/settings/connections/aws/{conn.id}")
    assert resp.status_code == 204
    # Verify gone
    stmt = select(AWSConnection).where(AWSConnection.id == conn.id)
    res = await db.execute(stmt)
    assert res.scalar_one_or_none() is None

@pytest.mark.asyncio
async def test_delete_aws_connection_tenant_isolation(ac, db, override_auth, auth_user):
    other_tenant = Tenant(id=uuid4(), name="Other Tenant", plan=PricingTier.GROWTH.value)
    db.add(other_tenant)
    await db.commit()

    conn = AWSConnection(
        tenant_id=other_tenant.id,
        aws_account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/Valdrix",
        external_id="vx-12345678901234567890123456789012",
        status="pending"
    )
    db.add(conn)
    await db.commit()

    resp = await ac.delete(f"/api/v1/settings/connections/aws/{conn.id}")
    assert resp.status_code == 404

# ==================== Azure API Tests ====================

@pytest.mark.asyncio
async def test_create_azure_connection_denied_on_free(ac, override_auth):
    payload = {
        "name": "Azure Test",
        "azure_tenant_id": str(uuid4()),
        "client_id": str(uuid4()),
        "subscription_id": str(uuid4()),
        "client_secret": "secret"
    }
    resp = await ac.post("/api/v1/settings/connections/azure", json=payload)
    if resp.status_code != 403:
        print(f"DEBUG: Unexpected status {resp.status_code}: {resp.text}")
    assert resp.status_code == 403
    data = resp.json()
    # Debug response content
    if "detail" not in data:
        print(f"DEBUG: Missing detail in 403 response: {data}")
    
    val = data.get("detail", str(data))
    assert "Growth" in val

@pytest.mark.asyncio
async def test_create_azure_connection_success_on_growth(ac, db, override_auth, auth_user):
    # Upgrade tenant
    tenant = await db.get(Tenant, auth_user.tenant_id)
    tenant.plan = PricingTier.GROWTH.value
    await db.commit()
    auth_user.tier = PricingTier.GROWTH

    payload = {
        "name": "Azure Growth",
        "azure_tenant_id": str(uuid4()),
        "client_id": str(uuid4()),
        "subscription_id": str(uuid4()),
        "client_secret": "secret"
    }
    resp = await ac.post("/api/v1/settings/connections/azure", json=payload)
    assert resp.status_code == 201
    assert resp.json()["subscription_id"] == payload["subscription_id"]

@pytest.mark.asyncio
async def test_create_azure_connection_requires_secret_when_auth_secret(ac, db, override_auth, auth_user):
    tenant = await db.get(Tenant, auth_user.tenant_id)
    tenant.plan = PricingTier.GROWTH.value
    await db.commit()
    auth_user.tier = PricingTier.GROWTH

    payload = {
        "name": "Azure Missing Secret",
        "azure_tenant_id": str(uuid4()),
        "client_id": str(uuid4()),
        "subscription_id": str(uuid4()),
        "auth_method": "secret"
    }
    resp = await ac.post("/api/v1/settings/connections/azure", json=payload)
    assert resp.status_code == 422

@pytest.mark.asyncio
async def test_create_azure_connection_invalid_auth_method(ac, db, override_auth, auth_user):
    tenant = await db.get(Tenant, auth_user.tenant_id)
    tenant.plan = PricingTier.GROWTH.value
    await db.commit()
    auth_user.tier = PricingTier.GROWTH

    payload = {
        "name": "Azure Bad Auth",
        "azure_tenant_id": str(uuid4()),
        "client_id": str(uuid4()),
        "subscription_id": str(uuid4()),
        "client_secret": "secret",
        "auth_method": "token"
    }
    resp = await ac.post("/api/v1/settings/connections/azure", json=payload)
    assert resp.status_code == 422

@pytest.mark.asyncio
async def test_verify_azure_connection(ac, db, override_auth, auth_user):
    tenant = await db.get(Tenant, auth_user.tenant_id)
    tenant.plan = PricingTier.GROWTH.value
    await db.commit()
    auth_user.tier = PricingTier.GROWTH

    conn = AzureConnection(tenant_id=auth_user.tenant_id, name="Az", azure_tenant_id="t", client_id="c", subscription_id="s")
    db.add(conn)
    await db.commit()
    with patch("app.shared.connections.azure.AzureConnectionService.verify_connection") as mock_verify:
        mock_verify.return_value = {"status": "verified"}
        resp = await ac.post(f"/api/v1/settings/connections/azure/{conn.id}/verify")
        assert resp.status_code == 200

@pytest.mark.asyncio
async def test_verify_azure_connection_tenant_isolation(ac, db, override_auth, auth_user):
    tenant = await db.get(Tenant, auth_user.tenant_id)
    tenant.plan = PricingTier.GROWTH.value
    await db.commit()
    auth_user.tier = PricingTier.GROWTH

    other_tenant = Tenant(id=uuid4(), name="Other Tenant", plan=PricingTier.GROWTH.value)
    db.add(other_tenant)
    await db.commit()

    conn = AzureConnection(
        tenant_id=other_tenant.id,
        name="Other Az",
        azure_tenant_id="t",
        client_id="c",
        subscription_id="s"
    )
    db.add(conn)
    await db.commit()

    resp = await ac.post(f"/api/v1/settings/connections/azure/{conn.id}/verify")
    assert resp.status_code == 404

@pytest.mark.asyncio
async def test_verify_azure_connection_denied_on_free(ac, db, override_auth, auth_user):
    tenant = await db.get(Tenant, auth_user.tenant_id)
    tenant.plan = PricingTier.FREE_TRIAL.value
    await db.commit()

    conn = AzureConnection(tenant_id=auth_user.tenant_id, name="Az", azure_tenant_id="t", client_id="c", subscription_id="s")
    db.add(conn)
    await db.commit()

    resp = await ac.post(f"/api/v1/settings/connections/azure/{conn.id}/verify")
    assert resp.status_code == 403

@pytest.mark.asyncio
async def test_list_azure_connections(ac, db, override_auth, auth_user):
    # Retrieve regardless of tier
    resp = await ac.get("/api/v1/settings/connections/azure")
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_list_azure_connections_tenant_isolation(ac, db, override_auth, auth_user):
    other_tenant = Tenant(id=uuid4(), name="Other Tenant", plan=PricingTier.GROWTH.value)
    db.add(other_tenant)
    await db.commit()

    db.add_all([
        AzureConnection(
            tenant_id=auth_user.tenant_id,
            name="Mine",
            azure_tenant_id="t1",
            client_id="c1",
            subscription_id="s1"
        ),
        AzureConnection(
            tenant_id=other_tenant.id,
            name="Other",
            azure_tenant_id="t2",
            client_id="c2",
            subscription_id="s2"
        )
    ])
    await db.commit()

    resp = await ac.get("/api/v1/settings/connections/azure")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["subscription_id"] == "s1"

# ==================== GCP API Tests ====================

@pytest.mark.asyncio
async def test_create_gcp_connection_success_on_growth(ac, db, override_auth, auth_user):
    # Upgrade tenant
    tenant = await db.get(Tenant, auth_user.tenant_id)
    tenant.plan = PricingTier.GROWTH.value
    await db.commit()
    auth_user.tier = PricingTier.GROWTH

    payload = {
        "name": "GCP Project",
        "project_id": "test-project-123",
        "service_account_json": "{}",
        "auth_method": "secret"
    }
    resp = await ac.post("/api/v1/settings/connections/gcp", json=payload)
    assert resp.status_code == 201
    assert resp.json()["project_id"] == "test-project-123"

@pytest.mark.asyncio
async def test_create_gcp_connection_requires_json_when_secret(ac, db, override_auth, auth_user):
    tenant = await db.get(Tenant, auth_user.tenant_id)
    tenant.plan = PricingTier.GROWTH.value
    await db.commit()
    auth_user.tier = PricingTier.GROWTH

    payload = {
        "name": "GCP Missing JSON",
        "project_id": "test-project-123",
        "auth_method": "secret"
    }
    resp = await ac.post("/api/v1/settings/connections/gcp", json=payload)
    assert resp.status_code == 422

@pytest.mark.asyncio
async def test_create_gcp_connection_invalid_json(ac, db, override_auth, auth_user):
    tenant = await db.get(Tenant, auth_user.tenant_id)
    tenant.plan = PricingTier.GROWTH.value
    await db.commit()
    auth_user.tier = PricingTier.GROWTH

    payload = {
        "name": "GCP Bad JSON",
        "project_id": "test-project-123",
        "service_account_json": "{bad-json",
        "auth_method": "secret"
    }
    resp = await ac.post("/api/v1/settings/connections/gcp", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_gcp_connection_workload_identity_verification_failure(ac, db, override_auth, auth_user):
    tenant = await db.get(Tenant, auth_user.tenant_id)
    tenant.plan = PricingTier.GROWTH.value
    await db.commit()
    auth_user.tier = PricingTier.GROWTH

    payload = {
        "name": "GCP WIF",
        "project_id": "wif-project-123",
        "auth_method": "workload_identity"
    }
    with patch("app.shared.connections.oidc.OIDCService.verify_gcp_access", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = (False, "STS exchange failed")
        resp = await ac.post("/api/v1/settings/connections/gcp", json=payload)
        assert resp.status_code == 400
        assert "Workload Identity verification failed" in (resp.json().get("error") or resp.json().get("message") or "")

@pytest.mark.asyncio
async def test_verify_gcp_connection_denied_on_free(ac, db, override_auth, auth_user):
    tenant = await db.get(Tenant, auth_user.tenant_id)
    tenant.plan = PricingTier.FREE_TRIAL.value
    await db.commit()

    conn = GCPConnection(tenant_id=auth_user.tenant_id, name="g", project_id="p")
    db.add(conn)
    await db.commit()

    resp = await ac.post(f"/api/v1/settings/connections/gcp/{conn.id}/verify")
    assert resp.status_code == 403

@pytest.mark.asyncio
async def test_list_gcp_connections(ac, db, override_auth, auth_user):
    resp = await ac.get("/api/v1/settings/connections/gcp")
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_list_gcp_connections_tenant_isolation(ac, db, override_auth, auth_user):
    other_tenant = Tenant(id=uuid4(), name="Other Tenant", plan=PricingTier.GROWTH.value)
    db.add(other_tenant)
    await db.commit()

    db.add_all([
        GCPConnection(tenant_id=auth_user.tenant_id, name="Mine", project_id="p1"),
        GCPConnection(tenant_id=other_tenant.id, name="Other", project_id="p2"),
    ])
    await db.commit()

    resp = await ac.get("/api/v1/settings/connections/gcp")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["project_id"] == "p1"

@pytest.mark.asyncio
async def test_delete_gcp_connection(ac, db, override_auth, auth_user):
    conn = GCPConnection(tenant_id=auth_user.tenant_id, name="g", project_id="p")
    db.add(conn)
    await db.commit()
    resp = await ac.delete(f"/api/v1/settings/connections/gcp/{conn.id}")
    assert resp.status_code == 204

@pytest.mark.asyncio
async def test_delete_gcp_connection_tenant_isolation(ac, db, override_auth, auth_user):
    other_tenant = Tenant(id=uuid4(), name="Other Tenant", plan=PricingTier.GROWTH.value)
    db.add(other_tenant)
    await db.commit()

    conn = GCPConnection(tenant_id=other_tenant.id, name="g", project_id="p")
    db.add(conn)
    await db.commit()

    resp = await ac.delete(f"/api/v1/settings/connections/gcp/{conn.id}")
    assert resp.status_code == 404


# ==================== Cloud+ API Tests ====================

@pytest.mark.asyncio
async def test_create_saas_connection_denied_on_growth(ac, db, override_auth, auth_user):
    tenant = await db.get(Tenant, auth_user.tenant_id)
    tenant.plan = PricingTier.GROWTH.value
    await db.commit()
    auth_user.tier = PricingTier.GROWTH

    payload = {
        "name": "Salesforce Feed",
        "vendor": "salesforce",
        "auth_method": "manual",
        "spend_feed": [],
    }
    resp = await ac.post("/api/v1/settings/connections/saas", json=payload)
    assert resp.status_code == 403
    assert "Cloud+ connectors require 'Pro' plan or higher" in resp.json().get("error", "")


@pytest.mark.asyncio
async def test_create_saas_connection_success_on_pro(ac, db, override_auth, auth_user):
    tenant = await db.get(Tenant, auth_user.tenant_id)
    tenant.plan = PricingTier.PRO.value
    await db.commit()
    auth_user.tier = PricingTier.PRO

    payload = {
        "name": "Salesforce Feed",
        "vendor": "salesforce",
        "auth_method": "manual",
        "spend_feed": [{"service": "Sales Cloud", "cost_usd": 12.5, "timestamp": "2026-02-11"}],
    }
    resp = await ac.post("/api/v1/settings/connections/saas", json=payload)
    assert resp.status_code == 201
    assert resp.json()["vendor"] == "salesforce"


@pytest.mark.asyncio
async def test_verify_saas_connection(ac, db, override_auth, auth_user):
    tenant = await db.get(Tenant, auth_user.tenant_id)
    tenant.plan = PricingTier.PRO.value
    await db.commit()
    auth_user.tier = PricingTier.PRO

    conn = SaaSConnection(
        tenant_id=auth_user.tenant_id,
        name="Salesforce Feed",
        vendor="salesforce",
        spend_feed=[],
        auth_method="manual",
    )
    db.add(conn)
    await db.commit()

    with patch("app.shared.connections.saas.SaaSConnectionService.verify_connection") as mock_verify:
        mock_verify.return_value = {"status": "verified"}
        resp = await ac.post(f"/api/v1/settings/connections/saas/{conn.id}/verify")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_create_license_connection_success_on_pro(ac, db, override_auth, auth_user):
    tenant = await db.get(Tenant, auth_user.tenant_id)
    tenant.plan = PricingTier.PRO.value
    await db.commit()
    auth_user.tier = PricingTier.PRO

    payload = {
        "name": "MS365 Seats",
        "vendor": "microsoft",
        "auth_method": "manual",
        "license_feed": [{"service": "M365 E5", "cost_usd": 100.0, "timestamp": "2026-02-11"}],
    }
    resp = await ac.post("/api/v1/settings/connections/license", json=payload)
    assert resp.status_code == 201
    assert resp.json()["vendor"] == "microsoft"


@pytest.mark.asyncio
async def test_list_license_connections_tenant_isolation(ac, db, override_auth, auth_user):
    tenant = await db.get(Tenant, auth_user.tenant_id)
    tenant.plan = PricingTier.PRO.value
    await db.commit()
    auth_user.tier = PricingTier.PRO

    other_tenant = Tenant(id=uuid4(), name="Other", plan=PricingTier.PRO.value)
    db.add(other_tenant)
    await db.commit()

    db.add_all([
        LicenseConnection(
            tenant_id=auth_user.tenant_id,
            name="Mine",
            vendor="microsoft",
            auth_method="manual",
            license_feed=[],
        ),
        LicenseConnection(
            tenant_id=other_tenant.id,
            name="Other",
            vendor="google",
            auth_method="manual",
            license_feed=[],
        ),
    ])
    await db.commit()

    resp = await ac.get("/api/v1/settings/connections/license")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Mine"

# ==================== Link Discovered Account Tests ====================

@pytest.mark.asyncio
async def test_link_discovered_account(ac, db, override_auth, auth_user):
    # 1. Create management connection
    mgmt = AWSConnection(
        tenant_id=auth_user.tenant_id,
        aws_account_id="111122223333",
        role_arn="arn:aws:iam::111122223333:role/Valdrix",
        external_id="vx-11112222333311112222333311112222",
        is_management_account=True,
        status="active"
    )
    db.add(mgmt)
    await db.commit()

    # 2. Create discovered account
    disc = DiscoveredAccount(
        management_connection_id=mgmt.id,
        account_id="444455556666",
        name="Member Account",
        status="discovered"
    )
    db.add(disc)
    await db.commit()

    # 3. Link it
    resp = await ac.post(f"/api/v1/settings/connections/aws/discovered/{disc.id}/link")
    assert resp.status_code == 200
    assert resp.json()["message"] == "Account linked successfully"

    # Verify connection created
    stmt = select(AWSConnection).where(AWSConnection.aws_account_id == "444455556666")
    res = await db.execute(stmt)
    new_conn = res.scalar_one()
    assert new_conn.tenant_id == auth_user.tenant_id
    assert new_conn.external_id == mgmt.external_id

@pytest.mark.asyncio
async def test_link_discovered_account_idempotent(ac, db, override_auth, auth_user):
    # 1. Management connection
    mgmt = AWSConnection(
        tenant_id=auth_user.tenant_id,
        aws_account_id="888888888888",
        role_arn="arn",
        external_id="vx-unique-test-id-888",
        is_management_account=True,
        status="active"
    )
    db.add(mgmt)
    await db.commit()
    await db.refresh(mgmt)
    
    # 2. Discovered account
    disc = DiscoveredAccount(
        management_connection_id=mgmt.id,
        account_id="777777777777",
        name="Linked Member",
        status="linked"
    )
    db.add(disc)
    await db.commit()
    await db.refresh(disc)
    
    # 3. Existing connection
    conn = AWSConnection(
        tenant_id=auth_user.tenant_id,
        aws_account_id="777777777777",
        role_arn="arn",
        external_id=mgmt.external_id, # Sharing external ID
        status="active"
    )
    db.add(conn)
    await db.commit()
    
    # 4. Try to link again (should return existing)
    resp = await ac.post(f"/api/v1/settings/connections/aws/discovered/{disc.id}/link")
    assert resp.status_code == 200
    assert resp.json()["status"] == "existing"

@pytest.mark.asyncio
async def test_link_discovered_account_not_authorized(ac, db, override_auth, auth_user):
    other_tenant = Tenant(id=uuid4(), name="Other", plan=PricingTier.GROWTH.value)
    db.add(other_tenant)
    await db.commit()

    mgmt = AWSConnection(
        tenant_id=other_tenant.id,
        aws_account_id="101010101010",
        role_arn="arn",
        external_id="vx-1010",
        is_management_account=True,
        status="active"
    )
    db.add(mgmt)
    await db.commit()

    disc = DiscoveredAccount(
        management_connection_id=mgmt.id,
        account_id="999999999998",
        name="Foreign Account",
        status="discovered"
    )
    db.add(disc)
    await db.commit()

    resp = await ac.post(f"/api/v1/settings/connections/aws/discovered/{disc.id}/link")
    assert resp.status_code == 404

@pytest.mark.asyncio
async def test_list_discovered_accounts_empty(ac, override_auth):
    resp = await ac.get("/api/v1/settings/connections/aws/discovered")
    assert resp.status_code == 200
    assert resp.json() == []

@pytest.mark.asyncio
async def test_list_discovered_accounts_sorted(ac, db, override_auth, auth_user):
    mgmt = AWSConnection(
        tenant_id=auth_user.tenant_id,
        aws_account_id="222233334444",
        role_arn="arn",
        external_id="vx-2222",
        is_management_account=True,
        status="active"
    )
    db.add(mgmt)
    await db.commit()

    older = DiscoveredAccount(
        management_connection_id=mgmt.id,
        account_id="111100001111",
        name="Old",
        status="discovered",
        last_discovered_at=datetime.now(timezone.utc) - timedelta(days=1)
    )
    newer = DiscoveredAccount(
        management_connection_id=mgmt.id,
        account_id="222200002222",
        name="New",
        status="discovered",
        last_discovered_at=datetime.now(timezone.utc)
    )
    db.add_all([older, newer])
    await db.commit()

    resp = await ac.get("/api/v1/settings/connections/aws/discovered")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["account_id"] == "222200002222"

@pytest.mark.asyncio
async def test_create_azure_connection_duplicate(ac, db, override_auth, auth_user):
    # Setup Growth tier
    tenant = await db.get(Tenant, auth_user.tenant_id)
    tenant.plan = PricingTier.GROWTH.value
    await db.commit()
    auth_user.tier = PricingTier.GROWTH
    
    # Pre-create
    conn = AzureConnection(
        tenant_id=auth_user.tenant_id,
        name="Existing",
        azure_tenant_id="t-1",
        client_id="c-1",
        subscription_id="sub-duplicate"
    )
    db.add(conn)
    await db.commit()
    
    payload = {
        "name": "New",
        "azure_tenant_id": "t-2",
        "client_id": "c-2",
        "subscription_id": "sub-duplicate",
        "client_secret": "s"
    }
    resp = await ac.post("/api/v1/settings/connections/azure", json=payload)
    assert resp.status_code == 409

@pytest.mark.asyncio
async def test_create_gcp_connection_duplicate(ac, db, override_auth, auth_user):
    # Setup Growth tier
    tenant = await db.get(Tenant, auth_user.tenant_id)
    tenant.plan = PricingTier.GROWTH.value
    await db.commit()
    auth_user.tier = PricingTier.GROWTH
    
    # Pre-create
    conn = GCPConnection(
        tenant_id=auth_user.tenant_id,
        name="Existing",
        project_id="proj-duplicate"
    )
    db.add(conn)
    await db.commit()
    
    payload = {
        "name": "New",
        "project_id": "proj-duplicate",
        "service_account_json": "{}",
        "auth_method": "secret"
    }
    resp = await ac.post("/api/v1/settings/connections/gcp", json=payload)
    assert resp.status_code == 409
