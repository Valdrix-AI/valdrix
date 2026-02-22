import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant, User, UserRole
from app.shared.core.auth import create_access_token


@pytest.mark.asyncio
async def test_identity_settings_get_creates_default(ac: AsyncClient, db: AsyncSession):
    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, name="Tenant Identity", plan="pro")
    db.add(tenant)
    user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        tenant_id=tenant_id,
        role=UserRole.ADMIN.value,
    )
    db.add(user)
    await db.commit()

    token = create_access_token({"sub": str(user.id), "email": "admin@example.com"})
    headers = {"Authorization": f"Bearer {token}"}

    res = await ac.get("/api/v1/settings/identity", headers=headers)
    assert res.status_code == 200
    payload = res.json()
    assert payload["sso_enabled"] is False
    assert payload["allowed_email_domains"] == []
    assert payload["sso_federation_enabled"] is False
    assert payload["sso_federation_mode"] == "domain"
    assert payload["sso_federation_provider_id"] is None
    assert payload["scim_enabled"] is False
    assert payload["has_scim_token"] is False


@pytest.mark.asyncio
async def test_identity_settings_put_normalizes_domains(
    ac: AsyncClient, db: AsyncSession
):
    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, name="Tenant Identity", plan="pro")
    db.add(tenant)
    user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        tenant_id=tenant_id,
        role=UserRole.ADMIN.value,
    )
    db.add(user)
    await db.commit()

    token = create_access_token({"sub": str(user.id), "email": "admin@example.com"})
    headers = {"Authorization": f"Bearer {token}"}

    res = await ac.put(
        "/api/v1/settings/identity",
        headers=headers,
        json={
            "sso_enabled": True,
            "allowed_email_domains": [
                "Example.com",
                "admin@EXAMPLE.com",
                "example.com",
            ],
            "scim_enabled": False,
        },
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["sso_enabled"] is True
    assert payload["allowed_email_domains"] == ["example.com"]
    assert payload["sso_federation_enabled"] is False
    assert payload["sso_federation_mode"] == "domain"
    assert payload["scim_enabled"] is False


@pytest.mark.asyncio
async def test_identity_settings_prevents_self_lockout(
    ac: AsyncClient, db: AsyncSession
):
    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, name="Tenant Identity", plan="pro")
    db.add(tenant)
    user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        tenant_id=tenant_id,
        role=UserRole.ADMIN.value,
    )
    db.add(user)
    await db.commit()

    token = create_access_token({"sub": str(user.id), "email": "admin@example.com"})
    headers = {"Authorization": f"Bearer {token}"}

    res = await ac.put(
        "/api/v1/settings/identity",
        headers=headers,
        json={
            "sso_enabled": True,
            "allowed_email_domains": ["not-example.com"],
            "scim_enabled": False,
        },
    )
    assert res.status_code == 400
    assert (
        "avoid locking yourself out"
        in (res.json().get("error", "") + res.json().get("message", "")).lower()
    )


@pytest.mark.asyncio
async def test_identity_rotate_scim_token_requires_enterprise(
    ac: AsyncClient, db: AsyncSession
):
    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, name="Tenant Identity", plan="pro")
    db.add(tenant)
    user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        tenant_id=tenant_id,
        role=UserRole.ADMIN.value,
    )
    db.add(user)
    await db.commit()

    token = create_access_token({"sub": str(user.id), "email": "admin@example.com"})
    headers = {"Authorization": f"Bearer {token}"}

    res = await ac.post("/api/v1/settings/identity/rotate-scim-token", headers=headers)
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_identity_rotate_scim_token_success(ac: AsyncClient, db: AsyncSession):
    from app.models.tenant_identity_settings import TenantIdentitySettings

    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, name="Tenant Identity", plan="enterprise")
    db.add(tenant)
    user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        tenant_id=tenant_id,
        role=UserRole.ADMIN.value,
    )
    db.add(user)
    await db.commit()

    token = create_access_token({"sub": str(user.id), "email": "admin@example.com"})
    headers = {"Authorization": f"Bearer {token}"}

    res = await ac.post("/api/v1/settings/identity/rotate-scim-token", headers=headers)
    assert res.status_code == 200
    payload = res.json()
    assert payload["scim_token"]

    # Ensure settings row exists and token is stored.
    identity = (
        await db.execute(
            TenantIdentitySettings.__table__.select().where(
                TenantIdentitySettings.tenant_id == tenant_id
            )
        )
    ).first()
    assert identity is not None


