from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.optimization.api.v1 import strategies as strategies_api
from app.shared.core.auth import CurrentUser, UserRole
from app.shared.core.dependencies import requires_feature
from app.shared.core.exceptions import ResourceNotFoundError
from app.shared.core.pricing import FeatureFlag, PricingTier


def _user() -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        email="finops@example.com",
        tenant_id=uuid4(),
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )


def _scalars_result(items: list[object]) -> MagicMock:
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    result.scalars.return_value = scalars
    return result


def _scalar_result(item: object | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = item
    return result


@pytest.mark.asyncio
async def test_list_recommendations_returns_scalars_result() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalars_result([{"id": "r1"}]))

    with patch.object(strategies_api, "set_session_tenant_id", new=AsyncMock()):
        out = await strategies_api.list_recommendations(
            tenant_id=uuid4(),
            user=_user(),
            db=db,
            status="open",
        )

    assert out == [{"id": "r1"}]
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_trigger_optimization_scan_returns_generated_count() -> None:
    db = MagicMock()
    tenant_id = uuid4()
    with (
        patch.object(strategies_api, "set_session_tenant_id", new=AsyncMock()),
        patch.object(strategies_api, "OptimizationService") as service_cls,
    ):
        service = MagicMock()
        service.generate_recommendations = AsyncMock(return_value=[{"id": "a"}, {"id": "b"}])
        service_cls.return_value = service

        out = await strategies_api.trigger_optimization_scan(
            tenant_id=tenant_id,
            user=_user(),
            db=db,
        )

    assert out.status == "success"
    assert out.recommendations_generated == 2
    service.generate_recommendations.assert_awaited_once_with(tenant_id)


@pytest.mark.asyncio
async def test_apply_recommendation_success_updates_model_and_audits() -> None:
    tenant_id = uuid4()
    recommendation_id = uuid4()
    recommendation = SimpleNamespace(
        id=recommendation_id,
        tenant_id=tenant_id,
        strategy_id=uuid4(),
        estimated_monthly_savings=12.5,
        region="us-east-1",
        resource_type="m5.large",
        status="open",
        applied_at=None,
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(recommendation))
    db.commit = AsyncMock()

    request = SimpleNamespace(
        method="POST",
        url=SimpleNamespace(path=f"/api/v1/strategies/apply/{recommendation_id}"),
    )
    user = _user()

    with (
        patch.object(strategies_api, "set_session_tenant_id", new=AsyncMock()),
        patch.object(strategies_api, "AuditLogger") as audit_cls,
    ):
        audit = MagicMock()
        audit.log = AsyncMock()
        audit_cls.return_value = audit

        out = await strategies_api.apply_recommendation(
            request=request,
            recommendation_id=recommendation_id,
            tenant_id=tenant_id,
            user=user,
            db=db,
        )

    assert out == {"status": "applied", "recommendation_id": str(recommendation_id)}
    assert recommendation.status == "applied"
    assert recommendation.applied_at is not None
    audit.log.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_apply_recommendation_not_found_raises() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(None))

    request = SimpleNamespace(
        method="POST",
        url=SimpleNamespace(path=f"/api/v1/strategies/apply/{uuid4()}"),
    )

    with patch.object(strategies_api, "set_session_tenant_id", new=AsyncMock()):
        with pytest.raises(ResourceNotFoundError):
            await strategies_api.apply_recommendation(
                request=request,
                recommendation_id=uuid4(),
                tenant_id=uuid4(),
                user=_user(),
                db=db,
            )


@pytest.mark.asyncio
async def test_backtest_invalid_provider_is_rejected() -> None:
    with (
        patch.object(strategies_api, "set_session_tenant_id", new=AsyncMock()),
        patch.object(strategies_api, "OptimizationService"),
    ):
        with pytest.raises(HTTPException) as exc:
            await strategies_api.backtest_strategies(
                tenant_id=uuid4(),
                user=_user(),
                db=MagicMock(),
                provider="oracle",
                strategy_type=None,
                days=30,
            )

    assert exc.value.status_code == 400
    assert "Unsupported provider" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_backtest_filtered_empty_returns_without_seeding() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalars_result([]))

    with (
        patch.object(strategies_api, "set_session_tenant_id", new=AsyncMock()),
        patch.object(strategies_api, "OptimizationService") as service_cls,
    ):
        service = MagicMock()
        service._seed_default_strategies = AsyncMock(return_value=[])
        service_cls.return_value = service

        out = await strategies_api.backtest_strategies(
            tenant_id=uuid4(),
            user=_user(),
            db=db,
            provider=None,
            strategy_type="savings_plan",
            days=30,
        )

    assert out.status == "success"
    assert out.strategies == []
    service._seed_default_strategies.assert_not_awaited()


@pytest.mark.asyncio
async def test_backtest_seeds_defaults_when_unfiltered_and_empty() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalars_result([]))
    seeded_strategy = SimpleNamespace(
        id=uuid4(),
        name="Seeded Strategy",
        provider="aws",
        type=SimpleNamespace(value="savings_plan"),
        config={},
    )
    impl = MagicMock()
    impl.backtest_hourly_series = MagicMock(return_value={"within_tolerance": True})

    with (
        patch.object(strategies_api, "set_session_tenant_id", new=AsyncMock()),
        patch.object(strategies_api, "OptimizationService") as service_cls,
    ):
        service = MagicMock()
        service._seed_default_strategies = AsyncMock(return_value=[seeded_strategy])
        service._get_strategy_impl = MagicMock(return_value=impl)
        service._aggregate_usage = AsyncMock(
            return_value={
                "provider": "aws",
                "canonical_charge_category": "compute",
                "granularity": "hour",
                "observed_buckets": 24,
                "expected_buckets": 24,
                "coverage_ratio": 1.0,
                "volatility": 0.1,
                "confidence_score": 0.95,
                "baseline_hourly_spend": 10.0,
                "average_hourly_spend": 10.2,
                "top_region": "us-east-1",
                "hourly_cost_series": [1.0, 1.2, 0.9],
            }
        )
        service_cls.return_value = service

        out = await strategies_api.backtest_strategies(
            tenant_id=tenant_id,
            user=_user(),
            db=db,
            provider=None,
            strategy_type=None,
            days=14,
        )

    assert out.status == "success"
    assert len(out.strategies) == 1
    assert out.strategies[0].provider == "aws"
    assert out.strategies[0].strategy_type == "savings_plan"
    service._seed_default_strategies.assert_awaited_once()
    impl.backtest_hourly_series.assert_called_once_with([1.0, 1.2, 0.9], tolerance=0.30)


@pytest.mark.asyncio
async def test_feature_gate_rejects_starter_for_commitment_optimization() -> None:
    starter_user = CurrentUser(
        id=uuid4(),
        email="starter@valdrics.io",
        tenant_id=uuid4(),
        role=UserRole.MEMBER,
        tier=PricingTier.STARTER,
    )

    checker = requires_feature(FeatureFlag.COMMITMENT_OPTIMIZATION)
    with pytest.raises(HTTPException) as exc:
        await checker(starter_user)

    assert exc.value.status_code == 403
    assert "requires an upgrade" in str(exc.value.detail)
