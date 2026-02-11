import pytest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient
from app.shared.core.auth import CurrentUser, get_current_user, UserRole
from app.shared.core.pricing import PricingTier


@pytest.mark.asyncio
async def test_get_costs_and_breakdown(async_client: AsyncClient, app):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="costs@valdrix.io",
        role=UserRole.MEMBER,
        tier=PricingTier.STARTER,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        with patch("app.modules.reporting.api.v1.costs.CostAggregator.get_dashboard_summary", new=AsyncMock()) as mock_summary, \
             patch("app.modules.reporting.api.v1.costs.CostAggregator.get_basic_breakdown", new=AsyncMock()) as mock_breakdown:
            mock_summary.return_value = {"total_cost": 123.45}
            mock_breakdown.return_value = {"services": []}

            response = await async_client.get(
                "/api/v1/costs",
                params={"start_date": "2024-01-01", "end_date": "2024-01-31"},
            )
            assert response.status_code == 200
            assert response.json()["total_cost"] == 123.45

            response = await async_client.get(
                "/api/v1/costs/breakdown",
                params={"start_date": "2024-01-01", "end_date": "2024-01-31"},
            )
            assert response.status_code == 200
            assert response.json()["services"] == []
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_cost_forecast_paths(async_client: AsyncClient, app):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="forecast@valdrix.io",
        role=UserRole.MEMBER,
        tier=PricingTier.STARTER,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        # Insufficient records -> 400
        with patch("app.modules.reporting.api.v1.costs.CostAggregator.get_summary", new=AsyncMock()) as mock_summary:
            mock_summary.return_value = SimpleNamespace(records=[])
            response = await async_client.get("/api/v1/costs/forecast", params={"days": 30})
            assert response.status_code == 400
            assert "Insufficient cost history" in response.json()["error"]

        # Sufficient records -> forecast returned
        with patch("app.modules.reporting.api.v1.costs.CostAggregator.get_summary", new=AsyncMock()) as mock_summary, \
             patch("app.shared.analysis.forecaster.SymbolicForecaster.forecast", new=AsyncMock()) as mock_forecast:
            mock_summary.return_value = SimpleNamespace(records=[{"cost": 10.0}])
            mock_forecast.return_value = {"forecast": [1, 2, 3]}
            response = await async_client.get("/api/v1/costs/forecast", params={"days": 14})
            assert response.status_code == 200
            assert response.json()["forecast"] == [1, 2, 3]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_analyze_costs_paths(async_client: AsyncClient, app):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="analyze@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        # No records -> fallback response
        with patch("app.modules.reporting.api.v1.costs.CostAggregator.get_summary", new=AsyncMock()) as mock_summary:
            mock_summary.return_value = SimpleNamespace(records=[])
            response = await async_client.post("/api/v1/costs/analyze")
            assert response.status_code == 200
            data = response.json()
            assert data["summary"] == "No cost data available for analysis."

        # Records -> analyzer path
        with patch("app.modules.reporting.api.v1.costs.CostAggregator.get_summary", new=AsyncMock()) as mock_summary, \
             patch("app.modules.reporting.api.v1.costs.LLMFactory.create", return_value=MagicMock()) as mock_create, \
             patch("app.modules.reporting.api.v1.costs.FinOpsAnalyzer") as mock_analyzer_class:
            mock_summary.return_value = SimpleNamespace(records=[{"cost": 10.0}])
            mock_analyzer = mock_analyzer_class.return_value
            mock_analyzer.analyze = AsyncMock(return_value={"summary": "ok"})

            response = await async_client.post("/api/v1/costs/analyze")
            assert response.status_code == 200
            assert response.json()["summary"] == "ok"
            assert mock_create.called
            assert mock_analyzer.analyze.await_count == 1
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_analyze_costs_requires_tier(async_client: AsyncClient, app):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="starter@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.STARTER,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.post("/api/v1/costs/analyze")
        assert response.status_code == 403
        assert "requires" in response.json()["error"].lower()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_trigger_ingest(async_client: AsyncClient, app):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="ingest@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.STARTER,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        mock_job = SimpleNamespace(id=uuid.uuid4())
        with patch("app.modules.governance.domain.jobs.processor.enqueue_job", new=AsyncMock(return_value=mock_job)):
            response = await async_client.post("/api/v1/costs/ingest")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "queued"
            assert data["job_id"] == str(mock_job.id)
    finally:
        app.dependency_overrides.pop(get_current_user, None)
