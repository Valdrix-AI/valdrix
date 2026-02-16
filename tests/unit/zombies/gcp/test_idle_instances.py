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


@pytest.mark.asyncio
async def test_gcp_idle_instances_metrics_failure_falls_back():
    plugin = GCPIdleInstancePlugin()
    client = MagicMock()

    inst = SimpleNamespace(
        id=789,
        name="idle-vm",
        status="RUNNING",
        machine_type="zones/us-central1-a/machineTypes/n1-standard-1",
        guest_accelerators=[],
        labels={},
        cpu_platform="Intel",
        creation_timestamp="2024-01-01T00:00:00Z",
    )
    response = SimpleNamespace(instances=[inst])
    client.aggregated_list.return_value = [("zones/us-central1-a", response)]

    monitoring_client = MagicMock()
    monitoring_client.list_time_series.side_effect = RuntimeError("metrics down")

    with _patch_monitoring_v3(), \
         patch("app.modules.reporting.domain.pricing.service.PricingService.estimate_monthly_waste", return_value=75.0):
        zombies = await plugin.scan(client, project_id="proj-1", monitoring_client=monitoring_client)

    assert len(zombies) == 1
    assert zombies[0]["monthly_waste"] == 75.0


@pytest.mark.asyncio
async def test_gcp_idle_instances_scan_exception_returns_empty():
    plugin = GCPIdleInstancePlugin()
    client = MagicMock()
    client.aggregated_list.side_effect = RuntimeError("boom")

    with _patch_monitoring_v3():
        zombies = await plugin.scan(client, project_id="proj-1")
    assert zombies == []


@pytest.mark.asyncio
async def test_gcp_idle_instances_attribution_failure():
    plugin = GCPIdleInstancePlugin()
    logging_client = MagicMock()
    logging_client.list_entries.side_effect = RuntimeError("audit down")

    owner = await plugin._get_attribution(logging_client, instance_id=1, zone="us-central1-a")
    assert owner == "attribution_failed"
