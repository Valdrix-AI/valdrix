from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.governance.api.v1.settings import connections_cloud_plus as cloud_plus_api
from app.schemas.connections import (
    HybridConnectionCreate,
    LicenseConnectionCreate,
    PlatformConnectionCreate,
    SaaSConnectionCreate,
)
from app.shared.core.auth import CurrentUser
from app.shared.core.pricing import PricingTier


def _user() -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        email="cloud-plus@example.com",
        tenant_id=uuid4(),
        tier=PricingTier.PRO,
    )


def _db() -> MagicMock:
    db = MagicMock()
    db.scalar = AsyncMock(return_value=None)
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    db.add = MagicMock()
    return db


def _scalar_result(value: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("func_name", "payload", "expected_vendor"),
    [
        (
            "create_saas_connection",
            SaaSConnectionCreate(
                name="Salesforce",
                vendor="salesforce",
                auth_method="manual",
                connector_config={},
                spend_feed=[],
            ),
            "salesforce",
        ),
        (
            "create_license_connection",
            LicenseConnectionCreate(
                name="M365",
                vendor="microsoft_365",
                auth_method="manual",
                connector_config={},
                license_feed=[],
            ),
            "microsoft_365",
        ),
        (
            "create_platform_connection",
            PlatformConnectionCreate(
                name="Datadog Feed",
                vendor="datadog",
                auth_method="manual",
                connector_config={},
                spend_feed=[],
            ),
            "datadog",
        ),
        (
            "create_hybrid_connection",
            HybridConnectionCreate(
                name="vCenter Feed",
                vendor="vmware",
                auth_method="manual",
                connector_config={},
                spend_feed=[],
            ),
            "vmware",
        ),
    ],
)
async def test_cloud_plus_create_connection_success_paths(
    func_name: str,
    payload: object,
    expected_vendor: str,
) -> None:
    user = _user()
    db = _db()
    request = MagicMock()
    request.url.path = "/api/v1/settings/connections/x"
    request.method = "POST"

    create_func = getattr(cloud_plus_api, func_name)

    with (
        patch.object(cloud_plus_api, "check_cloud_plus_tier", return_value=PricingTier.PRO),
        patch.object(cloud_plus_api, "_enforce_connection_limit", new=AsyncMock()),
        patch.object(cloud_plus_api, "audit_log") as audit_mock,
    ):
        out = await create_func(request, payload, user, db)

    assert out.tenant_id == user.tenant_id
    assert out.vendor == expected_vendor
    assert out.is_active is False
    db.add.assert_called_once()
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(out)
    audit_mock.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("func_name", "service_attr"),
    [
        ("verify_saas_connection", "SaaSConnectionService"),
        ("verify_license_connection", "LicenseConnectionService"),
        ("verify_platform_connection", "PlatformConnectionService"),
        ("verify_hybrid_connection", "HybridConnectionService"),
    ],
)
async def test_cloud_plus_verify_connection_wrappers(
    func_name: str,
    service_attr: str,
) -> None:
    user = _user()
    db = _db()
    request = MagicMock()
    connection_id = uuid4()
    verify_func = getattr(cloud_plus_api, func_name)

    with (
        patch.object(cloud_plus_api, "check_cloud_plus_tier", return_value=PricingTier.PRO),
        patch.object(cloud_plus_api, service_attr) as service_cls,
    ):
        service = MagicMock()
        service.verify_connection = AsyncMock(return_value={"status": "verified"})
        service_cls.return_value = service

        out = await verify_func(request, connection_id, user, db)

    assert out == {"status": "verified"}
    service.verify_connection.assert_awaited_once_with(connection_id, user.tenant_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("func_name", "service_attr"),
    [
        ("list_saas_connections", "SaaSConnectionService"),
        ("list_license_connections", "LicenseConnectionService"),
        ("list_platform_connections", "PlatformConnectionService"),
        ("list_hybrid_connections", "HybridConnectionService"),
    ],
)
async def test_cloud_plus_list_connection_wrappers(
    func_name: str,
    service_attr: str,
) -> None:
    user = _user()
    db = _db()
    list_func = getattr(cloud_plus_api, func_name)

    expected = [SimpleNamespace(id=uuid4(), name="conn")]

    with patch.object(cloud_plus_api, service_attr) as service_cls:
        service = MagicMock()
        service.list_connections = AsyncMock(return_value=expected)
        service_cls.return_value = service

        out = await list_func(user, db)

    assert out == expected
    service.list_connections.assert_awaited_once_with(user.tenant_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "func_name",
    [
        "delete_saas_connection",
        "delete_license_connection",
        "delete_platform_connection",
        "delete_hybrid_connection",
    ],
)
async def test_cloud_plus_delete_connection_success_paths(func_name: str) -> None:
    user = _user()
    db = _db()
    connection_id = uuid4()
    delete_func = getattr(cloud_plus_api, func_name)

    connection = SimpleNamespace(id=connection_id, tenant_id=user.tenant_id)
    db.execute.return_value = _scalar_result(connection)

    with patch.object(cloud_plus_api, "audit_log") as audit_mock:
        out = await delete_func(connection_id, user, db)

    assert out is None
    db.delete.assert_awaited_once_with(connection)
    db.commit.assert_awaited_once()
    audit_mock.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("func_name", "payload"),
    [
        (
            "create_saas_connection",
            SaaSConnectionCreate(
                name="Salesforce",
                vendor="salesforce",
                auth_method="manual",
                connector_config={},
                spend_feed=[],
            ),
        ),
        (
            "create_license_connection",
            LicenseConnectionCreate(
                name="M365",
                vendor="microsoft_365",
                auth_method="manual",
                connector_config={},
                license_feed=[],
            ),
        ),
        (
            "create_platform_connection",
            PlatformConnectionCreate(
                name="Datadog Feed",
                vendor="datadog",
                auth_method="manual",
                connector_config={},
                spend_feed=[],
            ),
        ),
        (
            "create_hybrid_connection",
            HybridConnectionCreate(
                name="vCenter Feed",
                vendor="vmware",
                auth_method="manual",
                connector_config={},
                spend_feed=[],
            ),
        ),
    ],
)
async def test_cloud_plus_create_platform_and_hybrid_duplicate_conflict(
    func_name: str,
    payload: object,
) -> None:
    user = _user()
    db = _db()
    db.scalar = AsyncMock(return_value=uuid4())
    request = MagicMock()
    request.url.path = "/api/v1/settings/connections/x"
    request.method = "POST"

    create_func = getattr(cloud_plus_api, func_name)

    with (
        patch.object(cloud_plus_api, "check_cloud_plus_tier", return_value=PricingTier.PRO),
        patch.object(cloud_plus_api, "_enforce_connection_limit", new=AsyncMock()) as limit_mock,
        patch.object(cloud_plus_api, "audit_log") as audit_mock,
    ):
        with pytest.raises(HTTPException) as exc:
            await create_func(request, payload, user, db)

    assert exc.value.status_code == 409
    assert "already exists" in str(exc.value.detail)
    limit_mock.assert_not_awaited()
    db.add.assert_not_called()
    audit_mock.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "func_name",
    [
        "delete_saas_connection",
        "delete_license_connection",
        "delete_platform_connection",
        "delete_hybrid_connection",
    ],
)
async def test_cloud_plus_delete_platform_and_hybrid_not_found(func_name: str) -> None:
    user = _user()
    db = _db()
    db.execute.return_value = _scalar_result(None)
    connection_id = uuid4()
    delete_func = getattr(cloud_plus_api, func_name)

    with patch.object(cloud_plus_api, "audit_log") as audit_mock:
        with pytest.raises(HTTPException) as exc:
            await delete_func(connection_id, user, db)

    assert exc.value.status_code == 404
    assert "Connection not found" in str(exc.value.detail)
    db.delete.assert_not_awaited()
    db.commit.assert_not_awaited()
    audit_mock.assert_not_called()
