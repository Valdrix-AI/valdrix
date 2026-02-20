from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError

from app.modules.optimization.domain.remediation import (
    RemediationAction,
    RemediationService,
)
from app.modules.optimization.domain.actions.base import RemediationContext, ExecutionStatus
from app.modules.optimization.domain.actions.aws.rds import AWSDeleteRdsInstanceAction
from app.modules.optimization.domain.actions.aws.volumes import AWSDeleteVolumeAction
from app.shared.llm.budget_manager import BudgetStatus


class _AsyncContextManager:
    def __init__(self, obj: object) -> None:
        self._obj = obj

    async def __aenter__(self) -> object:
        return self._obj

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


@pytest.fixture
def service() -> RemediationService:
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.refresh = AsyncMock()
    return RemediationService(db)


@pytest.mark.asyncio
async def test_backup_creation_errors_raise(service: RemediationService) -> None:
    err = ClientError({"Error": {"Code": "500", "Message": "boom"}}, "CreateSnapshot")
    ec2 = AsyncMock()
    ec2.create_snapshot.side_effect = err
    rds = AsyncMock()
    rds.create_db_snapshot.side_effect = err

    async def fake_client(name: str, _context: RemediationContext) -> _AsyncContextManager:
        return _AsyncContextManager({"ec2": ec2, "rds": rds}[name])

    context = RemediationContext(tenant_id=uuid4(), region="us-east-1", tier="pro")
    volume_action = AWSDeleteVolumeAction()
    rds_action = AWSDeleteRdsInstanceAction()
    volume_action._get_client = fake_client  # type: ignore[method-assign]
    rds_action._get_client = fake_client  # type: ignore[method-assign]

    with pytest.raises(ClientError):
        await volume_action.create_backup("vol-1", context)
    with pytest.raises(ClientError):
        await rds_action.create_backup("db-1", context)


@pytest.mark.asyncio
async def test_execute_action_delete_volume_detach_and_delete(
    service: RemediationService,
) -> None:
    action = AWSDeleteVolumeAction()
    ec2 = AsyncMock()
    ec2.describe_volumes.side_effect = [
        {"Volumes": [{"Attachments": [{"State": "attached", "InstanceId": "i-1"}]}]},
        {"Volumes": [{"Attachments": []}]},
    ]

    async def fake_client(
        _name: str, _context: RemediationContext
    ) -> _AsyncContextManager:
        return _AsyncContextManager(ec2)

    action._get_client = fake_client  # type: ignore[method-assign]
    context = RemediationContext(tenant_id=uuid4(), region="us-east-1", tier="pro")

    result = await action._perform_action("vol-1", context)

    ec2.detach_volume.assert_awaited_with(
        VolumeId="vol-1",
        InstanceId="i-1",
        Force=True,
    )
    ec2.delete_volume.assert_awaited_with(VolumeId="vol-1")
    assert result.status == ExecutionStatus.SUCCESS


@pytest.mark.asyncio
async def test_execute_action_delete_volume_detach_timeout(
    service: RemediationService,
) -> None:
    action = AWSDeleteVolumeAction()
    ec2 = AsyncMock()
    ec2.describe_volumes.side_effect = [
        {"Volumes": [{"Attachments": [{"State": "attached"}]}]},
        {"Volumes": [{"Attachments": [{"State": "attached"}]}]},
    ]

    async def fake_client(
        _name: str, _context: RemediationContext
    ) -> _AsyncContextManager:
        return _AsyncContextManager(ec2)

    action._get_client = fake_client  # type: ignore[method-assign]
    context = RemediationContext(tenant_id=uuid4(), region="us-east-1", tier="pro")

    with (
        patch(
            "app.modules.optimization.domain.actions.aws.volumes.time.monotonic",
            side_effect=[0, 0, 181],
        ),
        patch(
            "app.modules.optimization.domain.actions.aws.volumes.asyncio.sleep",
            new=AsyncMock(),
        ),
    ):
        with pytest.raises(ValueError, match="did not detach"):
            await action._perform_action("vol-timeout", context)


@pytest.mark.asyncio
async def test_enforce_hard_limit_non_hard_limit_short_circuit(
    service: RemediationService,
) -> None:
    tenant_id = uuid4()
    with patch("app.shared.llm.usage_tracker.UsageTracker") as usage_tracker_cls:
        usage_tracker_cls.return_value.check_budget = AsyncMock(
            return_value=BudgetStatus.SOFT_LIMIT
        )
        result = await service.enforce_hard_limit(tenant_id)
    assert result == []


