
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
from datetime import datetime

# -----------------------------------------------------------------------------
# Test: OverprovisionedEc2Plugin
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_overprovisioned_ec2_plugin_scan(mock_aws_creds):
    """
    TDD: Verify detecting an "Active" but "Overprovisioned" EC2 instance.
    Scenario: Instance is 'running', CPU > 1% (Active), but Max CPU < 10% (Overprovisioned).
    """
    # Mock AWS SDKs globally/lazily
    with patch.dict(sys.modules, {
        "aioboto3": MagicMock(),
        "botocore.exceptions": MagicMock(),
    }):
        from app.modules.optimization.adapters.aws.plugins.rightsizing import OverprovisionedEc2Plugin
        
        plugin = OverprovisionedEc2Plugin()
        # Note: We might use a new category key or stick to "rightsizing" prefix
        assert plugin.category_key == "overprovisioned_ec2_instances"
        
        # Mock Session and Clients
        mock_session = MagicMock()
        mock_ec2_client = MagicMock()
        mock_cloudwatch_client = AsyncMock()
        
        def client_side_effect(service_name, **kwargs):
            ctx = AsyncMock()
            if service_name == "ec2":
                ctx.__aenter__.return_value = mock_ec2_client
            elif service_name == "cloudwatch":
                ctx.__aenter__.return_value = mock_cloudwatch_client
            return ctx
            
        mock_session.client.side_effect = client_side_effect

        # Mock Instances
        # Instance A: Running, Large Type
        mock_instance = {
            "InstanceId": "i-overprovisioned",
            "InstanceType": "m5.2xlarge", # Expensive!
            "State": {"Name": "running"},
            "Tags": [{"Key": "Name", "Value": "legacy-app"}]
        }
        
        # Paginator mock for describe_instances
        mock_paginator = MagicMock()
        async def _page_iterator():
            yield {"Reservations": [{"Instances": [mock_instance]}]}

        mock_paginator.paginate.return_value = _page_iterator()
        mock_ec2_client.get_paginator.return_value = mock_paginator
        
        # Mock Metrics
        # We need "Maximum" CPUUtilization over 7 days.
        # Scenario: Max is 8.5% (Under 10% threshold)
        async def get_metric_statistics_side_effect(**kwargs):
            metric_name = kwargs.get("MetricName")
            if metric_name == "CPUUtilization":
                return {
                    "Datapoints": [
                        {"Maximum": 8.5, "Timestamp": datetime.now()},
                        {"Maximum": 2.0, "Timestamp": datetime.now()}
                    ]
                }
            return {"Datapoints": []}

        mock_cloudwatch_client.get_metric_statistics.side_effect = get_metric_statistics_side_effect

        zombies = await plugin.scan(
            session=mock_session,
            credentials=mock_aws_creds,
            region="us-east-1"
        )

    assert len(zombies) == 1
    z = zombies[0]
    assert z["resource_id"] == "i-overprovisioned"
    assert z["resource_type"] == "AWS EC2 Instance"
    assert "m5.2xlarge" in z["explainability_notes"]
    assert "8.5%" in z["explainability_notes"] # Verify metric context
    assert z["action"] == "resize_ec2_instance" 
    # High confidence because we have metric data
    assert z["confidence_score"] > 0.8
