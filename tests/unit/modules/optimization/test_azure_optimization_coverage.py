import pytest
import os
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from app.modules.optimization.adapters.azure.plugins.unattached_disks import AzureUnattachedDisksPlugin
from app.modules.optimization.adapters.azure.plugins.orphaned_ips import AzureOrphanedIpsPlugin

@pytest.mark.asyncio
async def test_azure_unattached_disks_scan():
    """Test Azure unattached disks detection."""
    plugin = AzureUnattachedDisksPlugin()
    mock_client = MagicMock()
    
    mock_disk = MagicMock()
    mock_disk.id = "/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.Compute/disks/disk1"
    mock_disk.name = "disk1"
    mock_disk.location = "eastus"
    mock_disk.disk_state = "Unattached"
    mock_disk.disk_size_gb = 128
    mock_disk.sku.name = "Premium_LRS"
    mock_disk.tags = {"env": "prod"}
    mock_disk.time_created = datetime.now(timezone.utc)
    
    async def async_iterator():
        yield mock_disk
        
    mock_client.disks.list.return_value = async_iterator()
    
    # 1. Basic scan (no monitor client)
    zombies = await plugin.scan(mock_client, region="eastus")
    assert len(zombies) == 1
    assert zombies[0]["resource_id"] == mock_disk.id
    assert zombies[0]["monthly_cost"] == 128 * 0.15

    # 2. Region filtering
    zombies = await plugin.scan(mock_client, region="westus")
    assert len(zombies) == 0

@pytest.mark.asyncio
async def test_azure_unattached_disks_scan_with_metrics():
    """Test Azure unattached disks with CloudWatch (Monitor) metrics."""
    plugin = AzureUnattachedDisksPlugin()
    mock_client = MagicMock()
    mock_monitor = AsyncMock()
    
    mock_disk = MagicMock()
    mock_disk.id = "disk-1"
    mock_disk.location = "eastus"
    mock_disk.disk_state = "Unattached"
    
    async def async_iterator():
        yield mock_disk
    mock_client.disks.list.return_value = async_iterator()
    
    # Mock monitor metrics (Total > 0 means active)
    mock_metric = MagicMock()
    mock_timeseries = MagicMock()
    mock_data = MagicMock()
    mock_data.total = 100 # Active
    mock_timeseries.data = [mock_data]
    mock_metric.timeseries = [mock_timeseries]
    
    mock_metrics_response = MagicMock()
    mock_metrics_response.value = [mock_metric]
    mock_monitor.metrics.list.return_value = mock_metrics_response
    
    zombies = await plugin.scan(mock_client, region="eastus", monitor_client=mock_monitor)
    assert len(zombies) == 0 # Skipped because it's active

@pytest.mark.asyncio
async def test_azure_orphaned_ips_scan():
    """Test Azure orphaned public IPs detection."""
    plugin = AzureOrphanedIpsPlugin()
    mock_client = MagicMock()
    
    mock_ip = MagicMock()
    mock_ip.id = "/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.Network/publicIPAddresses/ip1"
    mock_ip.name = "ip1"
    mock_ip.location = "eastus"
    mock_ip.ip_address = "40.114.1.1"
    mock_ip.ip_configuration = None
    mock_ip.sku.name = "Standard"
    mock_ip.tags = {}
    
    async def async_iterator():
        yield mock_ip
        
    mock_client.public_ip_addresses.list_all.return_value = async_iterator()
    
    zombies = await plugin.scan(mock_client, region="eastus")
    assert len(zombies) == 1
    assert zombies[0]["resource_id"] == mock_ip.id
    assert zombies[0]["monthly_waste"] == 3.65

    # Error handling
    mock_client.public_ip_addresses.list_all.side_effect = Exception("API Error")
    zombies = await plugin.scan(mock_client, region="eastus")
    assert len(zombies) == 0
