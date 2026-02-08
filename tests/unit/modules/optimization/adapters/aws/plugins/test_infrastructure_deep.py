import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import uuid
from datetime import datetime, timezone
import aioboto3
from botocore.exceptions import ClientError
from app.modules.optimization.adapters.aws.plugins.infrastructure import (
    StoppedInstancesWithEbsPlugin, UnusedLambdaPlugin, OrphanVpcEndpointsPlugin
)

@pytest.fixture
def mock_session():
    return MagicMock(spec=aioboto3.Session)

@pytest.mark.asyncio
async def test_stopped_instances_with_ebs_scan(mock_session):
    plugin = StoppedInstancesWithEbsPlugin()
    assert plugin.category_key == "stopped_instances_with_ebs"
    
    # Mock EC2 client
    mock_ec2 = MagicMock()
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value.__aiter__.return_value = [
        {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-123",
                            "State": {"Name": "stopped"},
                            "StateTransitionReason": "User initiated (2024-01-01 10:00:00 GMT)",
                            "BlockDeviceMappings": [
                                {
                                    "Ebs": {"VolumeId": "vol-123"}
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    ]
    mock_ec2.get_paginator.return_value = mock_paginator
    mock_ec2.describe_volumes = AsyncMock(return_value={
        "Volumes": [
            {
                "VolumeId": "vol-123",
                "Size": 100,
                "VolumeType": "gp3"
            }
        ]
    })
    
    mock_session.client.return_value.__aenter__.return_value = mock_ec2
    
    results = await plugin.scan(mock_session, "us-east-1")
    assert len(results) == 1
    assert results[0]["resource_id"] == "i-123"
    assert results[0]["monthly_cost"] > 0

@pytest.mark.asyncio
async def test_stopped_instances_unparseable_reason(mock_session):
    plugin = StoppedInstancesWithEbsPlugin()
    mock_ec2 = MagicMock()
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value.__aiter__.return_value = [{
        "Reservations": [{"Instances": [{
            "InstanceId": "i-unparseable",
            "StateTransitionReason": "Something weird without date",
            "BlockDeviceMappings": [{"Ebs": {"VolumeId": "vol-456"}}]
        }]}]
    }]
    mock_ec2.get_paginator.return_value = mock_paginator
    mock_ec2.describe_volumes = AsyncMock(return_value={"Volumes": [{"VolumeId": "vol-456", "Size": 10, "VolumeType": "gp2"}]})
    mock_session.client.return_value.__aenter__.return_value = mock_ec2
    
    results = await plugin.scan(mock_session, "us-east-1")
    assert len(results) == 1

@pytest.mark.asyncio
async def test_unused_lambda_scan_none(mock_session):
    """Test Lambda with invocations (not a zombie)."""
    plugin = UnusedLambdaPlugin()
    assert plugin.category_key == "unused_lambda_functions"
    
    mock_lambda = MagicMock()
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value.__aiter__.return_value = [{"Functions": [{"FunctionName": "active-func"}]}]
    mock_lambda.get_paginator.return_value = mock_paginator
    
    mock_cw = MagicMock()
    # Mock invocations > 0 (e.g. 5)
    mock_cw.get_metric_statistics = AsyncMock(return_value={"Datapoints": [{"Sum": 5.0}]})
    
    def side_effect(service, *args, **kwargs):
        if service == 'lambda': return mock_lambda
        if service == 'cloudwatch': return mock_cw
        return MagicMock()

    mock_session.client.side_effect = lambda s, **kw: MagicMock(__aenter__=AsyncMock(return_value=side_effect(s)))
    results = await plugin.scan(mock_session, "us-east-1")
    assert len(results) == 0

@pytest.mark.asyncio
async def test_orphan_vpc_endpoints_scan_none(mock_session):
    """Test VPC Endpoint with traffic (not a zombie)."""
    plugin = OrphanVpcEndpointsPlugin()
    assert plugin.category_key == "orphan_vpc_endpoints"
    
    mock_ec2 = MagicMock()
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value.__aiter__.return_value = [{
        "VpcEndpoints": [{"VpcEndpointId": "vpce-active", "VpcEndpointType": "Interface", "ServiceName": "s3", "SubnetIds": ["sn-1"]}]
    }]
    mock_ec2.get_paginator.return_value = mock_paginator
    
    mock_cw = MagicMock()
    # Mock traffic > 0
    mock_cw.get_metric_statistics = AsyncMock(return_value={"Datapoints": [{"Sum": 100.0}]})
    
    def side_effect(service, *args, **kwargs):
        if service == 'ec2': return mock_ec2
        if service == 'cloudwatch': return mock_cw
        return MagicMock()

    mock_session.client.side_effect = lambda s, **kw: MagicMock(__aenter__=AsyncMock(return_value=side_effect(s)))
    results = await plugin.scan(mock_session, "us-east-1")
    assert len(results) == 0

@pytest.mark.asyncio
async def test_vpc_endpoint_gateway_skipped(mock_session):
    """Test Gateway endpoint is skipped."""
    plugin = OrphanVpcEndpointsPlugin()
    mock_ec2 = MagicMock()
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value.__aiter__.return_value = [{
        "VpcEndpoints": [{"VpcEndpointId": "vpce-gw", "VpcEndpointType": "Gateway", "ServiceName": "s3"}]
    }]
    mock_ec2.get_paginator.return_value = mock_paginator
    mock_session.client.return_value.__aenter__.return_value = mock_ec2
    results = await plugin.scan(mock_session, "us-east-1")
    assert len(results) == 0

@pytest.mark.asyncio
async def test_lambda_scan_full_error(mock_session):
    """Test full scan error (line 197-198)."""
    plugin = UnusedLambdaPlugin()
    mock_session.client.side_effect = ClientError({"Error": {"Code": "500", "Message": "Fail"}}, "client")
    results = await plugin.scan(mock_session, "us-east-1")
    assert len(results) == 0

@pytest.mark.asyncio
async def test_vpc_scan_full_error(mock_session):
    """Test full VPC scan error (line 282-283)."""
    plugin = OrphanVpcEndpointsPlugin()
    mock_session.client.side_effect = ClientError({"Error": {"Code": "500", "Message": "Fail"}}, "client")
    results = await plugin.scan(mock_session, "us-east-1")
    assert len(results) == 0

@pytest.mark.asyncio
async def test_stopped_instances_malformed_date(mock_session):
    plugin = StoppedInstancesWithEbsPlugin()
    mock_ec2 = MagicMock()
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value.__aiter__.return_value = [{
        "Reservations": [{"Instances": [{
            "InstanceId": "i-malformed",
            "StateTransitionReason": "User initiated (INVALID_DATE)",
            "BlockDeviceMappings": [{"Ebs": {"VolumeId": "vol-789"}}]
        }]}]
    }]
    mock_ec2.get_paginator.return_value = mock_paginator
    mock_ec2.describe_volumes = AsyncMock(return_value={"Volumes": [{"VolumeId": "vol-789", "Size": 10, "VolumeType": "gp2"}]})
    mock_session.client.return_value.__aenter__.return_value = mock_ec2
    results = await plugin.scan(mock_session, "us-east-1")
    # Should default to 30 days
    assert len(results) == 1

@pytest.mark.asyncio
async def test_stopped_instances_client_error(mock_session):
    plugin = StoppedInstancesWithEbsPlugin()
    mock_ec2 = MagicMock()
    mock_ec2.get_paginator.return_value.paginate.return_value.__aiter__.return_value = [{
        "Reservations": [{"Instances": [{
            "InstanceId": "i-err",
            "StateTransitionReason": "User initiated (2024-01-01 10:00:00 GMT)",
            "BlockDeviceMappings": [{"Ebs": {"VolumeId": "vol-err"}}]
        }]}]
    }]
    mock_ec2.describe_volumes = AsyncMock(side_effect=ClientError({"Error": {"Code": "AccessDenied", "Message": "Denied"}}, "describe_volumes"))
    mock_session.client.return_value.__aenter__.return_value = mock_ec2
    
    results = await plugin.scan(mock_session, "us-east-1")
    assert len(results) == 1
    assert results[0]["monthly_cost"] == 10.0
