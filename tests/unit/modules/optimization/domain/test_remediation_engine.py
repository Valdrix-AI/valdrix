import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.models.remediation import RemediationAction
from app.modules.optimization.domain.actions.base import RemediationContext, ExecutionStatus
from app.modules.optimization.domain.actions.factory import RemediationActionFactory
from app.modules.optimization.domain.actions.aws.ec2 import AWSStopInstanceAction, AWSTerminateInstanceAction


class AsyncContextManagerMock:
    def __init__(self, obj):
        self.obj = obj

    async def __aenter__(self):
        return self.obj

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


@pytest.fixture
def mock_context():
    return RemediationContext(
        tenant_id=MagicMock(),
        region="us-east-1",
        tier="growth",
        credentials={"aws_access_key_id": "test"},
        db_session=MagicMock()
    )


def test_factory_registration():
    # Verify that EC2 strategies are correctly registered
    stop_strategy = RemediationActionFactory.get_strategy("aws", RemediationAction.STOP_INSTANCE)
    assert isinstance(stop_strategy, AWSStopInstanceAction)

    terminate_strategy = RemediationActionFactory.get_strategy("aws", RemediationAction.TERMINATE_INSTANCE)
    assert isinstance(terminate_strategy, AWSTerminateInstanceAction)


def test_factory_invalid_lookup():
    with pytest.raises(ValueError, match="No remediation strategy registered"):
        RemediationActionFactory.get_strategy("azure", RemediationAction.STOP_INSTANCE)


@pytest.mark.asyncio
async def test_aws_stop_instance_success(mock_context):
    strategy = AWSStopInstanceAction()
    
    with patch.object(strategy, "_get_client", new=AsyncMock()) as mock_get_client:
        mock_ec2 = MagicMock()
        mock_ec2.stop_instances = AsyncMock()
        mock_get_client.return_value = AsyncContextManagerMock(mock_ec2)
        
        result = await strategy.execute("i-12345", mock_context)
        
        assert result.status == ExecutionStatus.SUCCESS
        assert result.resource_id == "i-12345"
        mock_ec2.stop_instances.assert_awaited_once_with(InstanceIds=["i-12345"])


@pytest.mark.asyncio
async def test_aws_stop_instance_failure(mock_context):
    strategy = AWSStopInstanceAction()
    
    with patch.object(strategy, "_get_client", new=AsyncMock()) as mock_get_client:
        mock_ec2 = MagicMock()
        mock_ec2.stop_instances = AsyncMock(side_effect=Exception("API Error"))
        mock_get_client.return_value = AsyncContextManagerMock(mock_ec2)
        
        result = await strategy.execute("i-12345", mock_context)
        
        assert result.status == ExecutionStatus.FAILED
        assert "API Error" in result.error_message
