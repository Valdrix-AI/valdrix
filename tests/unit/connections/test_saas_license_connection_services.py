from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.shared.connections.license import LicenseConnectionService
from app.shared.connections.saas import SaaSConnectionService
from app.shared.core.exceptions import ResourceNotFoundError


def _list_result(items: list[object]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    return result


def _scalar_result(item: object | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = item
    return result


@pytest.mark.asyncio
async def test_saas_list_connections_returns_all() -> None:
    tenant_id = uuid4()
    conn_a = MagicMock()
    conn_b = MagicMock()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_list_result([conn_a, conn_b]))

    service = SaaSConnectionService(db)
    rows = await service.list_connections(tenant_id)

    assert rows == [conn_a, conn_b]
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_saas_verify_connection_success() -> None:
    tenant_id = uuid4()
    connection_id = uuid4()
    connection = MagicMock()
    connection.id = connection_id
    connection.tenant_id = tenant_id
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(connection))
    db.commit = AsyncMock()

    adapter = MagicMock()
    adapter.verify_connection = AsyncMock(return_value=True)
    adapter.last_error = None

    with patch("app.shared.connections.saas.AdapterFactory") as factory:
        factory.get_adapter.return_value = adapter

        service = SaaSConnectionService(db)
        result = await service.verify_connection(connection_id, tenant_id)

    assert result == {"status": "success", "message": "SaaS connection verified."}
    assert connection.is_active is True
    assert connection.error_message is None
    assert isinstance(connection.last_synced_at, datetime)
    assert connection.last_synced_at.tzinfo == timezone.utc
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_saas_verify_connection_failure_uses_adapter_message() -> None:
    tenant_id = uuid4()
    connection_id = uuid4()
    connection = MagicMock()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(connection))
    db.commit = AsyncMock()

    adapter = MagicMock()
    adapter.verify_connection = AsyncMock(return_value=False)
    adapter.last_error = "Upstream rejected token"

    with patch("app.shared.connections.saas.AdapterFactory") as factory:
        factory.get_adapter.return_value = adapter

        service = SaaSConnectionService(db)
        result = await service.verify_connection(connection_id, tenant_id)

    assert result == {"status": "failed", "message": "Upstream rejected token"}
    assert connection.is_active is False
    assert connection.error_message == "Upstream rejected token"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_saas_verify_connection_failure_uses_default_message() -> None:
    tenant_id = uuid4()
    connection_id = uuid4()
    connection = MagicMock()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(connection))
    db.commit = AsyncMock()

    adapter = MagicMock()
    adapter.verify_connection = AsyncMock(return_value=False)
    adapter.last_error = None

    with patch("app.shared.connections.saas.AdapterFactory") as factory:
        factory.get_adapter.return_value = adapter

        service = SaaSConnectionService(db)
        result = await service.verify_connection(connection_id, tenant_id)

    assert result == {
        "status": "failed",
        "message": "Failed to validate SaaS connector.",
    }
    assert connection.error_message == "Failed to validate SaaS connector."
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_saas_verify_connection_not_found_raises() -> None:
    tenant_id = uuid4()
    connection_id = uuid4()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(None))

    service = SaaSConnectionService(db)
    with pytest.raises(ResourceNotFoundError):
        await service.verify_connection(connection_id, tenant_id)


@pytest.mark.asyncio
async def test_license_list_connections_returns_all() -> None:
    tenant_id = uuid4()
    conn_a = MagicMock()
    conn_b = MagicMock()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_list_result([conn_a, conn_b]))

    service = LicenseConnectionService(db)
    rows = await service.list_connections(tenant_id)

    assert rows == [conn_a, conn_b]
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_license_verify_connection_success() -> None:
    tenant_id = uuid4()
    connection_id = uuid4()
    connection = MagicMock()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(connection))
    db.commit = AsyncMock()

    adapter = MagicMock()
    adapter.verify_connection = AsyncMock(return_value=True)
    adapter.last_error = None

    with patch("app.shared.connections.license.AdapterFactory") as factory:
        factory.get_adapter.return_value = adapter

        service = LicenseConnectionService(db)
        result = await service.verify_connection(connection_id, tenant_id)

    assert result == {"status": "success", "message": "License connection verified."}
    assert connection.is_active is True
    assert connection.error_message is None
    assert isinstance(connection.last_synced_at, datetime)
    assert connection.last_synced_at.tzinfo == timezone.utc
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_license_verify_connection_failure_uses_default_message() -> None:
    tenant_id = uuid4()
    connection_id = uuid4()
    connection = MagicMock()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(connection))
    db.commit = AsyncMock()

    adapter = MagicMock()
    adapter.verify_connection = AsyncMock(return_value=False)
    adapter.last_error = None

    with patch("app.shared.connections.license.AdapterFactory") as factory:
        factory.get_adapter.return_value = adapter

        service = LicenseConnectionService(db)
        result = await service.verify_connection(connection_id, tenant_id)

    assert result == {
        "status": "failed",
        "message": "Failed to validate license connector.",
    }
    assert connection.error_message == "Failed to validate license connector."
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_license_verify_connection_not_found_raises() -> None:
    tenant_id = uuid4()
    connection_id = uuid4()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(None))

    service = LicenseConnectionService(db)
    with pytest.raises(ResourceNotFoundError):
        await service.verify_connection(connection_id, tenant_id)

