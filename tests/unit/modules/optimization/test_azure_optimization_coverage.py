import pytest
from unittest.mock import patch

from app.modules.optimization.adapters.azure.plugins.network import OrphanPublicIpsPlugin
from app.modules.optimization.adapters.azure.plugins.storage import UnattachedDisksPlugin


@pytest.mark.asyncio
async def test_azure_unattached_disks_scan_uses_cost_records():
    plugin = UnattachedDisksPlugin()
    expected = [{"resource_id": "disk-1", "monthly_cost": 42.0}]

    with patch("app.shared.analysis.azure_usage_analyzer.AzureUsageAnalyzer") as analyzer_cls:
        analyzer = analyzer_cls.return_value
        analyzer.find_unattached_disks.return_value = expected

        zombies = await plugin.scan(
            "sub-123",
            credentials=object(),
            cost_records=[{"ResourceId": "/subscriptions/sub-123/disks/disk-1"}],
        )

    assert zombies == expected
    analyzer.find_unattached_disks.assert_called_once_with()


@pytest.mark.asyncio
async def test_azure_orphan_public_ips_scan_uses_cost_records():
    plugin = OrphanPublicIpsPlugin()
    expected = [{"resource_id": "pip-1", "monthly_cost": 9.0}]

    with patch("app.shared.analysis.azure_usage_analyzer.AzureUsageAnalyzer") as analyzer_cls:
        analyzer = analyzer_cls.return_value
        analyzer.find_orphan_public_ips.return_value = expected

        zombies = await plugin.scan(
            "sub-123",
            credentials=object(),
            cost_records=[{"ResourceId": "/subscriptions/sub-123/publicIPAddresses/pip-1"}],
        )

    assert zombies == expected
    analyzer.find_orphan_public_ips.assert_called_once_with()
