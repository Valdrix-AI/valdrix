
import pytest
from datetime import date, timedelta, datetime
from decimal import Decimal
from app.schemas.costs import CostRecord
from app.services.analysis.forecaster import SymbolicForecaster

@pytest.mark.asyncio
async def test_forecaster_insufficient_data():
    history = [
        CostRecord(date=datetime.now() - timedelta(days=i), amount=Decimal("10.0"), service="ec2")
        for i in range(5)
    ]
    result = await SymbolicForecaster.forecast(history)
    assert result["confidence"] == "low"
    assert "Need at least 7 days of data" in result["reason"]

@pytest.mark.asyncio
async def test_forecaster_prophet_success():
    # Create 20 days of data for Prophet (requires >= 14 in my implementation)
    history = [
        CostRecord(date=datetime.now() - timedelta(days=i), amount=Decimal(str(10.0 + (i % 7))), service="ec2")
        for i in range(20)
    ]
    result = await SymbolicForecaster.forecast(history, days=5)
    
    assert result["model"] == "Prophet"
    assert len(result["forecast"]) == 5
    assert result["total_forecasted_cost"] > 0
    assert "weekly_seasonality" in result["diagnostics"]

@pytest.mark.asyncio
async def test_forecaster_fallback_holt_winters():
    # Create 10 days of data (too few for Prophet, but enough for HW)
    history = [
        CostRecord(date=datetime.now() - timedelta(days=i), amount=Decimal(str(10.0 + i)), service="ec2")
        for i in range(10)
    ]
    result = await SymbolicForecaster.forecast(history, days=3)
    
    assert "Holt-Winters" in result["model"]
    assert len(result["forecast"]) == 3
    assert result["total_forecasted_cost"] > 0
