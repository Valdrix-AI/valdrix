import pytest
from uuid import uuid4
from decimal import Decimal
from unittest.mock import MagicMock, patch, AsyncMock
from app.modules.optimization.domain.remediation import RemediationService
from app.shared.core.exceptions import KillSwitchTriggeredError
from app.models.remediation import RemediationStatus, RemediationAction
from app.modules.optimization.domain.actions.base import ExecutionResult, ExecutionStatus
from app.shared.core.pricing import PricingTier


@pytest.mark.asyncio
async def test_remediation_kill_switch_triggered():
    """
    Test that the remediation kill switch blocks execution when the daily limit is hit.
    """
    # Arrange
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    service = RemediationService(db)
    tenant_id = uuid4()
    request_id = uuid4()

    mock_request = MagicMock()
    mock_request.id = request_id
    mock_request.tenant_id = tenant_id
    mock_request.status = RemediationStatus.APPROVED
    mock_request.action = RemediationAction.STOP_INSTANCE
    mock_request.resource_id = "i-123"
    mock_request.resource_type = "EC2 Instance"
    mock_request.provider = "aws"
    mock_request.estimated_monthly_savings = Decimal("50.0")

    mock_request_result = MagicMock()
    mock_request_result.scalar_one_or_none.return_value = mock_request
    db.execute.return_value = mock_request_result

    with (
        patch(
            "app.modules.optimization.domain.remediation.get_tenant_tier",
            new_callable=AsyncMock,
            return_value=PricingTier.PRO,
        ),
        patch(
            "app.modules.optimization.domain.remediation.AuditLogger.log",
            new_callable=AsyncMock,
        ),
        patch(
            "app.modules.optimization.domain.remediation.SafetyGuardrailService"
        ) as mock_safety,
    ):
        mock_safety.return_value.check_all_guards = AsyncMock(
            side_effect=KillSwitchTriggeredError("Safety kill-switch triggered")
        )
        result = await service.execute(request_id, tenant_id, bypass_grace_period=True)

    assert result.status == RemediationStatus.FAILED
    assert "Safety kill-switch triggered" in (result.execution_error or "")


@pytest.mark.asyncio
async def test_remediation_kill_switch_not_triggered():
    """
    Test that remediation proceeds when below the kill switch threshold.
    """
    # Arrange
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    service = RemediationService(db)
    tenant_id = uuid4()
    request_id = uuid4()

    mock_request = MagicMock()
    mock_request.id = request_id
    mock_request.tenant_id = tenant_id
    mock_request.status = RemediationStatus.APPROVED
    mock_request.action = RemediationAction.STOP_INSTANCE
    mock_request.resource_id = "i-123"
    mock_request.resource_type = "EC2 Instance"
    mock_request.provider = "aws"
    mock_request.estimated_monthly_savings = Decimal("25.0")

    mock_request_result = MagicMock()
    mock_request_result.scalar_one_or_none.return_value = mock_request

    db.execute.return_value = mock_request_result

    with (
        patch(
            "app.modules.optimization.domain.remediation.get_tenant_tier",
            new_callable=AsyncMock,
            return_value=PricingTier.PRO,
        ),
        patch(
            "app.modules.optimization.domain.remediation.AuditLogger.log",
            new_callable=AsyncMock,
        ),
        patch(
            "app.modules.optimization.domain.remediation.SafetyGuardrailService"
        ) as mock_safety,
        patch(
            "app.modules.optimization.domain.remediation.RemediationActionFactory.get_strategy"
        ) as mock_get_strategy,
        patch(
            "app.shared.core.notifications.NotificationDispatcher.notify_remediation_completed",
            new_callable=AsyncMock,
        ),
    ):
        mock_safety.return_value.check_all_guards = AsyncMock(return_value=None)
        strategy = MagicMock()
        strategy.execute = AsyncMock(
            return_value=ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                resource_id=mock_request.resource_id,
                action_taken=mock_request.action.value,
            )
        )
        mock_get_strategy.return_value = strategy

        result = await service.execute(request_id, tenant_id, bypass_grace_period=True)

    assert result.status == RemediationStatus.COMPLETED
