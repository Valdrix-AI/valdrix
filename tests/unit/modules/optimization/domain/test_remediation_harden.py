import pytest
from unittest.mock import AsyncMock
from uuid import uuid4
from app.modules.optimization.domain.actions.base import RemediationContext, ExecutionStatus, ExecutionResult
from app.modules.optimization.domain.actions.aws.ec2 import AWSStopInstanceAction, AWSResizeInstanceAction
from app.shared.core.pricing import PricingTier

@pytest.mark.asyncio
async def test_tier_gating_free_tier_rejection():
    """Verify that remediation actions are rejected for FREE tier."""
    action = AWSStopInstanceAction()
    context = RemediationContext(
        tenant_id=uuid4(),
        region="us-east-1",
        tier=PricingTier.FREE.value
    )
    
    result = await action.execute("i-1234567890abcdef0", context)
    
    assert result.status == ExecutionStatus.SKIPPED
    assert "not enabled for tier 'free'" in result.error_message

@pytest.mark.asyncio
async def test_tier_gating_growth_tier_acceptance():
    """Verify that remediation actions are accepted for GROWTH tier."""
    # Mocking validate and perform_action to avoid real AWS calls
    action = AWSStopInstanceAction()
    action.validate = AsyncMock(return_value=True)
    action._perform_action = AsyncMock(return_value=ExecutionResult(
        status=ExecutionStatus.SUCCESS,
        resource_id="i-123",
        action_taken="STOP"
    ))
    
    context = RemediationContext(
        tenant_id=uuid4(),
        region="us-east-1",
        tier=PricingTier.GROWTH.value
    )
    
    result = await action.execute("i-123", context)
    
    assert result.status == ExecutionStatus.SUCCESS
    action._perform_action.assert_called_once()

@pytest.mark.asyncio
async def test_resize_validation_missing_params():
    """Verify that RESIZE action fails validation if parameters are missing."""
    action = AWSResizeInstanceAction()
    context = RemediationContext(
        tenant_id=uuid4(),
        region="us-east-1",
        tier=PricingTier.PRO.value,
        parameters={} # Missing target_instance_type
    )
    
    result = await action.execute("i-123", context)
    
    assert result.status == ExecutionStatus.SKIPPED
    assert "Validation failed" in result.error_message
@pytest.mark.asyncio
async def test_resize_success():
    """Verify that RESIZE action succeeds if parameters are provided."""
    action = AWSResizeInstanceAction()
    action._perform_action = AsyncMock(return_value=ExecutionResult(
        status=ExecutionStatus.SUCCESS,
        resource_id="i-123",
        action_taken="RESIZE"
    ))
    
    context = RemediationContext(
        tenant_id=uuid4(),
        region="us-east-1",
        tier=PricingTier.PRO.value,
        parameters={"target_instance_type": "t3.micro"}
    )
    
    result = await action.execute("i-123", context)
    
    assert result.status == ExecutionStatus.SUCCESS
    action._perform_action.assert_called_once()
