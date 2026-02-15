"""Tests for Investor Health Dashboard API endpoints."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.health_dashboard import get_investor_health_dashboard
from app.modules.governance.api.v1.health_dashboard import (
    AWSConnectionHealth,
    InvestorHealthDashboard,
    JobQueueHealth,
    LLMUsageMetrics,
    TenantMetrics,
)


class _DisabledCache:
    enabled = False

    async def get(self, _key: str):
        return None

    async def set(self, _key: str, _value, ttl=None):
        return True


class _CacheHit:
    enabled = True

    def __init__(self, payload: dict):
        self.payload = payload
        self.set_called = False

    async def get(self, _key: str):
        return self.payload

    async def set(self, _key: str, _value, ttl=None):
        self.set_called = True
        return True


@pytest.mark.asyncio
async def test_get_investor_health_dashboard_handler_success():
    """Handler returns assembled dashboard payload when cache is cold."""
    mock_admin = MagicMock()
    mock_admin.role = "admin"
    mock_admin.tenant_id = uuid.uuid4()
    mock_db = AsyncMock()

    with (
        patch(
            "app.modules.governance.api.v1.health_dashboard.get_cache_service",
            return_value=_DisabledCache(),
        ),
        patch(
            "app.modules.governance.api.v1.health_dashboard._get_tenant_metrics",
            new=AsyncMock(
                return_value=TenantMetrics(
                    total_tenants=10,
                    active_last_24h=5,
                    active_last_7d=8,
                    trial_tenants=2,
                    paid_tenants=8,
                    churn_risk=1,
                )
            ),
        ),
        patch(
            "app.modules.governance.api.v1.health_dashboard._get_job_queue_health",
            new=AsyncMock(
                return_value=JobQueueHealth(
                    pending_jobs=1,
                    running_jobs=2,
                    failed_last_24h=0,
                    dead_letter_count=0,
                    avg_processing_time_ms=150.0,
                    p50_processing_time_ms=100.0,
                    p95_processing_time_ms=200.0,
                    p99_processing_time_ms=300.0,
                )
            ),
        ),
        patch(
            "app.modules.governance.api.v1.health_dashboard._get_llm_usage_metrics",
            new=AsyncMock(
                return_value=LLMUsageMetrics(
                    total_requests_24h=1000,
                    cache_hit_rate=0.85,
                    estimated_cost_24h=2.5,
                    budget_utilization=40.0,
                )
            ),
        ),
        patch(
            "app.modules.governance.api.v1.health_dashboard._get_aws_connection_health",
            new=AsyncMock(
                return_value=AWSConnectionHealth(
                    total_connections=5,
                    verified_connections=4,
                    failed_connections=1,
                )
            ),
        ),
    ):
        response = await get_investor_health_dashboard(mock_admin, mock_db)

    assert response.system.status == "healthy"
    assert response.tenants.total_tenants == 10
    assert response.job_queue.pending_jobs == 1
    assert response.llm_usage.total_requests_24h == 1000
    assert response.aws_connections.failed_connections == 1


@pytest.mark.asyncio
async def test_get_investor_health_dashboard_returns_cached_payload():
    """Handler short-circuits expensive queries when cache payload is present."""
    mock_admin = MagicMock()
    mock_admin.role = "admin"
    mock_admin.tenant_id = uuid.uuid4()
    mock_db = AsyncMock()

    cached_payload = InvestorHealthDashboard(
        generated_at=datetime.now(timezone.utc).isoformat(),
        system={
            "status": "healthy",
            "uptime_hours": 10.0,
            "last_check": datetime.now(timezone.utc).isoformat(),
        },
        tenants={
            "total_tenants": 5,
            "active_last_24h": 2,
            "active_last_7d": 4,
            "trial_tenants": 1,
            "paid_tenants": 4,
            "churn_risk": 0,
        },
        job_queue={
            "pending_jobs": 0,
            "running_jobs": 1,
            "failed_last_24h": 0,
            "dead_letter_count": 0,
            "avg_processing_time_ms": 50.0,
            "p50_processing_time_ms": 40.0,
            "p95_processing_time_ms": 70.0,
            "p99_processing_time_ms": 80.0,
        },
        llm_usage={
            "total_requests_24h": 10,
            "cache_hit_rate": 0.9,
            "estimated_cost_24h": 0.5,
            "budget_utilization": 15.0,
        },
        aws_connections={
            "total_connections": 2,
            "verified_connections": 2,
            "failed_connections": 0,
        },
    ).model_dump(mode="json")
    cache = _CacheHit(cached_payload)

    with (
        patch(
            "app.modules.governance.api.v1.health_dashboard.get_cache_service",
            return_value=cache,
        ),
        patch(
            "app.modules.governance.api.v1.health_dashboard._get_tenant_metrics",
            new=AsyncMock(),
        ) as tenant_metrics_mock,
        patch(
            "app.modules.governance.api.v1.health_dashboard._get_job_queue_health",
            new=AsyncMock(),
        ) as job_queue_mock,
        patch(
            "app.modules.governance.api.v1.health_dashboard._get_llm_usage_metrics",
            new=AsyncMock(),
        ) as llm_mock,
        patch(
            "app.modules.governance.api.v1.health_dashboard._get_aws_connection_health",
            new=AsyncMock(),
        ) as aws_mock,
    ):
        response = await get_investor_health_dashboard(mock_admin, mock_db)

    assert response.generated_at == cached_payload["generated_at"]
    tenant_metrics_mock.assert_not_awaited()
    job_queue_mock.assert_not_awaited()
    llm_mock.assert_not_awaited()
    aws_mock.assert_not_awaited()
    assert cache.set_called is False
