import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.shared.core.service import BaseService
from app.shared.core.exceptions import ResourceNotFoundError
from app.models.aws_connection import AWSConnection


@pytest.mark.asyncio
async def test_scoped_query_filters_by_tenant_id():
    db = AsyncMock()
    service = BaseService(db)
    tenant_id = uuid4()

    stmt = service._scoped_query(AWSConnection, tenant_id)
    where_clause = str(stmt.whereclause)

    assert "tenant_id" in where_clause


@pytest.mark.asyncio
async def test_get_by_id_returns_record():
    db = AsyncMock()
    record = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = record
    db.execute = AsyncMock(return_value=result)

    service = BaseService(db)
    out = await service.get_by_id(AWSConnection, uuid4(), uuid4())

    assert out is record
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_by_id_uses_for_update_when_locked():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = MagicMock()
    db.execute = AsyncMock(return_value=result)

    service = BaseService(db)
    await service.get_by_id(AWSConnection, uuid4(), uuid4(), lock=True)

    stmt = db.execute.call_args[0][0]
    assert getattr(stmt, "_for_update_arg", None) is not None


@pytest.mark.asyncio
async def test_get_by_id_raises_when_missing():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)

    service = BaseService(db)
    with pytest.raises(ResourceNotFoundError, match="AWSConnection"):
        await service.get_by_id(AWSConnection, uuid4(), uuid4())
