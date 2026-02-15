import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.modules.optimization.adapters.aws.plugins.database import (
    IdleRdsPlugin,
    ColdRedshiftPlugin,
)


class AsyncIterator:
    def __init__(self, items):
        self.items = items
        self.cursor = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.cursor >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.cursor]
        self.cursor += 1
        return item


@pytest.fixture
def mock_session():
    session = MagicMock()
    return_mock = MagicMock()
    return_mock.__aenter__ = AsyncMock()
    return_mock.__aexit__ = AsyncMock()
    session.client.return_value = return_mock
    return session


@pytest.fixture
def mock_pricing():
    with patch(
        "app.modules.optimization.adapters.aws.plugins.database.PricingService"
    ) as mock:
        mock.estimate_monthly_waste.return_value = 150.0
        yield mock


@pytest.mark.asyncio
async def test_idle_rds_plugin_scan_success(mock_session, mock_pricing):
    """Test RDS plugin finds idle databases via CloudWatch MetricData."""
    plugin = IdleRdsPlugin()

    mock_rds = MagicMock()
    mock_rds.get_paginator = MagicMock()
    mock_cw = MagicMock()
    mock_cw.get_metric_data = AsyncMock()

    mock_session.client.return_value.__aenter__.side_effect = [mock_rds, mock_cw]

    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = AsyncIterator(
        [
            {
                "DBInstances": [
                    {
                        "DBInstanceIdentifier": "db-1",
                        "DBInstanceClass": "db.t3.medium",
                        "Engine": "postgres",
                    }
                ]
            }
        ]
    )
    mock_rds.get_paginator.return_value = mock_paginator
    mock_cw.get_metric_data.return_value = {
        "MetricDataResults": [{"Id": "m0", "Values": [0.5]}]
    }

    results = await plugin.scan(mock_session, "us-east-1")

    assert len(results) == 1
    assert results[0]["resource_id"] == "db-1"


@pytest.mark.asyncio
async def test_cold_redshift_plugin_scan_success(mock_session, mock_pricing):
    """Test Redshift plugin finds idle clusters."""
    plugin = ColdRedshiftPlugin()

    mock_rs = MagicMock()
    mock_rs.get_paginator = MagicMock()
    mock_cw = MagicMock()
    mock_cw.get_metric_statistics = AsyncMock()

    mock_session.client.return_value.__aenter__.side_effect = [mock_rs, mock_cw]

    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = AsyncIterator(
        [{"Clusters": [{"ClusterIdentifier": "rs-1"}]}]
    )
    mock_rs.get_paginator.return_value = mock_paginator
    mock_cw.get_metric_statistics.return_value = {"Datapoints": [{"Sum": 0}]}

    results = await plugin.scan(mock_session, "us-east-1")

    assert len(results) == 1
    assert results[0]["resource_id"] == "rs-1"


@pytest.mark.asyncio
async def test_database_plugins_cur_path():
    """Test CUR path."""
    plugin = IdleRdsPlugin()
    mock_records = [{"line_item_product_code": "AmazonRDS"}]
    with patch(
        "app.shared.analysis.cur_usage_analyzer.CURUsageAnalyzer"
    ) as mock_analyzer_cls:
        mock_analyzer = MagicMock()
        mock_analyzer.find_idle_rds_databases.return_value = [
            {"resource_id": "cur-rds"}
        ]
        mock_analyzer_cls.return_value = mock_analyzer
        results = await plugin.scan(None, "us-east-1", cur_records=mock_records)
        assert len(results) == 1
