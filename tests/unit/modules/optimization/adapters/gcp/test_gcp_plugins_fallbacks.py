import pytest
import sys
import types
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.modules.optimization.adapters.gcp.plugins.containers import (
    EmptyGkeClusterPlugin,
    IdleCloudRunPlugin,
)
from app.modules.optimization.adapters.gcp.plugins.database import IdleCloudSqlPlugin
from app.modules.optimization.adapters.gcp.plugins.network import (
    OrphanExternalIpsPlugin,
)
from app.modules.optimization.adapters.gcp.plugins.storage import (
    UnattachedDisksPlugin,
    OldSnapshotsPlugin,
)


def _register_gcp_module(monkeypatch, module_name, **attrs):
    module = types.ModuleType(module_name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, module_name, module)
    return module


@pytest.mark.asyncio
async def test_gcp_container_plugins_billing_records():
    with patch(
        "app.shared.analysis.gcp_usage_analyzer.GCPUsageAnalyzer"
    ) as mock_analyzer:
        mock_analyzer.return_value.find_empty_gke_clusters.return_value = [
            {"resource_id": "gke-1"}
        ]
        zombies = await EmptyGkeClusterPlugin().scan(
            "proj-1", "us-central1", billing_records=[{"x": 1}]
        )
        assert zombies[0]["resource_id"] == "gke-1"

        mock_analyzer.return_value.find_idle_cloud_run.return_value = [
            {"resource_id": "run-1"}
        ]
        zombies = await IdleCloudRunPlugin().scan(
            "proj-1", "us-central1", billing_records=[{"x": 1}]
        )
        assert zombies[0]["resource_id"] == "run-1"


@pytest.mark.asyncio
async def test_gcp_cloud_sql_billing_records():
    plugin = IdleCloudSqlPlugin()
    with patch(
        "app.shared.analysis.gcp_usage_analyzer.GCPUsageAnalyzer"
    ) as mock_analyzer:
        mock_analyzer.return_value.find_idle_cloud_sql.return_value = [
            {"resource_id": "sql-1"}
        ]
        zombies = await plugin.scan("proj-1", "us-central1", billing_records=[{"x": 1}])
        assert zombies[0]["resource_id"] == "sql-1"


@pytest.mark.asyncio
async def test_gcp_gke_fallback(monkeypatch):
    plugin = EmptyGkeClusterPlugin()

    empty_cluster = SimpleNamespace(
        self_link="clusters/empty",
        name="empty",
        location="us-central1",
        node_pools=None,
    )
    active_cluster = SimpleNamespace(
        self_link="clusters/active",
        name="active",
        location="us-central1",
        node_pools=[SimpleNamespace(initial_node_count=3)],
    )
    response = SimpleNamespace(clusters=[empty_cluster, active_cluster])
    client = MagicMock()
    client.list_clusters.return_value = response

    container_mod = _register_gcp_module(
        monkeypatch,
        "google.cloud.container_v1",
        ClusterManagerClient=lambda credentials=None: client,
    )
    cloud_mod = _register_gcp_module(monkeypatch, "google.cloud")
    cloud_mod.container_v1 = container_mod

    google_mod = sys.modules.get("google") or _register_gcp_module(
        monkeypatch, "google"
    )
    setattr(google_mod, "cloud", cloud_mod)

    zombies = await plugin.scan("proj-1", "us-central1", credentials=MagicMock())
    assert len(zombies) == 1
    assert zombies[0]["resource_name"] == "empty"


@pytest.mark.asyncio
async def test_gcp_cloud_sql_fallback(monkeypatch):
    plugin = IdleCloudSqlPlugin()

    instance = SimpleNamespace(
        name="sql-1",
        state="RUNNABLE",
        settings=SimpleNamespace(tier="db-f1-micro"),
        database_version="POSTGRES_15",
    )
    response = SimpleNamespace(items=[instance])
    client = MagicMock()
    client.list.return_value = response

    sql_mod = _register_gcp_module(
        monkeypatch,
        "google.cloud.sqladmin_v1",
        SqlInstancesServiceClient=lambda credentials=None: client,
        SqlInstancesListRequest=lambda project: SimpleNamespace(project=project),
    )
    cloud_mod = _register_gcp_module(monkeypatch, "google.cloud")
    cloud_mod.sqladmin_v1 = sql_mod

    google_mod = sys.modules.get("google") or _register_gcp_module(
        monkeypatch, "google"
    )
    setattr(google_mod, "cloud", cloud_mod)

    zombies = await plugin.scan("proj-1", "us-central1", credentials=MagicMock())
    assert len(zombies) == 1
    assert zombies[0]["resource_id"] == "projects/proj-1/instances/sql-1"


@pytest.mark.asyncio
async def test_gcp_orphan_ips_fallback():
    plugin = OrphanExternalIpsPlugin()

    address = SimpleNamespace(
        name="ip-1",
        status="RESERVED",
        address="35.1.2.3",
    )
    response = SimpleNamespace(addresses=[address])
    client = MagicMock()
    client.aggregated_list.return_value = [("regions/us-central1", response)]

    with (
        patch(
            "app.modules.optimization.adapters.gcp.plugins.network.compute_v1.AddressesClient",
            return_value=client,
        ),
        patch(
            "app.modules.optimization.adapters.gcp.plugins.network.compute_v1.AggregatedListAddressesRequest",
            return_value=MagicMock(),
        ),
    ):
        zombies = await plugin.scan("proj-1", "us-central1", credentials=MagicMock())
        assert len(zombies) == 1
        assert zombies[0]["resource_name"] == "ip-1"


