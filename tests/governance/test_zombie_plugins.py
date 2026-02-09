import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone
import aioboto3

from app.modules.optimization.adapters.aws.plugins.network import UnderusedNatGatewaysPlugin
from app.modules.optimization.adapters.aws.plugins.containers import LegacyEcrImagesPlugin

@pytest.mark.asyncio
async def test_nat_gateway_plugin_idle():
    plugin = UnderusedNatGatewaysPlugin()
    session = MagicMock(spec=aioboto3.Session())
    
    # Mock EC2 client (S3, EC2 etc are mostly sync methods returning async objects)
    mock_ec2 = MagicMock()
    mock_paginator = MagicMock()
    # paginator.paginate() is sync, returns async iterator
    
    # Mock CloudWatch client
    mock_cw = MagicMock()
    mock_cw.get_metric_statistics = AsyncMock(return_value={
        "Datapoints": [{"Sum": 50}]  # Under 100 threshold
    })
    
    class AsyncContextManagerMock:
        def __init__(self, obj):
            self.obj = obj
        async def __aenter__(self):
            return self.obj
        async def __aexit__(self, exc_type, exc, tb):
            pass

    class AsyncIteratorMock:
        def __init__(self, items):
            self.items = items
        def __aiter__(self):
            return self
        async def __anext__(self):
            if not self.items:
                raise StopAsyncIteration
            return self.items.pop(0)

    with patch.object(plugin, "_get_client") as mock_get_client:
        mock_get_client.side_effect = [
            AsyncContextManagerMock(mock_ec2),
            AsyncContextManagerMock(mock_cw)
        ]
        
        mock_ec2.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = AsyncIteratorMock([
            {"NatGateways": [{"NatGatewayId": "nat-123", "State": "available"}]}
        ])
        
        results = await plugin.scan(session, "us-east-1")
        
        assert len(results) == 1
        assert results[0]["resource_id"] == "nat-123"

@pytest.mark.asyncio
async def test_ecr_legacy_images_plugin():
    plugin = LegacyEcrImagesPlugin()
    session = MagicMock(spec=aioboto3.Session())
    
    # Mock ECR client
    mock_ecr = MagicMock()
    repo_paginator = MagicMock()
    img_paginator = MagicMock()
    
    old_date = datetime.now(timezone.utc) - timedelta(days=40)
    
    class AsyncContextManagerMock:
        def __init__(self, obj):
            self.obj = obj
        async def __aenter__(self):
            return self.obj
        async def __aexit__(self, exc_type, exc, tb):
            pass

    class AsyncIteratorMock:
        def __init__(self, items):
            self.items = items
        def __aiter__(self):
            return self
        async def __anext__(self):
            if not self.items:
                raise StopAsyncIteration
            return self.items.pop(0)

    with patch.object(plugin, "_get_client") as mock_get_client:
        mock_get_client.return_value = AsyncContextManagerMock(mock_ecr)
        
        mock_ecr.get_paginator.side_effect = lambda x: repo_paginator if x == "describe_repositories" else img_paginator
        
        repo_paginator.paginate.return_value = AsyncIteratorMock([
            {"repositories": [{"repositoryName": "repo-1"}]}
        ])
        
        img_paginator.paginate.return_value = AsyncIteratorMock([
            {"imageDetails": [
                {
                    "imageDigest": "sha256:123",
                    "imagePushedAt": old_date,
                    "imageSizeInBytes": 1024 * 1024 * 100,
                }
            ]}
        ])
        
        results = await plugin.scan(session, "us-east-1")
        
        assert len(results) == 1
        assert "repo-1@sha256:123" in results[0]["resource_id"]
