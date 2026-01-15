"""
Symbolic Forecasting Engine

Provides deterministic, mathematical cost forecasts using statistical models (statsmodels)
to provide a reliable baseline for the AI interpretation layer.
"""

from decimal import Decimal
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from app.schemas.costs import CostRecord
import structlog

logger = structlog.get_logger()

class SymbolicForecaster:
    """
    Deterministic forecasting engine for cloud costs.
    """

    @staticmethod
    def forecast(history: List[CostRecord], days: int = 30) -> Dict[str, Any]:
        """
        Generates a 30-day forecast based on historical cost records.
        Uses Holt-Winters Triple Exponential Smoothing for seasonality.
        """
        if len(history) < 7:
            logger.warning("insufficient_data_for_symbolic_forecast", count=len(history))
            return {"forecast": [], "confidence": "low", "reason": "Need at least 7 days of data"}

        try:
            # 1. Prepare Data
            df = pd.DataFrame([
                {"date": r.date, "amount": float(r.amount)} 
                for r in history
            ])
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date').sort_index()

            # 2. Resample to daily (handle missing days)
            df = df.resample('D').mean().fillna(method='ffill')

            # 3. Fit Model (Holt-Winters)
            # We use 'add' for trend and seasonality (assuming additive)
            model = ExponentialSmoothing(
                df['amount'], 
                seasonal_periods=7, 
                trend='add', 
                seasonal='add'
            ).fit()

            # 4. Predict
            forecast_values = model.forecast(days)
            
            # 5. Format results
            forecast_results = [
                {
                    "date": (df.index[-1] + pd.Timedelta(days=i+1)).date().isoformat(),
                    "amount": Decimal(str(round(val, 4)))
                }
                for i, val in enumerate(forecast_values)
            ]

            return {
                "forecast": forecast_results,
                "total_forecasted_cost": Decimal(str(round(sum(forecast_values), 2))),
                "confidence": "medium" if len(history) < 30 else "high",
                "model": "Holt-Winters (Triple Exponential Smoothing)"
            }

        except Exception as e:
            logger.error("symbolic_forecast_failed", error=str(e))
            return {"forecast": [], "confidence": "error", "error": str(e)}
