import pytest
import aioboto3
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch
from botocore.exceptions import ClientError
from app.modules.optimization.adapters.aws.plugins.compute import UnusedElasticIpsPlugin, IdleInstancesPlugin

@pytest.fixture
def mock_session():
    session = MagicMock(spec=aioboto3.Session)
    return session

@pytest.mark.asyncio
async def test_eip_scan_zombie_and_error():
    """Test EIP scan detects zombies and handles errors."""
    plugin = UnusedElasticIpsPlugin()
    mock_session = MagicMock()
    mock_ec2 = AsyncMock()
    mock_ec2.__aenter__.return_value = mock_ec2 # Client IS the context manager
    
    plugin._get_client = MagicMock(return_value=mock_ec2)
    
    # 1. Success case with zombie
    mock_ec2.describe_addresses.return_value = {
        "Addresses": [
            {"PublicIp": "1.2.3.4", "AllocationId": "eip-1", "InstanceId": None, "AssociationId": None}
        ]
    }
    
    zombies = await plugin.scan(mock_session, "us-east-1")
    assert len(zombies) == 1
    assert zombies[0]["resource_id"] == "eip-1"

    # 2. Error case
    mock_ec2.describe_addresses.side_effect = ClientError({"Error": {"Code": "TestError", "Message": "msg"}}, "op")
    zombies = await plugin.scan(mock_session, "us-east-1")
    assert len(zombies) == 0

@pytest.mark.asyncio
async def test_idle_instances_attribution():
    """Test CloudTrail lookup for instance attribution."""
    plugin = IdleInstancesPlugin()
    mock_session = MagicMock()
    mock_ct = AsyncMock()
    mock_ct.__aenter__.return_value = mock_ct
    
    plugin._get_client = MagicMock(return_value=mock_ct)
    
    mock_ct.lookup_events.return_value = {
        "Events": [{"EventName": "RunInstances", "Username": "test-user"}]
    }
    
    owner = await plugin._get_attribution(mock_session, "us-east-1", "i-123")
    assert owner == "test-user"

@pytest.mark.asyncio
async def test_idle_instances_scan_tag_filtering():
    """Test instance filtering by tags."""
    plugin = IdleInstancesPlugin()
    mock_session = MagicMock()
    
    # 1. Mock EC2 Client
    mock_ec2 = MagicMock() # Use MagicMock because get_paginator is sync
    mock_paginator = MagicMock()
    async def mock_paginate(*args, **kwargs):
        yield {
            "Reservations": [{
                "Instances": [{
                    "InstanceId": "i-batch",
                    "InstanceType": "t3.micro",
                    "State": {"Name": "running"},
                    "Tags": [{"Key": "workload", "Value": "batch"}]
                }]
            }]
        }
    mock_paginator.paginate.side_effect = mock_paginate
    mock_ec2.get_paginator.return_value = mock_paginator
    
    # 2. Mock _get_client (Sync) to return Async Context Manager
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_ec2
    
    with patch.object(plugin, "_get_client", return_value=mock_cm):
        zombies = await plugin.scan(mock_session, "us-east-1")
        assert len(zombies) == 0

@pytest.mark.asyncio
async def test_idle_instances_scan_cloudwatch():
    """Test idle detection via CloudWatch metrics."""
    plugin = IdleInstancesPlugin()
    mock_session = MagicMock()
    
    # 1. EC2 setup
    mock_ec2 = MagicMock()
    mock_paginator = MagicMock()
    async def mock_paginate(*args, **kwargs):
        yield {
            "Reservations": [{
                "Instances": [{
                    "InstanceId": "i-idle",
                    "InstanceType": "t3.micro",
                    "State": {"Name": "running"},
                    "Tags": [],
                    "LaunchTime": datetime.now(timezone.utc)
                }]
            }]
        }
    mock_paginator.paginate.side_effect = mock_paginate
    mock_ec2.get_paginator.return_value = mock_paginator
    
    # 2. CloudWatch setup
    mock_cw = MagicMock()
    mock_cw.get_metric_data = AsyncMock()
    mock_cw.get_metric_data.return_value = {
        "MetricDataResults": [{"Id": "m0", "Values": [1.5]}]
    }

    def side_effect(sess, service, *args, **kwargs):
        cm = AsyncMock()
        cm.__aenter__.return_value = mock_ec2 if service == "ec2" else mock_cw
        return cm
    
    with patch.object(plugin, "_get_client", side_effect=side_effect), \
         patch.object(plugin, "_get_attribution", return_value="Unknown"):
        zombies = await plugin.scan(mock_session, "us-east-1")
        assert len(zombies) == 1
        assert zombies[0]["resource_id"] == "i-idle"
        assert zombies[0]["avg_cpu_percent"] == 1.5
