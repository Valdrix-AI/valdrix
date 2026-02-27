from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.modules.optimization.adapters.aws.plugins import database as db_plugins


class AsyncContext:
    def __init__(self, obj):
        self._obj = obj

    async def __aenter__(self):
        return self._obj

    async def __aexit__(self, *args):
        return None


class FailingAsyncContext:
    def __init__(self, exc: Exception):
        self._exc = exc

    async def __aenter__(self):
        raise self._exc

    async def __aexit__(self, *args):
        return None


class AsyncPaginator:
    def __init__(self, pages):
        self._pages = pages
        self._iter = iter([])

    def paginate(self, *args, **kwargs):
        self._iter = iter(self._pages)
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


def _client_error(code: str = "AccessDenied", operation: str = "Op") -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, operation)


def test_aws_database_plugin_category_keys() -> None:
    assert db_plugins.IdleRdsPlugin().category_key == "idle_rds_databases"
    assert db_plugins.ColdRedshiftPlugin().category_key == "cold_redshift_clusters"
    assert db_plugins.IdleDynamoDbPlugin().category_key == "idle_dynamodb_tables"


@pytest.mark.asyncio
async def test_idle_rds_cur_records_branch() -> None:
    plugin = db_plugins.IdleRdsPlugin()
    with patch("app.shared.analysis.cur_usage_analyzer.CURUsageAnalyzer") as analyzer_cls:
        analyzer_cls.return_value.find_idle_rds_databases.return_value = [{"resource_id": "db-cur"}]
        out = await plugin.scan(session=MagicMock(), region="us-east-1", cur_records=[{"x": 1}])

    assert out == [{"resource_id": "db-cur"}]
    analyzer_cls.return_value.find_idle_rds_databases.assert_called_once_with(days=7)


@pytest.mark.asyncio
async def test_idle_rds_returns_empty_when_no_instances_discovered(monkeypatch) -> None:
    plugin = db_plugins.IdleRdsPlugin()
    rds = MagicMock()
    rds.get_paginator.return_value = AsyncPaginator([{"DBInstances": []}])
    monkeypatch.setattr(plugin, "_get_client", lambda *args, **kwargs: AsyncContext(rds))

    out = await plugin.scan(session=MagicMock(), region="us-east-1")

    assert out == []


@pytest.mark.asyncio
async def test_idle_rds_skips_missing_values_and_non_idle_connections(monkeypatch) -> None:
    plugin = db_plugins.IdleRdsPlugin()
    rds = MagicMock()
    rds.get_paginator.return_value = AsyncPaginator(
        [
            {
                "DBInstances": [
                    {"DBInstanceIdentifier": "db-a", "DBInstanceClass": "db.t3.micro", "Engine": "postgres"},
                    {"DBInstanceIdentifier": "db-b", "DBInstanceClass": "db.t3.small", "Engine": "mysql"},
                ]
            }
        ]
    )
    cloudwatch = MagicMock()
    cloudwatch.get_metric_data = AsyncMock(
        return_value={
            "MetricDataResults": [
                {"Id": "m0", "Values": []},  # res present, no values
                {"Id": "m1", "Values": [2.0]},  # above threshold
            ]
        }
    )

    def client_factory(service_name):
        return rds if service_name == "rds" else cloudwatch

    monkeypatch.setattr(plugin, "_get_client", lambda *args, **kwargs: AsyncContext(client_factory(args[1])))

    with patch.object(db_plugins.PricingService, "estimate_monthly_waste") as pricing_mock:
        out = await plugin.scan(session=MagicMock(), region="us-east-1")

    assert out == []
    pricing_mock.assert_not_called()


@pytest.mark.asyncio
async def test_idle_rds_outer_client_error_logs_and_returns_empty(monkeypatch) -> None:
    plugin = db_plugins.IdleRdsPlugin()
    monkeypatch.setattr(
        plugin,
        "_get_client",
        lambda *args, **kwargs: FailingAsyncContext(_client_error(operation="DescribeDBInstances")),
    )

    with patch.object(db_plugins, "logger") as logger_mock:
        out = await plugin.scan(session=MagicMock(), region="us-east-1")

    assert out == []
    logger_mock.warning.assert_called_once()
    assert logger_mock.warning.call_args.args[0] == "idle_rds_scan_error"


@pytest.mark.asyncio
async def test_cold_redshift_cur_records_branch() -> None:
    plugin = db_plugins.ColdRedshiftPlugin()
    with patch("app.shared.analysis.cur_usage_analyzer.CURUsageAnalyzer") as analyzer_cls:
        analyzer_cls.return_value.find_idle_redshift_clusters.return_value = [
            {"resource_id": "rs-cur"}
        ]
        out = await plugin.scan(session=MagicMock(), region="us-east-1", cur_records=[{"x": 1}])

    assert out == [{"resource_id": "rs-cur"}]
    analyzer_cls.return_value.find_idle_redshift_clusters.assert_called_once_with(days=7)


