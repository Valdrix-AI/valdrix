import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from types import SimpleNamespace

# Import the adapter directly to avoid the domain/app dependency chain
from app.modules.optimization.adapters.azure.plugins.idle_vms import AzureIdleVMPlugin

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
    
    # Inject PricingService mock at class level for this test
    with patch("app.modules.reporting.domain.pricing.service.PricingService.estimate_monthly_waste", return_value=1200.0):
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
    
    # Inject PricingService mock
    with patch("app.modules.reporting.domain.pricing.service.PricingService.estimate_monthly_waste", return_value=150.0):
        zombies = await plugin.scan(client, monitor_client=monitor_client)
    
    assert len(zombies) == 1
    assert zombies[0]["owner"] == "admin@example.com"


@pytest.mark.asyncio
async def test_azure_idle_vm_plugin_skips_high_cpu():
    plugin = AzureIdleVMPlugin()
    client = MagicMock()
    monitor_client = MagicMock()

    mock_vm = MagicMock()
    mock_vm.id = "/resource/id"
    mock_vm.name = "busy-vm"
    mock_vm.location = "eastus"
    mock_vm.hardware_profile.vm_size = "Standard_D2s_v3"
    mock_vm.tags = {}
    mock_vm.provisioning_state = "Succeeded"
    mock_vm.vm_id = "uuid-456"

    async def mock_list():
        yield mock_vm

    client.virtual_machines.list_all = mock_list

    metric = SimpleNamespace(timeseries=[SimpleNamespace(data=[SimpleNamespace(average=10.0)])])
    metrics = SimpleNamespace(value=[metric])
    monitor_client.metrics.list = AsyncMock(return_value=metrics)

    zombies = await plugin.scan(client, monitor_client=monitor_client)
    assert zombies == []


@pytest.mark.asyncio
async def test_azure_idle_vm_metrics_failure_falls_back():
    plugin = AzureIdleVMPlugin()
    client = MagicMock()
    monitor_client = MagicMock()

    mock_vm = MagicMock()
    mock_vm.id = "/resource/id"
    mock_vm.name = "idle-vm"
    mock_vm.location = "eastus"
    mock_vm.hardware_profile.vm_size = "Standard_D2s_v3"
    mock_vm.tags = {}
    mock_vm.provisioning_state = "Succeeded"
    mock_vm.vm_id = "uuid-789"

    async def mock_list():
        yield mock_vm

    client.virtual_machines.list_all = mock_list
    monitor_client.metrics.list = AsyncMock(side_effect=RuntimeError("metrics down"))

    with patch("app.modules.reporting.domain.pricing.service.PricingService.estimate_monthly_waste", return_value=100.0), \
         patch.object(plugin, "_get_attribution", AsyncMock(return_value="owner@test.io")):
        zombies = await plugin.scan(client, monitor_client=monitor_client)

    assert len(zombies) == 1
    assert zombies[0]["owner"] == "owner@test.io"


@pytest.mark.asyncio
async def test_azure_idle_vm_region_filter_excludes():
    plugin = AzureIdleVMPlugin()
    client = MagicMock()

    mock_vm = MagicMock()
    mock_vm.id = "/resource/id"
    mock_vm.name = "idle-vm"
    mock_vm.location = "eastus"
    mock_vm.hardware_profile.vm_size = "Standard_D2s_v3"
    mock_vm.tags = {}

    async def mock_list():
        yield mock_vm

    client.virtual_machines.list_all = mock_list
    zombies = await plugin.scan(client, region="westus")
    assert zombies == []


@pytest.mark.asyncio
async def test_azure_idle_vm_scan_exception_returns_empty():
    plugin = AzureIdleVMPlugin()
    client = MagicMock()

    async def mock_list():
        if False:
            yield None
        raise RuntimeError("boom")

    client.virtual_machines.list_all = mock_list
    zombies = await plugin.scan(client)
    assert zombies == []


@pytest.mark.asyncio
async def test_azure_idle_vm_attribution_failure():
    plugin = AzureIdleVMPlugin()
    monitor_client = MagicMock()

    async def mock_activity_list(**kwargs):
        if False:
            yield None
        raise RuntimeError("audit down")

    monitor_client.activity_logs.list = mock_activity_list
    owner = await plugin._get_attribution(monitor_client, "/resource/id")
    assert owner == "attribution_failed"
