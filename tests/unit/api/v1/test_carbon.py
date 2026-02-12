import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from app.modules.reporting.api.v1.carbon import (
    get_carbon_footprint,
    get_carbon_budget,
    analyze_graviton_opportunities,
    get_carbon_intensity_forecast
)

@pytest.mark.asyncio
async def test_get_carbon_footprint_date_range_error():
    user = MagicMock()
    db = AsyncMock()
    start = date.today()
    end = start + timedelta(days=400)
    
    with pytest.raises(HTTPException) as exc:
        await get_carbon_footprint(start, end, user, db)
    assert exc.value.status_code == 400
    assert "Date range cannot exceed 1 year" in exc.value.detail

@pytest.mark.asyncio
@patch("app.modules.reporting.api.v1.carbon._fetch_provider_cost_data", new_callable=AsyncMock)
@patch("app.modules.reporting.api.v1.carbon._get_provider_connection", new_callable=AsyncMock)
async def test_get_carbon_footprint_success(mock_get_connection, mock_fetch_cost_data):
    user = MagicMock()
    user.tenant_id = "tenant-123"
    db = AsyncMock()
    mock_get_connection.return_value = MagicMock()
    mock_fetch_cost_data.return_value = [{"service": "Amazon EC2", "cost_usd": 100.0}]
    
    with patch("app.modules.reporting.api.v1.carbon.CarbonCalculator") as mock_calc_class:
        mock_calc = mock_calc_class.return_value
        mock_calc.calculate_from_costs.return_value = {"total_co2_kg": 10.5}
        
        response = await get_carbon_footprint(date.today(), date.today(), user, db)
        assert response["total_co2_kg"] == 10.5

@pytest.mark.asyncio
@patch("app.modules.reporting.api.v1.carbon._get_provider_connection", new_callable=AsyncMock)
async def test_get_carbon_budget_no_connection(mock_get_connection):
    user = MagicMock()
    user.tenant_id = "tenant-123"
    db = AsyncMock()
    mock_get_connection.return_value = None
    
    response = await get_carbon_budget(user, db)
    assert response["alert_status"] == "unknown"

@pytest.mark.asyncio
@patch("app.modules.reporting.api.v1.carbon._fetch_provider_cost_data", new_callable=AsyncMock)
@patch("app.modules.reporting.api.v1.carbon._get_provider_connection", new_callable=AsyncMock)
@patch("app.modules.reporting.api.v1.carbon.CarbonBudgetService")
async def test_get_carbon_budget_success(mock_budget_service_class, mock_get_connection, mock_fetch_cost_data):
    user = MagicMock()
    user.tenant_id = "tenant-123"
    db = AsyncMock()

    mock_get_connection.return_value = MagicMock()
    mock_fetch_cost_data.return_value = [{"service": "Amazon EC2", "cost_usd": 10.0}]

    # Carbon settings lookup query
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_result
    
    mock_budget_service = mock_budget_service_class.return_value
    mock_budget_service.get_budget_status = AsyncMock(return_value={"alert_status": "ok"})
    
    response = await get_carbon_budget(user, db)
    assert response["alert_status"] == "ok"

@pytest.mark.asyncio
async def test_get_carbon_footprint_invalid_provider():
    user = MagicMock()
    user.tenant_id = "tenant-123"
    db = AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await get_carbon_footprint(date.today(), date.today(), user, db, provider="oracle")
    assert exc.value.status_code == 400

@pytest.mark.asyncio
@patch("app.modules.reporting.api.v1.carbon.MultiTenantAWSAdapter")
@patch("app.modules.reporting.api.v1.carbon.GravitonAnalyzer")
async def test_analyze_graviton_opportunities_success(mock_analyzer_class, mock_adapter_class):
    user = MagicMock()
    user.tenant_id = "tenant-123"
    db = AsyncMock()
    
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = MagicMock()
    db.execute.return_value = mock_result
    
    mock_adapter = mock_adapter_class.return_value
    mock_adapter.get_credentials = AsyncMock(return_value={})
    
    mock_analyzer = mock_analyzer_class.return_value
    mock_analyzer.analyze_instances = AsyncMock(return_value={"candidates": []})
    
    response = await analyze_graviton_opportunities(user, db)
    assert "candidates" in response

@pytest.mark.asyncio
@patch("app.modules.reporting.api.v1.carbon.CarbonAwareScheduler")
async def test_get_carbon_intensity_forecast(mock_scheduler_class):
    user = MagicMock()
    mock_scheduler = mock_scheduler_class.return_value
    mock_scheduler.get_intensity_forecast = AsyncMock(return_value=[])
    mock_scheduler.get_region_intensity = AsyncMock(return_value=0.5)
    
    response = await get_carbon_intensity_forecast(user, "us-east-1", 24)
    assert response["current_intensity"] == 0.5
