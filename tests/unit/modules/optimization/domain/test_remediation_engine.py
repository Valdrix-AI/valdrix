import pytest
from unittest.mock import MagicMock, patch
from app.models.remediation import RemediationAction
from app.modules.optimization.domain.actions.base import RemediationContext, ExecutionResult, ExecutionStatus
from app.modules.optimization.domain.actions.factory import RemediationActionFactory
from app.modules.optimization.domain.actions.aws.ec2 import AWSStopInstanceAction, AWSTerminateInstanceAction


@pytest.fixture
def mock_context():
    return RemediationContext(
        tenant_id=MagicMock(),
        region="us-east-1",
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
    
    with patch.object(strategy, "_get_client") as mock_get_client:
        mock_ec2 = MagicMock()
        mock_ec2.stop_instances = MagicMock()
        # aioboto3 uses async context manager
        mock_get_client.return_value.__aenter__.return_value = mock_ec2
        
        result = await strategy.execute("i-12345", mock_context)
        
        assert result.status == ExecutionStatus.SUCCESS
        assert result.resource_id == "i-12345"
        mock_ec2.stop_instances.assert_called_once_with(InstanceIds=["i-12345"])


@pytest.mark.asyncio
async def test_aws_stop_instance_failure(mock_context):
    strategy = AWSStopInstanceAction()
    
    with patch.object(strategy, "_get_client") as mock_get_client:
        mock_ec2 = MagicMock()
        mock_ec2.stop_instances.side_effect = Exception("API Error")
        mock_get_client.return_value.__aenter__.return_value = mock_ec2
        
        result = await strategy.execute("i-12345", mock_context)
        
        assert result.status == ExecutionStatus.FAILED
        assert "API Error" in result.error_message
