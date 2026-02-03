import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.modules.optimization.domain.unified_discovery import UnifiedDiscoveryService
from app.models.aws_connection import AWSConnection

@pytest.fixture
def mock_connection():
    conn = MagicMock(spec=AWSConnection)
    conn.tenant_id = "test-tenant-id"
    conn.aws_account_id = "123456789012"
    conn.region = "us-east-1"
    return conn

@pytest.mark.asyncio
async def test_discover_aws_inventory_resource_explorer_enabled(mock_connection):
    service = UnifiedDiscoveryService("test-tenant-id")
    
    # Mocking the Resource Explorer Adapter
    mock_explorer = MagicMock()
    mock_explorer.is_enabled = AsyncMock(return_value=True)
    mock_explorer.search_resources = AsyncMock(return_value=[
        {"id": "i-123", "arn": "arn:i-123", "service": "ec2", "resource_type": "instance", "region": "us-east-1"}
    ])

    
    with patch("app.modules.optimization.domain.unified_discovery.AWSResourceExplorerAdapter", return_value=mock_explorer):
        inventory = await service.discover_aws_inventory(mock_connection)
        
    assert inventory.discovery_method == "resource-explorer-2"
    assert len(inventory.resources) == 1
    assert inventory.resources[0].id == "i-123"

@pytest.mark.asyncio
async def test_discover_aws_inventory_resource_explorer_disabled_fallback(mock_connection):
    service = UnifiedDiscoveryService("test-tenant-id")
    
    mock_explorer = MagicMock()
    mock_explorer.is_enabled = AsyncMock(return_value=False)
    
    with patch("app.modules.optimization.domain.unified_discovery.AWSResourceExplorerAdapter", return_value=mock_explorer):
        inventory = await service.discover_aws_inventory(mock_connection)
        
    assert inventory.discovery_method == "native-api-fallback"
    assert len(inventory.resources) == 0
