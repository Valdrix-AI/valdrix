from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.shared.connections.hybrid import HybridConnectionService
from app.shared.connections.platform import PlatformConnectionService
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
async def test_platform_list_connections_returns_all() -> None:
    tenant_id = uuid4()
    conn_a = MagicMock()
    conn_b = MagicMock()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_list_result([conn_a, conn_b]))

    service = PlatformConnectionService(db)
    rows = await service.list_connections(tenant_id)

    assert rows == [conn_a, conn_b]
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_platform_verify_connection_success_and_failures() -> None:
    tenant_id = uuid4()
    connection_id = uuid4()
    connection = MagicMock()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(connection))
    db.commit = AsyncMock()

    adapter = MagicMock()
    adapter.verify_connection = AsyncMock(return_value=True)
    adapter.last_error = None

    with patch("app.shared.connections.platform.AdapterFactory") as factory:
        factory.get_adapter.return_value = adapter
        service = PlatformConnectionService(db)
        result = await service.verify_connection(connection_id, tenant_id)

    assert result == {"status": "success", "message": "Platform connection verified."}
    assert connection.is_active is True
    assert connection.error_message is None
    assert isinstance(connection.last_synced_at, datetime)
    assert connection.last_synced_at.tzinfo == timezone.utc
    db.commit.assert_awaited_once()

    adapter.verify_connection = AsyncMock(return_value=False)
    adapter.last_error = "platform upstream rejected token"
    db.commit = AsyncMock()
    with patch("app.shared.connections.platform.AdapterFactory") as factory:
        factory.get_adapter.return_value = adapter
        service = PlatformConnectionService(db)
        result = await service.verify_connection(connection_id, tenant_id)

    assert result == {
        "status": "failed",
        "message": "platform upstream rejected token",
    }
    assert connection.is_active is False
    assert connection.error_message == "platform upstream rejected token"
    db.commit.assert_awaited_once()

    adapter.verify_connection = AsyncMock(return_value=False)
    adapter.last_error = None
    db.commit = AsyncMock()
    with patch("app.shared.connections.platform.AdapterFactory") as factory:
        factory.get_adapter.return_value = adapter
        service = PlatformConnectionService(db)
        result = await service.verify_connection(connection_id, tenant_id)

    assert result == {
        "status": "failed",
        "message": "Failed to validate platform connector.",
    }
    assert connection.error_message == "Failed to validate platform connector."
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_platform_verify_connection_not_found_raises() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(None))
    service = PlatformConnectionService(db)

    with pytest.raises(ResourceNotFoundError):
        await service.verify_connection(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_hybrid_list_connections_returns_all() -> None:
    tenant_id = uuid4()
    conn_a = MagicMock()
    conn_b = MagicMock()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_list_result([conn_a, conn_b]))

    service = HybridConnectionService(db)
    rows = await service.list_connections(tenant_id)

    assert rows == [conn_a, conn_b]
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_hybrid_verify_connection_success_and_failures() -> None:
    tenant_id = uuid4()
    connection_id = uuid4()
    connection = MagicMock()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(connection))
    db.commit = AsyncMock()

    adapter = MagicMock()
    adapter.verify_connection = AsyncMock(return_value=True)
    adapter.last_error = None

    with patch("app.shared.connections.hybrid.AdapterFactory") as factory:
        factory.get_adapter.return_value = adapter
        service = HybridConnectionService(db)
        result = await service.verify_connection(connection_id, tenant_id)

    assert result == {"status": "success", "message": "Hybrid connection verified."}
    assert connection.is_active is True
    assert connection.error_message is None
    assert isinstance(connection.last_synced_at, datetime)
    assert connection.last_synced_at.tzinfo == timezone.utc
    db.commit.assert_awaited_once()

    adapter.verify_connection = AsyncMock(return_value=False)
    adapter.last_error = "hybrid upstream rejected token"
    db.commit = AsyncMock()
    with patch("app.shared.connections.hybrid.AdapterFactory") as factory:
        factory.get_adapter.return_value = adapter
        service = HybridConnectionService(db)
        result = await service.verify_connection(connection_id, tenant_id)

    assert result == {
        "status": "failed",
        "message": "hybrid upstream rejected token",
    }
    assert connection.is_active is False
    assert connection.error_message == "hybrid upstream rejected token"
    db.commit.assert_awaited_once()

    adapter.verify_connection = AsyncMock(return_value=False)
    adapter.last_error = None
    db.commit = AsyncMock()
    with patch("app.shared.connections.hybrid.AdapterFactory") as factory:
        factory.get_adapter.return_value = adapter
        service = HybridConnectionService(db)
        result = await service.verify_connection(connection_id, tenant_id)

    assert result == {
        "status": "failed",
        "message": "Failed to validate hybrid connector.",
    }
    assert connection.error_message == "Failed to validate hybrid connector."
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_hybrid_verify_connection_not_found_raises() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(None))
    service = HybridConnectionService(db)

    with pytest.raises(ResourceNotFoundError):
        await service.verify_connection(uuid4(), uuid4())
