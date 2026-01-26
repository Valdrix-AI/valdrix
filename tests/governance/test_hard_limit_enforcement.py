import pytest
from uuid import uuid4
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch
from app.models.remediation import RemediationRequest, RemediationStatus, RemediationAction
from app.modules.optimization.domain.remediation_service import RemediationService
from app.shared.llm.usage_tracker import BudgetStatus

@pytest.mark.asyncio
async def test_enforce_hard_limit_auto_executes(db):
    """Verify that HARD_LIMIT triggers auto-execution of high-confidence requests."""
    tenant_id = uuid4()
    user_id = uuid4()
    
    # 1. Create a pending high-confidence request
    request = RemediationRequest(
        id=uuid4(),
        tenant_id=tenant_id,
        resource_id="vol-123",
        resource_type="ebs",
        action=RemediationAction.DELETE_VOLUME,
        status=RemediationStatus.PENDING,
        confidence_score=Decimal("0.95"),
        estimated_monthly_savings=Decimal("50.00"),
        requested_by_user_id=user_id
    )
    
    # 2. Mock DB to return this request
    db.execute = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [request]
    mock_execute_result = MagicMock()
    mock_execute_result.scalars.return_value = mock_scalars
    db.execute.return_value = mock_execute_result

    # 3. Mock UsageTracker to return HARD_LIMIT
    with patch("app.shared.llm.usage_tracker.UsageTracker.check_budget", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = BudgetStatus.HARD_LIMIT
        
        service = RemediationService(db)
        # Mock execute to avoid real AWS calls
        service.execute = AsyncMock()
        
        executed_ids = await service.enforce_hard_limit(tenant_id)
        
        # 4. Assertions
        assert len(executed_ids) == 1
        assert executed_ids[0] == request.id
        assert request.status == RemediationStatus.APPROVED
        assert "AUTO_APPROVED" in request.review_notes
        service.execute.assert_called_once_with(request.id, tenant_id, bypass_grace_period=True)

@pytest.mark.asyncio
async def test_enforce_hard_limit_ignores_low_confidence(db):
    """Verify that low-confidence requests are NOT auto-executed even if budget hit."""
    tenant_id = uuid4()
    
    # Mock UsageTracker to return HARD_LIMIT
    with patch("app.shared.llm.usage_tracker.UsageTracker.check_budget", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = BudgetStatus.HARD_LIMIT
        
        # Mock DB to return NO high-confidence requests
        db.execute = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_execute_result = MagicMock()
        mock_execute_result.scalars.return_value = mock_scalars
        db.execute.return_value = mock_execute_result
        
        service = RemediationService(db)
        service.execute = AsyncMock()
        
        executed_ids = await service.enforce_hard_limit(tenant_id)
        
        assert len(executed_ids) == 0
        service.execute.assert_not_called()