@pytest.mark.asyncio
async def test_identity_diagnostics_endpoint_returns_sso_and_scim_status(
    ac: AsyncClient, db: AsyncSession
):
    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, name="Tenant Identity Diagnostics", plan="pro")
    db.add(tenant)
    user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        tenant_id=tenant_id,
        role=UserRole.ADMIN.value,
    )
    db.add(user)
    await db.commit()

    token = create_access_token({"sub": str(user.id), "email": "admin@example.com"})
    headers = {"Authorization": f"Bearer {token}"}

    res = await ac.get("/api/v1/settings/identity/diagnostics", headers=headers)
    assert res.status_code == 200
    payload = res.json()
    assert payload["tier"] == "pro"
    assert payload["sso"]["enabled"] is False
    assert payload["sso"]["federation_enabled"] is False
    assert payload["sso"]["federation_mode"] == "domain"
    assert payload["sso"]["federation_ready"] is False
    assert payload["scim"]["available"] is False  # SCIM is Enterprise-only


@pytest.mark.asyncio
async def test_identity_sso_validation_endpoint_returns_computed_urls(
    ac: AsyncClient, db: AsyncSession
):
    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, name="Tenant Identity SSO Validation", plan="pro")
    db.add(tenant)
    user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        tenant_id=tenant_id,
        role=UserRole.ADMIN.value,
    )
    db.add(user)
    await db.commit()

    token = create_access_token({"sub": str(user.id), "email": "admin@example.com"})
    headers = {"Authorization": f"Bearer {token}"}

    res = await ac.get("/api/v1/settings/identity/sso/validation", headers=headers)
    assert res.status_code == 200
    payload = res.json()
    assert payload["tier"] == "pro"
    assert payload["frontend_url"].startswith("http")
    assert payload["expected_redirect_url"].endswith("/auth/callback")
    assert payload["discovery_endpoint"].endswith("/api/v1/public/sso/discovery")
    assert isinstance(payload["checks"], list)


@pytest.mark.asyncio
async def test_identity_scim_test_token_matches_and_mismatches(
    ac: AsyncClient, db: AsyncSession
):
    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, name="Tenant Identity SCIM", plan="enterprise")
    db.add(tenant)
    user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        tenant_id=tenant_id,
        role=UserRole.ADMIN.value,
    )
    db.add(user)
    await db.commit()

    token = create_access_token({"sub": str(user.id), "email": "admin@example.com"})
    headers = {"Authorization": f"Bearer {token}"}

    # Rotate token (creates tenant identity settings row + token bidx)
    rotate = await ac.post(
        "/api/v1/settings/identity/rotate-scim-token", headers=headers
    )
    assert rotate.status_code == 200
    scim_token = rotate.json()["scim_token"]
    assert scim_token

    ok = await ac.post(
        "/api/v1/settings/identity/scim/test-token",
        headers=headers,
        json={"scim_token": scim_token},
    )
    assert ok.status_code == 200
    assert ok.json()["token_matches"] is True

    mismatch = await ac.post(
        "/api/v1/settings/identity/scim/test-token",
        headers=headers,
        json={"scim_token": scim_token + "x"},
    )
    assert mismatch.status_code == 200
    assert mismatch.json()["token_matches"] is False


