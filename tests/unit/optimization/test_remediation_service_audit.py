import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from decimal import Decimal
from app.modules.optimization.domain.remediation import (
    RemediationService,
    RemediationStatus,
    RemediationAction,
)
from app.models.remediation import RemediationRequest


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.refresh = AsyncMock()
    db.merge = AsyncMock()
    return db


@pytest.fixture
def tenant_id():
    return uuid4()


@pytest.fixture
def user_id():
    return uuid4()


@pytest.mark.asyncio
async def test_create_remediation_request(mock_db, tenant_id, user_id):
    service = RemediationService(mock_db)

    # Mock connection check bypass or return None
    mock_db.execute.return_value.scalar_one_or_none.return_value = None

    request = await service.create_request(
        tenant_id=tenant_id,
        user_id=user_id,
        resource_id="vol-123",
        resource_type="EBS Volume",
        action=RemediationAction.DELETE_VOLUME,
        estimated_savings=15.5,
    )

    assert request.tenant_id == tenant_id
    assert request.resource_id == "vol-123"
    assert request.status == RemediationStatus.PENDING
    assert request.estimated_monthly_savings == Decimal("15.5")
    assert mock_db.add.called
    assert mock_db.commit.called


@pytest.mark.asyncio
async def test_approve_remediation(mock_db, tenant_id):
    service = RemediationService(mock_db)

    req = RemediationRequest(
        id=uuid4(), tenant_id=tenant_id, status=RemediationStatus.PENDING
    )
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = req
    mock_db.execute.return_value = mock_res

    reviewer_id = uuid4()
    approved = await service.approve(req.id, tenant_id, reviewer_id, notes="Approved")

    assert approved.status == RemediationStatus.APPROVED
    assert approved.reviewed_by_user_id == reviewer_id
    assert approved.review_notes == "Approved"
    assert mock_db.commit.called
    stmt = mock_db.execute.call_args[0][0]
    assert stmt._for_update_arg is not None


@pytest.mark.asyncio
async def test_reject_remediation_uses_row_lock(mock_db, tenant_id):
    service = RemediationService(mock_db)

    req = RemediationRequest(
        id=uuid4(), tenant_id=tenant_id, status=RemediationStatus.PENDING
    )
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = req
    mock_db.execute.return_value = mock_res

    reviewer_id = uuid4()
    rejected = await service.reject(req.id, tenant_id, reviewer_id, notes="Rejected")

    assert rejected.status == RemediationStatus.REJECTED
    assert rejected.reviewed_by_user_id == reviewer_id
    stmt = mock_db.execute.call_args[0][0]
    assert stmt._for_update_arg is not None


@pytest.mark.asyncio
async def test_execute_approved_triggers_grace_period(mock_db, tenant_id):
    service = RemediationService(mock_db)

    req = RemediationRequest(
        id=uuid4(),
        tenant_id=tenant_id,
        status=RemediationStatus.APPROVED,
        estimated_monthly_savings=Decimal("10.0"),
        resource_id="vol-1",
        resource_type="volume",
        action=RemediationAction.DELETE_VOLUME,
    )
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = req
    mock_res.with_for_update.return_value = mock_res  # Support chaining
    mock_db.execute.return_value = mock_res

    # Mock safety check
    mock_safety = AsyncMock()
    with patch(
        "app.modules.optimization.domain.remediation.SafetyGuardrailService",
        return_value=mock_safety,
    ):
        # Mock audit logger
        with patch(
            "app.modules.optimization.domain.remediation.AuditLogger"
        ) as mock_audit:
            mock_audit.return_value.log = AsyncMock()

            # Execute
            result = await service.execute(req.id, tenant_id)

            assert result.status == RemediationStatus.SCHEDULED
            assert result.scheduled_execution_at is not None
            assert mock_db.commit.called


@pytest.mark.asyncio
async def test_execute_immediate_action_success(mock_db, tenant_id):
    service = RemediationService(mock_db)

    req = RemediationRequest(
        id=uuid4(),
        tenant_id=tenant_id,
        status=RemediationStatus.APPROVED,
        resource_id="vol-1",
        resource_type="EBS Volume",
        action=RemediationAction.DELETE_VOLUME,
        provider="aws",
    )
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = req
    mock_db.execute.return_value = mock_res

    mock_aws_client = AsyncMock()
    mock_aws_client.delete_volume = AsyncMock()

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_aws_client
    mock_ctx.__aexit__.return_value = None

    # Patch local names in remediation module
    with (
        patch(
            "app.modules.optimization.domain.remediation.SafetyGuardrailService"
        ) as MockSafety,
        patch("app.modules.optimization.domain.remediation.AuditLogger") as MockAudit,
        patch.object(service, "_get_client", return_value=mock_ctx),
        patch("app.shared.core.notifications.NotificationDispatcher") as MockNotify,
    ):  # Patch Source for this one as it is imported inside method
        mock_safety_instance = MockSafety.return_value
        # Ensure it returns valid result (None is fine as it returns nothing on success)
        mock_safety_instance.check_all_guards = AsyncMock(return_value=None)

        mock_audit_instance = MockAudit.return_value
        mock_audit_instance.log = AsyncMock()

        MockNotify.notify_remediation_completed = AsyncMock()

        result = await service.execute(req.id, tenant_id, bypass_grace_period=True)

        assert result.status == RemediationStatus.COMPLETED
        mock_aws_client.delete_volume.assert_called_with(VolumeId="vol-1")


