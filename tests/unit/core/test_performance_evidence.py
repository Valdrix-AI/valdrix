from app.shared.core.performance_evidence import (
    LoadTestThresholds,
    evaluate_load_test_result,
)
from app.shared.core.performance_testing import LoadTestResult


def test_evaluate_load_test_result_fails_on_zero_requests() -> None:
    result = LoadTestResult(total_requests=0, successful_requests=0, failed_requests=0)
    thresholds = LoadTestThresholds(max_p95_seconds=1.0, max_error_rate_percent=0.0)

    evidence = evaluate_load_test_result(result, thresholds)

    assert evidence.meets_targets is False
    assert evidence.total_requests == 0


def test_evaluate_load_test_result_passes_when_targets_met() -> None:
    result = LoadTestResult(
        total_requests=100,
        successful_requests=100,
        failed_requests=0,
        throughput_rps=50.0,
        p95_response_time=0.8,
    )
    thresholds = LoadTestThresholds(
        max_p95_seconds=1.0, max_error_rate_percent=1.0, min_throughput_rps=10.0
    )

    evidence = evaluate_load_test_result(result, thresholds)

    assert evidence.meets_p95 is True
    assert evidence.meets_error_rate is True
    assert evidence.meets_throughput is True
    assert evidence.meets_targets is True


def test_evaluate_load_test_result_flags_tail_latency_regression() -> None:
    result = LoadTestResult(
        total_requests=200,
        successful_requests=200,
        failed_requests=0,
        throughput_rps=20.0,
        p95_response_time=2.5,
    )
    thresholds = LoadTestThresholds(max_p95_seconds=2.0, max_error_rate_percent=1.0)

    evidence = evaluate_load_test_result(result, thresholds)

    assert evidence.meets_p95 is False
    assert evidence.meets_targets is False
