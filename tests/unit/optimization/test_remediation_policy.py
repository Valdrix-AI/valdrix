from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.remediation import RemediationAction, RemediationStatus
from app.models.tenant import UserRole
from app.shared.core.pricing import PricingTier
from app.modules.governance.domain.security.remediation_policy import (
    PolicyConfig,
    PolicyDecision,
    RemediationPolicyEngine,
)
from app.modules.optimization.domain.remediation import RemediationService
from app.modules.optimization.domain.actions.base import ExecutionResult, ExecutionStatus


def _request(
    *,
    action: RemediationAction = RemediationAction.STOP_INSTANCE,
    resource_id: str = "dev-instance",
    resource_type: str = "EC2 Instance",
    confidence_score: Decimal | None = Decimal("0.95"),
    review_notes: str | None = None,
    action_parameters: dict[str, object] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        tenant_id=uuid4(),
        requested_by_user_id=uuid4(),
        reviewed_by_user_id=uuid4(),
        action=action,
        status=RemediationStatus.APPROVED,
        resource_id=resource_id,
        resource_type=resource_type,
        confidence_score=confidence_score,
        review_notes=review_notes,
        explainability_notes=None,
        create_backup=False,
        backup_resource_id=None,
        estimated_monthly_savings=Decimal("25.0"),
        provider="aws",
        action_parameters=action_parameters,
    )


def test_policy_engine_allows_default_safe_request() -> None:
    evaluation = RemediationPolicyEngine().evaluate(_request())
    assert evaluation.decision == PolicyDecision.ALLOW
    assert evaluation.rule_hits == ()


def test_policy_engine_warns_on_low_confidence() -> None:
    evaluation = RemediationPolicyEngine().evaluate(
        _request(confidence_score=Decimal("0.50"))
    )
    assert evaluation.decision == PolicyDecision.WARN
    assert evaluation.rule_hits[0].rule_id == "low-confidence-remediation"


def test_policy_engine_blocks_production_destructive_change() -> None:
    evaluation = RemediationPolicyEngine().evaluate(
        _request(
            action=RemediationAction.DELETE_S3_BUCKET,
            resource_id="prod-payments-logs",
            resource_type="S3 Bucket",
        )
    )
    assert evaluation.decision == PolicyDecision.BLOCK
    assert evaluation.rule_hits[0].rule_id == "protect-production-destructive"


def test_policy_engine_blocks_destructive_change_with_explicit_policy_context() -> None:
    evaluation = RemediationPolicyEngine().evaluate(
        _request(
            action=RemediationAction.DELETE_S3_BUCKET,
            resource_id="bucket-123",
            resource_type="S3 Bucket",
            action_parameters={
                "_system_policy_context": {
                    "source": "cloud_account",
                    "is_production": True,
                    "criticality": "high",
                }
            },
        )
    )
    assert evaluation.decision == PolicyDecision.BLOCK
    assert evaluation.rule_hits[0].rule_id == "protect-production-destructive"


def test_policy_engine_allows_destructive_change_with_explicit_non_prod_context() -> None:
    evaluation = RemediationPolicyEngine().evaluate(
        _request(
            action=RemediationAction.DELETE_S3_BUCKET,
            resource_id="prod-looking-bucket",
            resource_type="S3 Bucket",
            action_parameters={
                "_system_policy_context": {
                    "source": "cloud_account",
                    "is_production": False,
                    "criticality": "low",
                }
            },
        )
    )
    assert evaluation.decision == PolicyDecision.ALLOW


def test_policy_engine_escalates_gpu_changes_without_override() -> None:
    evaluation = RemediationPolicyEngine().evaluate(
        _request(
            action=RemediationAction.TERMINATE_INSTANCE,
            resource_id="gpu-training-node-1",
            resource_type="GPU Compute",
            review_notes="approved",
        )
    )
    assert evaluation.decision == PolicyDecision.ESCALATE
    assert evaluation.rule_hits[0].rule_id == "gpu-change-requires-explicit-override"


def test_policy_engine_allows_gpu_with_override_note() -> None:
    evaluation = RemediationPolicyEngine().evaluate(
        _request(
            action=RemediationAction.TERMINATE_INSTANCE,
            resource_id="gpu-training-node-1",
            resource_type="GPU Compute",
            review_notes="gpu-approved by cloud owner",
        )
    )
    assert evaluation.decision == PolicyDecision.ALLOW


@pytest.mark.asyncio
async def test_execute_policy_block_short_circuits_action() -> None:
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    request = _request(
        action=RemediationAction.DELETE_S3_BUCKET,
        resource_id="prod-core-bucket",
        resource_type="S3 Bucket",
    )
    request_id = request.id
    tenant_id = request.tenant_id

    db_result = MagicMock()
    db_result.scalar_one_or_none.return_value = request
    db.execute.return_value = db_result

    service = RemediationService(db)
    with (
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
            "app.modules.optimization.domain.remediation.get_tenant_tier",
            new_callable=AsyncMock,
            return_value=PricingTier.PRO,
        ),
        patch.object(
            service, "_resolve_credentials", new_callable=AsyncMock, return_value={}
        ),
    ):
        mock_safety.return_value.check_all_guards = AsyncMock(return_value=None)
        result = await service.execute(request_id, tenant_id, bypass_grace_period=True)

    assert result.status == RemediationStatus.FAILED
    assert "POLICY_BLOCK" in (result.execution_error or "")
    mock_get_strategy.assert_not_called()


