import pytest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace, ModuleType
from contextlib import contextmanager

from app.modules.optimization.adapters.gcp.plugins.idle_instances import GCPIdleInstancePlugin


@contextmanager
def _patch_monitoring_v3():
    module = ModuleType("google.cloud.monitoring_v3")

    class DummyInterval:
        def __init__(self, start_time, end_time):
            self.start_time = start_time
            self.end_time = end_time

    class DummyListTimeSeriesRequest:
        class TimeSeriesView:
            FULL = "FULL"

    module.TimeInterval = DummyInterval
    module.ListTimeSeriesRequest = DummyListTimeSeriesRequest

    with patch.dict("sys.modules", {"google.cloud.monitoring_v3": module}):
        yield


@pytest.mark.asyncio
async def test_gcp_idle_instances_aggregated_list_with_attribution():
    plugin = GCPIdleInstancePlugin()
    client = MagicMock()

    inst = SimpleNamespace(
        id=123,
        name="vm-1",
        status="RUNNING",
        machine_type="zones/us-central1-a/machineTypes/n1-standard-1",
        guest_accelerators=[],
        labels={"env": "prod"},
        cpu_platform="Intel",
        creation_timestamp="2024-01-01T00:00:00Z",
    )
    response = SimpleNamespace(instances=[inst])
    client.aggregated_list.return_value = [("zones/us-central1-a", response)]

    logging_client = MagicMock()
    entry = SimpleNamespace(payload={"authenticationInfo": {"principalEmail": "owner@test.io"}})
    logging_client.list_entries.return_value = [entry]

    with _patch_monitoring_v3(), \
         patch("app.modules.reporting.domain.pricing.service.PricingService.estimate_monthly_waste", return_value=200.0):
        zombies = await plugin.scan(client, project_id="proj-1", logging_client=logging_client)

    assert len(zombies) == 1
    assert zombies[0]["owner"] == "owner@test.io"
    assert zombies[0]["monthly_waste"] == 200.0


@pytest.mark.asyncio
async def test_gcp_idle_instances_skips_high_cpu():
    plugin = GCPIdleInstancePlugin()
    client = MagicMock()

    inst = SimpleNamespace(
        id=456,
        name="busy-vm",
        status="RUNNING",
        machine_type="zones/us-central1-a/machineTypes/n1-standard-1",
        guest_accelerators=[],
        labels={},
        cpu_platform="Intel",
        creation_timestamp="2024-01-01T00:00:00Z",
    )
    response = SimpleNamespace(instances=[inst])
    client.aggregated_list.return_value = [("zones/us-central1-a", response)]

    point = SimpleNamespace(value=SimpleNamespace(double_value=0.2))
    series = SimpleNamespace(points=[point])
    monitoring_client = MagicMock()
    monitoring_client.list_time_series.return_value = [series]

    with _patch_monitoring_v3():
        zombies = await plugin.scan(client, project_id="proj-1", monitoring_client=monitoring_client)
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
