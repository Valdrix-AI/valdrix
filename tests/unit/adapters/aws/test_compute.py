import pytest
import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from app.modules.optimization.adapters.aws.plugins.compute import (
    UnusedElasticIpsPlugin,
    IdleInstancesPlugin,
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


@pytest.mark.asyncio
async def test_unused_elastic_ips_plugin(mock_session):
    """Test EIP plugin finds unassociated IPs."""
    plugin = UnusedElasticIpsPlugin()

    mock_ec2 = MagicMock()
    mock_ec2.describe_addresses = AsyncMock()
    mock_session.client.return_value.__aenter__.return_value = mock_ec2

    mock_ec2.describe_addresses.return_value = {
        "Addresses": [
            {"PublicIp": "1.2.3.4", "AllocationId": "eipalloc-1"},  # Zombie
            {"PublicIp": "5.6.7.8", "InstanceId": "i-123"},  # Not Zombie
        ]
    }

    results = await plugin.scan(mock_session, "us-east-1")
    assert len(results) == 1
    assert results[0]["resource_id"] == "eipalloc-1"


@pytest.mark.asyncio
async def test_idle_instances_plugin_cloudwatch_path(mock_session):
    """Test EC2 idle detection via CloudWatch metrics."""
    plugin = IdleInstancesPlugin()

    mock_ec2 = MagicMock()
    mock_ec2.get_paginator = MagicMock()
    mock_cw = MagicMock()
    mock_cw.get_metric_data = AsyncMock()
    mock_ct = MagicMock()
    mock_ct.lookup_events = AsyncMock()

    mock_session.client.return_value.__aenter__.side_effect = [
        mock_ec2,
        mock_cw,
        mock_ct,
    ]

    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = AsyncIterator(
        [
            {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "InstanceId": "i-idle",
                                "InstanceType": "t3.medium",
                                "State": {"Name": "running"},
                                "LaunchTime": datetime.datetime.now(
                                    datetime.timezone.utc
                                ),
                            }
                        ]
                    }
                ]
            }
        ]
    )
    mock_ec2.get_paginator.return_value = mock_paginator

    # Low CPU result
    mock_cw.get_metric_data.return_value = {
        "MetricDataResults": [{"Id": "m0", "Values": [0.5]}]
    }

    # CloudTrail lookup for owner
    mock_ct.lookup_events.return_value = {
        "Events": [{"EventName": "RunInstances", "Username": "test-user"}]
    }

    with patch(
        "app.modules.reporting.domain.pricing.service.PricingService.estimate_monthly_waste"
    ) as mock_price:
        mock_price.return_value = 100.0
        results = await plugin.scan(mock_session, "us-east-1")

    assert len(results) == 1
    assert results[0]["resource_id"] == "i-idle"
    assert results[0]["owner"] == "test-user"


@pytest.mark.asyncio
async def test_idle_instances_cur_path(mock_session):
    """Test EC2 idle detection via CUR records."""
    plugin = IdleInstancesPlugin()

    # Discovery still happens via EC2 API
    mock_ec2 = MagicMock()
    mock_ec2.get_paginator = MagicMock()
    mock_session.client.return_value.__aenter__.return_value = mock_ec2

    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = AsyncIterator(
        [
            {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "InstanceId": "i-cur",
                                "InstanceType": "t3.medium",
                                "State": {"Name": "running"},
                                "Tags": [],
                            }
                        ]
                    }
                ]
            }
        ]
    )
    mock_ec2.get_paginator.return_value = mock_paginator

    mock_records = [{"resource_id": "i-cur"}]
    with patch(
        "app.shared.analysis.cur_usage_analyzer.CURUsageAnalyzer"
    ) as mock_analyzer_cls:
        mock_analyzer = MagicMock()
        mock_analyzer.find_low_usage_instances.return_value = [{"resource_id": "i-cur"}]
        mock_analyzer_cls.return_value = mock_analyzer

        results = await plugin.scan(mock_session, "us-east-1", cur_records=mock_records)
        assert len(results) == 1
        assert results[0]["resource_id"] == "i-cur"
