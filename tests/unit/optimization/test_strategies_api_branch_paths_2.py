from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.optimization.api.v1 import strategies as strategies_api
from app.shared.core.exceptions import ResourceNotFoundError
from app.shared.core.auth import CurrentUser, UserRole
from app.shared.core.pricing import PricingTier


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


def _scalar_result(item: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = item
    return result


@pytest.mark.asyncio
async def test_list_recommendations_direct_returns_scalars_all() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalars_result([{"id": "r1"}]))

    with patch.object(strategies_api, "set_session_tenant_id", new=AsyncMock()):
        out = await strategies_api.list_recommendations(
            tenant_id=tenant_id,
            user=_user(),
            db=db,
            status="open",
        )

    assert out == [{"id": "r1"}]
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_trigger_optimization_scan_direct_returns_generated_count() -> None:
    tenant_id = uuid4()
    db = MagicMock()

    with (
        patch.object(strategies_api, "set_session_tenant_id", new=AsyncMock()),
        patch.object(strategies_api, "OptimizationService") as service_cls,
    ):
        service = MagicMock()
        service.generate_recommendations = AsyncMock(return_value=[{"id": "r1"}, {"id": "r2"}])
        service_cls.return_value = service

        out = await strategies_api.trigger_optimization_scan(
            tenant_id=tenant_id,
            user=_user(),
            db=db,
        )

    assert out.status == "success"
    assert out.recommendations_generated == 2
    assert "Generated 2 new optimization opportunities" in out.message
    service.generate_recommendations.assert_awaited_once_with(tenant_id)


@pytest.mark.asyncio
async def test_backtest_strategies_seeds_defaults_and_skips_unknown_impl() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalars_result([]))
    user = _user()

    seeded = [
        SimpleNamespace(
            id=uuid4(),
            name="Seeded Strategy",
            provider="aws",
            type=SimpleNamespace(value="savings_plan"),
            config={},
        )
    ]

    with (
        patch.object(strategies_api, "set_session_tenant_id", new=AsyncMock()),
        patch.object(strategies_api, "OptimizationService") as service_cls,
    ):
        service = MagicMock()
        service._seed_default_strategies = AsyncMock(return_value=seeded)
        service._get_strategy_impl = MagicMock(return_value=None)
        service_cls.return_value = service

        out = await strategies_api.backtest_strategies(
            tenant_id=tenant_id,
            user=user,
            db=db,
            provider=None,
            strategy_type=None,
            days=30,
        )

    assert out.status == "success"
    assert out.strategies == []
    service._seed_default_strategies.assert_awaited_once()
    service._get_strategy_impl.assert_called_once_with(seeded[0])


@pytest.mark.asyncio
async def test_backtest_strategies_filtered_empty_result_returns_without_seeding() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalars_result([]))
    user = _user()

    with (
        patch.object(strategies_api, "set_session_tenant_id", new=AsyncMock()),
        patch.object(strategies_api, "OptimizationService") as service_cls,
    ):
        service = MagicMock()
        service._seed_default_strategies = AsyncMock(return_value=[])
        service_cls.return_value = service

        out = await strategies_api.backtest_strategies(
            tenant_id=tenant_id,
            user=user,
            db=db,
            provider=None,
            strategy_type="savings_plan",
            days=30,
        )

    assert out.status == "success"
    assert out.strategies == []
    service._seed_default_strategies.assert_not_awaited()


@pytest.mark.asyncio
async def test_backtest_strategies_handles_invalid_tolerance_and_no_series_path() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    strategy = SimpleNamespace(
        id=uuid4(),
        name="Unknown Shape Strategy",
        provider=None,
        type=None,
        config={"backtest_tolerance": "bad-number"},
    )
    db.execute = AsyncMock(return_value=_scalars_result([strategy]))
    user = _user()

    impl = MagicMock()
    impl.backtest_hourly_series = MagicMock(return_value={"within_tolerance": True})
    usage_data = {
        "provider": "aws",
        "canonical_charge_category": None,
        "granularity": "hour",
        "observed_buckets": 0,
        "expected_buckets": 24,
        "coverage_ratio": 0.0,
        "volatility": None,
        "confidence_score": None,
        "baseline_hourly_spend": 0.0,
        "average_hourly_spend": 0.0,
        "top_region": None,
        "hourly_cost_series": [],
    }

    with (
        patch.object(strategies_api, "set_session_tenant_id", new=AsyncMock()),
        patch.object(strategies_api, "OptimizationService") as service_cls,
    ):
        service = MagicMock()
        service._get_strategy_impl = MagicMock(return_value=impl)
        service._aggregate_usage = AsyncMock(return_value=usage_data)
        service_cls.return_value = service

        out = await strategies_api.backtest_strategies(
            tenant_id=tenant_id,
            user=user,
            db=db,
            provider=" AWS ",
            strategy_type=" RESERVED_INSTANCE ",
            days=14,
        )

    assert out.status == "success"
    assert len(out.strategies) == 1
    item = out.strategies[0]
    assert item.provider == "unknown"
    assert item.strategy_type == "unknown"
    assert item.backtest == {"reason": "no_series"}
    assert service._aggregate_usage.await_args.kwargs["provider"] is None
    assert service._aggregate_usage.await_args.kwargs["canonical_charge_category"] is None
    impl.backtest_hourly_series.assert_not_called()


