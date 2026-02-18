import pytest
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.optimization.domain.service import ZombieService
from app.modules.optimization.domain.remediation_service import RemediationService
from app.models.remediation import (
    RemediationRequest,
    RemediationStatus,
    RemediationAction,
)
from app.shared.core.pricing import PricingTier


@pytest.fixture
def mock_db():
    db = AsyncMock()
    # SQLAlchemy AsyncSession has synchronous mutators.
    db.add = MagicMock()
    db.add_all = MagicMock()
    return db


@pytest.mark.asyncio
async def test_zombie_service_scan_for_tenant_no_connections(mock_db):
    service = ZombieService(mock_db)

    # Mock db.execute to return a result that has scalars().all()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    results = await service.scan_for_tenant(uuid.uuid4(), MagicMock())

    assert results["error"] == "No cloud connections found."
    assert results["total_monthly_waste"] == 0.0


@pytest.mark.asyncio
async def test_remediation_service_create_request(mock_db):
    service = RemediationService(mock_db)
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    request = await service.create_request(
        tenant_id=tenant_id,
        user_id=user_id,
        resource_id="vol-12345",
        resource_type="ebs_volume",
        action=RemediationAction.DELETE_VOLUME,
        estimated_savings=25.50,
    )

    assert request.tenant_id == tenant_id
    assert request.status == RemediationStatus.PENDING
    assert request.estimated_monthly_savings == Decimal("25.50")
    assert mock_db.add.called
    assert mock_db.commit.called


@pytest.mark.asyncio
async def test_remediation_service_approve(mock_db):
    service = RemediationService(mock_db)
    req_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    # Mock existing request
    mock_request = MagicMock(spec=RemediationRequest)
    mock_request.id = req_id
    mock_request.tenant_id = tenant_id
    mock_request.status = RemediationStatus.PENDING

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_request
    mock_db.execute.return_value = mock_result

    approved_req = await service.approve(
        req_id, tenant_id, user_id, notes="Approved for cleanup"
    )

    assert approved_req.status == RemediationStatus.APPROVED
    assert approved_req.review_notes == "Approved for cleanup"
    assert mock_db.commit.called


@pytest.mark.asyncio
async def test_remediation_service_execute_delete_volume(mock_db):
    service = RemediationService(mock_db)
    req_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    mock_request = MagicMock(spec=RemediationRequest)
    mock_request.id = req_id
    mock_request.tenant_id = tenant_id
    mock_request.status = RemediationStatus.APPROVED
    mock_request.action = RemediationAction.DELETE_VOLUME
    mock_request.resource_id = "vol-12345"
    mock_request.create_backup = False

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_request
    mock_db.execute.return_value = mock_result

    mock_ec2 = AsyncMock()
    with patch.object(
        service,
        "_get_client",
        return_value=MagicMock(__aenter__=AsyncMock(return_value=mock_ec2)),
    ):
        with patch(
            "app.modules.governance.domain.security.audit_log.AuditLogger.log",
            new_callable=AsyncMock,
        ):
            with patch(
                "app.shared.core.safety_service.SafetyGuardrailService.check_all_guards",
                new_callable=AsyncMock,
            ):
                # Use bypass_grace_period=True to test immediate execution
                executed_req = await service.execute(
                    req_id, tenant_id, bypass_grace_period=True
                )

                assert executed_req.status == RemediationStatus.COMPLETED
                mock_ec2.delete_volume.assert_called_with(VolumeId="vol-12345")


@pytest.mark.asyncio
async def test_remediation_service_schedules_grace_period(mock_db):
    """Test that remediation schedules a 24h grace period by default."""
    service = RemediationService(mock_db)
    req_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    mock_request = MagicMock(spec=RemediationRequest)
    mock_request.id = req_id
    mock_request.tenant_id = tenant_id
    mock_request.status = RemediationStatus.APPROVED
    mock_request.action = RemediationAction.DELETE_VOLUME
    mock_request.resource_id = "vol-67890"
    mock_request.reviewed_by_user_id = uuid.uuid4()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_request
    mock_db.execute.return_value = mock_result

    with patch(
        "app.modules.governance.domain.security.audit_log.AuditLogger.log",
        new_callable=AsyncMock,
    ):
        with patch(
            "app.shared.core.safety_service.SafetyGuardrailService.check_all_guards",
            new_callable=AsyncMock,
        ):
            with patch(
                "app.modules.governance.domain.jobs.processor.enqueue_job",
                new_callable=AsyncMock,
            ):
                # Execute without bypass - should schedule, not complete
                scheduled_req = await service.execute(req_id, tenant_id)

            assert scheduled_req.status == RemediationStatus.SCHEDULED
            assert scheduled_req.scheduled_execution_at is not None


@pytest.mark.asyncio
async def test_zombie_service_enrich_with_ai_tier_restriction(mock_db):
    service = ZombieService(mock_db)
    zombies = {"total_monthly_waste": 100.0}

    mock_user = MagicMock()
    mock_user.tier = PricingTier.FREE

    await service._enrich_with_ai(zombies, uuid.uuid4(), mock_user.tier)

    assert "ai_analysis" in zombies
    assert zombies["ai_analysis"]["upgrade_required"] is True
    assert "requires Growth tier" in zombies["ai_analysis"]["error"]
