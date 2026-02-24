from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

import app.modules.governance.api.v1.health_dashboard as hd
from app.models.azure_connection import AzureConnection
from app.modules.governance.api.v1.health_dashboard import (
    CloudConnectionHealth,
    CloudPlusConnectionHealth,
    CloudPlusProviderHealth,
    JobQueueHealth,
    LLMUsageMetrics,
    LicenseGovernanceHealth,
    TenantMetrics,
)
from app.shared.core.pricing import PricingTier


def _result_one(row: object) -> MagicMock:
    result = MagicMock()
    result.one.return_value = row
    return result


def _result_scalar(value: object) -> MagicMock:
    result = MagicMock()
    result.scalar.return_value = value
    return result


def _result_all(rows: list[tuple[datetime | None, datetime | None]]) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows
    return result


class _EnabledCache:
    enabled = True

    def __init__(self, payload: object) -> None:
        self._payload = payload
        self.set = AsyncMock(return_value=True)

    async def get(self, _key: str):
        return self._payload


@pytest.mark.asyncio
async def test_numeric_normalization_helpers() -> None:
    assert hd._positive_int_or_none("12") == 12
    assert hd._positive_int_or_none(0) is None
    assert hd._positive_int_or_none("bad") is None

    assert hd._coerce_int_with_minimum("60", default=180, minimum=30) == 60
    assert hd._coerce_int_with_minimum("5", default=180, minimum=30) == 30
    assert hd._coerce_int_with_minimum("bad", default=180, minimum=30) == 180


@pytest.mark.asyncio
async def test_get_cloud_plus_provider_health_caps_error_counts() -> None:
    db = AsyncMock()
    db.execute.return_value = _result_one(
        SimpleNamespace(total_connections=5, active_connections=3, errored_connections=9)
    )

    snapshot = await hd._get_cloud_plus_provider_health(db, AzureConnection)

    assert snapshot.total_connections == 5
    assert snapshot.active_connections == 3
    assert snapshot.inactive_connections == 2
    assert snapshot.errored_connections == 5


@pytest.mark.asyncio
async def test_get_aws_provider_health_uses_status_fields() -> None:
    db = AsyncMock()
    db.execute.return_value = _result_one(
        SimpleNamespace(total_connections=4, active_connections=2, errored_connections=1)
    )

    snapshot = await hd._get_aws_provider_health(db)

    assert snapshot.total_connections == 4
    assert snapshot.active_connections == 2
    assert snapshot.inactive_connections == 2
    assert snapshot.errored_connections == 1


@pytest.mark.asyncio
async def test_get_cloud_connection_health_aggregates_provider_snapshots() -> None:
    db = AsyncMock()
    aws = CloudPlusProviderHealth(
        total_connections=5,
        active_connections=4,
        inactive_connections=1,
        errored_connections=1,
    )
    azure = CloudPlusProviderHealth(
        total_connections=2,
        active_connections=1,
        inactive_connections=1,
        errored_connections=0,
    )
    gcp = CloudPlusProviderHealth(
        total_connections=1,
        active_connections=1,
        inactive_connections=0,
        errored_connections=0,
    )
    with patch.object(hd, "_get_aws_provider_health", new=AsyncMock(return_value=aws)), patch.object(
        hd,
        "_get_cloud_plus_provider_health",
        new=AsyncMock(side_effect=[azure, gcp]),
    ):
        summary = await hd._get_cloud_connection_health(db)

    assert summary.total_connections == 8
    assert summary.active_connections == 6
    assert summary.inactive_connections == 2
    assert summary.errored_connections == 1
    assert set(summary.providers.keys()) == {"aws", "azure", "gcp"}


