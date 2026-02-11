import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.optimization.adapters.aws.plugins.analytics import IdleSageMakerPlugin
from app.modules.optimization.adapters.aws.plugins.containers import StaleEcrImagesPlugin
from app.modules.optimization.adapters.aws.plugins.database import IdleRdsPlugin, ColdRedshiftPlugin


class AsyncContext:
    def __init__(self, obj):
        self._obj = obj

    async def __aenter__(self):
        return self._obj

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


@pytest.mark.asyncio
async def test_idle_sagemaker_cur_records():
    plugin = IdleSageMakerPlugin()
    with patch("app.shared.analysis.cur_usage_analyzer.CURUsageAnalyzer") as mock_analyzer:
        mock_analyzer.return_value.find_idle_sagemaker_endpoints.return_value = [{"resource_id": "ep-1"}]
        zombies = await plugin.scan(session=MagicMock(), region="us-east-1", cur_records=[{"x": 1}])
        assert zombies[0]["resource_id"] == "ep-1"


@pytest.mark.asyncio
async def test_idle_sagemaker_cloudwatch(monkeypatch):
    plugin = IdleSageMakerPlugin()

    sagemaker = MagicMock()
    sagemaker.get_paginator.return_value = AsyncPaginator([
        {"Endpoints": [{"EndpointName": "ep-1"}]}
    ])

    cloudwatch = MagicMock()
    cloudwatch.get_metric_statistics = AsyncMock(return_value={"Datapoints": [{"Sum": 0}]})

    def client_factory(service_name):
        if service_name == "sagemaker":
            return sagemaker
        return cloudwatch

    monkeypatch.setattr(plugin, "_get_client", lambda *args, **kwargs: AsyncContext(client_factory(args[1])))

    with patch("app.modules.reporting.domain.pricing.service.PricingService.estimate_monthly_waste", return_value=100.0):
        zombies = await plugin.scan(session=MagicMock(), region="us-east-1")
        assert len(zombies) == 1
        assert zombies[0]["resource_id"] == "ep-1"


@pytest.mark.asyncio
async def test_stale_ecr_images_detected(monkeypatch):
    plugin = StaleEcrImagesPlugin()

    ecr = MagicMock()
    ecr.get_paginator.side_effect = [
        AsyncPaginator([{"repositories": [{"repositoryName": "repo-1"}]}]),
        AsyncPaginator([{"imageDetails": [{
            "imagePushedAt": datetime.now(timezone.utc) - timedelta(days=60),
            "imageSizeInBytes": 1024 ** 3,
            "imageDigest": "sha-1",
        }]}]),
    ]

    monkeypatch.setattr(plugin, "_get_client", lambda *args, **kwargs: AsyncContext(ecr))

    with patch("app.modules.reporting.domain.pricing.service.PricingService.get_hourly_rate", return_value=0.1):
        zombies = await plugin.scan(session=MagicMock(), region="us-east-1")
        assert len(zombies) == 1
        assert zombies[0]["resource_id"].startswith("repo-1@")


@pytest.mark.asyncio
async def test_idle_rds_cloudwatch(monkeypatch):
    plugin = IdleRdsPlugin()

    rds = MagicMock()
    rds.get_paginator.return_value = AsyncPaginator([
        {"DBInstances": [{"DBInstanceIdentifier": "db-1", "DBInstanceClass": "db.t3.micro", "Engine": "postgres"}]}
    ])

    cloudwatch = MagicMock()
    cloudwatch.get_metric_data = AsyncMock(return_value={
        "MetricDataResults": [{"Id": "m0", "Values": [0]}]
    })

    def client_factory(service_name):
        if service_name == "rds":
            return rds
        return cloudwatch

    monkeypatch.setattr(plugin, "_get_client", lambda *args, **kwargs: AsyncContext(client_factory(args[1])))

    with patch("app.modules.reporting.domain.pricing.service.PricingService.estimate_monthly_waste", return_value=15.0):
        zombies = await plugin.scan(session=MagicMock(), region="us-east-1")
        assert len(zombies) == 1
        assert zombies[0]["resource_id"] == "db-1"


@pytest.mark.asyncio
async def test_cold_redshift_cloudwatch(monkeypatch):
    plugin = ColdRedshiftPlugin()

    redshift = MagicMock()
    redshift.get_paginator.return_value = AsyncPaginator([
        {"Clusters": [{"ClusterIdentifier": "rs-1"}]}
    ])

    cloudwatch = MagicMock()
    cloudwatch.get_metric_statistics = AsyncMock(return_value={"Datapoints": [{"Sum": 0}]})

    def client_factory(service_name):
        if service_name == "redshift":
            return redshift
        return cloudwatch

    monkeypatch.setattr(plugin, "_get_client", lambda *args, **kwargs: AsyncContext(client_factory(args[1])))

    with patch("app.modules.reporting.domain.pricing.service.PricingService.estimate_monthly_waste", return_value=180.0):
        zombies = await plugin.scan(session=MagicMock(), region="us-east-1")
        assert len(zombies) == 1
        assert zombies[0]["resource_id"] == "rs-1"
