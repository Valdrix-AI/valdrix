import pandas as pd
from decimal import Decimal
from unittest.mock import MagicMock, patch
from app.shared.analysis.forecaster import SymbolicForecaster


def test_forecaster_fallback_logic():
    """Verify that Small data (<14 days) triggers Holt-Winters fallback."""
    # 10 days of data
    history = [MagicMock(date=f"2026-01-{i:02d}", amount=10.0) for i in range(1, 11)]

    with patch("app.shared.analysis.forecaster.PROPHET_AVAILABLE", True):
        # Even if prophet is available, <14 days should use Holt-Winters
        MagicMock()
        with patch.object(
            SymbolicForecaster,
            "_run_holt_winters",
            return_value={"model": "Holt-Winters"},
        ) as mock_hw:
            # We need to run it through the main entry point
            import asyncio

            asyncio.run(SymbolicForecaster.forecast(history))
            mock_hw.assert_called()


def test_forecaster_prophet_trigger():
    """Verify that Sufficient data (>=14 days) triggers Prophet."""
    # 20 days of data
    history = [MagicMock(date=f"2026-01-{i:02d}", amount=10.0) for i in range(1, 21)]

    with patch("app.shared.analysis.forecaster.PROPHET_AVAILABLE", True):
        with patch.object(
            SymbolicForecaster, "_run_prophet", return_value={"model": "Prophet"}
        ) as mock_prophet:
            import asyncio

            asyncio.run(SymbolicForecaster.forecast(history))
            mock_prophet.assert_called()


def test_outlier_detection_3sigma():
    """Verify that sharp cost spikes are identified as outliers."""
    # Increase sample size to make 3-sigma detection more reliable
    data = {
        "ds": pd.date_range(start="2026-01-01", periods=20),
        "y": [100] * 19 + [100000],
    }
    df = pd.DataFrame(data)

    result_df = SymbolicForecaster._detect_outliers(df)
    # Check the last element (index 19), which is the spike
    assert bool(result_df.iloc[19]["is_outlier"]) is True
    assert bool(result_df.iloc[0]["is_outlier"]) is False


def test_carbon_math_accuracy():
    """Verify carbon intensity projections per region."""
    history = [MagicMock(date=f"2026-01-{i:02d}", amount=1.0) for i in range(1, 8)]

    # Mock cost forecast to return $10 total over 30 days
    mock_cost = {
        "forecast": [{"amount": Decimal("1.0")}] * 10,
        "total_forecasted_cost": Decimal("10.0"),
    }

    with patch.object(SymbolicForecaster, "forecast", return_value=mock_cost):
        import asyncio

        # us-east-1 intensity is 412.0 gCO2e/USD
        result = asyncio.run(
            SymbolicForecaster.forecast_carbon(history, region="us-east-1", days=10)
        )

        # 10 USD * 412.0 = 4120.0 grams = 4.12 kg
        assert result["total_forecasted_co2_kg"] == Decimal("4.1200")
        assert result["region"] == "us-east-1"
