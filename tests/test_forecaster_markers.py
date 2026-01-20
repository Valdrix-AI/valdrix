
import pytest
from uuid import uuid4
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock
from app.services.analysis.forecaster import SymbolicForecaster
from app.models.anomaly_marker import AnomalyMarker

@pytest.mark.asyncio
async def test_forecast_with_anomaly_markers():
    """Test that anomaly markers are correctly fetched and passed to Prophet."""
    tenant_id = uuid4()
    db = AsyncMock()
    
    # 1. Mock anomaly markers in DB
    marker = AnomalyMarker(
        tenant_id=tenant_id,
        start_date=date(2025, 1, 15),
        end_date=date(2025, 1, 16),
        marker_type="PROMOTION_SPIKE",
        label="New Year Promo"
    )
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [marker]
    db.execute.return_value = mock_result
    
    # 2. Mock history (30 days)
    history = []
    for i in range(30):
        record = MagicMock()
        record.date = date(2025, 1, 1) + timedelta(days=i)
        record.amount = Decimal("100.0")
        record.service = "AmazonEC2"
        history.append(record)
        
    # We only want to verify the logic reaches Prophet with the right holidays
    # So we patch Prophet constructor
    with MagicMock() as mock_prophet_class:
        with MagicMock() as mock_prophet_instance:
            mock_prophet_class.return_value = mock_prophet_instance
            mock_prophet_instance.fit.return_value = mock_prophet_instance
            
            # Mock predict output to avoid full run
            import pandas as pd
            future_df = pd.DataFrame({
                'ds': pd.date_range(start='2025-01-31', periods=7),
                'yhat': [100.0] * 7,
                'yhat_lower': [90.0] * 7,
                'yhat_upper': [110.0] * 7
            })
            mock_prophet_instance.predict.return_value = future_df
            mock_prophet_instance.make_future_dataframe.return_value = future_df
            
            with pytest.MonkeyPatch().context() as mp:
                import app.services.analysis.forecaster
                mp.setattr(app.services.analysis.forecaster, "Prophet", mock_prophet_class)
                mp.setattr(app.services.analysis.forecaster, "PROPHET_AVAILABLE", True)
                
                results = await SymbolicForecaster.forecast(
                    history, 
                    days=7, 
                    db=db, 
                    tenant_id=tenant_id
                )
                
                # Verify Anomaly Marker query was called
                db.execute.assert_called()
                
                # Verify Prophet was initialized with holidays
                args, kwargs = mock_prophet_class.call_args
                assert "holidays" in kwargs
                assert kwargs["holidays"] is not None
                assert len(kwargs["holidays"]) == 2 # 15th and 16th
                assert kwargs["holidays"].iloc[0]['holiday'] == "PROMOTION_SPIKE"

@pytest.mark.asyncio
async def test_holt_winters_confidence_bands():
    """Test that Holt-Winters fallback provides confidence bands."""
    # 1. Mock history (enough for HW but less than 14 for Prophet fallback)
    history = []
    for i in range(10):
        record = MagicMock()
        record.date = date(2025, 1, 1) + timedelta(days=i)
        record.amount = Decimal("100.0") + Decimal(str(i % 2))
        record.service = "AmazonEC2"
        history.append(record)
        
    # force PROPHET_AVAILABLE = False to trigger HW
    with pytest.MonkeyPatch().context() as mp:
        import app.services.analysis.forecaster
        mp.setattr(app.services.analysis.forecaster, "PROPHET_AVAILABLE", False)
        
        results = await SymbolicForecaster.forecast(history, days=7)
        
        assert "Holt-Winters" in results["model"]
        assert len(results["forecast"]) == 7
        for item in results["forecast"]:
            assert item["confidence_lower"] is not None
            assert item["confidence_upper"] is not None
            assert item["confidence_upper"] > item["confidence_lower"]
