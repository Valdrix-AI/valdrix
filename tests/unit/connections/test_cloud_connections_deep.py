import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4
from app.shared.connections.aws import AWSConnectionService
from app.shared.connections.azure import AzureConnectionService
from app.shared.connections.gcp import GCPConnectionService
from app.shared.core.exceptions import ResourceNotFoundError, AdapterError
from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.gcp_connection import GCPConnection

class TestCloudConnectionsDeep:
    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_aws_verify_connection_success(self, mock_db):
        service = AWSConnectionService(mock_db)
        conn_id = uuid4()
        tenant_id = uuid4()
        
        # Mock DB results
        mock_conn = AWSConnection(id=conn_id, tenant_id=tenant_id, status="pending", region="us-east-1")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_conn
        mock_db.execute.return_value = mock_result
        
        with patch("app.shared.connections.aws.MultiTenantAWSAdapter") as mock_adapter_class:
            mock_adapter = mock_adapter_class.return_value
            mock_adapter.verify_connection = AsyncMock(return_value=True)
            
            res = await service.verify_connection(conn_id, tenant_id)
            assert res["status"] == "success"
            assert mock_conn.status == "active"
            assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_aws_verify_connection_not_found(self, mock_db):
        service = AWSConnectionService(mock_db)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        with pytest.raises(ResourceNotFoundError):
            await service.verify_connection(uuid4(), uuid4())

    @pytest.mark.asyncio
    async def test_aws_verify_connection_failed_adapter(self, mock_db):
        service = AWSConnectionService(mock_db)
        mock_conn = AWSConnection(id=uuid4(), status="pending", region="us-east-1")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_conn
        mock_db.execute.return_value = mock_result
        
        with patch("app.shared.connections.aws.MultiTenantAWSAdapter") as mock_adapter_class:
            mock_adapter = mock_adapter_class.return_value
            mock_adapter.verify_connection = AsyncMock(return_value=False)
            
            res = await service.verify_connection(mock_conn.id, uuid4())
            assert res["status"] == "failed"
            assert mock_conn.status == "error"

    @pytest.mark.asyncio
    async def test_aws_verify_connection_adapter_error(self, mock_db):
        service = AWSConnectionService(mock_db)
        mock_conn = AWSConnection(id=uuid4(), status="pending", region="us-east-1")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_conn
        mock_db.execute.return_value = mock_result
        
        with patch("app.shared.connections.aws.MultiTenantAWSAdapter") as mock_adapter_class:
            mock_adapter = mock_adapter_class.return_value
            mock_adapter.verify_connection.side_effect = AdapterError("IAM Error", code="AUTH_FAILED")
            
            res = await service.verify_connection(mock_conn.id, uuid4())
            assert res["status"] == "error"
            assert res["code"] == "AUTH_FAILED"

    @pytest.mark.asyncio
    async def test_aws_verify_connection_unexpected_error(self, mock_db):
        service = AWSConnectionService(mock_db)
        mock_conn = AWSConnection(id=uuid4(), status="pending", region="us-east-1")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_conn
        mock_db.execute.return_value = mock_result
        
        with patch("app.shared.connections.aws.MultiTenantAWSAdapter") as mock_adapter_class:
            mock_adapter = mock_adapter_class.return_value
            mock_adapter.verify_connection.side_effect = Exception("System Crash")
            
            res = await service.verify_connection(mock_conn.id, uuid4())
            assert res["status"] == "error"
            assert "unexpected error" in res["message"].lower()

    @pytest.mark.asyncio
    async def test_azure_verify_connection_success(self, mock_db):
        service = AzureConnectionService(mock_db)
        mock_conn = AzureConnection(id=uuid4(), is_active=False)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_conn
        mock_db.execute.return_value = mock_result
        
        with patch("app.shared.connections.azure.AzureAdapter") as mock_adapter_class:
            mock_adapter = mock_adapter_class.return_value
            mock_adapter.verify_connection = AsyncMock(return_value=True)
            
            res = await service.verify_connection(mock_conn.id, uuid4())
            assert res["status"] == "success"
            assert mock_conn.is_active is True

    @pytest.mark.asyncio
    async def test_azure_verify_connection_not_found(self, mock_db):
        service = AzureConnectionService(mock_db)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        with pytest.raises(ResourceNotFoundError):
            await service.verify_connection(uuid4(), uuid4())

    @pytest.mark.asyncio
    async def test_azure_verify_connection_failed(self, mock_db):
        service = AzureConnectionService(mock_db)
        mock_conn = AzureConnection(id=uuid4(), is_active=False)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_conn
        mock_db.execute.return_value = mock_result
        
        with patch("app.shared.connections.azure.AzureAdapter") as mock_adapter_class:
            mock_adapter = mock_adapter_class.return_value
            mock_adapter.verify_connection = AsyncMock(return_value=False)
            
            res = await service.verify_connection(mock_conn.id, uuid4())
            assert res["status"] == "failed"

    @pytest.mark.asyncio
    async def test_gcp_verify_connection_success(self, mock_db):
        service = GCPConnectionService(mock_db)
        mock_conn = GCPConnection(id=uuid4(), is_active=False)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_conn
        mock_db.execute.return_value = mock_result
        
        with patch("app.shared.connections.gcp.GCPAdapter") as mock_adapter_class:
            mock_adapter = mock_adapter_class.return_value
            mock_adapter.verify_connection = AsyncMock(return_value=True)
            
            res = await service.verify_connection(mock_conn.id, uuid4())
            assert res["status"] == "success"
            assert mock_conn.is_active is True

    @pytest.mark.asyncio
    async def test_gcp_verify_connection_not_found(self, mock_db):
        service = GCPConnectionService(mock_db)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        with pytest.raises(ResourceNotFoundError):
            await service.verify_connection(uuid4(), uuid4())

    @pytest.mark.asyncio
    async def test_gcp_verify_connection_failed(self, mock_db):
        service = GCPConnectionService(mock_db)
        mock_conn = GCPConnection(id=uuid4(), is_active=False)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_conn
        mock_db.execute.return_value = mock_result
        
        with patch("app.shared.connections.gcp.GCPAdapter") as mock_adapter_class:
            mock_adapter = mock_adapter_class.return_value
            mock_adapter.verify_connection = AsyncMock(return_value=False)
            
            res = await service.verify_connection(mock_conn.id, uuid4())
            assert res["status"] == "failed"
            
    def test_aws_setup_templates(self):
        templates = AWSConnectionService.get_setup_templates("ext-123")
        assert templates["external_id"] == "ext-123"
        assert "valdrix-role" in templates["cloudformation"]
        assert "valdrix/aws-connection" in templates["terraform"]

    @pytest.mark.asyncio
    async def test_azure_list_connections(self, mock_db):
        service = AzureConnectionService(mock_db)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [AzureConnection(id=uuid4())]
        mock_db.execute.return_value = mock_result
        
        conns = await service.list_connections(uuid4())
        assert len(conns) == 1
