import pytest
from unittest.mock import patch

from app.modules.optimization.adapters.azure.plugins.storage import (
    UnattachedDisksPlugin,
)


@pytest.fixture
def plugin():
    return UnattachedDisksPlugin()


@pytest.mark.asyncio
async def test_azure_unattached_disks_scan_uses_cost_records(plugin):
    expected = [{"resource_id": "disk-1", "monthly_cost": 5.0}]

    with patch(
        "app.shared.analysis.azure_usage_analyzer.AzureUsageAnalyzer"
    ) as analyzer_cls:
        analyzer = analyzer_cls.return_value
        analyzer.find_unattached_disks.return_value = expected

        results = await plugin.scan(
            "sub-123",
            "eastus",
            credentials=object(),
            cost_records=[{"ResourceId": "/subscriptions/sub-123/disks/disk-1"}],
        )

    assert results == expected
    analyzer.find_unattached_disks.assert_called_once_with()
