import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.models.discovery_candidate import DiscoveryCandidate
from app.models.license_connection import LicenseConnection
from app.models.tenant import Tenant, User, UserRole
from app.shared.connections.discovery import DiscoveryWizardService
from app.shared.core.auth import CurrentUser, get_current_user
from app.shared.core.pricing import PricingTier


@pytest_asyncio.fixture
async def test_tenant(db):
    tenant = Tenant(id=uuid4(), name="Discovery Tenant", plan=PricingTier.FREE.value)
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant


@pytest_asyncio.fixture
async def test_user(db, test_tenant):
    user = User(
        id=uuid4(),
        email="admin@example.com",
        tenant_id=test_tenant.id,
        role=UserRole.ADMIN,
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
        tier=PricingTier.FREE,
    )


@pytest_asyncio.fixture
def override_auth(app, auth_user):
    app.dependency_overrides[get_current_user] = lambda: auth_user
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_stage_a_discovery_persists_candidates(ac, override_auth):
    signals = {
        "mx_hosts": ["aspmx.l.google.com"],
        "txt_records": [
            "v=spf1 include:_spf.google.com ~all",
            "stripe-verification=abc123",
            "newrelic-domain-verification=xyz789",
        ],
        "cname_targets": {
            "slack.example.com": "acme.slack-edge.com",
            "datadog.example.com": "acme.datadoghq.com",
            "zoom.example.com": "acme.zoom.us",
        },
    }
    with patch.object(
        DiscoveryWizardService,
        "_collect_domain_signals",
        new=AsyncMock(return_value=(signals, [])),
    ):
        response = await ac.post(
            "/api/v1/settings/connections/discovery/stage-a",
            json={"email": "owner@example.com"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["domain"] == "example.com"
    assert payload["total_candidates"] >= 2

    listed = await ac.get("/api/v1/settings/connections/discovery/candidates")
    assert listed.status_code == 200
    providers = {entry["provider"] for entry in listed.json()}
    assert "google_workspace" in providers
    assert "gcp" in providers
    assert "stripe" in providers
    assert "zoom" in providers
    assert "datadog" in providers
    assert "newrelic" in providers


@pytest.mark.asyncio
async def test_discovery_candidate_ignore_and_filter(ac, override_auth):
    signals = {
        "mx_hosts": ["example-com.mail.protection.outlook.com"],
        "txt_records": ["v=spf1 include:spf.protection.outlook.com ~all"],
        "cname_targets": {},
    }
    with patch.object(
        DiscoveryWizardService,
        "_collect_domain_signals",
        new=AsyncMock(return_value=(signals, [])),
    ):
        created = await ac.post(
            "/api/v1/settings/connections/discovery/stage-a",
            json={"email": "owner@example.com"},
        )
    candidate_id = created.json()["candidates"][0]["id"]

    ignored = await ac.post(
        f"/api/v1/settings/connections/discovery/candidates/{candidate_id}/ignore"
    )
    assert ignored.status_code == 200
    assert ignored.json()["status"] == "ignored"

    filtered = await ac.get("/api/v1/settings/connections/discovery/candidates?status=ignored")
    assert filtered.status_code == 200
    assert any(entry["id"] == candidate_id for entry in filtered.json())


@pytest.mark.asyncio
async def test_deep_scan_requires_cloud_plus_tier(ac, override_auth):
    response = await ac.post(
        "/api/v1/settings/connections/discovery/deep-scan",
        json={"domain": "example.com", "idp_provider": "microsoft_365"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_deep_scan_microsoft_enriches_candidates(
    ac, db, override_auth, auth_user
):
    tenant = await db.get(Tenant, auth_user.tenant_id)
    tenant.plan = PricingTier.PRO.value
    await db.commit()
    auth_user.tier = PricingTier.PRO

    db.add(
        LicenseConnection(
            tenant_id=auth_user.tenant_id,
            name="M365 Admin",
            vendor="microsoft_365",
            auth_method="oauth",
            api_key="test-token",
            connector_config={},
            is_active=True,
        )
    )
    await db.commit()

    graph_payload = {
        "value": [
            {"displayName": "Amazon Web Services"},
            {"displayName": "Slack"},
            {"displayName": "Stripe"},
            {"displayName": "Datadog"},
        ]
    }
    with patch.object(
        DiscoveryWizardService,
        "_request_json",
        new=AsyncMock(return_value=graph_payload),
    ):
        response = await ac.post(
            "/api/v1/settings/connections/discovery/deep-scan",
            json={"domain": "example.com", "idp_provider": "microsoft_365"},
        )
    assert response.status_code == 200
    providers = {entry["provider"] for entry in response.json()["candidates"]}
    assert "microsoft_365" in providers
    assert "azure" in providers
    assert "aws" in providers
    assert "slack" in providers
    assert "stripe" in providers
    assert "datadog" in providers


@pytest.mark.asyncio
async def test_deep_scan_returns_400_when_idp_connector_missing(
    ac, db, override_auth, auth_user
):
    tenant = await db.get(Tenant, auth_user.tenant_id)
    tenant.plan = PricingTier.PRO.value
    await db.commit()
    auth_user.tier = PricingTier.PRO

    response = await ac.post(
        "/api/v1/settings/connections/discovery/deep-scan",
        json={"domain": "example.com", "idp_provider": "google_workspace"},
    )
    assert response.status_code == 400
    assert "No active google_workspace license connector found" in response.text


@pytest.mark.asyncio
async def test_list_discovery_candidates_rejects_invalid_status(
    ac, db, override_auth, auth_user
):
    tenant = await db.get(Tenant, auth_user.tenant_id)
    db.add(
        DiscoveryCandidate(
            tenant_id=tenant.id,
            domain="example.com",
            category="cloud_provider",
            provider="aws",
            source="domain_dns",
            status="pending",
            confidence_score=0.7,
            requires_admin_auth=True,
            connection_target="aws",
            evidence=["txt:amazonaws_or_amazonses"],
            details={"inference": "dns"},
        )
    )
    await db.commit()

    response = await ac.get("/api/v1/settings/connections/discovery/candidates?status=bad")
    assert response.status_code == 400
