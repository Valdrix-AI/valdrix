import pytest
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch
from app.modules.optimization.domain.remediation import (
    RemediationService,
    RemediationAction,
)
from app.models.remediation import RemediationStatus
from app.modules.optimization.domain.actions.base import ExecutionResult, ExecutionStatus


@pytest.fixture
def mock_db():
    db = MagicMock()
    # default result for safety checks
    mock_result = MagicMock()
    mock_result.scalar.return_value = Decimal("0")
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock()
    db.execute.return_value = mock_result
    db.add = MagicMock()
    db.add_all = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def remediation_service(mock_db):
    return RemediationService(mock_db)


class AsyncContextManagerMock:
    def __init__(self, obj):
        self.obj = obj

    async def __aenter__(self):
        return self.obj

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


@pytest.mark.asyncio
async def test_execute_remediation_error_handling(remediation_service, mock_db):
    """Test error handling in execute."""
    remediation_id = uuid.uuid4()
    mock_remediation = MagicMock()
    mock_remediation.id = remediation_id
    mock_remediation.status = RemediationStatus.APPROVED
    mock_remediation.resource_id = "i-123"
    mock_remediation.action = RemediationAction.STOP_INSTANCE
    mock_remediation.provider = "aws"
    mock_remediation.resource_type = "EC2 Instance"
    mock_remediation.region = "us-east-1"
    mock_remediation.tenant_id = uuid.uuid4()
    mock_remediation.reviewed_by_user_id = uuid.uuid4()
    mock_remediation.create_backup = False
    mock_remediation.estimated_monthly_savings = Decimal("10.0")
    mock_remediation.execution_error = None

    # Mock DB results for BOTH the main query and safety checks
    mock_result_main = MagicMock()
    mock_result_main.scalar_one_or_none.return_value = mock_remediation

    mock_result_safety = MagicMock()
    mock_result_safety.scalar.return_value = Decimal("0")
    mock_result_safety.scalar_one_or_none.return_value = None  # No settings

    async def db_side_effect(query, *args, **kwargs):
        query_str = str(query).lower()
        if "remediation_requests" in query_str:
            return mock_result_main
        return mock_result_safety

    mock_db.execute.side_effect = db_side_effect

    with patch(
        "app.modules.optimization.domain.remediation.RemediationActionFactory.get_strategy"
    ) as mock_get_strategy, patch(
        "app.modules.optimization.domain.remediation.SafetyGuardrailService", autospec=True
    ) as mock_safety_cls:
        mock_safety = mock_safety_cls.return_value
        mock_safety.check_all_guards = AsyncMock()

        mock_strategy = AsyncMock()
        mock_strategy.execute = AsyncMock(
            return_value=ExecutionResult(
                status=ExecutionStatus.FAILED,
                resource_id="i-123",
                action_taken=RemediationAction.STOP_INSTANCE.value,
                error_message="Execution failed",
            )
        )
        mock_get_strategy.return_value = mock_strategy

        await remediation_service.execute(
            remediation_id, mock_remediation.tenant_id, bypass_grace_period=True
        )

    assert mock_remediation.status == RemediationStatus.FAILED
    assert "Execution failed" in mock_remediation.execution_error


@pytest.mark.asyncio
async def test_remediation_with_backup_and_verify(remediation_service, mock_db):
    """Test remediation flow including backup steps."""
    remediation_id = uuid.uuid4()
    mock_remediation = MagicMock()
    mock_remediation.id = remediation_id
    mock_remediation.status = RemediationStatus.APPROVED
    mock_remediation.resource_id = "vol-123"
    mock_remediation.action = RemediationAction.DELETE_VOLUME
    mock_remediation.provider = "aws"
    mock_remediation.resource_type = "EBS Volume"
    mock_remediation.region = "us-east-1"
    mock_remediation.tenant_id = uuid.uuid4()
    mock_remediation.reviewed_by_user_id = uuid.uuid4()
    mock_remediation.create_backup = True
    mock_remediation.backup_retention_days = 7
    mock_remediation.estimated_monthly_savings = Decimal("10.0")
    mock_remediation.execution_error = None

    mock_result_main = MagicMock()
    mock_result_main.scalar_one_or_none.return_value = mock_remediation
    mock_result_safety = MagicMock()
    mock_result_safety.scalar.return_value = Decimal("0")
    mock_result_safety.scalar_one_or_none.return_value = None

    # Provide enough results
    mock_db.execute.side_effect = [
        mock_result_main,
        mock_result_safety,
        mock_result_safety,
        mock_result_safety,
        mock_result_safety,
        mock_result_safety,
        mock_result_safety,
        mock_result_safety,
    ]

    with patch(
        "app.modules.optimization.domain.remediation.RemediationActionFactory.get_strategy"
    ) as mock_get_strategy, patch(
        "app.modules.optimization.domain.remediation.SafetyGuardrailService", autospec=True
    ) as mock_safety_cls:
        mock_safety = mock_safety_cls.return_value
        mock_safety.check_all_guards = AsyncMock()

        mock_strategy = AsyncMock()
        mock_strategy.execute = AsyncMock(
            return_value=ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                resource_id="vol-123",
                action_taken=RemediationAction.DELETE_VOLUME.value,
                backup_id="snap-123",
            )
        )
        mock_get_strategy.return_value = mock_strategy
        
        # Override db.execute to handle specific calls:
        # 1. Fetch Request
        # 2. get_tenant_tier
        # 3. _get_remediation_settings (twice: building config and building policy config in execute)
        # 4. _apply_system_policy_context (multiple)
        # We use side_effect with a generator or a list to be safe.
        async def db_side_effect(query, *args, **kwargs):
            query_str = str(query).lower()
            if "remediation_requests" in query_str:
                return mock_result_main
            return mock_result_safety
            
        mock_db.execute.side_effect = db_side_effect

        with patch(
            "app.shared.core.notifications.NotificationDispatcher.notify_remediation_completed",
            new=AsyncMock(),
        ), patch(
            "app.shared.core.notifications.NotificationDispatcher.notify_remediation_started",
            new=AsyncMock(),
        ):
            await remediation_service.execute(
                remediation_id, mock_remediation.tenant_id, bypass_grace_period=True
            )
    assert mock_remediation.status == RemediationStatus.COMPLETED
    assert mock_remediation.backup_resource_id == "snap-123"
