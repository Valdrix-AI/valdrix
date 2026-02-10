
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch, AsyncMock
from app.shared.analysis.forecaster import SymbolicForecaster
from app.modules.governance.domain.scheduler.orchestrator import SchedulerOrchestrator

@pytest.mark.asyncio
async def test_forecast_carbon():
    """Test carbon forecasting integration."""
    # Mock history with the attributes forecaster expects: .date and .amount
    history = []
    for i in range(30):
        record = MagicMock()
        record.date = datetime(2025, 1, 1) + timedelta(days=i)
        record.amount = Decimal("10.0") + Decimal(str(i % 5))
        history.append(record)
    
    # Mock cost forecast to return 30 days of data
    mock_cost_res = {
        "forecast": [{"date": f"2025-02-{i+1:02d}", "amount": Decimal("10.0")} for i in range(30)],
        "total_forecasted_cost": Decimal("300.0"),
        "confidence": "high",
        "model": "Prophet"
    }
    
    async_mock_cost_res = AsyncMock(return_value=mock_cost_res)
    with patch.object(SymbolicForecaster, "forecast", side_effect=async_mock_cost_res):
        results = await SymbolicForecaster.forecast_carbon(history, region="us-east-1", days=30)
        
        assert results["total_forecasted_co2_kg"] > 0
        assert len(results["forecast"]) == 30
        assert results["unit"] == "kg CO2e"
        assert results["region"] == "us-east-1"

@pytest.mark.asyncio
async def test_is_low_carbon_window():
    """Test the Green Window logic."""
    session_maker = MagicMock()
    orchestrator = SchedulerOrchestrator(session_maker)
    
    # Test high solar window (12PM UTC)
    with patch("app.modules.governance.domain.scheduler.orchestrator.datetime") as mock_dt:
        mock_now = MagicMock()
        mock_now.hour = 12
        mock_dt.now.return_value = mock_now
        result = await orchestrator.is_low_carbon_window("us-east-1")
        assert result is True
        
    # Test peak demand window (7PM UTC)
    with patch("app.modules.governance.domain.scheduler.orchestrator.datetime") as mock_dt:
        mock_now = MagicMock()
        mock_now.hour = 19
        mock_dt.now.return_value = mock_now
        result = await orchestrator.is_low_carbon_window("us-east-1")
        assert result is False

@pytest.mark.asyncio
async def test_green_scheduling_delays_in_non_green_window():
    """Test that is_low_carbon_window returns False during peak hours."""
    session_maker = MagicMock()
    orchestrator = SchedulerOrchestrator(session_maker)
    
    # Test 8PM UTC - should NOT be green
    with patch("app.modules.governance.domain.scheduler.orchestrator.datetime") as mock_dt:
        mock_now = MagicMock()
        mock_now.hour = 20
        mock_dt.now.return_value = mock_now
        result = await orchestrator.is_low_carbon_window("us-east-1")
        assert result is False

    # Test 3AM UTC - SHOULD be green (low demand)
    with patch("app.modules.governance.domain.scheduler.orchestrator.datetime") as mock_dt:
        mock_now = MagicMock()
        mock_now.hour = 3
        mock_dt.now.return_value = mock_now
        result = await orchestrator.is_low_carbon_window("us-east-1")
        assert result is True
