from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.governance.api.v1.settings import identity as identity_api
from app.shared.core.auth import CurrentUser, UserRole
from app.shared.core.pricing import PricingTier
from app.shared.core.security import generate_secret_blind_index


class _ScalarOneResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> object:
        return self._value


class _ScalarsResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> "_ScalarsResult":
        return self

    def all(self) -> list[object]:
        return self._rows


class _AuditLoggerSuccess:
    def __init__(self, db: object, tenant_id: object, correlation_id: str) -> None:
        _ = (db, tenant_id, correlation_id)

    async def log(self, **_kwargs: object) -> None:
        return None


class _AuditLoggerFailure:
    def __init__(self, db: object, tenant_id: object, correlation_id: str) -> None:
        _ = (db, tenant_id, correlation_id)

    async def log(self, **_kwargs: object) -> None:
        raise RuntimeError("audit unavailable")


def _admin_user(
    tenant_id: object,
    *,
    tier: PricingTier = PricingTier.PRO,
    email: str = "admin@corp.example",
) -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        email=email,
        tenant_id=tenant_id,
        role=UserRole.ADMIN,
        tier=tier,
    )


@pytest.mark.asyncio
async def test_get_identity_settings_bootstraps_missing_identity() -> None:
    tenant_id = uuid4()
    mock_db = AsyncMock()
    mock_db.execute.return_value = _ScalarOneResult(None)
    mock_db.add = MagicMock()

    response = await identity_api.get_identity_settings(
        current_user=_admin_user(tenant_id),
        db=mock_db,
    )

    assert response.sso_enabled is False
    assert response.allowed_email_domains == []
    assert response.scim_enabled is False
    mock_db.add.assert_called_once()
    mock_db.commit.assert_awaited()
    mock_db.refresh.assert_awaited()


@pytest.mark.asyncio
async def test_get_identity_diagnostics_bootstraps_missing_identity() -> None:
    tenant_id = uuid4()
    mock_db = AsyncMock()
    mock_db.execute.return_value = _ScalarOneResult(None)
    mock_db.add = MagicMock()

    response = await identity_api.get_identity_diagnostics(
        current_user=_admin_user(tenant_id),
        db=mock_db,
    )

    assert response.sso.enabled is False
    assert response.scim.enabled is False
    mock_db.add.assert_called_once()
    mock_db.commit.assert_awaited()
    mock_db.refresh.assert_awaited()


@pytest.mark.asyncio
async def test_get_identity_diagnostics_reports_sso_scim_issues() -> None:
    tenant_id = uuid4()
    identity = SimpleNamespace(
        sso_enabled=True,
        allowed_email_domains=[],
        sso_federation_enabled=True,
        sso_federation_mode="provider_id",
        sso_federation_provider_id=None,
        scim_enabled=True,
        scim_bearer_token="secret-token",
        scim_token_bidx=None,
        scim_last_rotated_at=datetime.now(timezone.utc) - timedelta(days=120),
    )
    mock_db = AsyncMock()
    mock_db.execute.return_value = _ScalarOneResult(identity)

    response = await identity_api.get_identity_diagnostics(
        current_user=_admin_user(tenant_id, tier=PricingTier.PRO),
        db=mock_db,
    )

    assert response.sso.federation_enabled is True
    assert response.sso.federation_ready is False
    assert any("allowed_email_domains" in issue for issue in response.sso.issues)
    assert response.scim.available is False
    assert response.scim.rotation_overdue is True
    assert any("requires enterprise" in issue.lower() for issue in response.scim.issues)


@pytest.mark.asyncio
async def test_sso_federation_validation_bootstraps_missing_identity(
    monkeypatch,
) -> None:
    tenant_id = uuid4()
    settings = identity_api.get_settings()
    monkeypatch.setattr(settings, "FRONTEND_URL", "http://frontend.local", raising=False)
    monkeypatch.setattr(settings, "API_URL", "http://api.local", raising=False)
    monkeypatch.setattr(settings, "ENVIRONMENT", "development", raising=False)

    mock_db = AsyncMock()
    mock_db.execute.return_value = _ScalarOneResult(None)
    mock_db.add = MagicMock()

    response = await identity_api.get_sso_federation_validation(
        current_user=_admin_user(tenant_id),
        db=mock_db,
    )

    checks = {item.name: item for item in response.checks}
    assert response.federation_enabled is False
    assert checks["sso.federation_enabled"].severity == "info"
    assert checks["supabase.expected_redirect_url_computed"].passed is True
    mock_db.add.assert_called_once()
    mock_db.commit.assert_awaited()
    mock_db.refresh.assert_awaited()