@pytest.mark.asyncio
async def test_execute_policy_block_notifies_jira_for_pro_incident_tier() -> None:
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    request = _request(
        action=RemediationAction.DELETE_S3_BUCKET,
        resource_id="prod-core-bucket",
        resource_type="S3 Bucket",
    )
    request_id = request.id
    tenant_id = request.tenant_id

    db_result = MagicMock()
    db_result.scalar_one_or_none.return_value = request
    db.execute.return_value = db_result

    remediation_settings = SimpleNamespace(
        policy_violation_notify_slack=False,
        policy_violation_notify_jira=True,
    )

    service = RemediationService(db)
    with (
        patch(
            "app.modules.optimization.domain.remediation.AuditLogger.log",
            new_callable=AsyncMock,
        ),
        patch(
            "app.modules.optimization.domain.remediation.SafetyGuardrailService"
        ) as mock_safety,
        patch(
            "app.modules.optimization.domain.remediation.get_tenant_tier",
            new_callable=AsyncMock,
        ) as mock_tier,
        patch.object(
            service,
            "_build_policy_config",
            new_callable=AsyncMock,
            return_value=(PolicyConfig(), remediation_settings),
        ),
        patch(
            "app.shared.core.notifications.NotificationDispatcher.notify_policy_event",
            new_callable=AsyncMock,
        ) as mock_notify,
        patch(
            "app.modules.optimization.domain.remediation.RemediationActionFactory.get_strategy"
        ) as mock_get_strategy,
    ):
        mock_tier.return_value = PricingTier.PRO
        mock_safety.return_value.check_all_guards = AsyncMock(return_value=None)
        result = await service.execute(request_id, tenant_id, bypass_grace_period=True)

    assert result.status == RemediationStatus.FAILED
    mock_notify.assert_awaited_once()
    mock_get_strategy.assert_not_called()
    kwargs = mock_notify.await_args.kwargs
    assert kwargs["notify_slack"] is False
    assert kwargs["notify_jira"] is True
    assert kwargs["notify_workflow"] is True


@pytest.mark.asyncio
async def test_execute_policy_warn_still_executes() -> None:
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    request = _request(
        action=RemediationAction.STOP_INSTANCE,
        resource_id="dev-instance-1",
        resource_type="EC2 Instance",
        confidence_score=Decimal("0.60"),
    )
    request_id = request.id
    tenant_id = request.tenant_id

    db_result = MagicMock()
    db_result.scalar_one_or_none.return_value = request
    db.execute.return_value = db_result

    service = RemediationService(db)
    with (
        patch(
            "app.modules.optimization.domain.remediation.AuditLogger.log",
            new_callable=AsyncMock,
        ),
        patch(
            "app.modules.optimization.domain.remediation.SafetyGuardrailService"
        ) as mock_safety,
        patch(
            "app.shared.core.notifications.NotificationDispatcher.notify_remediation_completed",
            new_callable=AsyncMock,
        ),
        patch(
            "app.modules.optimization.domain.remediation.RemediationActionFactory.get_strategy"
        ) as mock_get_strategy,
        patch(
            "app.modules.optimization.domain.remediation.get_tenant_tier",
            new_callable=AsyncMock,
            return_value=PricingTier.PRO,
        ),
        patch.object(
            service, "_resolve_credentials", new_callable=AsyncMock, return_value={}
        ),
    ):
        mock_safety.return_value.check_all_guards = AsyncMock(return_value=None)
        strategy = MagicMock()
        strategy.execute = AsyncMock(
            return_value=ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                resource_id=request.resource_id,
                action_taken=request.action.value,
            )
        )
        mock_get_strategy.return_value = strategy
        result = await service.execute(request_id, tenant_id, bypass_grace_period=True)

    assert result.status == RemediationStatus.COMPLETED
    strategy.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_policy_escalate_sets_pending_escalation_state() -> None:
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    request = _request(
        action=RemediationAction.TERMINATE_INSTANCE,
        resource_id="gpu-training-node-1",
        resource_type="GPU Compute",
        review_notes="approved",
    )
    request_id = request.id
    tenant_id = request.tenant_id

    db_result = MagicMock()
    db_result.scalar_one_or_none.side_effect = [request, None]
    db.execute.return_value = db_result

    service = RemediationService(db)
    with (
        patch(
            "app.modules.optimization.domain.remediation.get_tenant_tier",
            new_callable=AsyncMock,
        ) as mock_tier,
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
    ):
        mock_tier.return_value = PricingTier.GROWTH
        mock_safety.return_value.check_all_guards = AsyncMock(return_value=None)
        result = await service.execute(request_id, tenant_id, bypass_grace_period=True)

    assert result.status == RemediationStatus.PENDING_APPROVAL
    assert result.escalation_required is True
    assert "requires explicit GPU approval override" in (result.escalation_reason or "")
    mock_get_strategy.assert_not_called()