@pytest.mark.asyncio
async def test_get_cloud_plus_connection_health_aggregates_models() -> None:
    db = AsyncMock()
    with patch.object(
        hd,
        "_get_cloud_plus_provider_health",
        new=AsyncMock(
            side_effect=[
                CloudPlusProviderHealth(
                    total_connections=1,
                    active_connections=1,
                    inactive_connections=0,
                    errored_connections=0,
                ),
                CloudPlusProviderHealth(
                    total_connections=2,
                    active_connections=1,
                    inactive_connections=1,
                    errored_connections=1,
                ),
                CloudPlusProviderHealth(
                    total_connections=3,
                    active_connections=2,
                    inactive_connections=1,
                    errored_connections=0,
                ),
                CloudPlusProviderHealth(
                    total_connections=4,
                    active_connections=3,
                    inactive_connections=1,
                    errored_connections=2,
                ),
            ]
        ),
    ):
        summary = await hd._get_cloud_plus_connection_health(db)

    assert summary.total_connections == 10
    assert summary.active_connections == 7
    assert summary.inactive_connections == 3
    assert summary.errored_connections == 3
    assert set(summary.providers.keys()) == {"saas", "license", "platform", "hybrid"}


@pytest.mark.asyncio
async def test_get_tenant_metrics_coerces_nulls_to_zero() -> None:
    db = AsyncMock()
    db.execute.return_value = _result_one(
        SimpleNamespace(
            total_tenants=None,
            active_last_24h=3,
            active_last_7d=None,
            free_tenants=2,
            paid_tenants=1,
            churn_risk=None,
        )
    )

    metrics = await hd._get_tenant_metrics(db, datetime.now(timezone.utc))

    assert metrics.total_tenants == 0
    assert metrics.active_last_24h == 3
    assert metrics.active_last_7d == 0
    assert metrics.free_tenants == 2
    assert metrics.paid_tenants == 1
    assert metrics.churn_risk == 0


@pytest.mark.asyncio
async def test_get_job_queue_health_sqlite_fallback_percentiles() -> None:
    db = AsyncMock()
    db.execute.side_effect = [
        _result_one(
            SimpleNamespace(
                pending_jobs=4,
                running_jobs=1,
                failed_last_24h=2,
                dead_letter_count=1,
            )
        ),
        _result_scalar(123.456),
    ]

    engine = SimpleNamespace(
        url=SimpleNamespace(get_backend_name=lambda: "sqlite"),
    )
    with patch("app.shared.db.session.get_engine", return_value=engine):
        metrics = await hd._get_job_queue_health(db, datetime.now(timezone.utc))

    assert metrics.pending_jobs == 4
    assert metrics.running_jobs == 1
    assert metrics.failed_last_24h == 2
    assert metrics.dead_letter_count == 1
    assert metrics.avg_processing_time_ms == 123.46
    assert metrics.p50_processing_time_ms == 123.46
    assert metrics.p95_processing_time_ms == 123.46
    assert metrics.p99_processing_time_ms == 123.46


@pytest.mark.asyncio
async def test_get_job_queue_health_postgres_percentiles() -> None:
    db = AsyncMock()
    db.execute.side_effect = [
        _result_one(
            SimpleNamespace(
                pending_jobs=0,
                running_jobs=0,
                failed_last_24h=0,
                dead_letter_count=0,
            )
        ),
        _result_one((10.1234, 5.1, 9.6, 11.2)),
    ]
    engine = SimpleNamespace(
        url=SimpleNamespace(get_backend_name=lambda: "postgresql+psycopg"),
    )
    with patch("app.shared.db.session.get_engine", return_value=engine):
        metrics = await hd._get_job_queue_health(db, datetime.now(timezone.utc))

    assert metrics.avg_processing_time_ms == 10.12
    assert metrics.p50_processing_time_ms == 5.1
    assert metrics.p95_processing_time_ms == 9.6
    assert metrics.p99_processing_time_ms == 11.2


