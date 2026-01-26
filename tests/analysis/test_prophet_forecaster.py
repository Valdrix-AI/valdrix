
import pytest
from datetime import timedelta, datetime
from decimal import Decimal
from app.schemas.costs import CostRecord
from app.shared.analysis.forecaster import SymbolicForecaster

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
    
    # Mock Prophet since it may not be installed
    import pandas as pd
    from unittest.mock import MagicMock, patch
    
    mock_prophet_instance = MagicMock()
    mock_prophet_instance.fit.return_value = mock_prophet_instance
    
    future_df = pd.DataFrame({
        'ds': pd.date_range(start=datetime.now(), periods=5),
        'yhat': [15.0] * 5,
        'yhat_lower': [12.0] * 5,
        'yhat_upper': [18.0] * 5
    })
    mock_prophet_instance.predict.return_value = future_df
    mock_prophet_instance.make_future_dataframe.return_value = future_df
    
    mock_prophet_class = MagicMock(return_value=mock_prophet_instance)
    
    with patch("app.shared.analysis.forecaster.Prophet", mock_prophet_class, create=True), \
         patch("app.shared.analysis.forecaster.PROPHET_AVAILABLE", True):
        
        result = await SymbolicForecaster.forecast(history, days=5)
        
        assert result["model"] == "Prophet"
        assert len(result["forecast"]) == 5
        assert result["total_forecasted_cost"] > 0

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