@pytest.mark.asyncio
async def test_execute_policy_escalation_does_not_notify_jira_without_incident_feature() -> (
    None
):
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    request = _request(
        action=RemediationAction.TERMINATE_INSTANCE,
        resource_id="gpu-training-node-1",
        resource_type="GPU Compute",
        review_notes="approved",
    )
    request_id = request.id
    tenant_id = request.tenant_id

    db_result = MagicMock()
    db_result.scalar_one_or_none.return_value = request
    db.execute.return_value = db_result

    remediation_settings = SimpleNamespace(
        policy_violation_notify_slack=False,
        policy_violation_notify_jira=True,
    )

    service = RemediationService(db)
    with (
        patch(
            "app.modules.optimization.domain.remediation.AuditLogger.log",
            new_callable=AsyncMock,
        ),
        patch(
            "app.modules.optimization.domain.remediation.SafetyGuardrailService"
        ) as mock_safety,
        patch(
            "app.modules.optimization.domain.remediation.get_tenant_tier",
            new_callable=AsyncMock,
        ) as mock_tier,
        patch.object(
            service,
            "_build_policy_config",
            new_callable=AsyncMock,
            return_value=(PolicyConfig(), remediation_settings),
        ),
        patch(
            "app.shared.core.notifications.NotificationDispatcher.notify_policy_event",
            new_callable=AsyncMock,
        ) as mock_notify,
        patch(
            "app.modules.optimization.domain.remediation.RemediationActionFactory.get_strategy"
        ) as mock_get_strategy,
    ):
        mock_tier.return_value = "growth"
        mock_safety.return_value.check_all_guards = AsyncMock(return_value=None)
        result = await service.execute(request_id, tenant_id, bypass_grace_period=True)

    assert result.status == RemediationStatus.PENDING_APPROVAL
    mock_notify.assert_not_awaited()
    mock_get_strategy.assert_not_called()


@pytest.mark.asyncio
async def test_execute_policy_escalation_is_pending_even_without_escalation_feature() -> (
    None
):
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    request = _request(
        action=RemediationAction.TERMINATE_INSTANCE,
        resource_id="gpu-training-node-1",
        resource_type="GPU Compute",
        review_notes="approved",
    )
    request_id = request.id
    tenant_id = request.tenant_id

    db_result = MagicMock()
    db_result.scalar_one_or_none.return_value = request
    db.execute.return_value = db_result

    service = RemediationService(db)
    with (
        patch(
            "app.modules.optimization.domain.remediation.AuditLogger.log",
            new_callable=AsyncMock,
        ),
        patch(
            "app.modules.optimization.domain.remediation.SafetyGuardrailService"
        ) as mock_safety,
        patch(
            "app.modules.optimization.domain.remediation.get_tenant_tier",
            new_callable=AsyncMock,
        ) as mock_tier,
        patch(
            "app.modules.optimization.domain.remediation.RemediationActionFactory.get_strategy"
        ) as mock_get_strategy,
    ):
        mock_tier.return_value = PricingTier.FREE
        mock_safety.return_value.check_all_guards = AsyncMock(return_value=None)
        result = await service.execute(request_id, tenant_id, bypass_grace_period=True)

    assert result.status == RemediationStatus.PENDING_APPROVAL
    assert result.escalation_required is True
    assert result.execution_error is None
    mock_get_strategy.assert_not_called()


@pytest.mark.asyncio
async def test_approve_escalated_requires_owner_role() -> None:
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    request = _request(
        action=RemediationAction.TERMINATE_INSTANCE,
        resource_id="gpu-training-node-1",
        resource_type="GPU Compute",
        review_notes="approved",
    )
    request.status = RemediationStatus.PENDING_APPROVAL
    request.escalation_required = True
    request.escalation_reason = "GPU requires owner override"

    db_result = MagicMock()
    db_result.scalar_one_or_none.return_value = request
    db.execute.return_value = db_result

    service = RemediationService(db)
    with pytest.raises(ValueError, match="owner approval"):
        await service.approve(
            request.id,
            request.tenant_id,
            request.reviewed_by_user_id,
            notes="ok",
            reviewer_role=UserRole.ADMIN,
        )

    approved = await service.approve(
        request.id,
        request.tenant_id,
        request.reviewed_by_user_id,
        notes="approved by owner",
        reviewer_role=UserRole.OWNER,
    )
    assert approved.status == RemediationStatus.APPROVED
    assert approved.escalation_required is False
    assert "gpu-approved" in (approved.review_notes or "")