@pytest.mark.asyncio
async def test_get_llm_usage_metrics_sets_burn_rate_metric() -> None:
    db = AsyncMock()
    db.execute.side_effect = [
        _result_one(SimpleNamespace(total_requests_24h=7, estimated_cost_24h=12.5)),
        _result_scalar(0.2378),
    ]
    burn_rate_metric = MagicMock()

    with patch.object(hd, "LLM_BUDGET_BURN_RATE", burn_rate_metric):
        metrics = await hd._get_llm_usage_metrics(db, datetime.now(timezone.utc))

    assert metrics.total_requests_24h == 7
    assert metrics.estimated_cost_24h == 12.5
    assert metrics.budget_utilization == 23.78
    burn_rate_metric.set.assert_called_once_with(23.78)


@pytest.mark.asyncio
async def test_get_license_governance_health_rates_and_duration() -> None:
    now = datetime.now(timezone.utc)
    db = AsyncMock()
    db.scalar.return_value = 3
    db.execute.side_effect = [
        _result_one(
            SimpleNamespace(
                created_requests=4,
                completed_requests=2,
                failed_requests=1,
                in_flight_requests=1,
            )
        ),
        _result_all(
            [
                (now - timedelta(hours=4), now - timedelta(hours=1)),
                (datetime.now() - timedelta(hours=2), datetime.now() - timedelta(hours=1)),
                (now - timedelta(hours=1), now - timedelta(hours=2)),
                (None, now),
            ]
        ),
    ]

    metrics = await hd._get_license_governance_health(db, now)

    assert metrics.active_license_connections == 3
    assert metrics.requests_created_24h == 4
    assert metrics.requests_completed_24h == 2
    assert metrics.requests_failed_24h == 1
    assert metrics.requests_in_flight == 1
    assert metrics.completion_rate_percent == 50.0
    assert metrics.failure_rate_percent == 25.0
    assert metrics.avg_time_to_complete_hours == 2.0


@pytest.mark.asyncio
async def test_get_license_governance_health_zero_denominator() -> None:
    now = datetime.now(timezone.utc)
    db = AsyncMock()
    db.scalar.return_value = 0
    db.execute.side_effect = [
        _result_one(
            SimpleNamespace(
                created_requests=0,
                completed_requests=0,
                failed_requests=0,
                in_flight_requests=0,
            )
        ),
        _result_all([]),
    ]

    metrics = await hd._get_license_governance_health(db, now)

    assert metrics.completion_rate_percent == 0.0
    assert metrics.failure_rate_percent == 0.0
    assert metrics.avg_time_to_complete_hours is None


