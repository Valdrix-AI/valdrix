import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.optimization.adapters.aws.plugins.compute import (
    UnusedElasticIpsPlugin,
    IdleInstancesPlugin,
)
from app.modules.optimization.adapters.aws.plugins.network import (
    OrphanLoadBalancersPlugin,
    UnderusedNatGatewaysPlugin,
)
from app.modules.optimization.adapters.aws.plugins.storage import (
    UnattachedVolumesPlugin,
    OldSnapshotsPlugin,
)


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
async def test_unused_elastic_ips_detects_unattached(monkeypatch):
    plugin = UnusedElasticIpsPlugin()
    ec2 = MagicMock()
    ec2.describe_addresses = AsyncMock(
        return_value={
            "Addresses": [
                {"PublicIp": "1.1.1.1", "AllocationId": "eip-1"},
                {"PublicIp": "2.2.2.2", "InstanceId": "i-123"},
            ]
        }
    )

    monkeypatch.setattr(
        plugin, "_get_client", lambda *args, **kwargs: AsyncContext(ec2)
    )

    with patch(
        "app.modules.reporting.domain.pricing.service.PricingService.estimate_monthly_waste",
        return_value=3.6,
    ):
        zombies = await plugin.scan(session=MagicMock(), region="us-east-1")
        assert len(zombies) == 1
        assert zombies[0]["resource_id"] == "eip-1"


@pytest.mark.asyncio
async def test_idle_instances_cloudwatch_detection(monkeypatch):
    plugin = IdleInstancesPlugin()

    instance = {
        "InstanceId": "i-abc",
        "InstanceType": "t3.micro",
        "LaunchTime": datetime.now(timezone.utc) - timedelta(days=10),
        "State": {"Name": "running"},
        "Tags": [{"Key": "env", "Value": "dev"}],
    }
    ec2 = MagicMock()
    ec2.get_paginator.return_value = AsyncPaginator(
        [
            {"Reservations": [{"Instances": [instance]}]},
        ]
    )

    cloudwatch = MagicMock()
    cloudwatch.get_metric_data = AsyncMock(
        return_value={"MetricDataResults": [{"Id": "m0", "Values": [1.0]}]}
    )

    def client_factory(service_name):
        if service_name == "ec2":
            return ec2
        return cloudwatch

    monkeypatch.setattr(
        plugin,
        "_get_client",
        lambda *args, **kwargs: AsyncContext(client_factory(args[1])),
    )
    monkeypatch.setattr(plugin, "_get_attribution", AsyncMock(return_value="alice"))

    with (
        patch(
            "app.modules.optimization.adapters.aws.plugins.compute.cloudwatch_limiter.acquire",
            new=AsyncMock(),
        ),
        patch(
            "app.modules.reporting.domain.pricing.service.PricingService.estimate_monthly_waste",
            return_value=10.0,
        ),
    ):
        zombies = await plugin.scan(session=MagicMock(), region="us-east-1")
        assert len(zombies) == 1
        assert zombies[0]["owner"] == "alice"


@pytest.mark.asyncio
async def test_orphan_load_balancers_no_healthy_targets(monkeypatch):
    plugin = OrphanLoadBalancersPlugin()

    elb = MagicMock()
    elb.get_paginator.side_effect = [
        AsyncPaginator(
            [
                {
                    "LoadBalancers": [
                        {
                            "LoadBalancerArn": "arn-1",
                            "LoadBalancerName": "lb1",
                            "Type": "application",
                        }
                    ]
                }
            ]
        ),
        AsyncPaginator([{"TargetGroups": [{"TargetGroupArn": "tg-1"}]}]),
    ]
    elb.describe_target_health = AsyncMock(
        return_value={
            "TargetHealthDescriptions": [{"TargetHealth": {"State": "unhealthy"}}]
        }
    )

    monkeypatch.setattr(
        plugin, "_get_client", lambda *args, **kwargs: AsyncContext(elb)
    )

    with patch(
        "app.modules.reporting.domain.pricing.service.PricingService.estimate_monthly_waste",
        return_value=20.0,
    ):
        zombies = await plugin.scan(session=MagicMock(), region="us-east-1")
        assert len(zombies) == 1
        assert zombies[0]["resource_name"] == "lb1"


