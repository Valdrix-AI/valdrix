import pytest
import sys
import types
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.modules.optimization.adapters.azure.plugins.compute import IdleVmsPlugin, IdleGpuVmsPlugin
from app.modules.optimization.adapters.azure.plugins.containers import IdleAksClusterPlugin, UnusedAppServicePlansPlugin
from app.modules.optimization.adapters.azure.plugins.database import IdleSqlDatabasesPlugin
from app.modules.optimization.adapters.azure.plugins.network import OrphanPublicIpsPlugin, OrphanNicsPlugin, OrphanNsgsPlugin
from app.modules.optimization.adapters.azure.plugins.storage import UnattachedDisksPlugin, OldSnapshotsPlugin


async def async_iter(items):
    for item in items:
        yield item


def _register_azure_module(monkeypatch, module_name, **attrs):
    module = types.ModuleType(module_name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, module_name, module)
    return module


@pytest.mark.asyncio
async def test_idle_vms_cost_records():
    plugin = IdleVmsPlugin()
    with patch("app.shared.analysis.azure_usage_analyzer.AzureUsageAnalyzer") as mock_analyzer:
        mock_analyzer.return_value.find_idle_vms.return_value = [{"resource_id": "vm-1"}]
        zombies = await plugin.scan(subscription_id="sub-1", cost_records=[{"x": 1}])
        assert zombies[0]["resource_id"] == "vm-1"


@pytest.mark.asyncio
async def test_idle_vms_gpu_fallback():
    plugin = IdleVmsPlugin()

    vm = MagicMock()
    vm.id = "vm-1"
    vm.name = "gpu-vm"
    vm.location = "eastus"
    vm.hardware_profile.vm_size = "Standard_NC6"
    status = MagicMock()
    status.code = "PowerState/running"
    vm.instance_view.statuses = [status]

    client = MagicMock()
    client.virtual_machines.list_all.return_value = async_iter([vm])

    with patch("app.modules.optimization.adapters.azure.plugins.compute.ComputeManagementClient", return_value=client):
        zombies = await plugin.scan(subscription_id="sub-1", credentials=MagicMock())
        assert len(zombies) == 1
        assert zombies[0]["resource_id"] == "vm-1"


@pytest.mark.asyncio
async def test_idle_gpu_vms_filters_gpu():
    plugin = IdleGpuVmsPlugin()
    with patch("app.shared.analysis.azure_usage_analyzer.AzureUsageAnalyzer") as mock_analyzer:
        mock_analyzer.return_value.find_idle_vms.return_value = [
            {"resource_id": "vm-gpu", "resource_type": "Virtual Machine (GPU)"},
            {"resource_id": "vm-cpu", "resource_type": "Virtual Machine"},
        ]
        zombies = await plugin.scan(subscription_id="sub-1", cost_records=[{"x": 1}])
        assert len(zombies) == 1
        assert zombies[0]["resource_id"] == "vm-gpu"


@pytest.mark.asyncio
async def test_idle_aks_cluster_cost_records():
    plugin = IdleAksClusterPlugin()
    with patch("app.shared.analysis.azure_usage_analyzer.AzureUsageAnalyzer") as mock_analyzer:
        mock_analyzer.return_value.find_idle_aks_clusters.return_value = [{"resource_id": "aks-1"}]
        zombies = await plugin.scan(subscription_id="sub-1", cost_records=[{"x": 1}])
        assert zombies[0]["resource_id"] == "aks-1"


@pytest.mark.asyncio
async def test_unused_app_service_plans_cost_records():
    plugin = UnusedAppServicePlansPlugin()
    with patch("app.shared.analysis.azure_usage_analyzer.AzureUsageAnalyzer") as mock_analyzer:
        mock_analyzer.return_value.find_unused_app_service_plans.return_value = [{"resource_id": "plan-1"}]
        zombies = await plugin.scan(subscription_id="sub-1", cost_records=[{"x": 1}])
        assert zombies[0]["resource_id"] == "plan-1"


@pytest.mark.asyncio
async def test_unused_app_service_plans_fallback(monkeypatch):
    plugin = UnusedAppServicePlansPlugin()

    plan = MagicMock()
    plan.id = "/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.Web/serverfarms/plan1"
    plan.name = "plan1"
    plan.location = "eastus"
    plan.sku.tier = "Standard"
    plan.sku.name = "S1"

    client = MagicMock()
    client.app_service_plans.list.return_value = async_iter([plan])
    client.web_apps.list_by_resource_group.return_value = async_iter([])

    web_aio = _register_azure_module(
        monkeypatch,
        "azure.mgmt.web.aio",
        WebSiteManagementClient=lambda credentials, subscription_id: client,
    )
    web_mod = _register_azure_module(monkeypatch, "azure.mgmt.web")
    web_mod.aio = web_aio

    azure_mod = sys.modules.get("azure") or _register_azure_module(monkeypatch, "azure")
    mgmt_mod = sys.modules.get("azure.mgmt") or _register_azure_module(monkeypatch, "azure.mgmt")
    setattr(mgmt_mod, "web", web_mod)
    setattr(azure_mod, "mgmt", mgmt_mod)

    zombies = await plugin.scan(subscription_id="sub-1", credentials=MagicMock())
    assert len(zombies) == 1
    assert zombies[0]["resource_id"] == plan.id


