from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.modules.optimization.domain.license_governance import LicenseGovernanceService
from app.shared.core.exceptions import ExternalAPIError


def _settings(*, enabled: bool = True, auto_pilot: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        license_auto_reclaim_enabled=enabled,
        auto_pilot_enabled=auto_pilot,
        license_inactive_threshold_days=30,
        license_reclaim_grace_period_days=7,
    )


def _connection() -> MagicMock:
    conn = MagicMock()
    conn.id = uuid4()
    conn.vendor = "custom_vendor"
    conn.auth_method = "api_key"
    conn.api_key = None
    conn.connector_config = {"default_seat_price_usd": 12.0}
    conn.license_feed = []
    return conn


def _connection_result(conns: list[MagicMock]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = conns
    return result


def _db_with_connections(conns: list[MagicMock]) -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_connection_result(conns))
    return db


def test_license_governance_helper_normalizers_cover_edge_cases() -> None:
    assert LicenseGovernanceService._normalize_user_id(None) is None
    assert LicenseGovernanceService._normalize_user_id("  user-1 ") == "user-1"
    assert LicenseGovernanceService._normalize_user_id("   ") is None

    assert LicenseGovernanceService._normalize_user_email(None) is None
    assert LicenseGovernanceService._normalize_user_email("no-at-symbol") is None
    assert (
        LicenseGovernanceService._normalize_user_email(" USER@Example.COM ")
        == "user@example.com"
    )

    dt, err = LicenseGovernanceService._normalize_last_active(None)
    assert dt is None and err is False

    dt, err = LicenseGovernanceService._normalize_last_active(datetime(2026, 2, 1, 0, 0))
    assert dt is not None and dt.tzinfo is not None and err is False

    dt, err = LicenseGovernanceService._normalize_last_active("   ")
    assert dt is None and err is True

    dt, err = LicenseGovernanceService._normalize_last_active("not-a-date")
    assert dt is None and err is True

    dt, err = LicenseGovernanceService._normalize_last_active("2026-02-01T00:00:00")
    assert dt is not None and dt.tzinfo is not None and err is False

    dt, err = LicenseGovernanceService._normalize_last_active(1700000000)
    assert dt is not None and err is False

    dt, err = LicenseGovernanceService._normalize_last_active(1e40)
    assert dt is None and err is True

    dt, err = LicenseGovernanceService._normalize_last_active(object())
    assert dt is None and err is True

    assert LicenseGovernanceService._resolve_estimated_savings({"default_seat_price_usd": "bad"}) == 12.0
    assert LicenseGovernanceService._resolve_estimated_savings({"default_seat_price_usd": 0}) == 12.0
    assert LicenseGovernanceService._resolve_estimated_savings({"default_seat_price_usd": 19}) == 19.0


@pytest.mark.asyncio
async def test_license_governance_direct_db_helpers() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    settings_result = MagicMock()
    settings_obj = object()
    settings_result.scalar_one_or_none.return_value = settings_obj
    pending_result = MagicMock()
    pending_result.scalar_one_or_none.return_value = "request-id"
    db.execute = AsyncMock(side_effect=[settings_result, pending_result])

    service = LicenseGovernanceService(db)
    assert await service.get_governance_settings(tenant_id) is settings_obj
    assert await service._has_pending_request(tenant_id, "user-1") is True


@pytest.mark.asyncio
async def test_license_governance_skips_when_feature_disabled() -> None:
    tenant_id = uuid4()
    service = LicenseGovernanceService(_db_with_connections([_connection()]))
    service.get_governance_settings = AsyncMock(return_value=_settings(enabled=False))

    result = await service.run_tenant_governance(tenant_id)

    assert result == {"status": "skipped", "reason": "feature_disabled"}


@pytest.mark.asyncio
async def test_license_governance_run_loop_skips_invalid_suspended_admin_active_and_duplicate() -> None:
    tenant_id = uuid4()
    conn = _connection()
    service = LicenseGovernanceService(_db_with_connections([conn]))
    service.get_governance_settings = AsyncMock(return_value=_settings(enabled=True, auto_pilot=False))
    service._has_pending_request = AsyncMock(return_value=True)
    service.remediation_service.create_request = AsyncMock()

    recent = datetime.now(timezone.utc) - timedelta(days=2)
    users = [
        "not-a-dict",
        {"user_id": "suspended", "email": "s@example.com", "last_active_at": None, "suspended": True, "is_admin": False},
        {"user_id": "admin", "email": "a@example.com", "last_active_at": None, "suspended": False, "is_admin": True},
        {"user_id": "recent", "email": "r@example.com", "last_active_at": recent.isoformat(), "suspended": False, "is_admin": False},
        {"user_id": "dup", "email": "dup@example.com", "last_active_at": None, "suspended": False, "is_admin": False},
    ]

    with patch("app.modules.optimization.domain.license_governance.LicenseAdapter") as adapter_cls:
        adapter_cls.return_value.list_users_activity = AsyncMock(return_value=users)
        result = await service.run_tenant_governance(tenant_id)

    stats = result["stats"]
    assert result["status"] == "completed"
    assert stats["users_skipped_invalid"] == 1
    assert stats["users_flagged"] == 1
    assert stats["duplicates_skipped"] == 1
    assert stats["requests_created"] == 0
    service.remediation_service.create_request.assert_not_awaited()


@pytest.mark.asyncio
async def test_license_governance_autopilot_execute_exception_counts_failure() -> None:
    tenant_id = uuid4()
    conn = _connection()
    service = LicenseGovernanceService(_db_with_connections([conn]))
    service.get_governance_settings = AsyncMock(return_value=_settings(enabled=True, auto_pilot=True))
    service._has_pending_request = AsyncMock(return_value=False)
    request = SimpleNamespace(id=uuid4())
    service.remediation_service.create_request = AsyncMock(return_value=request)
    service.remediation_service.execute = AsyncMock(side_effect=RuntimeError("exec boom"))

    user = {
        "user_id": "u-1",
        "email": "u1@example.com",
        "last_active_at": None,
        "suspended": False,
        "is_admin": False,
    }
    with patch("app.modules.optimization.domain.license_governance.LicenseAdapter") as adapter_cls:
        adapter_cls.return_value.list_users_activity = AsyncMock(return_value=[user])
        result = await service.run_tenant_governance(tenant_id)

    assert result["status"] == "completed"
    assert result["stats"]["requests_created"] == 1
    assert result["stats"]["executions_failed"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc",
    [
        ExternalAPIError("vendor API down"),
        httpx.HTTPError("transport error"),
        SQLAlchemyError("db write failed"),
        RuntimeError("unexpected"),
    ],
)
async def test_license_governance_connection_level_exception_branches(exc: Exception) -> None:
    tenant_id = uuid4()
    conn = _connection()
    service = LicenseGovernanceService(_db_with_connections([conn]))
    service.get_governance_settings = AsyncMock(return_value=_settings(enabled=True, auto_pilot=False))

    with (
        patch("app.modules.optimization.domain.license_governance.LicenseAdapter") as adapter_cls,
        patch("app.modules.optimization.domain.license_governance.logger.error") as logger_error,
    ):
        if isinstance(exc, ExternalAPIError):
            adapter_cls.side_effect = exc
        else:
            adapter_cls.return_value.list_users_activity = AsyncMock(side_effect=exc)

        result = await service.run_tenant_governance(tenant_id)

    assert result["status"] == "completed"
    assert result["stats"]["requests_created"] == 0
    logger_error.assert_called()

