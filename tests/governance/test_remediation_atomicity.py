import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from app.modules.optimization.domain.remediation_service import RemediationService
from app.models.remediation import (
    RemediationRequest,
    RemediationStatus,
    RemediationAction,
)
from app.modules.governance.domain.security.audit_log import AuditEventType
from app.shared.core.pricing import PricingTier


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def remediation_service(mock_db):
    return RemediationService(db=mock_db)


@pytest.mark.asyncio
async def test_execute_fails_if_backup_fails(remediation_service, mock_db):
    """
    BE-ZD-1: Verify that remediation aborts and resource is NOT deleted
    if the pre-deletion backup fails.
    """
    tenant_id = uuid4()
    request_id = uuid4()

    # Setup mock request - Start with SCHEDULED in the past to bypass grace period
    request = RemediationRequest(
        id=request_id,
        tenant_id=tenant_id,
        resource_id="vol-12345",
        resource_type="volume",
        provider="aws",
        action=RemediationAction.DELETE_VOLUME,
        status=RemediationStatus.SCHEDULED,
        scheduled_execution_at=datetime.now(timezone.utc) - timedelta(hours=1),
        create_backup=True,
        reviewed_by_user_id=uuid4(),
    )

    # Mock DB query
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = request
    mock_db.execute.return_value = mock_result

    # Mock backup failure
    with (
        patch(
            "app.modules.optimization.domain.actions.aws.volumes.AWSDeleteVolumeAction.create_backup",
            side_effect=Exception("BACKUP_FAILED: AWS Backup Error"),
        ),
        patch(
            "app.modules.optimization.domain.remediation.get_tenant_tier", return_value=PricingTier.PRO
        ),
        patch(
            "app.modules.optimization.domain.remediation.SafetyGuardrailService"
        ) as mock_safety_cls,
    ):
        mock_safety_cls.return_value.check_all_guards = AsyncMock()

        # Mock deletion action to track if it's called
        with patch(
            "app.modules.optimization.domain.actions.aws.volumes.AWSDeleteVolumeAction._perform_action",
            AsyncMock(),
        ) as mock_delete:
            # Mock AuditLogger to verify logging
            with patch(
                "app.modules.optimization.domain.remediation.AuditLogger"
            ) as MockAuditLogger:
                mock_audit = AsyncMock()
                MockAuditLogger.return_value = mock_audit

                # EXECUTE
                updated_request = await remediation_service.execute(
                    request_id, tenant_id
                )

                # ASSERTIONS
                assert updated_request.status == RemediationStatus.FAILED
                assert "BACKUP_FAILED" in updated_request.execution_error

                # CRITICAL: Resource deletion must NOT have been called
                mock_delete.assert_not_called()

                # Verify audit logging
                # 1. Verification of STARTED log
                # 2. Verification of FAILED log
                assert mock_audit.log.call_count >= 2

                calls = [c[1]["event_type"] for c in mock_audit.log.call_args_list]
                assert AuditEventType.REMEDIATION_EXECUTION_STARTED in calls
                assert AuditEventType.REMEDIATION_EXECUTED in calls


@pytest.mark.asyncio
async def test_execute_success_with_audit_trail(remediation_service, mock_db):
    """
    BE-ZD-1: Verify full success path with proper audit trail.
    """
    tenant_id = uuid4()
    request_id = uuid4()

    # Setup mock request - Start with SCHEDULED in the past to bypass grace period
    request = RemediationRequest(
        id=request_id,
        tenant_id=tenant_id,
        resource_id="vol-12345",
        resource_type="volume",
        provider="aws",
        action=RemediationAction.DELETE_VOLUME,
        status=RemediationStatus.SCHEDULED,
        scheduled_execution_at=datetime.now(timezone.utc) - timedelta(hours=1),
        create_backup=True,
        reviewed_by_user_id=uuid4(),
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = request
    mock_db.execute.return_value = mock_result

    with (
        patch(
            "app.modules.optimization.domain.actions.aws.volumes.AWSDeleteVolumeAction.create_backup",
            AsyncMock(return_value="snap-123"),
        ),
        patch(
            "app.modules.optimization.domain.remediation.get_tenant_tier", return_value=PricingTier.PRO
        ),
        patch(
            "app.modules.optimization.domain.remediation.SafetyGuardrailService"
        ) as mock_safety_cls,
    ):
        mock_safety_cls.return_value.check_all_guards = AsyncMock()

        with patch(
            "app.modules.optimization.domain.actions.aws.volumes.AWSDeleteVolumeAction._perform_action",
            new_callable=AsyncMock,
        ) as mock_delete:
            from app.modules.optimization.domain.actions.base import ExecutionResult, ExecutionStatus
            mock_delete.return_value = ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                resource_id="vol-12345",
                action_taken="DELETE_VOLUME"
            )
            with patch(
                "app.modules.optimization.domain.remediation.AuditLogger"
            ) as MockAuditLogger:
                mock_audit = AsyncMock()
                MockAuditLogger.return_value = mock_audit

                # EXECUTE
                updated_request = await remediation_service.execute(
                    request_id, tenant_id
                )

                # ASSERTIONS
                assert updated_request.status == RemediationStatus.COMPLETED
                assert updated_request.backup_resource_id == "snap-123"

                # Resource deletion was called
                mock_delete.assert_called_once()

                # Audit trail
                calls = [c[1]["event_type"] for c in mock_audit.log.call_args_list]
                assert AuditEventType.REMEDIATION_EXECUTION_STARTED in calls
                assert AuditEventType.REMEDIATION_EXECUTED in calls
