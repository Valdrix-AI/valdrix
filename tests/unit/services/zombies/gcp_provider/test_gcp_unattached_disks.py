import pytest
from unittest.mock import MagicMock
from app.services.zombies.gcp_provider.plugins.unattached_disks import GCPUnattachedDisksPlugin

@pytest.fixture
def plugin():
    return GCPUnattachedDisksPlugin()

@pytest.mark.asyncio
async def test_gcp_unattached_disks_scan(plugin):
    # Mock GCP Disk object
    mock_disk = MagicMock()
    mock_disk.id = "123"
    mock_disk.name = "my-disk"
    mock_disk.users = [] # Unattached
    mock_disk.size_gb = 50
    mock_disk.type_ = "projects/my-proj/zones/us-central1-a/diskTypes/pd-ssd"
    mock_disk.labels = {"team": "dev"}
    mock_disk.creation_timestamp = "2024-01-01T00:00:00Z"
    
    mock_used_disk = MagicMock()
    mock_used_disk.users = ["instance-1"]
    
    mock_client = MagicMock()
    mock_client.list.return_value = [mock_disk, mock_used_disk]
    
    results = await plugin.scan(mock_client, project_id="my-proj", zone="us-central1-a")
    
    assert len(results) == 1
    assert results[0]["name"] == "my-disk"
    assert results[0]["type"] == "pd-ssd"
    # 50 GB * 0.17 = 8.5
    assert results[0]["monthly_waste"] == 8.5
