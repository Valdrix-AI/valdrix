import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4
from fastapi import HTTPException
from app.shared.connections.aws import AWSConnectionService
from app.models.aws_connection import AWSConnection

@pytest.mark.asyncio
async def test_verify_connection_success():
    """Verify that verify_connection returns success on valid role."""
    db = AsyncMock()
    connection_id = uuid4()
    tenant_id = uuid4()
    
    # Mock Connection
    mock_conn = AWSConnection(
        id=connection_id,
        tenant_id=tenant_id,
        role_arn="arn:aws:iam::123:role/TestRole",
        external_id="ext-123"
    )
    
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_conn
    db.execute.return_value = mock_result

    with patch.object(AWSConnectionService, 'verify_role_access', AsyncMock(return_value=(True, None))):
        service = AWSConnectionService(db)
        res = await service.verify_connection(connection_id, tenant_id)
        
        assert res["status"] == "active"
        assert mock_conn.status == "active"
        assert mock_conn.last_verified_at is not None
        db.commit.assert_called_once()

@pytest.mark.asyncio
async def test_verify_connection_failure():
    """Verify that verify_connection raises HTTPException on failure."""
    db = AsyncMock()
    connection_id = uuid4()
    tenant_id = uuid4()
    
    # Mock Connection
    mock_conn = AWSConnection(
        id=connection_id,
        tenant_id=tenant_id,
        role_arn="arn:aws:iam::123:role/TestRole",
        external_id="ext-123"
    )
    
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_conn
    db.execute.return_value = mock_result

    with patch.object(AWSConnectionService, 'verify_role_access', AsyncMock(return_value=(False, "AccessDenied"))):
        with pytest.raises(HTTPException) as excinfo:
            service = AWSConnectionService(db)
            await service.verify_connection(connection_id, tenant_id)
        
        assert excinfo.value.status_code == 400
        assert "AccessDenied" in excinfo.value.detail
        assert mock_conn.status == "error"
        db.commit.assert_called_once()