@pytest.mark.asyncio
async def test_cold_redshift_skips_active_cluster_and_logs_metric_failure(monkeypatch) -> None:
    plugin = db_plugins.ColdRedshiftPlugin()
    redshift = MagicMock()
    redshift.get_paginator.return_value = AsyncPaginator(
        [
            {
                "Clusters": [
                    {"ClusterIdentifier": "rs-active"},
                    {"ClusterIdentifier": "rs-error"},
                ]
            }
        ]
    )
    cloudwatch = MagicMock()
    cloudwatch.get_metric_statistics = AsyncMock(
        side_effect=[
            {"Datapoints": [{"Sum": 1}]},  # active cluster skip branch
            _client_error(operation="GetMetricStatistics"),  # metric failure branch
        ]
    )

    def client_factory(service_name):
        return redshift if service_name == "redshift" else cloudwatch

    monkeypatch.setattr(plugin, "_get_client", lambda *args, **kwargs: AsyncContext(client_factory(args[1])))

    with patch.object(db_plugins, "logger") as logger_mock:
        out = await plugin.scan(session=MagicMock(), region="us-east-1")

    assert out == []
    logger_mock.warning.assert_called_once()
    assert logger_mock.warning.call_args.args[0] == "redshift_metric_fetch_failed"


@pytest.mark.asyncio
async def test_cold_redshift_outer_client_error_logs_and_returns_empty(monkeypatch) -> None:
    plugin = db_plugins.ColdRedshiftPlugin()
    monkeypatch.setattr(
        plugin,
        "_get_client",
        lambda *args, **kwargs: FailingAsyncContext(_client_error(operation="DescribeClusters")),
    )

    with patch.object(db_plugins, "logger") as logger_mock:
        out = await plugin.scan(session=MagicMock(), region="us-east-1")

    assert out == []
    logger_mock.warning.assert_called_once()
    assert logger_mock.warning.call_args.args[0] == "redshift_scan_error"


@pytest.mark.asyncio
async def test_idle_dynamodb_detects_idle_provisioned_table(monkeypatch) -> None:
    plugin = db_plugins.IdleDynamoDbPlugin()
    ddb = MagicMock()
    ddb.get_paginator.return_value = AsyncPaginator([{"TableNames": ["tbl-idle"]}])
    ddb.describe_table = AsyncMock(
        return_value={
            "Table": {
                "BillingModeSummary": {"BillingMode": "PROVISIONED"},
                "ProvisionedThroughput": {"ReadCapacityUnits": 10, "WriteCapacityUnits": 5},
            }
        }
    )
    cloudwatch = MagicMock()
    cloudwatch.get_metric_data = AsyncMock(
        return_value={"MetricDataResults": [{"Values": [0]}, {"Values": [0]}]}
    )

    def client_factory(service_name):
        return ddb if service_name == "dynamodb" else cloudwatch

    monkeypatch.setattr(plugin, "_get_client", lambda *args, **kwargs: AsyncContext(client_factory(args[1])))

    out = await plugin.scan(session=MagicMock(), region="us-east-1")

    assert len(out) == 1
    item = out[0]
    assert item["resource_id"] == "tbl-idle"
    assert item["rcu"] == 10
    assert item["wcu"] == 5
    assert item["action"] == "modify_dynamodb_table"


@pytest.mark.asyncio
async def test_idle_dynamodb_skip_branches_and_table_check_error(monkeypatch) -> None:
    plugin = db_plugins.IdleDynamoDbPlugin()
    ddb = MagicMock()
    ddb.get_paginator.return_value = AsyncPaginator(
        [{"TableNames": ["tbl-ondemand", "tbl-zero", "tbl-used", "tbl-error"]}]
    )
    ddb.describe_table = AsyncMock(
        side_effect=[
            {"Table": {"BillingModeSummary": {"BillingMode": "PAY_PER_REQUEST"}}},
            {"Table": {"BillingModeSummary": {"BillingMode": "PROVISIONED"}, "ProvisionedThroughput": {"ReadCapacityUnits": 0, "WriteCapacityUnits": 0}}},
            {"Table": {"BillingModeSummary": {"BillingMode": "PROVISIONED"}, "ProvisionedThroughput": {"ReadCapacityUnits": 1, "WriteCapacityUnits": 1}}},
            _client_error(operation="DescribeTable"),
        ]
    )
    cloudwatch = MagicMock()
    cloudwatch.get_metric_data = AsyncMock(
        return_value={"MetricDataResults": [{"Values": [1]}, {"Values": [2]}]}
    )

    def client_factory(service_name):
        return ddb if service_name == "dynamodb" else cloudwatch

    monkeypatch.setattr(plugin, "_get_client", lambda *args, **kwargs: AsyncContext(client_factory(args[1])))

    with patch.object(db_plugins, "logger") as logger_mock:
        out = await plugin.scan(session=MagicMock(), region="us-east-1")

    assert out == []
    # Only tbl-used reaches CloudWatch; tbl-error logs table-check failure.
    cloudwatch.get_metric_data.assert_awaited_once()
    logger_mock.warning.assert_called_once()
    assert logger_mock.warning.call_args.args[0] == "dynamodb_table_check_failed"


@pytest.mark.asyncio
async def test_idle_dynamodb_outer_client_error_logs_and_returns_empty(monkeypatch) -> None:
    plugin = db_plugins.IdleDynamoDbPlugin()
    monkeypatch.setattr(
        plugin,
        "_get_client",
        lambda *args, **kwargs: FailingAsyncContext(_client_error(operation="ListTables")),
    )

    with patch.object(db_plugins, "logger") as logger_mock:
        out = await plugin.scan(session=MagicMock(), region="us-east-1")

    assert out == []
    logger_mock.warning.assert_called_once()
    assert logger_mock.warning.call_args.args[0] == "dynamodb_scan_error"
