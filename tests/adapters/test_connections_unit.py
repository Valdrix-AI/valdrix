import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4
from app.shared.connections.aws import AWSConnectionService
from app.models.aws_connection import AWSConnection
# Import all models to prevent mapper errors during Mock usage

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

    # Mock the adapter's verify_connection method
    with patch("app.shared.connections.aws.MultiTenantAWSAdapter") as MockAdapter:
        mock_adapter_instance = MockAdapter.return_value
        mock_adapter_instance.verify_connection = AsyncMock(return_value=True)
        
        service = AWSConnectionService(db)
        res = await service.verify_connection(connection_id, tenant_id)
        
        # Production returns 'success', not 'active'
        assert res["status"] == "success"
        assert mock_conn.status == "active"
        db.commit.assert_called_once()

@pytest.mark.asyncio
async def test_verify_connection_failure():
    """Verify that verify_connection returns failure status on failure."""
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

    # Mock the adapter's verify_connection method to return False
    with patch("app.shared.connections.aws.MultiTenantAWSAdapter") as MockAdapter:
        mock_adapter_instance = MockAdapter.return_value
        mock_adapter_instance.verify_connection = AsyncMock(return_value=False)
        
        service = AWSConnectionService(db)
        res = await service.verify_connection(connection_id, tenant_id)
        
        # Production returns status dict, not HTTPException
        assert res["status"] == "failed"
        assert mock_conn.status == "error"
        db.commit.assert_called_once()

