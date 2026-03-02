import json
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sso_domain_mapping import SsoDomainMapping
from app.models.tenant import Tenant, User, UserRole
from app.models.tenant_identity_settings import TenantIdentitySettings
from app.shared.core.auth import create_access_token
from app.shared.core.security import generate_secret_blind_index


async def _seed_admin(
    db: AsyncSession,
    *,
    plan: str = "pro",
    email: str = "admin@example.com",
) -> tuple[Tenant, User, dict[str, str]]:
    tenant = Tenant(id=uuid.uuid4(), name=f"Tenant {email}", plan=plan)
    user = User(
        id=uuid.uuid4(),
        email=email,
        tenant_id=tenant.id,
        role=UserRole.ADMIN.value,
    )
    db.add(tenant)
    db.add(user)
    await db.commit()

    token = create_access_token({"sub": str(user.id), "email": email})
    return tenant, user, {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_get_identity_settings_creates_default_record(
    ac,
    db: AsyncSession,
) -> None:
    _tenant, _user, headers = await _seed_admin(db, plan="pro")

    response = await ac.get("/api/v1/settings/identity", headers=headers)
    assert response.status_code == 200

    payload = response.json()
    assert payload["sso_enabled"] is False
    assert payload["allowed_email_domains"] == []
    assert payload["sso_federation_enabled"] is False
    assert payload["sso_federation_mode"] == "domain"
    assert payload["scim_enabled"] is False
    assert payload["has_scim_token"] is False


@pytest.mark.asyncio
async def test_identity_diagnostics_creates_default_record_when_missing(
    ac,
    db: AsyncSession,
) -> None:
    _tenant, _user, headers = await _seed_admin(db, plan="pro")

    response = await ac.get("/api/v1/settings/identity/diagnostics", headers=headers)
    assert response.status_code == 200

    payload = response.json()
    assert payload["sso"]["enabled"] is False
    assert payload["sso"]["federation_enabled"] is False
    assert payload["scim"]["enabled"] is False
    assert payload["recommendations"] == []


@pytest.mark.asyncio
async def test_identity_sso_validation_default_non_federated_path(
    ac,
    db: AsyncSession,
) -> None:
    _tenant, _user, headers = await _seed_admin(db, plan="pro")

    response = await ac.get("/api/v1/settings/identity/sso/validation", headers=headers)
    assert response.status_code == 200

    payload = response.json()
    checks = {item["name"]: item for item in payload["checks"]}

    assert payload["federation_enabled"] is False
    assert checks["sso.federation_enabled"]["passed"] is False
    assert checks["sso.federation_enabled"]["severity"] == "info"
    assert checks["supabase.expected_redirect_url_computed"]["passed"] is True
    assert checks["valdrics.discovery_endpoint_computed"]["passed"] is True


@pytest.mark.asyncio
async def test_identity_scim_test_token_match_and_mismatch(
    ac,
    db: AsyncSession,
) -> None:
    tenant, _user, headers = await _seed_admin(db, plan="enterprise")

    token_value = "tenant-scim-super-secret"
    identity = TenantIdentitySettings(
        tenant_id=tenant.id,
        sso_enabled=False,
        allowed_email_domains=[],
        sso_federation_enabled=False,
        sso_federation_mode="domain",
        scim_enabled=True,
        scim_bearer_token=token_value,
    )
    identity.scim_token_bidx = generate_secret_blind_index(token_value)
    db.add(identity)
    await db.commit()

    match_response = await ac.post(
        "/api/v1/settings/identity/scim/test-token",
        headers=headers,
        json={"scim_token": token_value},
    )
    assert match_response.status_code == 200
    assert match_response.json()["status"] == "ok"
    assert match_response.json()["token_matches"] is True

    mismatch_response = await ac.post(
        "/api/v1/settings/identity/scim/test-token",
        headers=headers,
        json={"scim_token": "different-token-value"},
    )
    assert mismatch_response.status_code == 200
    assert mismatch_response.json()["status"] == "mismatch"
    assert mismatch_response.json()["token_matches"] is False


@pytest.mark.asyncio
async def test_identity_update_requires_enterprise_for_scim_and_mappings(
    ac,
    db: AsyncSession,
) -> None:
    _tenant, _user, headers = await _seed_admin(db, plan="pro")

    scim_response = await ac.put(
        "/api/v1/settings/identity",
        headers=headers,
        json={
            "sso_enabled": False,
            "allowed_email_domains": [],
            "scim_enabled": True,
        },
    )
    assert scim_response.status_code == 403
    assert "requires enterprise" in json.dumps(scim_response.json()).lower()

    mappings_response = await ac.put(
        "/api/v1/settings/identity",
        headers=headers,
        json={
            "sso_enabled": False,
            "allowed_email_domains": [],
            "scim_enabled": False,
            "scim_group_mappings": [{"group": "ops", "role": "admin"}],
        },
    )
    assert mappings_response.status_code == 403
    assert "group mappings require enterprise" in json.dumps(
        mappings_response.json()
    ).lower()


@pytest.mark.asyncio
async def test_identity_update_guardrail_blocks_lockout_allowlist(
    ac,
    db: AsyncSession,
) -> None:
    _tenant, _user, headers = await _seed_admin(
        db,
        plan="pro",
        email="admin@corp.example",
    )

    response = await ac.put(
        "/api/v1/settings/identity",
        headers=headers,
        json={
            "sso_enabled": True,
            "allowed_email_domains": ["other.example"],
            "sso_federation_enabled": False,
            "scim_enabled": False,
        },
    )

    assert response.status_code == 400
    assert "include your current email domain" in json.dumps(response.json()).lower()


@pytest.mark.asyncio
async def test_identity_update_creates_domain_mappings_for_provider_id_mode(
    ac,
    db: AsyncSession,
) -> None:
    tenant, _user, headers = await _seed_admin(
        db,
        plan="pro",
        email="admin@corp.example",
    )

    response = await ac.put(
        "/api/v1/settings/identity",
        headers=headers,
        json={
            "sso_enabled": True,
            "allowed_email_domains": ["corp.example", "eng.example"],
            "sso_federation_enabled": True,
            "sso_federation_mode": "provider_id",
            "sso_federation_provider_id": "supabase-idp-1",
            "scim_enabled": False,
            "scim_group_mappings": [],
        },
    )
    assert response.status_code == 200

    mappings = (
        (
            await db.execute(
                select(SsoDomainMapping).where(SsoDomainMapping.tenant_id == tenant.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(mappings) == 2
    assert all(item.federation_mode == "provider_id" for item in mappings)
    assert all(item.provider_id == "supabase-idp-1" for item in mappings)


@pytest.mark.asyncio
async def test_identity_rotate_scim_token_requires_enterprise(
    ac,
    db: AsyncSession,
) -> None:
    _tenant, _user, headers = await _seed_admin(db, plan="pro")

    response = await ac.post("/api/v1/settings/identity/rotate-scim-token", headers=headers)
    assert response.status_code == 403
    assert "requires enterprise" in json.dumps(response.json()).lower()


@pytest.mark.asyncio
async def test_identity_rotate_scim_token_creates_settings_when_missing(
    ac,
    db: AsyncSession,
) -> None:
    tenant, _user, headers = await _seed_admin(db, plan="enterprise")

    response = await ac.post("/api/v1/settings/identity/rotate-scim-token", headers=headers)
    assert response.status_code == 200

    payload = response.json()
    assert isinstance(payload.get("scim_token"), str)
    assert payload.get("scim_token")

    identity = (
        (
            await db.execute(
                select(TenantIdentitySettings).where(
                    TenantIdentitySettings.tenant_id == tenant.id
                )
            )
        )
        .scalar_one_or_none()
    )
    assert identity is not None
    assert bool(identity.scim_enabled) is True
    assert bool(identity.scim_bearer_token)