@pytest.mark.asyncio
async def test_execute_with_backup_aws_rds(mock_db, tenant_id):
    service = RemediationService(mock_db)

    req = RemediationRequest(
        id=uuid4(),
        tenant_id=tenant_id,
        status=RemediationStatus.APPROVED,
        resource_id="db-1",
        resource_type="RDS Instance",
        action=RemediationAction.DELETE_RDS_INSTANCE,
        create_backup=True,
        backup_retention_days=7,
    )
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = req
    mock_res.with_for_update.return_value = mock_res
    mock_db.execute.return_value = mock_res

    mock_rds_client = AsyncMock()
    mock_rds_client.create_db_snapshot = AsyncMock()
    mock_rds_client.delete_db_instance = AsyncMock()

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_rds_client
    mock_ctx.__aexit__.return_value = None

    with (
        patch(
            "app.modules.optimization.domain.remediation.SafetyGuardrailService"
        ) as MockSafety,
        patch("app.modules.optimization.domain.remediation.AuditLogger") as MockAudit,
        patch.object(service, "_get_client", return_value=mock_ctx),
        patch("app.shared.core.notifications.NotificationDispatcher") as MockNotify,
    ):
        mock_safety_instance = MockSafety.return_value
        mock_safety_instance.check_all_guards = AsyncMock(return_value=None)

        mock_audit_instance = MockAudit.return_value
        mock_audit_instance.log = AsyncMock()

        MockNotify.notify_remediation_completed = AsyncMock()

        await service.execute(req.id, tenant_id, bypass_grace_period=True)

        # Verify backup call
        assert mock_rds_client.create_db_snapshot.called
        assert req.backup_resource_id.startswith("valdrix-backup-db-1")
        # Verify deletion call
        mock_rds_client.delete_db_instance.assert_called_with(
            DBInstanceIdentifier="db-1", SkipFinalSnapshot=True
        )


@pytest.mark.asyncio
async def test_enforce_hard_limit_triggers_remediation(mock_db, tenant_id):
    service = RemediationService(mock_db)

    pending_req = RemediationRequest(
        id=uuid4(),
        tenant_id=tenant_id,
        action=RemediationAction.STOP_INSTANCE,
        status=RemediationStatus.PENDING,
        confidence_score=Decimal("0.95"),
        estimated_monthly_savings=Decimal("100.00"),
    )

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [pending_req]
    mock_db.execute.return_value = mock_res

    # Mock UsageTracker returning Hard Limit
    mock_tracker = MagicMock()
    from app.shared.llm.usage_tracker import BudgetStatus

    # Ensure check_budget is an AsyncMock
    mock_tracker.check_budget = AsyncMock(return_value=BudgetStatus.HARD_LIMIT)

    with patch("app.shared.llm.usage_tracker.UsageTracker", return_value=mock_tracker):
        # Mock execute to avoid actual calls
        service.execute = AsyncMock()

        executed_ids = await service.enforce_hard_limit(tenant_id)

        assert len(executed_ids) == 1
        assert executed_ids[0] == pending_req.id
        # Verify it auto-approved
        assert pending_req.status == RemediationStatus.APPROVED
        assert pending_req.review_notes == "AUTO_APPROVED: Budget Hard Limit Exceeded"
        # Verify it called execute with bypass
        service.execute.assert_called_with(
            pending_req.id, tenant_id, bypass_grace_period=False
        )


@pytest.mark.asyncio
async def test_generate_iac_plan_pro_tier(mock_db, tenant_id):
    service = RemediationService(mock_db)
    req = RemediationRequest(
        resource_id="i-1234567890abcdef0",
        resource_type="EC2 Instance",
        action=RemediationAction.TERMINATE_INSTANCE,
        provider="aws",
        estimated_monthly_savings=50.0,
    )

    # Patch source for local imports
    with patch(
        "app.shared.core.pricing.get_tenant_tier", AsyncMock(return_value="starter")
    ):
        with patch("app.shared.core.pricing.is_feature_enabled", return_value=True):
            plan = await service.generate_iac_plan(req, tenant_id)

            assert (
                'resource "aws_instance"' in plan
                or "terraform state rm aws_instance" in plan
            )
            assert "removed {" in plan
            assert "i_1234567890abcdef0" in plan  # Sanitized ID


@pytest.mark.asyncio
async def test_generate_iac_plan_free_tier(mock_db, tenant_id):
    service = RemediationService(mock_db)
    req = RemediationRequest(
        resource_id="i-1",
        resource_type="EC2",
        action=RemediationAction.TERMINATE_INSTANCE,
        provider="aws",
    )

    # Patch source for local imports
    with (
        patch(
            "app.shared.core.pricing.get_tenant_tier", AsyncMock(return_value="starter")
        ),
        patch("app.shared.core.pricing.is_feature_enabled", return_value=False),
    ):
        plan = await service.generate_iac_plan(req, tenant_id)
        assert "upgrade" in plan
