import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List
from app.schemas.costs import CostRecord
from app.shared.analysis.forecaster import SymbolicForecaster

def generate_mock_history(days: int, start_val: float = 100.0, trend: float = 1.0, spiky: bool = False, noise: bool = True) -> List[CostRecord]:
    history = []
    base_date = datetime.now() - timedelta(days=days)
    rng = np.random.default_rng(42) # Seeded for reproducibility
    for i in range(days):
        amount = start_val + (i * trend)
        if spiky and i == days // 2:
            amount *= 5  # Sharp spike in the middle
        if noise:
            amount += rng.standard_normal() * 2.0 # Add some noise
        history.append(CostRecord(
            date=base_date + timedelta(days=i),
            amount=Decimal(str(max(0, round(amount, 2)))),
            service="ec2"
        ))
    return history

@pytest.mark.asyncio
async def test_outlier_detection_logic():
    """
    Test that the outlier detection correctly identifies a sharp cost spike.
    """
    history = generate_mock_history(30, spiky=True)
    df = pd.DataFrame([{"ds": r.date, "y": float(r.amount)} for r in history])
    
    # Access private method for testing logic
    detected_df = SymbolicForecaster._detect_outliers(df)
    
    anomalies = detected_df[detected_df['is_outlier']]
    assert len(anomalies) >= 1
    # The spike was at index 15 (30 // 2)
    assert 15 in anomalies.index

@pytest.mark.asyncio
async def test_confidence_intervals_present():
    """
    Test that the forecast result includes confidence intervals.
    """
    history = generate_mock_history(30)
    # We'll use a longer history to trigger Prophet if available, 
    # but the test should pass even with Holt-Winters fallback.
    result = await SymbolicForecaster.forecast(history, days=7)
    
    assert "forecast" in result
    for entry in result["forecast"]:
        assert "confidence_lower" in entry
        assert "confidence_upper" in entry
        assert entry["confidence_lower"] <= entry["amount"] <= entry["confidence_upper"]

@pytest.mark.asyncio
async def test_interval_growth_over_time():
    """
    Statistical forecasts should generally become less certain (wider intervals) over time.
    """
    history = generate_mock_history(30, trend=5.0) # Add some volatility/trend
    result = await SymbolicForecaster.forecast(history, days=14)
    
    intervals = []
    for entry in result["forecast"]:
        intervals.append(float(entry["confidence_upper"] - entry["confidence_lower"]))
    
    # The last interval should be wider than the first (simplified check)
    assert intervals[-1] > intervals[0]

@pytest.mark.asyncio
async def test_mape_accuracy_tracking():
    """
    Verify that MAPE is calculated during backtesting for sufficient data.
    """
    history = generate_mock_history(40) # Plenty of data for backtesting
    result = await SymbolicForecaster.forecast(history)
    
    # If the model is Prophet or HW, accuracy_mape should ideally be present
    # unless it failed specifically.
    assert "accuracy_mape" in result
    if result["accuracy_mape"] is not None:
        assert 0 <= result["accuracy_mape"] <= 100

@pytest.mark.asyncio
async def test_forecast_edge_cases_zero_cost():
    """
    Test resilience to zero cost data.
    """
    history = [
        CostRecord(date=datetime.now() - timedelta(days=i), amount=Decimal("0.0"), service="ec2")
        for i in range(20)
    ]
    result = await SymbolicForecaster.forecast(history)
    
    assert result["confidence"] != "error"
    assert result["total_forecasted_cost"] == Decimal("0")

@pytest.mark.asyncio
async def test_forecast_insufficient_data_protection():
    """
    Test that very small datasets don't crash the system.
    """
    history = generate_mock_history(3)
    result = await SymbolicForecaster.forecast(history)
    
    assert result["confidence"] == "low"
    assert len(result["forecast"]) == 0
