import pytest
from unittest.mock import patch

from app.modules.optimization.adapters.azure.plugins.network import OrphanPublicIpsPlugin


@pytest.fixture
def plugin():
    return OrphanPublicIpsPlugin()


@pytest.mark.asyncio
async def test_azure_orphan_public_ips_scan_uses_cost_records(plugin):
    expected = [{"resource_id": "ip-1", "monthly_cost": 3.65}]

    with patch("app.shared.analysis.azure_usage_analyzer.AzureUsageAnalyzer") as analyzer_cls:
        analyzer = analyzer_cls.return_value
        analyzer.find_orphan_public_ips.return_value = expected

        results = await plugin.scan(
            "sub-123",
            credentials=object(),
            cost_records=[{"ResourceId": "/subscriptions/sub-123/publicIPAddresses/ip-1"}],
        )

    assert results == expected
    analyzer.find_orphan_public_ips.assert_called_once_with()
