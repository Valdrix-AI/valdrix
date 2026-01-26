import pytest
from unittest.mock import MagicMock
from app.modules.optimization.domain.azure_provider.plugins.unattached_disks import AzureUnattachedDisksPlugin

@pytest.fixture
def plugin():
    return AzureUnattachedDisksPlugin()

@pytest.mark.asyncio
async def test_azure_unattached_disks_scan(plugin):
    # Mock Azure Disk object
    mock_disk = MagicMock()
    mock_disk.id = "/subscriptions/123/disks/my-disk"
    mock_disk.name = "my-disk"
    mock_disk.location = "eastus"
    mock_disk.disk_state = "Unattached"
    mock_disk.disk_size_gb = 100
    mock_disk.sku.name = "Premium_LRS"
    mock_disk.tags = {"env": "prod"}
    mock_disk.time_created = MagicMock()
    mock_disk.time_created.isoformat.return_value = "2024-01-01T00:00:00Z"
    
    mock_attached_disk = MagicMock()
    mock_attached_disk.disk_state = "Attached"
    
    class AsyncIter:
        def __init__(self, items):
            self.items = items
        def __aiter__(self):
            return self
        async def __anext__(self):
            if not self.items:
                raise StopAsyncIteration
            return self.items.pop(0)

    # Mock client
    mock_client = MagicMock()
    mock_client.disks.list.return_value = AsyncIter([mock_disk, mock_attached_disk])
    
    results = await plugin.scan(mock_client)
    
    assert len(results) == 1
    assert results[0]["name"] == "my-disk"
    assert results[0]["sku"] == "Premium_LRS"
    # 100 GB * 0.15 = 15.0
    assert results[0]["monthly_waste"] == 15.0

@pytest.mark.asyncio
async def test_azure_unattached_disks_region_filter(plugin):
    mock_disk_east = MagicMock()
    mock_disk_east.location = "eastus"
    mock_disk_east.disk_state = "Unattached"
    mock_disk_east.disk_size_gb = 10
    mock_disk_east.sku.name = "Standard_LRS"
    mock_disk_east.time_created = None
    
    mock_disk_west = MagicMock()
    mock_disk_west.location = "westus"
    mock_disk_west.disk_state = "Unattached"
    mock_disk_west.disk_size_gb = 10
    mock_disk_west.sku.name = "Standard_LRS"
    mock_disk_west.time_created = None
    
    class AsyncIter:
        def __init__(self, items):
            self.items = items
        def __aiter__(self):
            return self
        async def __anext__(self):
            if not self.items:
                raise StopAsyncIteration
            return self.items.pop(0)

    mock_client = MagicMock()
    mock_client.disks.list.return_value = AsyncIter([mock_disk_east, mock_disk_west])
    
    results = await plugin.scan(mock_client, region="eastus")
    
    assert len(results) == 1
    assert results[0]["region"] == "eastus"
