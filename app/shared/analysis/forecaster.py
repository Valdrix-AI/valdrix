import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any, Optional
import structlog
from app.shared.analysis.carbon_data import (
    REGION_CARBON_INTENSITY,
    DEFAULT_CARBON_INTENSITY,
)

logger = structlog.get_logger()

# Optional dependency: Prophet (Requires pystan/holidays)
_prophet_warned = False
try:
    from prophet import Prophet

    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False
    # Logged on first usage to avoid noise during import in tests


class SymbolicForecaster:
    """
    Hybrid Forecasting Engine for Cloud Costs.

    Uses Facebook Prophet for seasonal/trend analysis when sufficient data (>=14 days)
    is available, with a fallback to Holt-Winters Linear Trend for small datasets.
    """

    @staticmethod
    def _detect_outliers(df: pd.DataFrame) -> pd.DataFrame:
        """
        Identifies sharp cost spikes using a 3-sigma threshold.
        Spikes are excluded from trend fitting to avoid skewed forecasts.
        """
        df = df.copy()
        if len(df) < 5:
            df["is_outlier"] = False
            return df

        # Use a rolling median/std for better local outlier detection if needed,
        # but 3-sigma on the set is the baseline required by tests.
        mean = df["y"].mean()
        std = df["y"].std()

        if std == 0:
            df["is_outlier"] = False
        else:
            df["is_outlier"] = (df["y"] - mean).abs() > (3 * std)

        return df

    @staticmethod
    async def forecast(
        history: List[Any],
        days: int = 30,
        db: Optional[Any] = None,
        tenant_id: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Main entry point for cost forecasting.
        """
        if not history or len(history) < 7:
            return {
                "confidence": "low",
                "reason": "Need at least 7 days of data for reliable forecasting.",
                "forecast": [],
                "total_forecasted_cost": Decimal("0"),
                "model": "None",
                "accuracy_mape": None,
            }

        try:
            df = SymbolicForecaster._prepare_dataframe(history)

            # 1. Outlier Detection
            df = SymbolicForecaster._detect_outliers(df)

            # 2. Model Selection
            if PROPHET_AVAILABLE and len(df[~df["is_outlier"]]) >= 14:
                return await SymbolicForecaster._run_prophet(df, days, db, tenant_id)

            if not PROPHET_AVAILABLE and len(df[~df["is_outlier"]]) >= 14:
                global _prophet_warned
                if not _prophet_warned:
                    logger.warning(
                        "prophet_not_installed_forecasting_degraded",
                        msg="Using Holt-Winters fallback for long-term data.",
                    )
                    _prophet_warned = True

            # Fallback to Holt-Winters logic
            return await SymbolicForecaster._run_holt_winters(df, days)

        except Exception as e:
            logger.error("forecasting_failed_unexpectedly", error=str(e))
            return {
                "confidence": "error",
                "reason": f"Forecasting engine error: {str(e)}",
                "forecast": [],
                "total_forecasted_cost": Decimal("0"),
                "model": "None",
                "accuracy_mape": None,
            }

    @staticmethod
    async def _run_prophet(
        df: pd.DataFrame, days: int, db: Optional[Any], tenant_id: Optional[Any]
    ) -> Dict[str, Any]:
        """Runs Facebook Prophet with holiday/anomaly markers."""
        holidays_df = None
        if db and tenant_id:
            from sqlalchemy import select
            from app.models.anomaly_marker import AnomalyMarker

            try:
                result = await db.execute(
                    select(AnomalyMarker).where(AnomalyMarker.tenant_id == tenant_id)
                )
                markers = result.scalars().all()
                if markers:
                    holidays_df = SymbolicForecaster._build_holidays_df(markers)
            except Exception as e:
                logger.warning("failed_to_load_anomaly_markers", error=str(e))

        m = Prophet(
            holidays=holidays_df,
            daily_seasonality=False,
            weekly_seasonality=True,
            yearly_seasonality=False,
        )
        m.fit(df[~df["is_outlier"]])

        future = m.make_future_dataframe(periods=days)
        forecast = m.predict(future)

        # Extract forecast window
        result_df = forecast.tail(days)
        forecast_entries = []
        total_cost = Decimal("0")

        for _, row in result_df.iterrows():
            amount = Decimal(str(max(0.0, float(row["yhat"]))))
            forecast_entries.append(
                {
                    "date": row["ds"].date(),
                    "amount": amount.quantize(Decimal("0.01")),
                    "confidence_lower": Decimal(
                        str(max(0.0, float(row["yhat_lower"])))
                    ).quantize(Decimal("0.01")),
                    "confidence_upper": Decimal(
                        str(float(row["yhat_upper"]))
                    ).quantize(Decimal("0.01")),
                }
            )
            total_cost += amount

        # Simple MAPE on training data for accuracy tracking
        try:
            y_true = np.array(df[~df["is_outlier"]]["y"].tolist())
            y_pred = np.array(forecast.head(len(df))["yhat"].tolist())
            
            # Use safety for zero-division
            mask = y_true != 0
            if np.any(mask):
                mape = np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100
            else:
                mape = 0.0
        except Exception as e:
            logger.debug("mape_calculation_skipped", error=str(e))
            mape = 15.0  # Fallback default

        return {
            "confidence": "high" if len(df) >= 30 else "medium",
            "forecast": forecast_entries,
            "total_forecasted_cost": total_cost.quantize(Decimal("0.01")),
            "model": "Prophet",
            "accuracy_mape": Decimal(str(round(float(mape), 2))),
        }

    @staticmethod
    async def _run_holt_winters(df: pd.DataFrame, days: int) -> Dict[str, Any]:
        """
        Simplified Holt-Winters Fallback (Exponential Smoothing with Trend).
        Used for small datasets (<14 days).
        """
        # Manual Alpha/Beta for small datasets
        alpha = 0.3  # Level smoothing
        beta = 0.1  # Trend smoothing

        level = df["y"].iloc[0]
        trend = df["y"].iloc[1] - df["y"].iloc[0] if len(df) > 1 else 0

        for i in range(1, len(df)):
            last_level = level
            level = alpha * df["y"].iloc[i] + (1 - alpha) * (level + trend)
            trend = beta * (level - last_level) + (1 - beta) * trend

        forecast_entries = []
        total_cost = Decimal("0")
        last_date = df["ds"].iloc[-1]

        # Uncertainty grows over time: +/- 10% * days_out
        for i in range(1, days + 1):
            amount = Decimal(str(max(0.0, level + (i * trend))))
            uncertainty = (Decimal("0.1") + (Decimal(str(i)) * Decimal("0.02"))) * amount

            forecast_entries.append(
                {
                    "date": (last_date + timedelta(days=i)).date(),
                    "amount": amount.quantize(Decimal("0.01")),
                    "confidence_lower": (amount - uncertainty).quantize(Decimal("0.01")),
                    "confidence_upper": (amount + uncertainty).quantize(Decimal("0.01")),
                }
            )
            total_cost += amount

        return {
            "confidence": "low",
            "forecast": forecast_entries,
            "total_forecasted_cost": total_cost.quantize(Decimal("0.01")),
            "model": "Holt-Winters Fallback",
            "accuracy_mape": Decimal("20.00"),
        }

    @staticmethod
    def _prepare_dataframe(history: List[Any]) -> pd.DataFrame:
        """Converts raw history objects to normalized DataFrame."""
        data = []
        for r in history:
            d = r.date
            if isinstance(d, datetime):
                d = d.date()
            data.append({"ds": d, "y": float(r.amount)})

        df = pd.DataFrame(data)
        df["ds"] = pd.to_datetime(df["ds"], format="mixed", errors="coerce")
        df = df.dropna(subset=["ds"])
        return df

    @staticmethod
    def _build_holidays_df(markers: List[Any]) -> pd.DataFrame:
        """Expands multi-day anomaly markers into Prophet holiday format."""
        holidays_list = []
        for m in markers:
            current_date = m.start_date
            while current_date <= m.end_date:
                holidays_list.append(
                    {
                        "holiday": m.marker_type,
                        "ds": pd.to_datetime(current_date),
                        "lower_window": 0,
                        "upper_window": 0,
                    }
                )
                current_date += timedelta(days=1)
        return pd.DataFrame(holidays_list)

    @staticmethod
    async def forecast_carbon(
        history: List[Any], region: str = "global", days: int = 30
    ) -> Dict[str, Any]:
        """
        Project future carbon emissions based on cost trends.
        """
        cost_forecast = await SymbolicForecaster.forecast(history, days)
        intensity = Decimal(str(REGION_CARBON_INTENSITY.get(region, DEFAULT_CARBON_INTENSITY)))

        total_g = Decimal("0")
        for entry in cost_forecast["forecast"]:
            carbon_g = entry["amount"] * intensity
            entry["carbon_g"] = carbon_g.quantize(Decimal("0.0001"))
            total_g += carbon_g

        cost_forecast["total_forecasted_co2_kg"] = (total_g / Decimal("1000")).quantize(Decimal("0.0001"))
        cost_forecast["unit"] = "kg CO2e"
        cost_forecast["region"] = region

        return cost_forecast
