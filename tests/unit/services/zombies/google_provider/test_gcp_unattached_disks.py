import pytest
from unittest.mock import patch

from app.modules.optimization.adapters.gcp.plugins.storage import UnattachedDisksPlugin


@pytest.fixture
def plugin():
    return UnattachedDisksPlugin()


@pytest.mark.asyncio
async def test_gcp_unattached_disks_scan_uses_billing_records(plugin):
    expected = [{"resource_id": "disk-1", "monthly_cost": 8.5}]

    with patch(
        "app.shared.analysis.gcp_usage_analyzer.GCPUsageAnalyzer"
    ) as analyzer_cls:
        analyzer = analyzer_cls.return_value
        analyzer.find_unattached_disks.return_value = expected

        results = await plugin.scan(
            "proj-123",
            "us-central1",
            credentials=object(),
            billing_records=[{"resource_id": "projects/proj-123/disks/disk-1"}],
        )

    assert results == expected
    analyzer.find_unattached_disks.assert_called_once_with()
