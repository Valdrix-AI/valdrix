import pytest
import datetime
from unittest.mock import MagicMock, AsyncMock, patch
from app.modules.optimization.domain.aws_provider.plugins.compute import IdleInstancesPlugin
from app.models.notification_settings import NotificationSettings  # Required for SQLAlchemy relationship resolution

@pytest.fixture
def mock_aws_session():
    session = MagicMock()
    # Mock for aioboto3 context managers
    context_manager = AsyncMock()
    session.client.return_value = context_manager
    return session, context_manager

@pytest.mark.asyncio
async def test_gpu_instance_detection_with_attribution():
    """
    Mock-First Test: Verifies that the refined plugin identifies 
    expensive GPU instances and correctly attributes ownership.
    """
    plugin = IdleInstancesPlugin()
    session = MagicMock()
    # 1. Mock EC2 Client
    mock_ec2 = MagicMock()
    mock_ec2.__aenter__ = AsyncMock(return_value=mock_ec2)
    mock_ec2.__aexit__ = AsyncMock()
    mock_ec2.get_paginator = MagicMock()
    mock_paginator = MagicMock()
    
    class AsyncIterator:
        def __init__(self, items):
            self.items = items
        def __aiter__(self):
            return self
        async def __anext__(self):
            if not self.items:
                raise StopAsyncIteration
            return self.items.pop(0)

    mock_paginator.paginate.return_value = AsyncIterator([{
        'Reservations': [{
            'Instances': [{
                'InstanceId': 'i-gpu-zombie-123',
                'InstanceType': 'g5.4xlarge', # GPU instance
                'LaunchTime': datetime.datetime.now(datetime.UTC),
                'Tags': []
            }]
        }]
    }])
    mock_ec2.get_paginator.return_value = mock_paginator
    
    # 2. Mock CloudWatch Client
    mock_cw = MagicMock()
    mock_cw.__aenter__ = AsyncMock(return_value=mock_cw)
    mock_cw.__aexit__ = AsyncMock()
    mock_cw.get_metric_data = AsyncMock(return_value={
        'MetricDataResults': [{
            'Id': 'm0',
            'Values': [1.5] # Low CPU for a G5 instance
        }]
    })
    
    # 3. Mock CloudTrail Client
    mock_ct = MagicMock()
    mock_ct.__aenter__ = AsyncMock(return_value=mock_ct)
    mock_ct.__aexit__ = AsyncMock()
    mock_ct.lookup_events = AsyncMock(return_value={
        'Events': [{'EventName': 'RunInstances', 'Username': 'ml-engineer-target'}]
    })

    # Setup the _get_client mock to return the correct client
    def mock_get_client(session_arg, service_name, region, creds, config=None):
        if service_name == "ec2":
            return mock_ec2
        if service_name == "cloudwatch":
            return mock_cw
        if service_name == "cloudtrail":
            return mock_ct
        return AsyncMock()

    with patch.object(IdleInstancesPlugin, '_get_client', side_effect=mock_get_client):
        zombies = await plugin.scan(session, "us-east-1")
        
        assert len(zombies) == 1
        zombie = zombies[0]
        assert zombie['is_gpu'] is True
        assert zombie['owner'] == 'ml-engineer-target'
        assert "HIGH PRIORITY: Expensive GPU instance detected" in zombie['explainability_notes']
        assert zombie['confidence_score'] == 0.99

@pytest.mark.asyncio
async def test_iac_plan_generation():
    """Verifies that the remediation service generates a valid TF plan."""
    from app.modules.optimization.domain.remediation_service import RemediationService
    from app.models.remediation import RemediationRequest, RemediationAction
    from decimal import Decimal
    
    db = AsyncMock()
    service = RemediationService(db)
    
    request = RemediationRequest(
        resource_id="i-123456789",
        resource_type="EC2 Instance",
        provider="aws",
        action=RemediationAction.STOP_INSTANCE,
        estimated_monthly_savings=Decimal("1500.00")
    )
    
    from uuid import uuid4
    from app.shared.core.pricing import PricingTier
    
    tenant_id = uuid4()
    
    with patch("app.shared.core.pricing.get_tenant_tier", new_callable=AsyncMock) as mock_tier:
        mock_tier.return_value = PricingTier.PRO
        
        plan = await service.generate_iac_plan(request, tenant_id)
        
        assert "terraform state rm aws_instance.i_123456789" in plan
        assert "removed {" in plan
        assert "destroy = true" in plan
        assert "$1500.00/mo" in plan
