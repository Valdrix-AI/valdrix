from __future__ import annotations

from dataclasses import asdict, dataclass

from app.shared.core.performance_testing import LoadTestResult


@dataclass(frozen=True)
class LoadTestThresholds:
    """
    Thresholds for a load test run.

    Notes:
    - p95 is the primary UX guardrail for dashboards (tail latency).
    - error_rate_percent should include 4xx/5xx considered "failed" by the runner.
    """

    max_p95_seconds: float
    max_error_rate_percent: float
    min_throughput_rps: float | None = None


@dataclass(frozen=True)
class LoadTestEvidence:
    total_requests: int
    successful_requests: int
    failed_requests: int
    error_rate_percent: float
    throughput_rps: float
    p95_response_time: float
    meets_p95: bool
    meets_error_rate: bool
    meets_throughput: bool
    meets_targets: bool
    thresholds: LoadTestThresholds

    def model_dump(self) -> dict[str, object]:
        payload = asdict(self)
        payload["thresholds"] = asdict(self.thresholds)
        return payload


def evaluate_load_test_result(
    result: LoadTestResult,
    thresholds: LoadTestThresholds,
) -> LoadTestEvidence:
    total = int(result.total_requests or 0)
    failed = int(result.failed_requests or 0)
    successful = int(result.successful_requests or 0)
    if total <= 0:
        error_rate = 100.0 if failed > 0 else 0.0
    else:
        error_rate = round((failed / total) * 100.0, 4)

    p95 = float(result.p95_response_time or 0.0)
    throughput = float(result.throughput_rps or 0.0)

    meets_p95 = total > 0 and p95 <= float(thresholds.max_p95_seconds)
    meets_error_rate = total > 0 and error_rate <= float(
        thresholds.max_error_rate_percent
    )
    meets_throughput = True
    if thresholds.min_throughput_rps is not None:
        meets_throughput = total > 0 and throughput >= float(
            thresholds.min_throughput_rps
        )

    meets_targets = bool(
        total > 0 and meets_p95 and meets_error_rate and meets_throughput
    )

    return LoadTestEvidence(
        total_requests=total,
        successful_requests=successful,
        failed_requests=failed,
        error_rate_percent=error_rate,
        throughput_rps=round(throughput, 4),
        p95_response_time=round(p95, 4),
        meets_p95=meets_p95,
        meets_error_rate=meets_error_rate,
        meets_throughput=meets_throughput,
        meets_targets=meets_targets,
        thresholds=thresholds,
    )