@pytest.mark.asyncio
async def test_backtest_strategies_calls_backtest_with_default_tolerance_when_cfg_missing() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    strategy = SimpleNamespace(
        id=uuid4(),
        name="SP Strategy",
        provider="aws",
        type=SimpleNamespace(value="savings_plan"),
        config=None,
    )
    db.execute = AsyncMock(return_value=_scalars_result([strategy]))
    user = _user()

    impl = MagicMock()
    impl.backtest_hourly_series = MagicMock(
        return_value={"reason": "tested", "within_tolerance": True}
    )
    usage_data = {
        "provider": "aws",
        "canonical_charge_category": "compute",
        "granularity": "hour",
        "observed_buckets": 24,
        "expected_buckets": 24,
        "coverage_ratio": 1.0,
        "volatility": 0.1,
        "confidence_score": 0.99,
        "baseline_hourly_spend": 5.0,
        "average_hourly_spend": 5.1,
        "top_region": "us-east-1",
        "hourly_cost_series": [1.0, 1.2, 0.9],
    }

    with (
        patch.object(strategies_api, "set_session_tenant_id", new=AsyncMock()),
        patch.object(strategies_api, "OptimizationService") as service_cls,
    ):
        service = MagicMock()
        service._get_strategy_impl = MagicMock(return_value=impl)
        service._aggregate_usage = AsyncMock(return_value=usage_data)
        service_cls.return_value = service

        out = await strategies_api.backtest_strategies(
            tenant_id=tenant_id,
            user=user,
            db=db,
            provider=None,
            strategy_type=None,
            days=7,
        )

    assert out.status == "success"
    assert len(out.strategies) == 1
    impl.backtest_hourly_series.assert_called_once_with(
        [1.0, 1.2, 0.9], tolerance=0.30
    )
    assert service._aggregate_usage.await_args.kwargs["canonical_charge_category"] == "compute"


@pytest.mark.asyncio
async def test_backtest_strategies_rejects_unsupported_provider() -> None:
    tenant_id = uuid4()
    db = MagicMock()

    with (
        patch.object(strategies_api, "set_session_tenant_id", new=AsyncMock()),
        patch.object(strategies_api, "OptimizationService"),
    ):
        with pytest.raises(HTTPException) as exc:
            await strategies_api.backtest_strategies(
                tenant_id=tenant_id,
                user=_user(),
                db=db,
                provider="digitalocean",
                strategy_type=None,
                days=30,
            )

    assert exc.value.status_code == 400
    assert "Unsupported provider" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_apply_recommendation_direct_success_returns_response_payload() -> None:
    tenant_id = uuid4()
    recommendation_id = uuid4()
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()

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
    db.execute.return_value = _scalar_result(recommendation)

    request = SimpleNamespace(
        method="POST",
        url=SimpleNamespace(path=f"/api/v1/strategies/apply/{recommendation_id}"),
    )
    user = _user()
    user.tenant_id = tenant_id

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
    assert isinstance(recommendation.applied_at, datetime)
    assert recommendation.applied_at.tzinfo == timezone.utc
    audit.log.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_apply_recommendation_direct_not_found_raises_resource_not_found() -> None:
    tenant_id = uuid4()
    recommendation_id = uuid4()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(None))

    request = SimpleNamespace(
        method="POST",
        url=SimpleNamespace(path=f"/api/v1/strategies/apply/{recommendation_id}"),
    )

    with patch.object(strategies_api, "set_session_tenant_id", new=AsyncMock()):
        with pytest.raises(ResourceNotFoundError, match="Recommendation not found"):
            await strategies_api.apply_recommendation(
                request=request,
                recommendation_id=recommendation_id,
                tenant_id=tenant_id,
                user=_user(),
                db=db,
            )