@pytest.mark.asyncio
async def test_underused_nat_gateways_cur_records(monkeypatch):
    plugin = UnderusedNatGatewaysPlugin()

    with patch(
        "app.shared.analysis.cur_usage_analyzer.CURUsageAnalyzer"
    ) as mock_analyzer:
        mock_analyzer.return_value.find_idle_nat_gateways.return_value = [
            {"resource_id": "nat-1"}
        ]
        zombies = await plugin.scan(
            session=MagicMock(), region="us-east-1", cur_records=[{"x": 1}]
        )
        assert zombies[0]["resource_id"] == "nat-1"


@pytest.mark.asyncio
async def test_underused_nat_gateways_cloudwatch(monkeypatch):
    plugin = UnderusedNatGatewaysPlugin()

    ec2 = MagicMock()
    ec2.get_paginator.return_value = AsyncPaginator(
        [{"NatGateways": [{"NatGatewayId": "nat-1", "State": "available"}]}]
    )

    cloudwatch = MagicMock()
    cloudwatch.get_metric_statistics = AsyncMock(
        return_value={"Datapoints": [{"Sum": 0}]}
    )

    def client_factory(service_name):
        if service_name == "ec2":
            return ec2
        return cloudwatch

    monkeypatch.setattr(
        plugin,
        "_get_client",
        lambda *args, **kwargs: AsyncContext(client_factory(args[1])),
    )

    with patch(
        "app.modules.reporting.domain.pricing.service.PricingService.estimate_monthly_waste",
        return_value=32.4,
    ):
        zombies = await plugin.scan(session=MagicMock(), region="us-east-1")
        assert len(zombies) == 1
        assert zombies[0]["resource_id"] == "nat-1"


@pytest.mark.asyncio
async def test_unattached_volumes_detected(monkeypatch):
    plugin = UnattachedVolumesPlugin()

    ec2 = MagicMock()
    ec2.get_paginator.return_value = AsyncPaginator(
        [
            {
                "Volumes": [
                    {
                        "VolumeId": "vol-1",
                        "Size": 10,
                        "CreateTime": datetime.now(timezone.utc) - timedelta(days=20),
                    }
                ]
            }
        ]
    )

    cloudwatch = MagicMock()
    cloudwatch.get_metric_data = AsyncMock(
        return_value={"MetricDataResults": [{"Values": [0]}, {"Values": [0]}]}
    )

    def client_factory(service_name):
        if service_name == "ec2":
            return ec2
        return cloudwatch

    monkeypatch.setattr(
        plugin,
        "_get_client",
        lambda *args, **kwargs: AsyncContext(client_factory(args[1])),
    )

    with patch(
        "app.modules.reporting.domain.pricing.service.PricingService.estimate_monthly_waste",
        return_value=5.0,
    ):
        zombies = await plugin.scan(session=MagicMock(), region="us-east-1")
        assert len(zombies) == 1
        assert zombies[0]["resource_id"] == "vol-1"


@pytest.mark.asyncio
async def test_old_snapshots_detected(monkeypatch):
    plugin = OldSnapshotsPlugin()

    old_time = datetime.now(timezone.utc) - timedelta(days=200)
    ec2 = MagicMock()
    ec2.get_paginator.return_value = AsyncPaginator(
        [
            {
                "Snapshots": [
                    {"SnapshotId": "snap-1", "StartTime": old_time, "VolumeSize": 50}
                ]
            }
        ]
    )

    monkeypatch.setattr(
        plugin, "_get_client", lambda *args, **kwargs: AsyncContext(ec2)
    )

    with patch(
        "app.modules.reporting.domain.pricing.service.PricingService.estimate_monthly_waste",
        return_value=2.5,
    ):
        zombies = await plugin.scan(session=MagicMock(), region="us-east-1")
        assert len(zombies) == 1
        assert zombies[0]["resource_id"] == "snap-1"