@pytest.mark.asyncio
async def test_identity_scim_group_mappings_requires_enterprise(
    ac: AsyncClient, db: AsyncSession
):
    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, name="Tenant Identity SCIM Groups", plan="pro")
    db.add(tenant)
    user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        tenant_id=tenant_id,
        role=UserRole.ADMIN.value,
    )
    db.add(user)
    await db.commit()

    token = create_access_token({"sub": str(user.id), "email": "admin@example.com"})
    headers = {"Authorization": f"Bearer {token}"}

    res = await ac.put(
        "/api/v1/settings/identity",
        headers=headers,
        json={
            "sso_enabled": False,
            "allowed_email_domains": [],
            "scim_enabled": False,
            "scim_group_mappings": [
                {
                    "group": "finops-admins",
                    "role": "admin",
                    "persona": "finance",
                    "permissions": ["remediation.approve.nonprod"],
                }
            ],
        },
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_identity_scim_group_mappings_update_success_enterprise(
    ac: AsyncClient, db: AsyncSession
):
    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, name="Tenant Identity SCIM Groups", plan="enterprise")
    db.add(tenant)
    user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        tenant_id=tenant_id,
        role=UserRole.ADMIN.value,
    )
    db.add(user)
    await db.commit()

    token = create_access_token({"sub": str(user.id), "email": "admin@example.com"})
    headers = {"Authorization": f"Bearer {token}"}

    res = await ac.put(
        "/api/v1/settings/identity",
        headers=headers,
        json={
            "sso_enabled": False,
            "allowed_email_domains": [],
            "scim_enabled": False,
            "scim_group_mappings": [
                {
                    "group": "FinOps-Admins",
                    "role": "admin",
                    "persona": "finance",
                    "permissions": [
                        "remediation.approve.nonprod",
                        "remediation.approve.prod",
                    ],
                }
            ],
        },
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["scim_group_mappings"] == [
        {
            "group": "finops-admins",
            "role": "admin",
            "persona": "finance",
            "permissions": [
                "remediation.approve.nonprod",
                "remediation.approve.prod",
            ],
        }
    ]


@pytest.mark.asyncio
async def test_identity_scim_group_mappings_reject_invalid_permissions(
    ac: AsyncClient, db: AsyncSession
):
    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, name="Tenant Identity SCIM Groups", plan="enterprise")
    db.add(tenant)
    user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        tenant_id=tenant_id,
        role=UserRole.ADMIN.value,
    )
    db.add(user)
    await db.commit()

    token = create_access_token({"sub": str(user.id), "email": "admin@example.com"})
    headers = {"Authorization": f"Bearer {token}"}

    res = await ac.put(
        "/api/v1/settings/identity",
        headers=headers,
        json={
            "sso_enabled": False,
            "allowed_email_domains": [],
            "scim_enabled": False,
            "scim_group_mappings": [
                {
                    "group": "FinOps-Admins",
                    "role": "admin",
                    "permissions": ["not-a-real-permission"],
                }
            ],
        },
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_identity_sso_federation_provider_id_mode_requires_provider_id(
    ac: AsyncClient, db: AsyncSession
):
    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, name="Tenant Identity Federation", plan="pro")
    db.add(tenant)
    user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        tenant_id=tenant_id,
        role=UserRole.ADMIN.value,
    )
    db.add(user)
    await db.commit()

    token = create_access_token({"sub": str(user.id), "email": "admin@example.com"})
    headers = {"Authorization": f"Bearer {token}"}

    res = await ac.put(
        "/api/v1/settings/identity",
        headers=headers,
        json={
            "sso_enabled": True,
            "allowed_email_domains": ["example.com"],
            "sso_federation_enabled": True,
            "sso_federation_mode": "provider_id",
            "scim_enabled": False,
        },
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_identity_sso_federation_provider_id_mode_success(
    ac: AsyncClient, db: AsyncSession
):
    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, name="Tenant Identity Federation", plan="pro")
    db.add(tenant)
    user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        tenant_id=tenant_id,
        role=UserRole.ADMIN.value,
    )
    db.add(user)
    await db.commit()

    token = create_access_token({"sub": str(user.id), "email": "admin@example.com"})
    headers = {"Authorization": f"Bearer {token}"}

    res = await ac.put(
        "/api/v1/settings/identity",
        headers=headers,
        json={
            "sso_enabled": True,
            "allowed_email_domains": ["example.com"],
            "sso_federation_enabled": True,
            "sso_federation_mode": "provider_id",
            "sso_federation_provider_id": "sso-provider-123",
            "scim_enabled": False,
        },
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["sso_federation_enabled"] is True
    assert payload["sso_federation_mode"] == "provider_id"
    assert payload["sso_federation_provider_id"] == "sso-provider-123"
