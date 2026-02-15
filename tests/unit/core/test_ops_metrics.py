import pytest
from unittest.mock import patch
from prometheus_client import REGISTRY
from app.shared.core import ops_metrics


def test_zombie_metrics_existence():
    """Verify that the new zombie metrics are defined in ops_metrics."""
    # This will fail until we define them in ops_metrics.py
    assert hasattr(ops_metrics, "ZOMBIES_DETECTED")
    assert hasattr(ops_metrics, "POTENTIAL_SAVINGS")


def test_zombie_metrics_behavior():
    """Verify that we can record values into these metrics."""
    ops_metrics.ZOMBIES_DETECTED.labels(
        provider="aws", account_id="123456789012", resource_type="ebs_volume"
    ).inc()

    val = REGISTRY.get_sample_value(
        "valdrix_ops_zombies_detected_total",
        labels={
            "provider": "aws",
            "account_id": "123456789012",
            "resource_type": "ebs_volume",
        },
    )
    assert val == 1.0

    ops_metrics.POTENTIAL_SAVINGS.labels(provider="aws", account_id="123456789012").set(
        99.99
    )

    savings = REGISTRY.get_sample_value(
        "valdrix_ops_potential_savings_monthly",
        labels={"provider": "aws", "account_id": "123456789012"},
    )
    assert savings == 99.99


def test_existing_metrics_integrity():
    """Ensure we haven't broken existing metrics like API_ERRORS_TOTAL."""
    assert hasattr(ops_metrics, "API_ERRORS_TOTAL")
    # Register a sample so it appears in the registry
    ops_metrics.API_ERRORS_TOTAL.labels(
        path="/test", method="GET", status_code="500"
    ).inc()
    val = REGISTRY.get_sample_value(
        "valdrix_ops_api_errors_total",
        labels={"path": "/test", "method": "GET", "status_code": "500"},
    )
    assert val == 1.0


def test_time_operation_records_db_duration():
    """Decorator should record DB duration for db operations."""
    with patch("app.shared.core.ops_metrics.DB_QUERY_DURATION") as mock_hist:
        decorator = ops_metrics.time_operation("db_query")

        @decorator
        def work():
            return "ok"

        assert work() == "ok"
        mock_hist.labels.assert_called_once_with(operation_type="db_query")
        mock_hist.labels.return_value.observe.assert_called_once()


def test_time_operation_records_db_error_duration():
    """Decorator should record DB error duration on failure."""
    with patch("app.shared.core.ops_metrics.DB_QUERY_DURATION") as mock_hist:
        decorator = ops_metrics.time_operation("db_query")

        @decorator
        def work():
            raise ValueError("boom")

        with pytest.raises(ValueError):
            work()

        mock_hist.labels.assert_called_once_with(operation_type="db_query_error")
        mock_hist.labels.return_value.observe.assert_called_once()


def test_time_operation_skips_api_and_cache_metrics():
    with patch("app.shared.core.ops_metrics.DB_QUERY_DURATION") as mock_hist:
        api_decorator = ops_metrics.time_operation("api_request")
        cache_decorator = ops_metrics.time_operation("cache_get")

        @api_decorator
        def api_work():
            return "ok"

        @cache_decorator
        def cache_work():
            return "ok"

        assert api_work() == "ok"
        assert cache_work() == "ok"
        mock_hist.labels.assert_not_called()


def test_time_operation_error_skips_api_and_cache_metrics():
    with patch("app.shared.core.ops_metrics.DB_QUERY_DURATION") as mock_hist:
        api_decorator = ops_metrics.time_operation("api_request")
        cache_decorator = ops_metrics.time_operation("cache_get")

        @api_decorator
        def api_work():
            raise RuntimeError("api boom")

        @cache_decorator
        def cache_work():
            raise RuntimeError("cache boom")

        with pytest.raises(RuntimeError):
            api_work()
        with pytest.raises(RuntimeError):
            cache_work()

        mock_hist.labels.assert_not_called()


def test_record_circuit_breaker_metrics():
    """Record circuit breaker state + counters."""
    with (
        patch("app.shared.core.ops_metrics.CIRCUIT_BREAKER_STATE") as mock_state,
        patch("app.shared.core.ops_metrics.CIRCUIT_BREAKER_FAILURES") as mock_failures,
        patch(
            "app.shared.core.ops_metrics.CIRCUIT_BREAKER_RECOVERIES"
        ) as mock_recoveries,
    ):
        ops_metrics.record_circuit_breaker_metrics(
            circuit_name="cb",
            state="open",
            failures=2,
            successes=3,
        )

        mock_state.labels.assert_called_once_with(circuit_name="cb")
        mock_state.labels.return_value.set.assert_called_once_with(1)
        mock_failures.labels.assert_called_once_with(circuit_name="cb")
        mock_failures.labels.return_value.inc.assert_called_once_with(2)
        mock_recoveries.labels.assert_called_once_with(circuit_name="cb")
        mock_recoveries.labels.return_value.inc.assert_called_once_with(3)


def test_record_circuit_breaker_metrics_zero_counts():
    with (
        patch("app.shared.core.ops_metrics.CIRCUIT_BREAKER_STATE") as mock_state,
        patch("app.shared.core.ops_metrics.CIRCUIT_BREAKER_FAILURES") as mock_failures,
        patch(
            "app.shared.core.ops_metrics.CIRCUIT_BREAKER_RECOVERIES"
        ) as mock_recoveries,
    ):
        ops_metrics.record_circuit_breaker_metrics(
            circuit_name="cb-zero",
            state="closed",
            failures=0,
            successes=0,
        )

        mock_state.labels.assert_called_once_with(circuit_name="cb-zero")
        mock_state.labels.return_value.set.assert_called_once_with(0)
        mock_failures.labels.assert_not_called()
        mock_recoveries.labels.assert_not_called()


def test_record_circuit_breaker_metrics_unknown_state():
    with (
        patch("app.shared.core.ops_metrics.CIRCUIT_BREAKER_STATE") as mock_state,
        patch("app.shared.core.ops_metrics.CIRCUIT_BREAKER_FAILURES") as mock_failures,
        patch(
            "app.shared.core.ops_metrics.CIRCUIT_BREAKER_RECOVERIES"
        ) as mock_recoveries,
    ):
        ops_metrics.record_circuit_breaker_metrics(
            circuit_name="cb-unknown",
            state="invalid_state",
            failures=1,
            successes=0,
        )

        mock_state.labels.assert_called_once_with(circuit_name="cb-unknown")
        mock_state.labels.return_value.set.assert_called_once_with(0)
        mock_failures.labels.assert_called_once_with(circuit_name="cb-unknown")
        mock_failures.labels.return_value.inc.assert_called_once_with(1)
        mock_recoveries.labels.assert_not_called()


def test_record_retry_and_timeout_metrics():
    with (
        patch("app.shared.core.ops_metrics.OPERATION_RETRIES_TOTAL") as mock_retries,
        patch("app.shared.core.ops_metrics.OPERATION_TIMEOUTS_TOTAL") as mock_timeouts,
    ):
        ops_metrics.record_retry_metrics("op", 2)
        ops_metrics.record_timeout_metrics("op")

        mock_retries.labels.assert_called_once_with(operation_type="op", attempt="2")
        mock_retries.labels.return_value.inc.assert_called_once()
        mock_timeouts.labels.assert_called_once_with(operation_type="op")
        mock_timeouts.labels.return_value.inc.assert_called_once()
