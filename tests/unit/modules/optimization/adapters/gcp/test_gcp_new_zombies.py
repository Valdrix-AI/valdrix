
import pytest
from unittest.mock import MagicMock, patch
from app.modules.optimization.adapters.gcp.plugins.compute import StoppedVmsPlugin

@pytest.mark.asyncio
async def test_gcp_stopped_vms_plugin():
    plugin = StoppedVmsPlugin()
    assert plugin.category_key == "stopped_gcp_instances"

    # Mock Credentials
    mock_creds = MagicMock()

    # Mock Instances Client
    mock_client = MagicMock()

    # Mock Instance 1: RUNNING (Ignored)
    inst_running = MagicMock()
    inst_running.status = "RUNNING"
    inst_running.name = "inst-running"

    # Mock Instance 2: TERMINATED (Detected)
    inst_stopped = MagicMock()
    inst_stopped.status = "TERMINATED"
    inst_stopped.name = "inst-stopped"
    # Disks
    disk1 = MagicMock()
    disk1.disk_size_gb = 50
    inst_stopped.disks = [disk1]

    # Mock Aggregated List
    # Returns an iterable of (zone, response) tuples
    mock_response = MagicMock()
    mock_response.instances = [inst_running, inst_stopped]
    
    mock_client.aggregated_list.return_value = [
        ("zones/us-central1-a", mock_response)
    ]

    # Patch the client class
    with patch("app.modules.optimization.adapters.gcp.plugins.compute.compute_v1.InstancesClient", return_value=mock_client):
        zombies = await plugin.scan(
            project_id="proj-1",
            credentials=mock_creds
        )

    assert len(zombies) == 1
    zombie = zombies[0]
    assert zombie["resource_name"] == "inst-stopped"
    assert zombie["status"] == "TERMINATED"
    assert "us-central1-a" in zombie["zone"]
    # Cost: 50GB * $0.04 = $2.00
    assert zombie["monthly_cost"] == 2.00
