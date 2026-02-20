import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.remediation import RemediationStatus
from app.modules.optimization.domain.license_governance import LicenseGovernanceService


def _settings(auto_pilot_enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        license_auto_reclaim_enabled=True,
        auto_pilot_enabled=auto_pilot_enabled,
        license_inactive_threshold_days=30,
        license_reclaim_grace_period_days=7,
    )


def _connection() -> MagicMock:
    conn = MagicMock()
    conn.id = uuid4()
    conn.vendor = "microsoft_365"
    conn.auth_method = "api_key"
    conn.api_key = None
    conn.connector_config = {"default_seat_price_usd": 12.0}
    return conn


def _connection_result(conn: MagicMock) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = [conn]
    return result


def _inactive_user() -> dict:
    return {
        "user_id": "user-123",
        "email": "user@example.com",
        "last_active_at": datetime.now(timezone.utc).replace(year=2024),
        "suspended": False,
        "is_admin": False,
    }


@pytest.mark.asyncio
async def test_license_governance_autopilot_completed_notifies() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    conn = _connection()
    db.execute = AsyncMock(return_value=_connection_result(conn))

    service = LicenseGovernanceService(db)
    service.get_governance_settings = AsyncMock(return_value=_settings(True))
    service._has_pending_request = AsyncMock(return_value=False)
    request = SimpleNamespace(id=uuid4())
    service.remediation_service.create_request = AsyncMock(return_value=request)
    service.remediation_service.execute = AsyncMock(
        return_value=SimpleNamespace(
            id=request.id,
            status=RemediationStatus.COMPLETED,
            execution_error=None,
        )
    )

    with (
        patch(
            "app.modules.optimization.domain.license_governance.LicenseAdapter"
        ) as adapter_cls,
        patch(
            "app.shared.core.notifications.NotificationDispatcher.notify_license_reclamation",
            new_callable=AsyncMock,
        ) as notify_mock,
    ):
        adapter_cls.return_value.list_users_activity = AsyncMock(
            return_value=[_inactive_user()]
        )

        result = await service.run_tenant_governance(tenant_id)

    assert result["status"] == "completed"
    assert result["stats"]["requests_created"] == 1
    assert result["stats"]["executions_completed"] == 1
    assert result["stats"]["executions_failed"] == 0
    assert result["stats"]["executions_deferred"] == 0
    notify_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_license_governance_autopilot_failed_does_not_notify() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    conn = _connection()
    db.execute = AsyncMock(return_value=_connection_result(conn))

    service = LicenseGovernanceService(db)
    service.get_governance_settings = AsyncMock(return_value=_settings(True))
    service._has_pending_request = AsyncMock(return_value=False)
    request = SimpleNamespace(id=uuid4())
    service.remediation_service.create_request = AsyncMock(return_value=request)
    service.remediation_service.execute = AsyncMock(
        return_value=SimpleNamespace(
            id=request.id,
            status=RemediationStatus.FAILED,
            execution_error="[aws_connection_missing] No AWS connection found (Status: 400)",
        )
    )

    with (
        patch(
            "app.modules.optimization.domain.license_governance.LicenseAdapter"
        ) as adapter_cls,
        patch(
            "app.shared.core.notifications.NotificationDispatcher.notify_license_reclamation",
            new_callable=AsyncMock,
        ) as notify_mock,
    ):
        adapter_cls.return_value.list_users_activity = AsyncMock(
            return_value=[_inactive_user()]
        )

        result = await service.run_tenant_governance(tenant_id)

    assert result["status"] == "completed"
    assert result["stats"]["requests_created"] == 1
    assert result["stats"]["executions_completed"] == 0
    assert result["stats"]["executions_failed"] == 1
    assert result["stats"]["executions_deferred"] == 0
    notify_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_license_governance_autopilot_deferred_does_not_notify() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    conn = _connection()
    db.execute = AsyncMock(return_value=_connection_result(conn))

    service = LicenseGovernanceService(db)
    service.get_governance_settings = AsyncMock(return_value=_settings(True))
    service._has_pending_request = AsyncMock(return_value=False)
    request = SimpleNamespace(id=uuid4())
    service.remediation_service.create_request = AsyncMock(return_value=request)
    service.remediation_service.execute = AsyncMock(
        return_value=SimpleNamespace(
            id=request.id,
            status=RemediationStatus.SCHEDULED,
            execution_error=None,
        )
    )

    with (
        patch(
            "app.modules.optimization.domain.license_governance.LicenseAdapter"
        ) as adapter_cls,
        patch(
            "app.shared.core.notifications.NotificationDispatcher.notify_license_reclamation",
            new_callable=AsyncMock,
        ) as notify_mock,
    ):
        adapter_cls.return_value.list_users_activity = AsyncMock(
            return_value=[_inactive_user()]
        )

        result = await service.run_tenant_governance(tenant_id)

    assert result["status"] == "completed"
    assert result["stats"]["requests_created"] == 1
    assert result["stats"]["executions_completed"] == 0
    assert result["stats"]["executions_failed"] == 0
    assert result["stats"]["executions_deferred"] == 1
    notify_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_license_governance_skips_invalid_user_identity() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    conn = _connection()
    db.execute = AsyncMock(return_value=_connection_result(conn))

    service = LicenseGovernanceService(db)
    service.get_governance_settings = AsyncMock(return_value=_settings(False))
    service._has_pending_request = AsyncMock(return_value=False)
    service.remediation_service.create_request = AsyncMock()

    invalid_user = {
        "user_id": None,
        "email": "user@example.com",
        "last_active_at": None,
        "suspended": False,
        "is_admin": False,
    }

    with patch(
        "app.modules.optimization.domain.license_governance.LicenseAdapter"
    ) as adapter_cls:
        adapter_cls.return_value.list_users_activity = AsyncMock(
            return_value=[invalid_user]
        )
        result = await service.run_tenant_governance(tenant_id)

    assert result["status"] == "completed"
    assert result["stats"]["users_skipped_invalid"] == 1
    assert result["stats"]["requests_created"] == 0
    service.remediation_service.create_request.assert_not_awaited()