@pytest.mark.asyncio
async def test_sso_federation_validation_production_checks_and_guardrails(
    monkeypatch,
) -> None:
    tenant_id = uuid4()
    settings = identity_api.get_settings()
    monkeypatch.setattr(settings, "FRONTEND_URL", "http://frontend.local", raising=False)
    monkeypatch.setattr(settings, "API_URL", "http://api.local", raising=False)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production", raising=False)

    identity = SimpleNamespace(
        sso_enabled=True,
        allowed_email_domains=["corp.example"],
        sso_federation_enabled=True,
        sso_federation_mode="provider_id",
        sso_federation_provider_id="",
    )
    mock_db = AsyncMock()
    mock_db.execute.return_value = _ScalarOneResult(identity)

    response = await identity_api.get_sso_federation_validation(
        current_user=_admin_user(tenant_id, email="admin@other.example"),
        db=mock_db,
    )

    checks = {item.name: item for item in response.checks}
    assert checks["config.frontend_url_is_https_in_production"].passed is False
    assert checks["config.api_url_is_https_in_production"].passed is False
    assert checks["sso.provider_id_required_in_provider_id_mode"].passed is False
    assert checks["sso.current_admin_domain_allowed"].passed is False
    assert response.passed is False


@pytest.mark.asyncio
async def test_scim_token_match_and_mismatch_direct() -> None:
    tenant_id = uuid4()
    token_value = "tenant-scim-secret"
    identity = SimpleNamespace(
        scim_enabled=True,
        scim_token_bidx=generate_secret_blind_index(token_value),
    )

    match_db = AsyncMock()
    match_db.execute.return_value = _ScalarOneResult(identity)
    match_response = await identity_api.test_scim_token(
        payload=identity_api.ScimTokenTestRequest(scim_token=token_value),
        current_user=_admin_user(tenant_id, tier=PricingTier.ENTERPRISE),
        db=match_db,
    )
    assert match_response.status == "ok"
    assert match_response.token_matches is True

    mismatch_db = AsyncMock()
    mismatch_db.execute.return_value = _ScalarOneResult(identity)
    mismatch_response = await identity_api.test_scim_token(
        payload=identity_api.ScimTokenTestRequest(scim_token="wrong-token"),
        current_user=_admin_user(tenant_id, tier=PricingTier.ENTERPRISE),
        db=mismatch_db,
    )
    assert mismatch_response.status == "mismatch"
    assert mismatch_response.token_matches is False


