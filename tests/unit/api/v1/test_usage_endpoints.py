"""
Tests for Usage Metering API Endpoints
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from app.modules.reporting.api.v1.usage import (
    get_usage_metrics,
    LLMUsageMetrics,
    WorkloadMeteringMetrics,
    FeatureUsageMetrics,
)


@pytest.mark.asyncio
async def test_get_usage_metrics_handler_success():
    """Test get_usage_metrics direct handler call."""
    tenant_id = uuid4()
    mock_user = MagicMock()
    mock_user.tenant_id = tenant_id
    mock_user.tier = "growth"

    mock_db = AsyncMock()

    now = datetime.now(timezone.utc)

    with (
        patch(
            "app.modules.reporting.api.v1.usage._get_llm_usage",
            new=AsyncMock(
                return_value=LLMUsageMetrics(
                    tokens_used=5000,
                    tokens_limit=100000,
                    requests_count=10,
                    estimated_cost_usd=0.5,
                    period_start=now.isoformat(),
                    period_end=now.isoformat(),
                    utilization_percent=5.0,
                )
            ),
        ),
        patch(
            "app.modules.reporting.api.v1.usage._get_recent_llm_activity",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.reporting.api.v1.usage._get_workload_metering",
            new=AsyncMock(
                return_value=WorkloadMeteringMetrics(
                    finops_analysis_jobs_today=5,
                    zombie_scans_today=2,
                    active_connection_count=4,
                    active_provider_count=3,
                    last_scan_at=now.isoformat(),
                )
            ),
        ),
        patch(
            "app.modules.reporting.api.v1.usage._get_feature_usage",
            new=AsyncMock(
                return_value=FeatureUsageMetrics(
                    greenops_enabled=True,
                    activeops_enabled=True,
                    webhooks_configured=1,
                    total_remediations=10,
                )
            ),
        ),
    ):
        response = await get_usage_metrics(mock_user, mock_db)

    assert response.tenant_id == tenant_id
    assert response.llm.tokens_used == 5000
    assert response.workloads.zombie_scans_today == 2
    assert response.features.total_remediations == 10
