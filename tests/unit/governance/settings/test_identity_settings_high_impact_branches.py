import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sso_domain_mapping import SsoDomainMapping
from app.models.tenant import Tenant, User, UserRole
from app.models.tenant_identity_settings import TenantIdentitySettings
from app.modules.governance.api.v1.settings import identity as identity_api
from app.modules.governance.api.v1.settings.identity import (
    IdentitySettingsUpdate,
    ScimGroupMapping,
)
from app.shared.core.auth import CurrentUser, create_access_token, get_current_user
from app.shared.core.config import get_settings
from app.shared.core.pricing import PricingTier


async def _seed_admin(
    db: AsyncSession, *, plan: str = "pro", email: str = "admin@example.com"
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


def _admin_override_user(tenant_id: uuid.UUID, email: str = "admin@example.com") -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        email=email,
        tenant_id=tenant_id,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )


def test_identity_url_helpers_handle_parser_exceptions(monkeypatch) -> None:
    def _boom(_: str) -> object:
        raise ValueError("broken parser")

    monkeypatch.setattr(identity_api, "urlparse", _boom)
    assert identity_api._is_http_url("https://example.com") is False
    assert identity_api._is_https_url("https://example.com") is False


def test_identity_domain_normalization_and_token_generation() -> None:
    normalized = identity_api._normalize_domains(
        ["", "  ", ".Example.com.", "admin@EXAMPLE.com", "example.com", "."]
    )
    assert normalized == ["example.com"]

    token = identity_api._generate_scim_token()
    assert isinstance(token, str)
    assert len(token) >= 48