@pytest.mark.asyncio
async def test_update_identity_settings_rejects_non_enterprise_scim() -> None:
    payload = identity_api.IdentitySettingsUpdate.model_validate(
        {
            "sso_enabled": False,
            "allowed_email_domains": [],
            "scim_enabled": True,
        }
    )

    with pytest.raises(HTTPException) as exc:
        await identity_api.update_identity_settings(
            payload=payload,
            current_user=_admin_user(uuid4(), tier=PricingTier.PRO),
            db=AsyncMock(),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_update_identity_settings_rejects_non_enterprise_mappings() -> None:
    payload = identity_api.IdentitySettingsUpdate.model_validate(
        {
            "sso_enabled": False,
            "allowed_email_domains": [],
            "scim_enabled": False,
            "scim_group_mappings": [{"group": "ops", "role": "admin"}],
        }
    )

    with pytest.raises(HTTPException) as exc:
        await identity_api.update_identity_settings(
            payload=payload,
            current_user=_admin_user(uuid4(), tier=PricingTier.PRO),
            db=AsyncMock(),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_update_identity_settings_creates_mappings_and_scim_token(
    monkeypatch,
) -> None:
    tenant_id = uuid4()
    payload = identity_api.IdentitySettingsUpdate.model_validate(
        {
            "sso_enabled": True,
            "allowed_email_domains": ["corp.example", "eng.example"],
            "sso_federation_enabled": True,
            "sso_federation_mode": "provider_id",
            "sso_federation_provider_id": "provider-123",
            "scim_enabled": True,
            "scim_group_mappings": [{"group": "ops", "role": "admin"}],
        }
    )

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        side_effect=[
            _ScalarOneResult(None),
            _ScalarsResult([]),
            SimpleNamespace(rowcount=2),
        ]
    )
    mock_db.add = MagicMock()
    mock_db.refresh = AsyncMock()

    monkeypatch.setattr(identity_api, "AuditLogger", _AuditLoggerSuccess)

    response = await identity_api.update_identity_settings(
        payload=payload,
        current_user=_admin_user(
            tenant_id,
            tier=PricingTier.ENTERPRISE,
            email="admin@corp.example",
        ),
        db=mock_db,
    )

    assert response.sso_enabled is True
    assert response.sso_federation_mode == "provider_id"
    assert response.has_scim_token is True
    assert response.scim_enabled is True
    assert mock_db.commit.await_count >= 2


@pytest.mark.asyncio
async def test_update_identity_settings_tolerates_audit_failure_and_refresh_failure(
    monkeypatch,
) -> None:
    tenant_id = uuid4()
    payload = identity_api.IdentitySettingsUpdate.model_validate(
        {
            "sso_enabled": False,
            "allowed_email_domains": [],
            "scim_enabled": False,
            "scim_group_mappings": [],
        }
    )
    identity = SimpleNamespace(
        sso_enabled=True,
        allowed_email_domains=["corp.example"],
        sso_federation_enabled=False,
        sso_federation_mode="domain",
        sso_federation_provider_id=None,
        scim_enabled=False,
        scim_bearer_token=None,
        scim_last_rotated_at=None,
        scim_group_mappings=[],
    )

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        side_effect=[
            _ScalarOneResult(identity),
            SimpleNamespace(rowcount=1),
        ]
    )
    mock_db.refresh = AsyncMock(side_effect=[None, RuntimeError("refresh failed")])

    monkeypatch.setattr(identity_api, "AuditLogger", _AuditLoggerFailure)

    response = await identity_api.update_identity_settings(
        payload=payload,
        current_user=_admin_user(
            tenant_id,
            tier=PricingTier.ENTERPRISE,
            email="admin@corp.example",
        ),
        db=mock_db,
    )

    assert response.sso_enabled is False
    assert response.scim_enabled is False
    mock_db.rollback.assert_awaited()


@pytest.mark.asyncio
async def test_rotate_scim_token_rejects_non_enterprise_direct() -> None:
    with pytest.raises(HTTPException) as exc:
        await identity_api.rotate_scim_token(
            current_user=_admin_user(uuid4(), tier=PricingTier.PRO),
            db=AsyncMock(),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_rotate_scim_token_creates_identity_and_audit_success(monkeypatch) -> None:
    tenant_id = uuid4()
    mock_db = AsyncMock()
    mock_db.execute.return_value = _ScalarOneResult(None)
    mock_db.add = MagicMock()

    monkeypatch.setattr(identity_api, "AuditLogger", _AuditLoggerSuccess)

    response = await identity_api.rotate_scim_token(
        current_user=_admin_user(tenant_id, tier=PricingTier.ENTERPRISE),
        db=mock_db,
    )

    assert isinstance(response.scim_token, str)
    assert response.scim_token
    mock_db.add.assert_called_once()
    assert mock_db.commit.await_count >= 2


@pytest.mark.asyncio
async def test_rotate_scim_token_tolerates_audit_and_refresh_failures(
    monkeypatch,
) -> None:
    tenant_id = uuid4()
    identity = SimpleNamespace(
        scim_enabled=False,
        scim_bearer_token=None,
        scim_last_rotated_at=None,
    )
    mock_db = AsyncMock()
    mock_db.execute.return_value = _ScalarOneResult(identity)
    mock_db.refresh = AsyncMock(side_effect=[None, RuntimeError("refresh failed")])

    monkeypatch.setattr(identity_api, "AuditLogger", _AuditLoggerFailure)

    response = await identity_api.rotate_scim_token(
        current_user=_admin_user(tenant_id, tier=PricingTier.ENTERPRISE),
        db=mock_db,
    )

    assert isinstance(response.scim_token, str)
    assert response.scim_token
    mock_db.rollback.assert_awaited()