@pytest.mark.asyncio
async def test_license_governance_skips_invalid_last_active() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    conn = _connection()
    db.execute = AsyncMock(return_value=_connection_result(conn))

    service = LicenseGovernanceService(db)
    service.get_governance_settings = AsyncMock(return_value=_settings(False))
    service._has_pending_request = AsyncMock(return_value=False)
    service.remediation_service.create_request = AsyncMock()

    user = {
        "user_id": "user-123",
        "email": "user@example.com",
        "last_active_at": "not-a-timestamp",
        "suspended": False,
        "is_admin": False,
    }

    with patch(
        "app.modules.optimization.domain.license_governance.LicenseAdapter"
    ) as adapter_cls:
        adapter_cls.return_value.list_users_activity = AsyncMock(return_value=[user])
        result = await service.run_tenant_governance(tenant_id)

    assert result["status"] == "completed"
    assert result["stats"]["users_skipped_invalid"] == 1
    assert result["stats"]["requests_created"] == 0
    service.remediation_service.create_request.assert_not_awaited()


@pytest.mark.asyncio
async def test_license_governance_connection_timeout_isolated() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    conn = _connection()
    db.execute = AsyncMock(return_value=_connection_result(conn))

    service = LicenseGovernanceService(db)
    service.get_governance_settings = AsyncMock(return_value=_settings(False))
    service._has_pending_request = AsyncMock(return_value=False)
    service.remediation_service.create_request = AsyncMock()

    with patch(
        "app.modules.optimization.domain.license_governance.LicenseAdapter"
    ) as adapter_cls:
        adapter_cls.return_value.list_users_activity = AsyncMock(
            side_effect=asyncio.TimeoutError
        )
        result = await service.run_tenant_governance(tenant_id)

    assert result["status"] == "completed"
    assert result["stats"]["connections_timed_out"] == 1
    assert result["stats"]["requests_created"] == 0
    service.remediation_service.create_request.assert_not_awaited()


@pytest.mark.asyncio
async def test_license_governance_sanitizes_default_seat_price() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    conn = _connection()
    conn.connector_config = {"default_seat_price_usd": "invalid"}
    db.execute = AsyncMock(return_value=_connection_result(conn))

    service = LicenseGovernanceService(db)
    service.get_governance_settings = AsyncMock(return_value=_settings(False))
    service._has_pending_request = AsyncMock(return_value=False)
    request = SimpleNamespace(id=uuid4())
    service.remediation_service.create_request = AsyncMock(return_value=request)

    with patch(
        "app.modules.optimization.domain.license_governance.LicenseAdapter"
    ) as adapter_cls:
        adapter_cls.return_value.list_users_activity = AsyncMock(
            return_value=[_inactive_user()]
        )
        result = await service.run_tenant_governance(tenant_id)

    assert result["status"] == "completed"
    assert result["stats"]["requests_created"] == 1
    create_kwargs = service.remediation_service.create_request.await_args.kwargs
    assert create_kwargs["estimated_savings"] == 12.0


@pytest.mark.asyncio
async def test_license_governance_manual_feed_wiring_creates_request() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    conn = _connection()
    conn.vendor = "custom_vendor"
    conn.auth_method = "manual"
    conn.api_key = None
    conn.license_feed = [
        {
            "user_id": "manual-user-1",
            "email": "manual.user@example.com",
            "last_active_at": "2024-01-01T00:00:00Z",
            "is_admin": False,
            "suspended": False,
        }
    ]
    db.execute = AsyncMock(return_value=_connection_result(conn))

    service = LicenseGovernanceService(db)
    service.get_governance_settings = AsyncMock(return_value=_settings(False))
    service._has_pending_request = AsyncMock(return_value=False)
    request = SimpleNamespace(id=uuid4())
    service.remediation_service.create_request = AsyncMock(return_value=request)

    result = await service.run_tenant_governance(tenant_id)

    assert result["status"] == "completed"
    assert result["stats"]["requests_created"] == 1
    create_kwargs = service.remediation_service.create_request.await_args.kwargs
    assert create_kwargs["resource_id"] == "manual-user-1"
    assert create_kwargs["provider"] == "license"


@pytest.mark.asyncio
async def test_license_governance_queries_active_connections_only() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_connection_result(_connection()))

    service = LicenseGovernanceService(db)
    service.get_governance_settings = AsyncMock(return_value=_settings(False))

    with patch(
        "app.modules.optimization.domain.license_governance.LicenseAdapter"
    ) as adapter_cls:
        adapter_cls.return_value.list_users_activity = AsyncMock(return_value=[])
        await service.run_tenant_governance(tenant_id)

    first_stmt = db.execute.await_args_list[0].args[0]
    stmt_text = str(first_stmt)
    assert "license_connections.is_active" in stmt_text
