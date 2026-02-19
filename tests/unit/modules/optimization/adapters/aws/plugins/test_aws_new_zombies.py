
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta, timezone
from botocore.exceptions import ClientError

from app.modules.optimization.adapters.aws.plugins.security import CustomerManagedKeysPlugin
from app.modules.optimization.adapters.aws.plugins.network import IdleCloudFrontPlugin



@pytest.mark.asyncio
async def test_customer_managed_keys_plugin():
    plugin = CustomerManagedKeysPlugin()
    assert plugin.category_key == "customer_managed_kms_keys"

    # Mock KMS Client
    mock_kms = AsyncMock()
    
    # Mock List Keys
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [
        {"Keys": [{"KeyId": "key-1"}, {"KeyId": "key-2"}]}
    ]
    mock_kms.get_paginator.return_value = mock_paginator

    # Mock Describe Key
    async def describe_key_side_effect(KeyId):
        if KeyId == "key-1":
            return {"KeyMetadata": {"KeyManager": "CUSTOMER", "KeyState": "Enabled"}}
        else:
            return {"KeyMetadata": {"KeyManager": "AWS", "KeyState": "Enabled"}}
    
    mock_kms.describe_key.side_effect = describe_key_side_effect

    # Mock List Aliases
    mock_kms.list_aliases.return_value = {"Aliases": [{"AliasName": "alias/test-key"}]}

    # Mock Session Context Manager
    mock_session = MagicMock()
    # Correctly mock the async context manager for the client
    mock_session.client.return_value.__aenter__.return_value = mock_kms

    zombies = await plugin.scan(session=mock_session, region="us-east-1")

    assert len(zombies) == 1
    assert zombies[0]["resource_id"] == "key-1"
    assert zombies[0]["monthly_cost"] == 1.00
    assert zombies[0]["resource_name"] == "alias/test-key"


@pytest.mark.asyncio
async def test_idle_cloudfront_plugin():
    plugin = IdleCloudFrontPlugin()
    assert plugin.category_key == "idle_cloudfront_distributions"

    # Test region filter (only scans us-east-1)
    zombies_wrong_region = await plugin.scan(session=None, region="us-west-2")
    assert zombies_wrong_region == []

    # Mock Clients
    mock_cf = AsyncMock()
    mock_cw = AsyncMock()

    # Mock List Distributions
    mock_paginator = MagicMock()
    # Async iterator for paginate
    async def async_paginate():
        yield {
            "DistributionList": {
                "Items": [
                    {"Id": "dist-1", "Enabled": True, "DomainName": "example.com"},
                    {"Id": "dist-2", "Enabled": False, "DomainName": "disabled.com"},
                ]
            }
        }
    
    mock_paginator.paginate.side_effect = async_paginate
    mock_cf.get_paginator.return_value = mock_paginator

    # Mock CloudWatch Metrics
    mock_cw.get_metric_statistics.return_value = {
        "Datapoints": [{"Sum": 99}]
    }

    # Mock Session Context Managers
    mock_session = MagicMock()
    
    # Side effect for client creation
    def client_side_effect(service_name, region_name, **kwargs):
        mock_ctx = AsyncMock()
        if service_name == "cloudfront":
            mock_ctx.__aenter__.return_value = mock_cf
        elif service_name == "cloudwatch":
            mock_ctx.__aenter__.return_value = mock_cw
        return mock_ctx

    mock_session.client.side_effect = client_side_effect

    zombies = await plugin.scan(session=mock_session, region="us-east-1")

    assert len(zombies) == 1
    assert zombies[0]["resource_id"] == "dist-1"
    assert "99 requests" in zombies[0]["explainability_notes"]