@pytest.mark.asyncio
async def test_dashboard_cache_decode_failure_falls_back_to_fresh_payload() -> None:
    user = MagicMock()
    user.tenant_id = uuid4()
    db = AsyncMock()
    cache = _EnabledCache({"invalid": "payload"})

    with patch.object(hd, "get_cache_service", return_value=cache), patch.object(
        hd, "_get_tenant_metrics", new=AsyncMock(return_value=TenantMetrics(
            total_tenants=1,
            active_last_24h=1,
            active_last_7d=1,
            free_tenants=1,
            paid_tenants=0,
            churn_risk=0,
        ))
    ), patch.object(
        hd, "_get_job_queue_health", new=AsyncMock(return_value=JobQueueHealth(
            pending_jobs=0,
            running_jobs=0,
            failed_last_24h=0,
            dead_letter_count=0,
            avg_processing_time_ms=0.0,
            p50_processing_time_ms=0.0,
            p95_processing_time_ms=0.0,
            p99_processing_time_ms=0.0,
        ))
    ), patch.object(
        hd, "_get_llm_usage_metrics", new=AsyncMock(return_value=LLMUsageMetrics(
            total_requests_24h=0,
            cache_hit_rate=0.85,
            estimated_cost_24h=0.0,
            budget_utilization=0.0,
        ))
    ), patch.object(
        hd, "_get_cloud_connection_health", new=AsyncMock(return_value=CloudConnectionHealth(
            total_connections=0,
            active_connections=0,
            inactive_connections=0,
            errored_connections=0,
            providers={},
        ))
    ), patch.object(
        hd, "_get_cloud_plus_connection_health", new=AsyncMock(return_value=CloudPlusConnectionHealth(
            total_connections=0,
            active_connections=0,
            inactive_connections=0,
            errored_connections=0,
            providers={},
        ))
    ), patch.object(
        hd, "_get_license_governance_health", new=AsyncMock(return_value=LicenseGovernanceHealth(
            window_hours=24,
            active_license_connections=0,
            requests_created_24h=0,
            requests_completed_24h=0,
            requests_failed_24h=0,
            requests_in_flight=0,
            completion_rate_percent=0.0,
            failure_rate_percent=0.0,
            avg_time_to_complete_hours=None,
        ))
    ), patch.object(hd.logger, "warning") as warning_mock:
        payload = await hd.get_investor_health_dashboard(user, db)

    assert payload.system.status == "healthy"
    warning_mock.assert_called()
    cache.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_fair_use_runtime_tier_lookup_failure_and_cache_set() -> None:
    user = MagicMock()
    user.tenant_id = uuid4()
    db = AsyncMock()
    cache = _EnabledCache({"invalid": "payload"})
    settings = SimpleNamespace(
        LLM_FAIR_USE_GUARDS_ENABLED=True,
        LLM_FAIR_USE_PRO_DAILY_SOFT_CAP="0",
        LLM_FAIR_USE_ENTERPRISE_DAILY_SOFT_CAP="bad",
        LLM_FAIR_USE_PER_MINUTE_CAP=-10,
        LLM_FAIR_USE_PER_TENANT_CONCURRENCY_CAP=None,
        LLM_FAIR_USE_CONCURRENCY_LEASE_TTL_SECONDS="10",
    )

    with patch.object(hd, "get_cache_service", return_value=cache), patch.object(
        hd, "get_settings", return_value=settings
    ), patch.object(
        hd, "get_tenant_tier", new=AsyncMock(side_effect=RuntimeError("tier lookup failed"))
    ) as tier_mock, patch.object(hd.logger, "warning") as warning_mock:
        payload = await hd.get_llm_fair_use_runtime(user, db)

    assert payload.guards_enabled is True
    assert payload.tenant_tier == PricingTier.FREE.value
    assert payload.tier_eligible is False
    assert payload.active_for_tenant is False
    assert payload.thresholds.pro_daily_soft_cap is None
    assert payload.thresholds.enterprise_daily_soft_cap is None
    assert payload.thresholds.per_minute_cap is None
    assert payload.thresholds.per_tenant_concurrency_cap is None
    assert payload.thresholds.concurrency_lease_ttl_seconds == 30
    tier_mock.assert_awaited_once()
    warning_mock.assert_called()
    cache.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_fair_use_runtime_global_scope_skips_tier_lookup() -> None:
    user = MagicMock()
    user.tenant_id = None
    db = AsyncMock()
    cache = _EnabledCache(None)
    settings = SimpleNamespace(
        LLM_FAIR_USE_GUARDS_ENABLED=False,
        LLM_FAIR_USE_PRO_DAILY_SOFT_CAP=100,
        LLM_FAIR_USE_ENTERPRISE_DAILY_SOFT_CAP=500,
        LLM_FAIR_USE_PER_MINUTE_CAP=5,
        LLM_FAIR_USE_PER_TENANT_CONCURRENCY_CAP=2,
        LLM_FAIR_USE_CONCURRENCY_LEASE_TTL_SECONDS=180,
    )

    with patch.object(hd, "get_cache_service", return_value=cache), patch.object(
        hd, "get_settings", return_value=settings
    ), patch.object(hd, "get_tenant_tier", new=AsyncMock()) as tier_mock:
        payload = await hd.get_llm_fair_use_runtime(user, db)

    assert payload.tenant_tier == PricingTier.FREE.value
    assert payload.active_for_tenant is False
    tier_mock.assert_not_awaited()
