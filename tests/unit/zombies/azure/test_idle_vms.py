import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Mock engine before any app imports to avoid ConnectionRefusedError
with patch("sqlalchemy.ext.asyncio.create_async_engine"):
    with patch("app.db.session.engine"):
        from app.services.zombies.azure_provider.plugins.idle_vms import AzureIdleVMPlugin

from decimal import Decimal

@pytest.mark.asyncio
async def test_azure_idle_vm_plugin_gpu_detection():
    plugin = AzureIdleVMPlugin()
    client = MagicMock()
    
    # Mock VM list
    mock_vm = MagicMock()
    mock_vm.id = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/gpu-vm"
    mock_vm.name = "gpu-vm"
    mock_vm.location = "eastus"
    mock_vm.hardware_profile.vm_size = "Standard_NC6"
    mock_vm.tags = {"env": "prod"}
    mock_vm.provisioning_state = "Succeeded"
    mock_vm.vm_id = "uuid-123"
    
    # client.virtual_machines.list_all() is an async iterator
    async def mock_list():
        yield mock_vm
    
    client.virtual_machines.list_all = mock_list
    
    zombies = await plugin.scan(client, region="eastus")
    
    assert len(zombies) == 1
    assert zombies[0]["name"] == "gpu-vm"
    assert zombies[0]["is_gpu"] is True
    assert zombies[0]["confidence_score"] == 0.95
    assert zombies[0]["monthly_waste"] == 1200.0

@pytest.mark.asyncio
async def test_azure_idle_vm_plugin_attribution():
    plugin = AzureIdleVMPlugin()
    client = MagicMock()
    monitor_client = MagicMock()
    
    mock_vm = MagicMock()
    mock_vm.id = "/resource/id"
    mock_vm.name = "test-vm"
    mock_vm.location = "eastus"
    mock_vm.hardware_profile.vm_size = "Standard_D2s_v3"
    mock_vm.tags = {}
    
    async def mock_list():
        yield mock_vm
    client.virtual_machines.list_all = mock_list
    
    # Mock Activity Logs
    mock_event = MagicMock()
    mock_event.caller = "admin@example.com"
    
    async def mock_activity_list(**kwargs):
        yield mock_event
    
    monitor_client.activity_logs.list = mock_activity_list
    
    zombies = await plugin.scan(client, monitor_client=monitor_client)
    
    assert len(zombies) == 1
    assert zombies[0]["owner"] == "admin@example.com"