@pytest.mark.asyncio
async def test_idle_sql_databases_cost_records():
    plugin = IdleSqlDatabasesPlugin()
    with patch("app.shared.analysis.azure_usage_analyzer.AzureUsageAnalyzer") as mock_analyzer:
        mock_analyzer.return_value.find_idle_sql_databases.return_value = [{"resource_id": "db-1"}]
        zombies = await plugin.scan(subscription_id="sub-1", cost_records=[{"x": 1}])
        assert zombies[0]["resource_id"] == "db-1"


@pytest.mark.asyncio
async def test_idle_sql_databases_fallback(monkeypatch):
    plugin = IdleSqlDatabasesPlugin()

    server = MagicMock()
    server.id = "/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.Sql/servers/s1"
    server.name = "s1"
    db = MagicMock()
    db.id = "db-1"
    db.name = "db1"
    db.sku.name = "Basic"

    client = MagicMock()
    client.servers.list.return_value = async_iter([server])
    client.databases.list_by_server.return_value = async_iter([db])

    sql_aio = _register_azure_module(
        monkeypatch,
        "azure.mgmt.sql.aio",
        SqlManagementClient=lambda credentials, subscription_id: client,
    )
    sql_mod = _register_azure_module(monkeypatch, "azure.mgmt.sql")
    sql_mod.aio = sql_aio

    azure_mod = sys.modules.get("azure") or _register_azure_module(monkeypatch, "azure")
    mgmt_mod = sys.modules.get("azure.mgmt") or _register_azure_module(monkeypatch, "azure.mgmt")
    setattr(mgmt_mod, "sql", sql_mod)
    setattr(azure_mod, "mgmt", mgmt_mod)

    zombies = await plugin.scan(subscription_id="sub-1", credentials=MagicMock())
    assert len(zombies) == 1
    assert zombies[0]["resource_id"] == "db-1"


@pytest.mark.asyncio
async def test_orphan_network_resources_fallback():
    ip = MagicMock()
    ip.id = "ip-1"
    ip.name = "ip1"
    ip.location = "eastus"
    ip.ip_address = "1.2.3.4"
    ip.ip_configuration = None
    ip.sku.name = "Standard"

    nic = MagicMock()
    nic.id = "nic-1"
    nic.name = "nic1"
    nic.location = "eastus"
    nic.virtual_machine = None

    nsg = MagicMock()
    nsg.id = "nsg-1"
    nsg.name = "nsg1"
    nsg.location = "eastus"
    nsg.network_interfaces = []
    nsg.subnets = []

    client = MagicMock()
    client.public_ip_addresses.list_all.return_value = async_iter([ip])
    client.network_interfaces.list_all.return_value = async_iter([nic])
    client.network_security_groups.list_all.return_value = async_iter([nsg])

    with patch("app.modules.optimization.adapters.azure.plugins.network.NetworkManagementClient", return_value=client):
        zombies = await OrphanPublicIpsPlugin().scan(subscription_id="sub-1", credentials=MagicMock())
        assert len(zombies) == 1

        zombies = await OrphanNicsPlugin().scan(subscription_id="sub-1", credentials=MagicMock())
        assert len(zombies) == 1

        zombies = await OrphanNsgsPlugin().scan(subscription_id="sub-1", credentials=MagicMock())
        assert len(zombies) == 1


@pytest.mark.asyncio
async def test_idle_aks_cluster_fallback(monkeypatch):
    plugin = IdleAksClusterPlugin()

    cluster = MagicMock()
    cluster.id = "aks-1"
    cluster.name = "aks"
    cluster.location = "eastus"
    cluster.sku.tier = "Paid"
    cluster.agent_pool_profiles = [MagicMock(count=0)]

    client = MagicMock()
    client.managed_clusters.list.return_value = async_iter([cluster])

    cs_aio = _register_azure_module(
        monkeypatch,
        "azure.mgmt.containerservice.aio",
        ContainerServiceClient=lambda credentials, subscription_id: client,
    )
    cs_mod = _register_azure_module(monkeypatch, "azure.mgmt.containerservice")
    cs_mod.aio = cs_aio

    azure_mod = sys.modules.get("azure") or _register_azure_module(monkeypatch, "azure")
    mgmt_mod = sys.modules.get("azure.mgmt") or _register_azure_module(monkeypatch, "azure.mgmt")
    setattr(mgmt_mod, "containerservice", cs_mod)
    setattr(azure_mod, "mgmt", mgmt_mod)

    zombies = await plugin.scan(subscription_id="sub-1", credentials=MagicMock())
    assert len(zombies) == 1
    assert zombies[0]["resource_id"] == "aks-1"