@pytest.mark.asyncio
async def test_enforce_hard_limit_execute_errors_are_captured(
    service: RemediationService,
) -> None:
    tenant_id = uuid4()
    req = MagicMock()
    req.id = uuid4()
    req.action = RemediationAction.STOP_INSTANCE
    req.status = "pending"
    req.confidence_score = Decimal("0.99")
    req.estimated_monthly_savings = Decimal("25")
    result = MagicMock()
    result.scalars.return_value.all.return_value = [req]
    service.db.execute.return_value = result
    service.execute = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]

    with (
        patch("app.shared.llm.usage_tracker.UsageTracker") as usage_tracker_cls,
        patch(
            "app.modules.optimization.domain.remediation.get_settings"
        ) as get_settings,
    ):
        usage_tracker_cls.return_value.check_budget = AsyncMock(
            return_value=BudgetStatus.HARD_LIMIT
        )
        get_settings.return_value.AUTOPILOT_BYPASS_GRACE_PERIOD = False
        executed = await service.enforce_hard_limit(tenant_id)
    assert executed == []


@pytest.mark.asyncio
async def test_generate_iac_plan_provider_paths_and_bulk(
    service: RemediationService,
) -> None:
    req = MagicMock()
    req.resource_id = "123-invalid/id"
    req.resource_type = "Azure VM"
    req.estimated_monthly_savings = Decimal("12.5")
    req.action = RemediationAction.STOP_INSTANCE
    req.provider = "azure"

    with (
        patch(
            "app.shared.core.pricing.get_tenant_tier", new=AsyncMock(return_value="pro")
        ),
        patch(
            "app.modules.optimization.domain.remediation.get_tenant_tier",
            new=AsyncMock(return_value="pro"),
        ),
        patch("app.shared.core.pricing.is_feature_enabled", return_value=True),
    ):
        azure_plan = await service.generate_iac_plan(req, uuid4())
        assert "terraform state rm" in azure_plan
        assert "removed {" in azure_plan

        req.provider = "gcp"
        req.resource_type = "GCP Instance"
        gcp_plan = await service.generate_iac_plan(req, uuid4())
        assert "terraform state rm" in gcp_plan
        assert "removed {" in gcp_plan

        req.provider = "platform"
        req.resource_type = "Platform Service"
        platform_plan = await service.generate_iac_plan(req, uuid4())
        assert "terraform state rm cloud_resource." in platform_plan
        assert "removed {" in platform_plan

        bulk = await service.bulk_generate_iac_plan([req], uuid4())
        assert "Bulk IaC Remediation Plan" in bulk
        assert "Generated:" in bulk


@pytest.mark.asyncio
async def test_bulk_generate_iac_plan_resolves_tier_once(
    service: RemediationService,
) -> None:
    req1 = MagicMock()
    req1.resource_id = "r-1"
    req1.resource_type = "EC2 Instance"
    req1.estimated_monthly_savings = Decimal("5")
    req1.action = RemediationAction.STOP_INSTANCE
    req1.provider = "aws"

    req2 = MagicMock()
    req2.resource_id = "r-2"
    req2.resource_type = "EC2 Instance"
    req2.estimated_monthly_savings = Decimal("7")
    req2.action = RemediationAction.STOP_INSTANCE
    req2.provider = "aws"

    mock_tier_lookup = AsyncMock(return_value="pro")
    with (
        patch(
            "app.modules.optimization.domain.remediation.get_tenant_tier",
            new=mock_tier_lookup,
        ),
        patch("app.shared.core.pricing.is_feature_enabled", return_value=True),
    ):
        bulk = await service.bulk_generate_iac_plan([req1, req2], uuid4())

    assert "Bulk IaC Remediation Plan" in bulk
    mock_tier_lookup.assert_awaited_once()


def test_sanitize_tf_identifier_edge_cases(service: RemediationService) -> None:
    empty = service._sanitize_tf_identifier("aws", "EBS Volume", "!!!")
    starts_numeric = service._sanitize_tf_identifier("aws", "EBS Volume", "123abc")
    assert empty.startswith("resource_")
    assert starts_numeric.startswith("r_")
    assert len(empty.split("_")[-1]) == 10
