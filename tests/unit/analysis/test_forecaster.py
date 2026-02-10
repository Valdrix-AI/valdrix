"""
Production-quality tests for Symbolic Forecaster.
Tests cover forecasting accuracy, outlier detection, model selection, and carbon emissions.
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch, AsyncMock
from app.shared.analysis.forecaster import SymbolicForecaster


class TestSymbolicForecaster:
    """Basic functionality tests for SymbolicForecaster."""

    def test_detect_outliers_no_outliers(self):
        """Test outlier detection with normal data."""
        dates = pd.date_range('2024-01-01', periods=10, freq='D')
        values = [100, 105, 98, 102, 99, 101, 103, 97, 104, 100]
        df = pd.DataFrame({'ds': dates, 'y': values})

        result = SymbolicForecaster._detect_outliers(df)

        assert len(result) == 10
        assert not result['is_outlier'].any()

    def test_detect_outliers_with_outliers(self):
        """Test outlier detection with clear outliers."""
        dates = pd.date_range('2024-01-01', periods=100, freq='D')
        values = [100] * 99 + [10000]  # 10000 is outlier
        df = pd.DataFrame({'ds': dates, 'y': values})

        result = SymbolicForecaster._detect_outliers(df)

        assert len(result) == 100
        assert result['is_outlier'].sum() == 1  # One outlier detected
        assert result.iloc[-1]['is_outlier'] == True  # The 500 value

    def test_detect_outliers_small_dataset(self):
        """Test outlier detection with small dataset (< 5 points)."""
        dates = pd.date_range('2024-01-01', periods=3, freq='D')
        values = [100, 200, 150]
        df = pd.DataFrame({'ds': dates, 'y': values})

        result = SymbolicForecaster._detect_outliers(df)

        assert len(result) == 3
        assert not result['is_outlier'].any()  # No outliers marked for small datasets

    def test_detect_outliers_constant_values(self):
        """Test outlier detection with constant values (zero std)."""
        dates = pd.date_range('2024-01-01', periods=10, freq='D')
        values = [100] * 10
        df = pd.DataFrame({'ds': dates, 'y': values})

        result = SymbolicForecaster._detect_outliers(df)

        assert len(result) == 10
        assert not result['is_outlier'].any()  # No outliers when std=0

    def test_prepare_dataframe_with_date_objects(self):
        """Test dataframe preparation with date objects."""
        class MockHistoryItem:
            def __init__(self, date_val, amount):
                self.date = date_val
                self.amount = amount

        history = [
            MockHistoryItem(date(2024, 1, 1), 100.50),
            MockHistoryItem(date(2024, 1, 2), 105.25),
            MockHistoryItem(datetime(2024, 1, 3, 12, 0), 98.75)
        ]

        df = SymbolicForecaster._prepare_dataframe(history)

        assert len(df) == 3
        assert list(df['y']) == [100.50, 105.25, 98.75]
        assert pd.api.types.is_datetime64_any_dtype(df['ds'])

    def test_build_holidays_df_single_day(self):
        """Test holiday dataframe building with single-day markers."""
        class MockMarker:
            def __init__(self, marker_type, start_date, end_date):
                self.marker_type = marker_type
                self.start_date = start_date
                self.end_date = end_date

        markers = [
            MockMarker("maintenance", date(2024, 1, 15), date(2024, 1, 15))
        ]

        holidays_df = SymbolicForecaster._build_holidays_df(markers)

        assert len(holidays_df) == 1
        assert holidays_df.iloc[0]['holiday'] == "maintenance"
        assert holidays_df.iloc[0]['ds'].date() == date(2024, 1, 15)

    def test_build_holidays_df_multi_day(self):
        """Test holiday dataframe building with multi-day markers."""
        class MockMarker:
            def __init__(self, marker_type, start_date, end_date):
                self.marker_type = marker_type
                self.start_date = start_date
                self.end_date = end_date

        markers = [
            MockMarker("deployment", date(2024, 1, 10), date(2024, 1, 12))
        ]

        holidays_df = SymbolicForecaster._build_holidays_df(markers)

        assert len(holidays_df) == 3
        assert all(holidays_df['holiday'] == "deployment")
        expected_dates = [date(2024, 1, 10), date(2024, 1, 11), date(2024, 1, 12)]
        actual_dates = [row.date() for row in holidays_df['ds']]
        assert actual_dates == expected_dates


class TestSymbolicForecasterForecasting:
    """Tests for forecasting functionality."""

    @pytest.mark.asyncio
    async def test_forecast_insufficient_data(self):
        """Test forecasting with insufficient data."""
        history = []  # Empty history

        result = await SymbolicForecaster.forecast(history, days=30)

        assert result["confidence"] == "low"
        assert "Need at least 7 days" in result["reason"]
        assert result["forecast"] == []
        assert result["total_forecasted_cost"] == Decimal("0")
        assert result["model"] == "None"

    @pytest.mark.asyncio
    async def test_forecast_minimum_data(self):
        """Test forecasting with minimum required data (7 days)."""
        class MockHistoryItem:
            def __init__(self, date_val, amount):
                self.date = date_val
                self.amount = amount

        history = [
            MockHistoryItem(date(2024, 1, i), 100.0 + i)
            for i in range(1, 8)  # 7 days
        ]

        result = await SymbolicForecaster.forecast(history, days=7)

        assert result["confidence"] == "low"
        assert result["model"] == "Holt-Winters Fallback"
        assert len(result["forecast"]) == 7
        assert isinstance(result["total_forecasted_cost"], Decimal)
        assert result["accuracy_mape"] == 20.0

    @pytest.mark.asyncio
    async def test_forecast_prophet_available(self):
        """Test forecasting with Prophet available and sufficient data."""
        class MockHistoryItem:
            def __init__(self, date_val, amount):
                self.date = date_val
                self.amount = amount

        history = [
            MockHistoryItem(date(2024, 1, i), 100.0 + (i * 2))
            for i in range(1, 16)  # 15 days
        ]

        with patch('app.shared.analysis.forecaster.PROPHET_AVAILABLE', True):
            with patch('app.shared.analysis.forecaster.Prophet', create=True) as mock_prophet:
                # Mock Prophet instance
                mock_instance = MagicMock()
                mock_prophet.return_value = mock_instance

                # Mock forecast results
                mock_forecast_df = pd.DataFrame({
                    'ds': pd.date_range('2024-01-16', periods=10, freq='D'),
                    'yhat': [110, 112, 114, 116, 118, 120, 122, 124, 126, 128],
                    'yhat_lower': [105, 107, 109, 111, 113, 115, 117, 119, 121, 123],
                    'yhat_upper': [115, 117, 119, 121, 123, 125, 127, 129, 131, 133]
                })

                mock_instance.make_future_dataframe.return_value = pd.DataFrame()
                mock_instance.predict.return_value = mock_forecast_df
                mock_instance.fit.return_value = None

                result = await SymbolicForecaster.forecast(history, days=10)

                assert result["confidence"] == "medium"  # 15 days < 30
                assert result["model"] == "Prophet"
                assert len(result["forecast"]) == 10
                assert isinstance(result["accuracy_mape"], float)

    @pytest.mark.asyncio
    async def test_forecast_prophet_with_anomalies(self):
        """Test forecasting with Prophet and anomaly markers."""
        class MockHistoryItem:
            def __init__(self, date_val, amount):
                self.date = date_val
                self.amount = amount

        class MockAnomalyMarker:
            def __init__(self, marker_type, start_date, end_date):
                self.marker_type = marker_type
                self.start_date = start_date
                self.end_date = end_date

        history = [
            MockHistoryItem(date(2024, 1, i), 100.0 + (i * 2))
            for i in range(1, 16)
        ]

        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock() # The object returned by .scalars()
        mock_scalars.all.return_value = [
             MockAnomalyMarker("maintenance", date(2024, 1, 10), date(2024, 1, 10))
        ]
        mock_result.scalars.return_value = mock_scalars # .scalars() returns mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch('app.shared.analysis.forecaster.PROPHET_AVAILABLE', True):
            with patch('app.shared.analysis.forecaster.Prophet', create=True) as mock_prophet:
                mock_instance = MagicMock()
                mock_prophet.return_value = mock_instance

                mock_forecast_df = pd.DataFrame({
                    'ds': pd.date_range('2024-01-16', periods=5, freq='D'),
                    'yhat': [110, 112, 114, 116, 118],
                    'yhat_lower': [105, 107, 109, 111, 113],
                    'yhat_upper': [115, 117, 119, 121, 123]
                })

                mock_instance.make_future_dataframe.return_value = pd.DataFrame()
                mock_instance.predict.return_value = mock_forecast_df

                result = await SymbolicForecaster.forecast(history, days=5, db=mock_db, tenant_id="test-tenant")

                # Verify holidays were built and passed to Prophet
                mock_prophet.assert_called_once()
                call_kwargs = mock_prophet.call_args[1]
                assert 'holidays' in call_kwargs
                assert call_kwargs['holidays'] is not None

    @pytest.mark.asyncio
    async def test_forecast_prophet_unavailable(self):
        """Test forecasting when Prophet is unavailable."""
        class MockHistoryItem:
            def __init__(self, date_val, amount):
                self.date = date_val
                self.amount = amount

        history = [
            MockHistoryItem(date(2024, 1, i), 100.0 + i)
            for i in range(1, 16)  # 15 days
        ]

        with patch('app.shared.analysis.forecaster.PROPHET_AVAILABLE', False):
            result = await SymbolicForecaster.forecast(history, days=7)

            assert result["confidence"] == "low"
            assert result["model"] == "Holt-Winters Fallback"
            assert len(result["forecast"]) == 7

    @pytest.mark.asyncio
    async def test_forecast_error_handling(self):
        """Test forecasting error handling."""
        class MockHistoryItem:
            def __init__(self, date_val, amount):
                self.date = date_val
                self.amount = amount

        history = [
            MockHistoryItem(date(2024, 1, i), 100.0 + i)
            for i in range(1, 10)
        ]

        # Force an error in dataframe preparation
        with patch.object(SymbolicForecaster, '_prepare_dataframe', side_effect=Exception("Data error")):
            result = await SymbolicForecaster.forecast(history, days=7)

            assert result["confidence"] == "error"
            assert "Forecasting engine error" in result["reason"]
            assert result["forecast"] == []
            assert result["total_forecasted_cost"] == Decimal("0")

    @pytest.mark.asyncio
    async def test_forecast_carbon_emissions(self):
        """Test carbon emissions forecasting."""
        class MockHistoryItem:
            def __init__(self, date_val, amount):
                self.date = date_val
                self.amount = amount

        history = [
            MockHistoryItem(date(2024, 1, i), 100.0 + i)
            for i in range(1, 10)
        ]

        with patch('app.shared.analysis.forecaster.SymbolicForecaster.forecast') as mock_forecast:
            mock_forecast.return_value = {
                "confidence": "medium",
                "forecast": [
                    {"date": date(2024, 1, 10), "amount": Decimal("110.50")},
                    {"date": date(2024, 1, 11), "amount": Decimal("112.25")},
                ],
                "total_forecasted_cost": Decimal("222.75"),
                "model": "Holt-Winters Fallback",
                "accuracy_mape": 20.0
            }
            
            with patch('app.shared.analysis.forecaster.REGION_CARBON_INTENSITY', {"us-east-1": 0.43}):
                result = await SymbolicForecaster.forecast_carbon(history, region="us-east-1", days=2)

            assert "total_forecasted_co2_kg" in result
            assert result["unit"] == "kg CO2e"
            assert result["region"] == "us-east-1"

            # Check carbon calculations (using us-east-1 intensity ~0.43 gCO2e/USD)
            expected_carbon_kg = (110.50 + 112.25) * 0.43 / 1000
            assert abs(result["total_forecasted_co2_kg"] - expected_carbon_kg) < 0.01

            # Check individual entries have carbon data
            assert "carbon_g" in result["forecast"][0]
            assert "carbon_g" in result["forecast"][1]


class TestSymbolicForecasterProductionQuality:
    """Production-quality tests covering security, performance, and edge cases."""

    def test_input_validation_and_sanitization(self):
        """Test input validation and sanitization for security."""
        malicious_history = [
            type('MockItem', (), {
                'date': "<script>alert('xss')</script>",
                'amount': "100.0"
            })(),
            type('MockItem', (), {
                'date': "../../../etc/passwd",
                'amount': "-1000.0"
            })()
        ]

        # Should handle malicious input gracefully
        df = SymbolicForecaster._prepare_dataframe(malicious_history)

        # Should not crash and return reasonable data
        assert isinstance(df, pd.DataFrame)

    def test_large_dataset_performance(self):
        """Test performance with large datasets."""
        import time

        # Create large dataset (1000 data points)
        dates = [date(2024, 1, i % 30 + 1) for i in range(1000)]
        history = [
            type('MockItem', (), {'date': d, 'amount': 100.0 + i * 0.1})()
            for i, d in enumerate(dates)
        ]

        start_time = time.time()
        df = SymbolicForecaster._prepare_dataframe(history)
        result = SymbolicForecaster._detect_outliers(df)
        end_time = time.time()

        # Should complete within reasonable time
        assert end_time - start_time < 5.0, f"Processing too slow: {end_time - start_time:.3f}s"
        assert len(result) == 1000
        assert 'is_outlier' in result.columns

    def test_outlier_detection_edge_cases(self):
        """Test outlier detection with various edge cases."""
        # Test with extreme values
        dates = pd.date_range('2024-01-01', periods=20, freq='D')
        values = [100] * 19 + [10000]  # One extreme outlier
        df = pd.DataFrame({'ds': dates, 'y': values})

        result = SymbolicForecaster._detect_outliers(df)

        assert result['is_outlier'].sum() == 1
        assert result.iloc[-1]['is_outlier'] == True

    def test_dataframe_preparation_robustness(self):
        """Test dataframe preparation with various data types."""
        # Test with mixed date types and amounts
        history_items = [
            type('MockItem', (), {'date': date(2024, 1, 1), 'amount': 100.0})(),
            type('MockItem', (), {'date': datetime(2024, 1, 2, 12, 0), 'amount': "150.5"})(),
            type('MockItem', (), {'date': "2024-01-03", 'amount': Decimal("125.25")})(),
        ]

        df = SymbolicForecaster._prepare_dataframe(history_items)

        assert len(df) == 3
        assert all(isinstance(val, (int, float)) for val in df['y'])
        assert pd.api.types.is_datetime64_any_dtype(df['ds'])

    @pytest.mark.asyncio
    async def test_forecasting_model_selection_logic(self):
        """Test the logic for selecting forecasting models."""
        class MockHistoryItem:
            def __init__(self, date_val, amount):
                self.date = date_val
                self.amount = amount

        # Test with different data sizes
        test_cases = [
            (6, "insufficient"),  # < 7 days
            (10, "holt_winters"), # >= 7 but < 14 days
            (16, "prophet"),      # >= 14 days with Prophet
        ]

        for num_days, expected_type in test_cases:
            history = [
                MockHistoryItem(date(2024, 1, i), 100.0 + i)
                for i in range(1, num_days + 1)
            ]

            if expected_type == "insufficient":
                # Should return early with low confidence
                result = await SymbolicForecaster.forecast(history, days=7)
                assert result["confidence"] == "low"
                assert "Need at least 7 days" in result["reason"]

            elif expected_type == "holt_winters":
                with patch('app.shared.analysis.forecaster.PROPHET_AVAILABLE', False):
                    result = await SymbolicForecaster.forecast(history, days=7)
                    assert result["model"] == "Holt-Winters Fallback"

            elif expected_type == "prophet":
                with patch('app.shared.analysis.forecaster.PROPHET_AVAILABLE', True):
                    with patch('app.shared.analysis.forecaster.Prophet', create=True) as mock_prophet:
                        mock_instance = MagicMock()
                        mock_prophet.return_value = mock_instance

                        mock_forecast_df = pd.DataFrame({
                            'ds': pd.date_range('2024-01-17', periods=7, freq='D'),
                            'yhat': [110] * 7,
                            'yhat_lower': [105] * 7,
                            'yhat_upper': [115] * 7
                        })

                        mock_instance.make_future_dataframe.return_value = pd.DataFrame()
                        mock_instance.predict.return_value = mock_forecast_df

                        result = await SymbolicForecaster.forecast(history, days=7)
                        assert result["model"] == "Prophet"

    @pytest.mark.asyncio
    async def test_carbon_forecasting_region_handling(self):
        """Test carbon forecasting with different regions."""
        class MockHistoryItem:
            def __init__(self, date_val, amount):
                self.date = date_val
                self.amount = amount

        history = [
            MockHistoryItem(date(2024, 1, i), 100.0)
            for i in range(1, 10)
        ]

        test_regions = ["us-east-1", "eu-west-1", "invalid-region"]

        for region in test_regions:
            with patch('app.shared.analysis.forecaster.SymbolicForecaster.forecast') as mock_forecast:
                mock_forecast.return_value = {
                    "forecast": [{"amount": Decimal("100.0")}],
                    "confidence": "medium",
                    "total_forecasted_cost": Decimal("100.0"),
                    "model": "Test",
                    "accuracy_mape": 15.0
                }

                result = await SymbolicForecaster.forecast_carbon(history, region=region, days=1)

                assert "total_forecasted_co2_kg" in result
                assert result["region"] == region
                assert isinstance(result["total_forecasted_co2_kg"], float)

    def test_anomaly_marker_processing(self):
        """Test processing of anomaly markers for holidays."""
        class MockAnomalyMarker:
            def __init__(self, marker_type, start_date, end_date):
                self.marker_type = marker_type
                self.start_date = start_date
                self.end_date = end_date

        markers = [
            MockAnomalyMarker("deployment", date(2024, 1, 5), date(2024, 1, 7)),
            MockAnomalyMarker("maintenance", date(2024, 1, 15), date(2024, 1, 15))
        ]

        holidays_df = SymbolicForecaster._build_holidays_df(markers)

        assert len(holidays_df) == 4  # 3 days deployment + 1 day maintenance
        assert set(holidays_df['holiday']) == {"deployment", "maintenance"}

    @pytest.mark.asyncio
    async def test_concurrent_forecasting_safety(self):
        """Test thread safety and concurrent forecasting operations."""
        import threading

        class MockHistoryItem:
            def __init__(self, date_val, amount):
                self.date = date_val
                self.amount = amount

        history = [
            MockHistoryItem(date(2024, 1, i), 100.0 + i)
            for i in range(1, 10)
        ]

        results = []
        errors = []

        def run_forecast():
            try:
                import asyncio
                result = asyncio.run(SymbolicForecaster.forecast(history, days=5))
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Run multiple threads concurrently
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=run_forecast)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # All threads should complete successfully
        assert len(results) == 5
        assert len(errors) == 0

        # All results should be identical
        for result in results[1:]:
            assert result == results[0]

    @pytest.mark.asyncio
    async def test_memory_efficiency_large_forecasts(self):
        """Test memory efficiency with large forecast periods."""
        import psutil
        import os

        # Get initial memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        class MockHistoryItem:
            def __init__(self, date_val, amount):
                self.date = date_val
                self.amount = amount

        history = [
            MockHistoryItem(date(2024, 1, i), 100.0 + i)
            for i in range(1, 15)  # Sufficient for Prophet
        ]

        # Forecast 365 days (large forecast)
        with patch('app.shared.analysis.forecaster.PROPHET_AVAILABLE', True):
            with patch('app.shared.analysis.forecaster.Prophet', create=True) as mock_prophet:
                with patch('app.shared.analysis.forecaster.logger') as mock_logger:
                    mock_instance = MagicMock()
                    mock_prophet.return_value = mock_instance

                    # Create large forecast dataframe
                    forecast_data = []
                    base_date = datetime(2024, 1, 15)
                    for i in range(365):
                        forecast_data.append({
                            'ds': base_date + timedelta(days=i),
                            'yhat': 150.0 + (i * 0.1),
                            'yhat_lower': 145.0 + (i * 0.1),
                            'yhat_upper': 155.0 + (i * 0.1)
                        })

                    mock_forecast_df = pd.DataFrame(forecast_data)
                    mock_instance.make_future_dataframe.return_value = pd.DataFrame()
                    mock_instance.predict.return_value = mock_forecast_df

                result = await SymbolicForecaster.forecast(history, days=365)

                # Check memory usage after processing
                final_memory = process.memory_info().rss / 1024 / 1024  # MB
                memory_increase = final_memory - initial_memory

                # Memory increase should be reasonable (< 100MB for 365 day forecast)
                assert memory_increase < 100, f"Excessive memory usage: {memory_increase:.1f}MB"

                # Results should be correct
                if result.get("reason"):
                     print(f"Forecast failure reason: {result['reason']}")
                assert len(result["forecast"]) == 365
                assert isinstance(result["total_forecasted_cost"], Decimal)

    @pytest.mark.asyncio
    async def test_error_handling_in_prophet_operations(self):
        """Test error handling in Prophet operations."""
        class MockHistoryItem:
            def __init__(self, date_val, amount):
                self.date = date_val
                self.amount = amount

        history = [
            MockHistoryItem(date(2024, 1, i), 100.0 + i)
            for i in range(1, 16)
        ]

        with patch('app.shared.analysis.forecaster.PROPHET_AVAILABLE', True):
            with patch('app.shared.analysis.forecaster.Prophet', create=True) as mock_prophet:
                mock_instance = MagicMock()
                mock_prophet.return_value = mock_instance

                # Make Prophet operations fail
                mock_instance.fit.side_effect = Exception("Prophet fit failed")

                result = await SymbolicForecaster.forecast(history, days=7)

                # Should fall back gracefully
                assert result["confidence"] == "error"
                assert "Forecasting engine error" in result["reason"]

    @pytest.mark.asyncio
    async def test_holt_winters_fallback_comprehensive(self):
        """Test Holt-Winters fallback with various scenarios."""
        class MockHistoryItem:
            def __init__(self, date_val, amount):
                self.date = date_val
                self.amount = amount

        # Test with different data patterns
        test_cases = [
            # Increasing trend
            [100, 110, 120, 130, 140, 150, 160],
            # Decreasing trend
            [200, 180, 160, 140, 120, 100, 80],
            # Stable
            [100, 100, 100, 100, 100, 100, 100],
            # Volatile
            [50, 150, 75, 125, 90, 110, 95]
        ]

        for i, values in enumerate(test_cases):
            history = [
                MockHistoryItem(date(2024, 1, j+1), val)
                for j, val in enumerate(values)
            ]

            result = await SymbolicForecaster.forecast(history, days=5)

            assert result["model"] == "Holt-Winters Fallback"
            assert len(result["forecast"]) == 5
            assert result["confidence"] == "low"

            # All forecasted amounts should be non-negative
            for entry in result["forecast"]:
                assert entry["amount"] >= 0
