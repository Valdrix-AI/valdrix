from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.modules.optimization.api.v1 import zombies
from app.models.remediation import RemediationStatus
from app.shared.core.auth import CurrentUser, UserRole
from app.shared.core.exceptions import ResourceNotFoundError, ValdrixException
from app.shared.core.pricing import PricingTier


def _scalar_one_or_none_result(value: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _first_result(value: object) -> MagicMock:
    result = MagicMock()
    scalars = MagicMock()
    scalars.first.return_value = value
    result.scalars.return_value = scalars
    return result


@pytest.mark.asyncio
async def test_preview_remediation_policy_not_found() -> None:
    tenant_id = uuid4()
    request_id = uuid4()
    db = AsyncMock()
    user = CurrentUser(
        id=uuid4(),
        email="admin@example.com",
        tenant_id=tenant_id,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )

    with patch(
        "app.modules.optimization.api.v1.zombies.RemediationService"
    ) as service_cls:
        service = service_cls.return_value
        service.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(ResourceNotFoundError):
            await zombies.preview_remediation_policy(
                request_id=request_id,
                tenant_id=tenant_id,
                user=user,
                db=db,
            )


@pytest.mark.asyncio
async def test_preview_remediation_policy_payload_invalid_action() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    user = CurrentUser(
        id=uuid4(),
        email="admin@example.com",
        tenant_id=tenant_id,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )

    payload = zombies.PolicyPreviewCreate(
        resource_id="i-gpu-123",
        resource_type="GPU Compute",
        action="invalid_action",
        provider="aws",
    )

    with pytest.raises(ValdrixException, match="Invalid action"):
        await zombies.preview_remediation_policy_payload(
            payload=payload,
            tenant_id=tenant_id,
            user=user,
            db=db,
        )


@pytest.mark.asyncio
async def test_preview_remediation_policy_payload_success() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    user = CurrentUser(
        id=uuid4(),
        email="admin@example.com",
        tenant_id=tenant_id,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )

    payload = zombies.PolicyPreviewCreate(
        resource_id="i-gpu-123",
        resource_type="GPU Compute",
        action="terminate_instance",
        provider="aws",
        confidence_score=0.88,
        explainability_notes="gpu node from dev experiment",
        review_notes="manual validation",
    )

    with patch(
        "app.modules.optimization.api.v1.zombies.RemediationService"
    ) as service_cls:
        service = service_cls.return_value
        service.preview_policy_input = AsyncMock(
            return_value={
                "decision": "escalate",
                "summary": "GPU-related remediation requires explicit GPU approval override.",
                "tier": "pro",
                "rule_hits": [{"rule_id": "gpu-change-requires-explicit-override"}],
                "config": {
                    "enabled": True,
                    "block_production_destructive": True,
                    "require_gpu_override": True,
                    "low_confidence_warn_threshold": 0.9,
                },
            }
        )

        response = await zombies.preview_remediation_policy_payload(
            payload=payload,
            tenant_id=tenant_id,
            user=user,
            db=db,
        )

        assert response.decision == "escalate"
        assert response.tier == "pro"
        service.preview_policy_input.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_remediation_no_matching_request() -> None:
    tenant_id = uuid4()
    request_id = uuid4()
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_one_or_none_result(None))
    user = CurrentUser(
        id=uuid4(),
        email="admin@example.com",
        tenant_id=tenant_id,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )

    with pytest.raises(ResourceNotFoundError):
        await zombies.execute_remediation(
            request=MagicMock(),
            request_id=request_id,
            tenant_id=tenant_id,
            user=user,
            db=db,
        )


@pytest.mark.asyncio
async def test_execute_remediation_missing_aws_connection() -> None:
    tenant_id = uuid4()
    request_id = uuid4()
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_one_or_none_result(
                SimpleNamespace(connection_id=None, status=RemediationStatus.PENDING)
            ),
            _first_result(None),
        ]
    )
    user = CurrentUser(
        id=uuid4(),
        email="admin@example.com",
        tenant_id=tenant_id,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )

    with pytest.raises(ValdrixException, match="No AWS connection found"):
        await zombies.execute_remediation(
            request=MagicMock(),
            request_id=request_id,
            tenant_id=tenant_id,
            user=user,
            db=db,
        )


@pytest.mark.asyncio
async def test_execute_remediation_value_error_is_wrapped() -> None:
    tenant_id = uuid4()
    request_id = uuid4()
    remediation = SimpleNamespace(connection_id=None, status=RemediationStatus.PENDING)
    connection = SimpleNamespace()
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_one_or_none_result(remediation),
            _first_result(connection),
        ]
    )
    user = CurrentUser(
        id=uuid4(),
        email="admin@example.com",
        tenant_id=tenant_id,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )

    with (
        patch(
            "app.shared.adapters.aws_multitenant.MultiTenantAWSAdapter"
        ) as adapter_cls,
        patch(
            "app.modules.optimization.api.v1.zombies.RemediationService"
        ) as service_cls,
    ):
        adapter = adapter_cls.return_value
        adapter.get_credentials = AsyncMock(return_value={"access_key": "x"})
        service = service_cls.return_value
        service.execute = AsyncMock(side_effect=ValueError("grace period active"))

        with pytest.raises(ValdrixException, match="grace period active"):
            await zombies.execute_remediation(
                request=MagicMock(),
                request_id=request_id,
                tenant_id=tenant_id,
                user=user,
                db=db,
            )


@pytest.mark.asyncio
async def test_get_remediation_plan_not_found() -> None:
    tenant_id = uuid4()
    request_id = uuid4()
    db = AsyncMock()
    user = CurrentUser(
        id=uuid4(),
        email="admin@example.com",
        tenant_id=tenant_id,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )

    with patch(
        "app.modules.optimization.api.v1.zombies.RemediationService"
    ) as service_cls:
        service = service_cls.return_value
        service.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(ResourceNotFoundError):
            await zombies.get_remediation_plan(
                request_id=request_id,
                tenant_id=tenant_id,
                user=user,
                db=db,
            )
