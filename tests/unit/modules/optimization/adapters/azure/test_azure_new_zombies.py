
import pytest
from unittest.mock import MagicMock, patch
from app.modules.optimization.adapters.azure.plugins.compute import StoppedVmsPlugin

@pytest.mark.asyncio
async def test_azure_stopped_vms_plugin():
    plugin = StoppedVmsPlugin()
    assert plugin.category_key == "stopped_azure_vms"

    # Mock Credentials
    mock_creds = MagicMock()

    # Mock Compute Client
    mock_client = MagicMock()
    
    # Mock VM 1: Running (Should be ignored)
    vm_running = MagicMock()
    vm_running.name = "vm-running"
    vm_running.instance_view.statuses = [
        MagicMock(code="PowerState/running")
    ]
    
    # Mock VM 2: Stopped (Should be detected)
    vm_stopped = MagicMock()
    vm_stopped.id = "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Compute/virtualMachines/vm-stopped"
    vm_stopped.name = "vm-stopped"
    vm_stopped.location = "eastus"
    vm_stopped.instance_view.statuses = [
        MagicMock(code="PowerState/deallocated")
    ]
    # Storage Profile for cost calc
    vm_stopped.storage_profile.os_disk.disk_size_gb = 100

    # Mock List All
    async def list_all_iterator(*args, **kwargs):
        for vm in [vm_running, vm_stopped]:
            yield vm

    mock_client.virtual_machines.list_all.return_value = list_all_iterator()

    # Mock Client Constructor to return our mock
    # The plugin instantiates ComputeManagementClient(credentials, subscription_id)
    with patch("app.modules.optimization.adapters.azure.plugins.compute.ComputeManagementClient", return_value=mock_client):
        zombies = await plugin.scan(
            session="sub-1", # Acts as subscription_id fallback
            credentials=mock_creds,
            subscription_id="sub-1"
        )

    assert len(zombies) == 1
    zombie = zombies[0]
    assert zombie["resource_name"] == "vm-stopped"
    assert zombie["status"] == "PowerState/deallocated"
    # Cost: 100GB * $0.05 = $5.00
    assert zombie["monthly_cost"] == 5.00
