import pytest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.modules.optimization.adapters.azure.plugins.storage import OldSnapshotsPlugin as AzureOldSnapshotsPlugin
from app.modules.optimization.adapters.gcp.plugins.network import OrphanExternalIpsPlugin
from app.modules.optimization.adapters.gcp.plugins.storage import OldSnapshotsPlugin as GCPOldSnapshotsPlugin
from app.modules.optimization.domain.azure_provider.detector import AzureZombieDetector
from app.modules.optimization.domain.gcp_provider.detector import GCPZombieDetector


@pytest.mark.asyncio
async def test_azure_old_snapshots_plugin_scan_detects_old_snapshots():
    plugin = AzureOldSnapshotsPlugin()
    old_snapshot = SimpleNamespace(
        id="/subscriptions/sub-123/resourceGroups/rg/providers/Microsoft.Compute/snapshots/snap-1",
        name="snap-1",
        location="eastus",
        disk_size_gb=60,
        creation_timestamp=None,
        time_created=datetime.now(timezone.utc) - timedelta(days=120),
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
        snapshots=SimpleNamespace(list=lambda: AsyncIter([old_snapshot]))
    )

    with patch(
        "app.modules.optimization.adapters.azure.plugins.storage.ComputeManagementClient",
        return_value=client,
    ):
        results = await plugin.scan("sub-123", credentials=object(), age_days=90)

    assert len(results) == 1
    assert results[0]["resource_name"] == "snap-1"
    assert results[0]["monthly_cost"] == round(60 * 0.05, 2)


@pytest.mark.asyncio
async def test_gcp_orphan_ips_plugin_scan_uses_billing_records():
    plugin = OrphanExternalIpsPlugin()
    expected = [{"resource_id": "ip-1", "monthly_cost": 7.2}]

    with patch("app.shared.analysis.gcp_usage_analyzer.GCPUsageAnalyzer") as analyzer_cls:
        analyzer = analyzer_cls.return_value
        analyzer.find_orphan_ips.return_value = expected

        results = await plugin.scan(
            "proj-123",
            credentials=object(),
            billing_records=[{"resource_id": "projects/proj-123/regions/us-central1/addresses/ip-1"}],
        )

    assert results == expected
    analyzer.find_orphan_ips.assert_called_once_with()


@pytest.mark.asyncio
async def test_gcp_old_snapshots_plugin_scan_detects_old_snapshots():
    plugin = GCPOldSnapshotsPlugin()
    old_snapshot = SimpleNamespace(
        name="snap-1",
        disk_size_gb=80,
        creation_timestamp=(datetime.now(timezone.utc) - timedelta(days=120)).isoformat().replace("+00:00", "Z"),
    )
    client = SimpleNamespace(
        list=lambda request: [old_snapshot]
    )

    with patch(
        "app.modules.optimization.adapters.gcp.plugins.storage.compute_v1.SnapshotsClient",
        return_value=client,
    ):
        results = await plugin.scan("proj-123", credentials=object(), age_days=90)

    assert len(results) == 1
    assert results[0]["resource_name"] == "snap-1"
    assert results[0]["monthly_cost"] == round(80 * 0.026, 2)


@pytest.mark.asyncio
async def test_azure_detector_lifecycle():
    creds = {
        "tenant_id": "test-tenant",
        "client_id": "test-client",
        "client_secret": "test-secret",
        "subscription_id": "test-sub",
    }

    mock_creds = MagicMock()
    with patch("azure.identity.aio.ClientSecretCredential", return_value=mock_creds), \
         patch("azure.mgmt.compute.aio.ComputeManagementClient"), \
         patch("azure.mgmt.network.aio.NetworkManagementClient"):

        async with AzureZombieDetector(region="eastus", credentials=creds) as detector:
            assert detector.subscription_id == "test-sub"
            assert detector._credential is not None


@pytest.mark.asyncio
async def test_gcp_detector_initialization():
    detector = GCPZombieDetector(region="us-central1-a", credentials={"project_id": "test-proj"})

    assert detector.project_id == "test-proj"
    assert detector._address_client is None
    assert detector._images_client is None
