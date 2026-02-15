import pytest
from types import SimpleNamespace
from unittest.mock import patch

from app.modules.optimization.adapters.azure.plugins.compute import IdleVmsPlugin


@pytest.mark.asyncio
async def test_azure_idle_vms_scan_uses_cost_records():
    plugin = IdleVmsPlugin()
    expected = [{"resource_id": "vm-1", "monthly_cost": 100.0}]

    with patch(
        "app.shared.analysis.azure_usage_analyzer.AzureUsageAnalyzer"
    ) as analyzer_cls:
        analyzer = analyzer_cls.return_value
        analyzer.find_idle_vms.return_value = expected

        zombies = await plugin.scan(
            "sub-123",
            credentials=object(),
            cost_records=[
                {"ResourceId": "/subscriptions/sub-123/virtualMachines/vm-1"}
            ],
        )

    assert zombies == expected
    analyzer.find_idle_vms.assert_called_once_with(days=7)


@pytest.mark.asyncio
async def test_azure_idle_vms_fallback_detects_running_gpu_vm():
    plugin = IdleVmsPlugin()

    vm = SimpleNamespace(
        id="/subscriptions/sub-123/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/gpu-vm",
        name="gpu-vm",
        location="eastus",
        hardware_profile=SimpleNamespace(vm_size="Standard_NC6"),
        instance_view=SimpleNamespace(
            statuses=[SimpleNamespace(code="PowerState/running")]
        ),
    )

    class AsyncIter:
        def __init__(self, items):
            self.items = list(items)

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self.items:
                raise StopAsyncIteration
            return self.items.pop(0)

    client = SimpleNamespace(
        virtual_machines=SimpleNamespace(list_all=lambda: AsyncIter([vm]))
    )

    with patch(
        "app.modules.optimization.adapters.azure.plugins.compute.ComputeManagementClient",
        return_value=client,
    ):
        zombies = await plugin.scan("sub-123", credentials=object())

    assert len(zombies) == 1
    assert zombies[0]["resource_name"] == "gpu-vm"
    assert zombies[0]["resource_type"] == "Virtual Machine (GPU)"


@pytest.mark.asyncio
async def test_azure_idle_vms_fallback_failure_returns_empty():
    plugin = IdleVmsPlugin()

    with patch(
        "app.modules.optimization.adapters.azure.plugins.compute.ComputeManagementClient",
        side_effect=RuntimeError("azure down"),
    ):
        zombies = await plugin.scan("sub-123", credentials=object())

    assert zombies == []