@pytest.mark.asyncio
async def test_gcp_storage_fallbacks():
    disk = SimpleNamespace(
        name="disk-1",
        users=[],
        size_gb=10,
        type_="https://.../pd-standard",
    )
    disk_response = SimpleNamespace(disks=[disk])

    snapshot_time = datetime.now(timezone.utc) - timedelta(days=120)
    snapshot = SimpleNamespace(
        name="snap-1",
        creation_timestamp=snapshot_time.isoformat().replace("+00:00", "Z"),
        disk_size_gb=5,
    )

    disks_client = MagicMock()
    disks_client.aggregated_list.return_value = [("zones/us-central1-a", disk_response)]

    snapshots_client = MagicMock()
    snapshots_client.list.return_value = [snapshot]

    with (
        patch(
            "app.modules.optimization.adapters.gcp.plugins.storage.compute_v1.DisksClient",
            return_value=disks_client,
        ),
        patch(
            "app.modules.optimization.adapters.gcp.plugins.storage.compute_v1.SnapshotsClient",
            return_value=snapshots_client,
        ),
        patch(
            "app.modules.optimization.adapters.gcp.plugins.storage.compute_v1.AggregatedListDisksRequest",
            return_value=MagicMock(),
        ),
        patch(
            "app.modules.optimization.adapters.gcp.plugins.storage.compute_v1.ListSnapshotsRequest",
            return_value=MagicMock(),
        ),
    ):
        zombies = await UnattachedDisksPlugin().scan(
            "proj-1", "us-central1", credentials=MagicMock()
        )
        assert len(zombies) == 1
        assert zombies[0]["resource_name"] == "disk-1"

        zombies = await OldSnapshotsPlugin().scan(
            "proj-1", "us-central1", credentials=MagicMock()
        )
        assert len(zombies) == 1
        assert zombies[0]["resource_name"] == "snap-1"


@pytest.mark.asyncio
async def test_gcp_fallbacks_handle_errors(monkeypatch):
    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    # GKE fallback error
    container_mod = _register_gcp_module(
        monkeypatch,
        "google.cloud.container_v1",
        ClusterManagerClient=_raise,
    )
    cloud_mod = _register_gcp_module(monkeypatch, "google.cloud")
    cloud_mod.container_v1 = container_mod
    google_mod = sys.modules.get("google") or _register_gcp_module(
        monkeypatch, "google"
    )
    setattr(google_mod, "cloud", cloud_mod)

    with patch(
        "app.modules.optimization.adapters.gcp.plugins.containers.logger"
    ) as mock_logger:
        zombies = await EmptyGkeClusterPlugin().scan(
            "proj-1", "us-central1", credentials=MagicMock()
        )
        assert zombies == []
        mock_logger.warning.assert_called_once()

    # Cloud SQL fallback error
    sql_mod = _register_gcp_module(
        monkeypatch,
        "google.cloud.sqladmin_v1",
        SqlInstancesServiceClient=_raise,
        SqlInstancesListRequest=lambda project: SimpleNamespace(project=project),
    )
    cloud_mod.sqladmin_v1 = sql_mod
    setattr(google_mod, "cloud", cloud_mod)

    with patch(
        "app.modules.optimization.adapters.gcp.plugins.database.logger"
    ) as mock_logger:
        zombies = await IdleCloudSqlPlugin().scan(
            "proj-1", "us-central1", credentials=MagicMock()
        )
        assert zombies == []
        mock_logger.warning.assert_called_once()

    # Orphan IPs fallback error
    with (
        patch(
            "app.modules.optimization.adapters.gcp.plugins.network.compute_v1.AddressesClient",
            side_effect=RuntimeError("boom"),
        ),
        patch(
            "app.modules.optimization.adapters.gcp.plugins.network.compute_v1.AggregatedListAddressesRequest",
            return_value=MagicMock(),
        ),
        patch(
            "app.modules.optimization.adapters.gcp.plugins.network.logger"
        ) as mock_logger,
    ):
        zombies = await OrphanExternalIpsPlugin().scan(
            "proj-1", "us-central1", credentials=MagicMock()
        )
        assert zombies == []
        mock_logger.warning.assert_called_once()

    # Storage fallback error
    with (
        patch(
            "app.modules.optimization.adapters.gcp.plugins.storage.compute_v1.DisksClient",
            side_effect=RuntimeError("boom"),
        ),
        patch(
            "app.modules.optimization.adapters.gcp.plugins.storage.compute_v1.SnapshotsClient",
            side_effect=RuntimeError("boom"),
        ),
        patch(
            "app.modules.optimization.adapters.gcp.plugins.storage.compute_v1.AggregatedListDisksRequest",
            return_value=MagicMock(),
        ),
        patch(
            "app.modules.optimization.adapters.gcp.plugins.storage.compute_v1.ListSnapshotsRequest",
            return_value=MagicMock(),
        ),
        patch(
            "app.modules.optimization.adapters.gcp.plugins.storage.logger"
        ) as mock_logger,
    ):
        assert (
            await UnattachedDisksPlugin().scan(
                "proj-1", "us-central1", credentials=MagicMock()
            )
            == []
        )
        assert (
            await OldSnapshotsPlugin().scan(
                "proj-1", "us-central1", credentials=MagicMock()
            )
            == []
        )
        assert mock_logger.warning.call_count == 2
