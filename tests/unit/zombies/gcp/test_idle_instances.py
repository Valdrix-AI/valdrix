import pytest
from types import SimpleNamespace
from unittest.mock import patch

from app.modules.optimization.adapters.gcp.plugins.compute import IdleVmsPlugin


@pytest.mark.asyncio
async def test_gcp_idle_instances_scan_uses_billing_records():
    plugin = IdleVmsPlugin()
    expected = [{"resource_id": "vm-1", "monthly_cost": 55.0}]

    with patch(
        "app.shared.analysis.gcp_usage_analyzer.GCPUsageAnalyzer"
    ) as analyzer_cls:
        analyzer = analyzer_cls.return_value
        analyzer.find_idle_vms.return_value = expected

        zombies = await plugin.scan(
            "proj-123",
            credentials=object(),
            billing_records=[{"resource_id": "projects/proj-123/instances/vm-1"}],
        )

    assert zombies == expected
    analyzer.find_idle_vms.assert_called_once_with(days=7)


@pytest.mark.asyncio
async def test_gcp_idle_instances_fallback_detects_running_gpu_vm():
    plugin = IdleVmsPlugin()

    instance = SimpleNamespace(
        name="gpu-vm",
        status="RUNNING",
        guest_accelerators=[{"type": "nvidia"}],
        machine_type="zones/us-central1-a/machineTypes/a2-highgpu-1g",
    )
    response = SimpleNamespace(instances=[instance])

    client = SimpleNamespace(
        aggregated_list=lambda request: [("zones/us-central1-a", response)]
    )

    with patch(
        "app.modules.optimization.adapters.gcp.plugins.compute.compute_v1.InstancesClient",
        return_value=client,
    ):
        zombies = await plugin.scan("proj-123", credentials=object())

    assert len(zombies) == 1
    assert zombies[0]["resource_name"] == "gpu-vm"
    assert zombies[0]["resource_type"] == "Compute Engine VM (GPU)"


@pytest.mark.asyncio
async def test_gcp_idle_instances_fallback_failure_returns_empty():
    plugin = IdleVmsPlugin()

    with patch(
        "app.modules.optimization.adapters.gcp.plugins.compute.compute_v1.InstancesClient",
        side_effect=RuntimeError("gcp down"),
    ):
        zombies = await plugin.scan("proj-123", credentials=object())

    assert zombies == []
