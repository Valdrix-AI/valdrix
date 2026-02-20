from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.modules.optimization.api.v1 import zombies
from app.shared.core.auth import CurrentUser, UserRole
from app.shared.core.exceptions import ResourceNotFoundError, ValdrixException
from app.shared.core.pricing import PricingTier


def _scalar_one_or_none_result(value: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
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
    connection_id = uuid4()
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
        connection_id=connection_id,
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
        assert (
            service.preview_policy_input.await_args.kwargs["connection_id"]
            == connection_id
        )


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
async def test_execute_remediation_wraps_service_error() -> None:
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
        service.execute = AsyncMock(
            side_effect=ValueError("No AWS connection found for this tenant")
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
async def test_execute_remediation_unexpected_error_is_sanitized() -> None:
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
        service.execute = AsyncMock(side_effect=RuntimeError("raw upstream timeout"))

        with pytest.raises(ValdrixException) as exc_info:
            await zombies.execute_remediation(
                request=MagicMock(),
                request_id=request_id,
                tenant_id=tenant_id,
                user=user,
                db=db,
            )

    assert exc_info.value.code == "remediation_execution_failed"
    assert exc_info.value.status_code == 500
    assert exc_info.value.message == "Failed to execute remediation request."


@pytest.mark.asyncio
async def test_execute_remediation_failed_status_propagates_code_and_status() -> None:
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

    failed_request = MagicMock()
    failed_request.id = request_id
    failed_request.status.value = "failed"
    failed_request.execution_error = (
        "[aws_connection_missing] No AWS connection found for this tenant (Status: 400)"
    )

    with patch(
        "app.modules.optimization.api.v1.zombies.RemediationService"
    ) as service_cls:
        service = service_cls.return_value
        service.execute = AsyncMock(return_value=failed_request)

        with pytest.raises(ValdrixException) as exc_info:
            await zombies.execute_remediation(
                request=MagicMock(),
                request_id=request_id,
                tenant_id=tenant_id,
                user=user,
                db=db,
            )

    assert exc_info.value.code == "aws_connection_missing"
    assert exc_info.value.status_code == 400
    assert exc_info.value.message == "No AWS connection found for this tenant"


@pytest.mark.asyncio
async def test_execute_remediation_failed_status_without_error_uses_default() -> None:
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

    failed_request = MagicMock()
    failed_request.id = request_id
    failed_request.status.value = "failed"
    failed_request.execution_error = None

    with patch(
        "app.modules.optimization.api.v1.zombies.RemediationService"
    ) as service_cls:
        service = service_cls.return_value
        service.execute = AsyncMock(return_value=failed_request)

        with pytest.raises(ValdrixException) as exc_info:
            await zombies.execute_remediation(
                request=MagicMock(),
                request_id=request_id,
                tenant_id=tenant_id,
                user=user,
                db=db,
            )

    assert exc_info.value.code == "remediation_execution_failed"
    assert exc_info.value.status_code == 400
    assert exc_info.value.message == "Remediation execution failed."


@pytest.mark.asyncio
async def test_execute_remediation_deferred_status_returns_as_is() -> None:
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

    deferred_request = MagicMock()
    deferred_request.id = request_id
    deferred_request.status.value = "scheduled"
    deferred_request.execution_error = None

    with patch(
        "app.modules.optimization.api.v1.zombies.RemediationService"
    ) as service_cls:
        service = service_cls.return_value
        service.execute = AsyncMock(return_value=deferred_request)

        result = await zombies.execute_remediation(
            request=MagicMock(),
            request_id=request_id,
            tenant_id=tenant_id,
            user=user,
            db=db,
        )

    assert result["status"] == "scheduled"
    assert result["request_id"] == str(request_id)


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


@pytest.mark.asyncio
async def test_scan_zombies_default_region_hint_is_global() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    user = CurrentUser(
        id=uuid4(),
        email="member@example.com",
        tenant_id=tenant_id,
        role=UserRole.MEMBER,
        tier=PricingTier.PRO,
    )

    with patch("app.modules.optimization.api.v1.zombies.ZombieService") as service_cls:
        service = service_cls.return_value
        service.scan_for_tenant = AsyncMock(return_value={"status": "ok", "results": []})

        await zombies.scan_zombies(
            request=MagicMock(),
            tenant_id=tenant_id,
            user=user,
            db=db,
        )

        service.scan_for_tenant.assert_awaited_once()
        kwargs = service.scan_for_tenant.await_args.kwargs
        assert kwargs["region"] == "global"


@pytest.mark.asyncio
async def test_scan_zombies_background_default_region_hint_is_global() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    user = CurrentUser(
        id=uuid4(),
        email="member@example.com",
        tenant_id=tenant_id,
        role=UserRole.MEMBER,
        tier=PricingTier.PRO,
    )
    job = MagicMock()
    job.id = uuid4()

    with patch(
        "app.modules.optimization.api.v1.zombies.enqueue_job",
        new=AsyncMock(return_value=job),
    ) as mock_enqueue:
        response = await zombies.scan_zombies(
            request=MagicMock(),
            tenant_id=tenant_id,
            user=user,
            db=db,
            background=True,
        )

        assert response["status"] == "pending"
        payload = mock_enqueue.await_args.kwargs["payload"]
        assert payload["region"] == "global"
        assert payload["analyze"] is False


@pytest.mark.asyncio
async def test_create_remediation_request_default_region_hint_is_global() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    user = CurrentUser(
        id=uuid4(),
        email="admin@example.com",
        tenant_id=tenant_id,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    created = MagicMock()
    created.id = uuid4()
    payload = zombies.RemediationRequestCreate(
        resource_id="vm-123",
        resource_type="VM Instance",
        action="stop_instance",
        provider="azure",
        estimated_savings=25.5,
    )

    with patch(
        "app.modules.optimization.api.v1.zombies.RemediationService"
    ) as service_cls:
        service = service_cls.return_value
        service.create_request = AsyncMock(return_value=created)

        result = await zombies.create_remediation_request(
            request=payload,
            tenant_id=tenant_id,
            user=user,
            db=db,
        )

    service_cls.assert_called_once_with(db=db, region="global")
    assert result["status"] == "pending"
