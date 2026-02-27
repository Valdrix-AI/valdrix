from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.modules.reporting.api.v1 import usage as usage_api
from app.modules.reporting.api.v1.usage import (
    FeatureUsageMetrics,
    LLMUsageMetrics,
    LLMUsageRecord,
    WorkloadMeteringMetrics,
)
from app.shared.core.auth import CurrentUser, UserRole
from app.shared.core.pricing import PricingTier


def _user(*, tenant_id: object | None = None) -> CurrentUser:
    if tenant_id is ...:
        tenant_id_value = None
    else:
        tenant_id_value = tenant_id if tenant_id is not None else uuid4()
    return CurrentUser(
        id=uuid4(),
        email="usage@example.com",
        tenant_id=tenant_id_value,
        role=UserRole.MEMBER,
        tier=PricingTier.PRO,
    )


def _scalars_result(rows: list[object]) -> MagicMock:
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    return result


def _one_result(row: object) -> MagicMock:
    result = MagicMock()
    result.one.return_value = row
    return result


class _Cache:
    def __init__(self, *, enabled: bool, cached_value: object):
        self.enabled = enabled
        self._cached_value = cached_value
        self.get = AsyncMock(return_value=cached_value)
        self.set = AsyncMock(return_value=True)


def _llm_metrics() -> LLMUsageMetrics:
    return LLMUsageMetrics(
        tokens_used=100,
        tokens_limit=1000,
        requests_count=2,
        estimated_cost_usd=0.1234,
        period_start="2026-02-01T00:00:00+00:00",
        period_end="2026-03-01T00:00:00+00:00",
        utilization_percent=10.0,
    )


def _workload_metrics() -> WorkloadMeteringMetrics:
    return WorkloadMeteringMetrics(
        finops_analysis_jobs_today=1,
        zombie_scans_today=2,
        active_connection_count=3,
        active_provider_count=2,
        last_scan_at="2026-02-26T12:00:00+00:00",
    )


def _feature_metrics() -> FeatureUsageMetrics:
    return FeatureUsageMetrics(
        greenops_enabled=True,
        activeops_enabled=True,
        webhooks_configured=1,
        total_remediations=4,
    )


def _recent_usage() -> list[LLMUsageRecord]:
    return [
        LLMUsageRecord(
            id=uuid4(),
            created_at="2026-02-26T12:00:00+00:00",
            model="gpt-4o-mini",
            input_tokens=10,
            output_tokens=20,
            total_tokens=30,
            cost_usd=0.0012,
            request_type="analysis",
        )
    ]


@pytest.mark.asyncio
async def test_usage_require_tenant_id_raises_without_tenant() -> None:
    user = _user(tenant_id=...)
    with pytest.raises(ValueError, match="tenant_id is required for usage metrics"):
        usage_api._require_tenant_id(user)


@pytest.mark.asyncio
async def test_get_usage_metrics_cache_non_dict_falls_through_and_sets_cache() -> None:
    user = _user()
    db = MagicMock()
    cache = _Cache(enabled=True, cached_value="not-a-dict")

    with (
        patch.object(usage_api, "get_cache_service", return_value=cache),
        patch.object(usage_api, "_get_llm_usage", new=AsyncMock(return_value=_llm_metrics())),
        patch.object(
            usage_api,
            "_get_recent_llm_activity",
            new=AsyncMock(return_value=_recent_usage()),
        ),
        patch.object(
            usage_api,
            "_get_workload_metering",
            new=AsyncMock(return_value=_workload_metrics()),
        ),
        patch.object(
            usage_api, "_get_feature_usage", new=AsyncMock(return_value=_feature_metrics())
        ),
    ):
        response = await usage_api.get_usage_metrics(user=user, db=db)

    assert response.tenant_id == user.tenant_id
    cache.get.assert_awaited_once()
    cache.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_usage_metrics_cache_invalid_dict_logs_warning_and_rebuilds() -> None:
    user = _user()
    db = MagicMock()
    cache = _Cache(enabled=True, cached_value={"tenant_id": str(user.tenant_id)})

    with (
        patch.object(usage_api, "get_cache_service", return_value=cache),
        patch.object(usage_api, "_get_llm_usage", new=AsyncMock(return_value=_llm_metrics())),
        patch.object(
            usage_api,
            "_get_recent_llm_activity",
            new=AsyncMock(return_value=_recent_usage()),
        ),
        patch.object(
            usage_api,
            "_get_workload_metering",
            new=AsyncMock(return_value=_workload_metrics()),
        ),
        patch.object(
            usage_api, "_get_feature_usage", new=AsyncMock(return_value=_feature_metrics())
        ),
        patch.object(usage_api, "logger") as logger_mock,
    ):
        response = await usage_api.get_usage_metrics(user=user, db=db)

    assert response.tenant_id == user.tenant_id
    logger_mock.warning.assert_called_once()
    cache.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_recent_llm_activity_serializes_records() -> None:
    tenant_id = uuid4()
    now = datetime(2026, 2, 26, 12, 0, tzinfo=timezone.utc)
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=_scalars_result(
            [
                SimpleNamespace(
                    id=uuid4(),
                    created_at=now,
                    model="gpt-4.1",
                    input_tokens=11,
                    output_tokens=22,
                    total_tokens=33,
                    cost_usd=Decimal("0.0421"),
                    request_type="chat",
                )
            ]
        )
    )

    out = await usage_api._get_recent_llm_activity(db, tenant_id)

    assert len(out) == 1
    assert out[0].created_at == now.isoformat()
    assert out[0].cost_usd == 0.0421
    assert out[0].request_type == "chat"


