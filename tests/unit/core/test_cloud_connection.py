import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from fastapi import HTTPException

from app.shared.core.cloud_connection import CloudConnectionService
from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection

@pytest.fixture
def mock_db():
    return AsyncMock()

@pytest.fixture
def tenant_id():
    return uuid4()

@pytest.mark.asyncio
async def test_list_all_connections(mock_db, tenant_id):
    service = CloudConnectionService(mock_db)
    
    mock_aws = [MagicMock(spec=AWSConnection), MagicMock(spec=AWSConnection)]
    mock_azure = [MagicMock(spec=AzureConnection)]
    mock_gcp = []
    
    # Mock sequence of DB executions
    mock_db.execute.side_effect = [
        MagicMock(scalars=lambda: MagicMock(all=lambda: mock_aws)),
        MagicMock(scalars=lambda: MagicMock(all=lambda: mock_azure)),
        MagicMock(scalars=lambda: MagicMock(all=lambda: mock_gcp)),
    ]
    
    results = await service.list_all_connections(tenant_id)
    
    assert results["aws"] == mock_aws
    assert results["azure"] == mock_azure
    assert results["gcp"] == mock_gcp
    assert mock_db.execute.call_count == 3

@pytest.mark.asyncio
async def test_verify_connection_unsupported_provider(mock_db, tenant_id):
    service = CloudConnectionService(mock_db)
    with pytest.raises(HTTPException) as exc:
        await service.verify_connection("unsupported", uuid4(), tenant_id)
    assert exc.value.status_code == 400

@pytest.mark.asyncio
async def test_verify_connection_not_found(mock_db, tenant_id):
    service = CloudConnectionService(mock_db)
    
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res
    
    with pytest.raises(HTTPException) as exc:
        await service.verify_connection("aws", uuid4(), tenant_id)
    assert exc.value.status_code == 404

@pytest.mark.asyncio
async def test_verify_connection_success(mock_db, tenant_id):
    service = CloudConnectionService(mock_db)
    connection = MagicMock(spec=AWSConnection)
    connection.id = uuid4()
    connection.tenant_id = tenant_id
    connection.aws_account_id = "123456789012"
    connection.status = "pending"
    
    # Ensure attributes exist for hasattr checks
    connection.is_active = False
    connection.last_verified_at = None
    
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = connection
    mock_db.execute.return_value = mock_res
    
    mock_adapter = AsyncMock()
    mock_adapter.verify_connection.return_value = True
    
    with patch("app.shared.core.cloud_connection.AdapterFactory.get_adapter", return_value=mock_adapter):
        result = await service.verify_connection("aws", connection.id, tenant_id)
        
        assert result["status"] == "active"
        assert result["account_id"] == "123456789012"
        assert connection.status == "active"
        assert mock_db.commit.called

@pytest.mark.asyncio
async def test_verify_connection_failure(mock_db, tenant_id):
    service = CloudConnectionService(mock_db)
    
    # Use non-spec mock to avoid hasattr issues with spec
    connection = MagicMock()
    connection.id = uuid4()
    connection.tenant_id = tenant_id
    connection.is_active = True
    connection.status = "pending"
    
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = connection
    mock_db.execute.return_value = mock_res
    
    mock_adapter = AsyncMock()
    mock_adapter.verify_connection.return_value = False
    
    with patch("app.shared.core.cloud_connection.AdapterFactory.get_adapter", return_value=mock_adapter):
        with pytest.raises(HTTPException) as exc:
            await service.verify_connection("azure", connection.id, tenant_id)
        assert exc.value.status_code == 400
        assert connection.is_active is False
        assert connection.status == "error"

def test_get_aws_setup_templates():
    result = CloudConnectionService.get_aws_setup_templates("ext-123")
    assert "ext-123" in result["magic_link"]
    assert "ext-123" in result["terraform_snippet"]