@pytest.mark.asyncio
async def test_unattached_disks_and_old_snapshots_fallback():
    disk = MagicMock()
    disk.id = "disk-1"
    disk.name = "disk1"
    disk.location = "eastus"
    disk.disk_state = "Unattached"
    disk.disk_size_gb = 10
    disk.sku.name = "Premium_LRS"

    snapshot = MagicMock()
    snapshot.id = "snap-1"
    snapshot.name = "snap1"
    snapshot.location = "eastus"
    snapshot.disk_size_gb = 5
    snapshot.time_created = datetime.now(timezone.utc) - timedelta(days=120)

    client = MagicMock()
    client.disks.list.return_value = async_iter([disk])
    client.snapshots.list.return_value = async_iter([snapshot])

    with patch("app.modules.optimization.adapters.azure.plugins.storage.ComputeManagementClient", return_value=client):
        zombies = await UnattachedDisksPlugin().scan(subscription_id="sub-1", credentials=MagicMock())
        assert len(zombies) == 1

        zombies = await OldSnapshotsPlugin().scan(subscription_id="sub-1", credentials=MagicMock())
        assert len(zombies) == 1


@pytest.mark.asyncio
async def test_azure_fallbacks_handle_errors(monkeypatch):
    # Compute fallback error (idle vms)
    with patch("app.modules.optimization.adapters.azure.plugins.compute.ComputeManagementClient", side_effect=RuntimeError("boom")), \
         patch("app.modules.optimization.adapters.azure.plugins.compute.logger") as mock_logger:
        zombies = await IdleVmsPlugin().scan(subscription_id="sub-1", credentials=MagicMock())
        assert zombies == []
        mock_logger.warning.assert_called_once()

    # Containers fallback error (AKS)
    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    cs_aio = _register_azure_module(
        monkeypatch,
        "azure.mgmt.containerservice.aio",
        ContainerServiceClient=_raise,
    )
    cs_mod = _register_azure_module(monkeypatch, "azure.mgmt.containerservice")
    cs_mod.aio = cs_aio

    azure_mod = sys.modules.get("azure") or _register_azure_module(monkeypatch, "azure")
    mgmt_mod = sys.modules.get("azure.mgmt") or _register_azure_module(monkeypatch, "azure.mgmt")
    setattr(mgmt_mod, "containerservice", cs_mod)
    setattr(azure_mod, "mgmt", mgmt_mod)

    with patch("app.modules.optimization.adapters.azure.plugins.containers.logger") as mock_logger:
        zombies = await IdleAksClusterPlugin().scan(subscription_id="sub-1", credentials=MagicMock())
        assert zombies == []
        mock_logger.warning.assert_called_once()

    # SQL fallback error
    sql_aio = _register_azure_module(
        monkeypatch,
        "azure.mgmt.sql.aio",
        SqlManagementClient=_raise,
    )
    sql_mod = _register_azure_module(monkeypatch, "azure.mgmt.sql")
    sql_mod.aio = sql_aio
    setattr(mgmt_mod, "sql", sql_mod)
    setattr(azure_mod, "mgmt", mgmt_mod)

    with patch("app.modules.optimization.adapters.azure.plugins.database.logger") as mock_logger:
        zombies = await IdleSqlDatabasesPlugin().scan(subscription_id="sub-1", credentials=MagicMock())
        assert zombies == []
        mock_logger.warning.assert_called_once()

    # Network fallback error
    with patch("app.modules.optimization.adapters.azure.plugins.network.NetworkManagementClient", side_effect=RuntimeError("boom")), \
         patch("app.modules.optimization.adapters.azure.plugins.network.logger") as mock_logger:
        assert await OrphanPublicIpsPlugin().scan(subscription_id="sub-1", credentials=MagicMock()) == []
        assert await OrphanNicsPlugin().scan(subscription_id="sub-1", credentials=MagicMock()) == []
        assert await OrphanNsgsPlugin().scan(subscription_id="sub-1", credentials=MagicMock()) == []
        assert mock_logger.warning.call_count == 3

    # Storage fallback error
    with patch("app.modules.optimization.adapters.azure.plugins.storage.ComputeManagementClient", side_effect=RuntimeError("boom")), \
         patch("app.modules.optimization.adapters.azure.plugins.storage.logger") as mock_logger:
        assert await UnattachedDisksPlugin().scan(subscription_id="sub-1", credentials=MagicMock()) == []
        assert await OldSnapshotsPlugin().scan(subscription_id="sub-1", credentials=MagicMock()) == []
        assert mock_logger.warning.call_count == 2