@pytest.mark.asyncio
async def test_get_llm_usage_computes_limits_from_budget_and_rounds() -> None:
    tenant_id = uuid4()
    now = datetime(2026, 2, 26, 12, 0, tzinfo=timezone.utc)
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=_one_result(
            SimpleNamespace(
                tokens_used=1500,
                requests_count=3,
                cost_usd=Decimal("1.23456"),
                budget_limit_usd=Decimal("2.5"),
            )
        )
    )

    metrics = await usage_api._get_llm_usage(db, tenant_id, now)

    assert metrics.tokens_used == 1500
    assert metrics.tokens_limit == 250000
    assert metrics.requests_count == 3
    assert metrics.estimated_cost_usd == 1.2346
    assert metrics.period_start.startswith("2026-02-01T00:00:00")
    assert metrics.period_end.startswith("2026-03-01T00:00:00")
    assert metrics.utilization_percent == 0.6


@pytest.mark.asyncio
async def test_get_llm_usage_handles_zero_budget_limit_without_divide_by_zero() -> None:
    tenant_id = uuid4()
    now = datetime(2026, 2, 26, 12, 0, tzinfo=timezone.utc)
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=_one_result(
            SimpleNamespace(
                tokens_used=5,
                requests_count=1,
                cost_usd=0,
                budget_limit_usd=0,
            )
        )
    )

    metrics = await usage_api._get_llm_usage(db, tenant_id, now)

    assert metrics.tokens_limit == 0
    assert metrics.utilization_percent == 0.0


@pytest.mark.asyncio
async def test_get_workload_metering_counts_active_connections_and_providers() -> None:
    tenant_id = uuid4()
    today_start = datetime(2026, 2, 26, 0, 0, tzinfo=timezone.utc)
    last_scan = datetime(2026, 2, 26, 10, 30, tzinfo=timezone.utc)
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=_one_result(
            SimpleNamespace(
                cost_analysis_calls=4,
                zombie_scans=2,
                last_scan=last_scan,
            )
        )
    )
    connections = [
        SimpleNamespace(provider=" AWS "),
        SimpleNamespace(provider="aws"),
        SimpleNamespace(provider=" gcp "),
        SimpleNamespace(provider=""),
        SimpleNamespace(provider=None),
    ]

    with patch.object(usage_api, "list_tenant_connections", new=AsyncMock(return_value=connections)):
        metrics = await usage_api._get_workload_metering(db, tenant_id, today_start)

    assert metrics.finops_analysis_jobs_today == 4
    assert metrics.zombie_scans_today == 2
    assert metrics.active_connection_count == 5
    assert metrics.active_provider_count == 2
    assert metrics.last_scan_at == last_scan.isoformat()


@pytest.mark.asyncio
async def test_get_feature_usage_paid_tier_with_enum_like_plan_and_slack_enabled() -> None:
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=_one_result(
            SimpleNamespace(
                tenant_plan=SimpleNamespace(value="pro"),
                slack_enabled=1,
                remediation_count=7,
            )
        )
    )

    metrics = await usage_api._get_feature_usage(db, uuid4())

    assert metrics.greenops_enabled is True
    assert metrics.activeops_enabled is True
    assert metrics.webhooks_configured == 1
    assert metrics.total_remediations == 7


@pytest.mark.asyncio
async def test_get_feature_usage_starter_tier_disables_paid_flags() -> None:
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=_one_result(
            SimpleNamespace(
                tenant_plan="starter",
                slack_enabled=0,
                remediation_count=None,
            )
        )
    )

    metrics = await usage_api._get_feature_usage(db, uuid4())

    assert metrics.greenops_enabled is False
    assert metrics.activeops_enabled is False
    assert metrics.webhooks_configured == 0
    assert metrics.total_remediations == 0