@pytest.mark.parametrize(
    "payload",
    [
        {"group": "   ", "role": "admin"},
        {"group": "ops", "role": "not-a-role"},
        {"group": "ops", "role": "admin", "persona": "unknown"},
        {"group": "ops", "role": "admin", "permissions": "nope"},
    ],
)
def test_scim_group_mapping_rejects_invalid_values(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ScimGroupMapping.model_validate(payload)


def test_scim_group_mapping_normalizes_empty_persona_and_permissions() -> None:
    mapping = ScimGroupMapping.model_validate(
        {"group": "FinOps-Admins", "role": "admin", "persona": "  ", "permissions": None}
    )
    assert mapping.group == "finops-admins"
    assert mapping.persona is None
    assert mapping.permissions == []


@pytest.mark.parametrize(
    "payload",
    [
        {
            "sso_enabled": False,
            "allowed_email_domains": [],
            "scim_enabled": False,
            "scim_group_mappings": [
                {"group": "ops", "role": "admin"},
                {"group": "ops", "role": "member"},
            ],
        },
        {
            "sso_enabled": True,
            "allowed_email_domains": ["example.com"],
            "sso_federation_enabled": True,
            "sso_federation_mode": "invalid",
            "scim_enabled": False,
        },
        {
            "sso_enabled": False,
            "allowed_email_domains": [],
            "sso_federation_enabled": True,
            "sso_federation_mode": "domain",
            "scim_enabled": False,
        },
        {
            "sso_enabled": True,
            "allowed_email_domains": ["example.com"],
            "sso_federation_enabled": True,
            "sso_federation_mode": "provider_id",
            "scim_enabled": False,
        },
        {
            "sso_enabled": True,
            "allowed_email_domains": "example.com",
            "scim_enabled": False,
        },
    ],
)
def test_identity_settings_update_validation_branches(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        IdentitySettingsUpdate.model_validate(payload)


@pytest.mark.asyncio
async def test_identity_diagnostics_reports_sso_and_scim_issues(
    ac, db: AsyncSession
) -> None:
    tenant, _user, headers = await _seed_admin(db, plan="pro", email="admin@example.com")

    identity = TenantIdentitySettings(
        tenant_id=tenant.id,
        sso_enabled=True,
        allowed_email_domains=[],
        sso_federation_enabled=True,
        sso_federation_mode="provider_id",
        sso_federation_provider_id=None,
        scim_enabled=True,
        scim_bearer_token="scim-secret-token-value",
        scim_last_rotated_at=datetime.now(timezone.utc) - timedelta(days=120),
    )
    # Simulate legacy row where token exists but blind index is missing.
    identity.scim_token_bidx = None
    db.add(identity)
    await db.commit()

    response = await ac.get("/api/v1/settings/identity/diagnostics", headers=headers)
    assert response.status_code == 200
    payload = response.json()

    assert payload["sso"]["federation_ready"] is False
    assert any(
        "allowed_email_domains" in issue.lower() for issue in payload["sso"]["issues"]
    )
    assert any("provider_id" in issue.lower() for issue in payload["sso"]["issues"])

    assert payload["scim"]["available"] is False
    assert payload["scim"]["rotation_overdue"] is True
    assert any("requires enterprise" in issue.lower() for issue in payload["scim"]["issues"])
    assert any("blind index" in issue.lower() for issue in payload["scim"]["issues"])
    assert any("upgrade to enterprise" in rec.lower() for rec in payload["recommendations"])


@pytest.mark.asyncio
async def test_identity_diagnostics_detects_admin_lockout_risk(
    ac, db: AsyncSession
) -> None:
    tenant, _user, _headers = await _seed_admin(
        db, plan="pro", email="admin@example.com"
    )

    db.add(
        TenantIdentitySettings(
            tenant_id=tenant.id,
            sso_enabled=True,
            allowed_email_domains=["corp.example"],
            sso_federation_enabled=False,
            sso_federation_mode="domain",
            scim_enabled=False,
        )
    )
    await db.commit()

    ac.app.dependency_overrides[get_current_user] = lambda: _admin_override_user(
        tenant.id
    )
    try:
        response = await ac.get("/api/v1/settings/identity/diagnostics")
    finally:
        ac.app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    payload = response.json()

    assert payload["sso"]["enforcement_active"] is True
    assert payload["sso"]["current_admin_domain_allowed"] is False
    assert any("lockout" in issue.lower() for issue in payload["sso"]["issues"])


@pytest.mark.asyncio
async def test_identity_sso_validation_production_checks_and_provider_requirements(
    ac, db: AsyncSession, monkeypatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "ENVIRONMENT", "production", raising=False)
    monkeypatch.setattr(settings, "FRONTEND_URL", "http://frontend.local", raising=False)
    monkeypatch.setattr(settings, "API_URL", "http://api.local", raising=False)

    tenant, _user, _headers = await _seed_admin(
        db, plan="pro", email="admin@example.com"
    )
    db.add(
        TenantIdentitySettings(
            tenant_id=tenant.id,
            sso_enabled=True,
            allowed_email_domains=["corp.example"],
            sso_federation_enabled=True,
            sso_federation_mode="provider_id",
            sso_federation_provider_id=None,
            scim_enabled=False,
        )
    )
    await db.commit()

    ac.app.dependency_overrides[get_current_user] = lambda: _admin_override_user(
        tenant.id
    )
    try:
        response = await ac.get("/api/v1/settings/identity/sso/validation")
    finally:
        ac.app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    payload = response.json()
    checks = {item["name"]: item for item in payload["checks"]}

    assert checks["config.frontend_url_is_https_in_production"]["passed"] is False
    assert checks["config.api_url_is_https_in_production"]["passed"] is False
    assert checks["sso.provider_id_required_in_provider_id_mode"]["passed"] is False
    assert checks["sso.current_admin_domain_allowed"]["passed"] is False
    assert payload["passed"] is False


@pytest.mark.asyncio
async def test_identity_scim_test_token_requires_enterprise(ac, db: AsyncSession) -> None:
    _tenant, _user, headers = await _seed_admin(db, plan="pro")

    response = await ac.post(
        "/api/v1/settings/identity/scim/test-token",
        headers=headers,
        json={"scim_token": "some-long-token"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_identity_scim_test_token_requires_enabled_scim(
    ac, db: AsyncSession
) -> None:
    _tenant, _user, headers = await _seed_admin(db, plan="enterprise")

    response = await ac.post(
        "/api/v1/settings/identity/scim/test-token",
        headers=headers,
        json={"scim_token": "some-long-token"},
    )
    assert response.status_code == 400
    assert "not enabled" in json.dumps(response.json()).lower()


@pytest.mark.asyncio
async def test_identity_scim_test_token_requires_blind_index(
    ac, db: AsyncSession
) -> None:
    tenant, _user, headers = await _seed_admin(db, plan="enterprise")
    identity = TenantIdentitySettings(
        tenant_id=tenant.id,
        sso_enabled=False,
        allowed_email_domains=[],
        sso_federation_enabled=False,
        sso_federation_mode="domain",
        scim_enabled=True,
        scim_bearer_token="tenant-scim-secret-token",
    )
    identity.scim_token_bidx = None
    db.add(identity)
    await db.commit()

    response = await ac.post(
        "/api/v1/settings/identity/scim/test-token",
        headers=headers,
        json={"scim_token": "some-long-token"},
    )
    assert response.status_code == 400
    assert "rotate" in json.dumps(response.json()).lower()


@pytest.mark.asyncio
async def test_identity_update_rejects_cross_tenant_domain_conflict(
    ac, db: AsyncSession
) -> None:
    tenant_a, _user_a, headers_a = await _seed_admin(
        db, plan="pro", email="admin@shared.example"
    )
    tenant_b, _user_b, _headers_b = await _seed_admin(
        db, plan="pro", email="other@example.com"
    )

    db.add(
        SsoDomainMapping(
            tenant_id=tenant_b.id,
            domain="shared.example",
            federation_mode="domain",
            provider_id=None,
            is_active=True,
        )
    )
    await db.commit()

    response = await ac.put(
        "/api/v1/settings/identity",
        headers=headers_a,
        json={
            "sso_enabled": True,
            "allowed_email_domains": ["shared.example"],
            "sso_federation_enabled": True,
            "sso_federation_mode": "domain",
            "scim_enabled": False,
        },
    )
    assert response.status_code == 409
    assert "already configured for another tenant" in json.dumps(response.json()).lower()


@pytest.mark.asyncio
async def test_identity_update_succeeds_when_audit_log_fails(
    ac, db: AsyncSession, monkeypatch
) -> None:
    _tenant, _user, headers = await _seed_admin(db, plan="enterprise")
    monkeypatch.setattr(
        identity_api.AuditLogger,
        "log",
        AsyncMock(side_effect=RuntimeError("audit unavailable")),
    )

    response = await ac.put(
        "/api/v1/settings/identity",
        headers=headers,
        json={
            "sso_enabled": False,
            "allowed_email_domains": [],
            "scim_enabled": True,
            "scim_group_mappings": [],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["scim_enabled"] is True
    assert payload["has_scim_token"] is True
    assert payload["scim_last_rotated_at"] is not None


@pytest.mark.asyncio
async def test_identity_rotate_scim_token_succeeds_when_audit_log_fails(
    ac, db: AsyncSession, monkeypatch
) -> None:
    _tenant, _user, headers = await _seed_admin(db, plan="enterprise")
    monkeypatch.setattr(
        identity_api.AuditLogger,
        "log",
        AsyncMock(side_effect=RuntimeError("audit unavailable")),
    )

    response = await ac.post("/api/v1/settings/identity/rotate-scim-token", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload.get("scim_token"), str)
    assert payload.get("scim_token")
