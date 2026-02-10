import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch

from app.shared.core.performance_testing import (
    LoadTestConfig,
    LoadTester,
    PerformanceBenchmark,
    BenchmarkResult,
    PerformanceRegressionDetector,
    LoadTestResult,
    generate_k6_script,
    run_comprehensive_performance_test,
)


def test_calculate_metrics_no_requests():
    tester = LoadTester(LoadTestConfig())
    tester._calculate_metrics(total_duration=1.0)

    assert tester.results.total_requests == 0
    assert tester.results.throughput_rps == 0.0
    assert tester.results.avg_response_time == 0.0


def test_calculate_metrics_small_sample():
    tester = LoadTester(LoadTestConfig())
    tester.results.response_times = [0.1, 0.2, 0.3, 0.4, 0.5]
    tester.results.total_requests = 5
    tester.results.total_response_time = sum(tester.results.response_times)

    tester._calculate_metrics(total_duration=2.0)

    assert tester.results.avg_response_time == pytest.approx(0.3)
    assert tester.results.median_response_time == pytest.approx(0.3)
    assert tester.results.p95_response_time == tester.results.median_response_time
    assert tester.results.p99_response_time == tester.results.p95_response_time
    assert tester.results.throughput_rps == pytest.approx(2.5)


def test_calculate_metrics_large_sample_quantiles():
    tester = LoadTester(LoadTestConfig())
    tester.results.response_times = [float(i) for i in range(1, 101)]
    tester.results.total_requests = 100
    tester.results.total_response_time = sum(tester.results.response_times)

    tester._calculate_metrics(total_duration=10.0)

    assert tester.results.p95_response_time > tester.results.median_response_time
    assert tester.results.p99_response_time >= tester.results.p95_response_time


@pytest.mark.asyncio
async def test_run_load_test_uses_simulated_users(monkeypatch):
    async def fake_simulate_user(self, user_id, test_start_time):
        self.results.total_requests += 1
        self.results.successful_requests += 1
        self.results.total_response_time += 0.2
        self.results.response_times.append(0.2)
        self.results.min_response_time = min(self.results.min_response_time, 0.2)
        self.results.max_response_time = max(self.results.max_response_time, 0.2)

    monkeypatch.setattr(LoadTester, "_simulate_user", fake_simulate_user)

    config = LoadTestConfig(duration_seconds=1, concurrent_users=3, ramp_up_seconds=0)
    tester = LoadTester(config)
    result = await tester.run_load_test()

    assert result.total_requests == 3
    assert result.successful_requests == 3
    assert result.avg_response_time == pytest.approx(0.2)
    assert result.throughput_rps > 0


@pytest.mark.asyncio
async def test_simulate_user_records_failure_and_exception(monkeypatch):
    config = LoadTestConfig(duration_seconds=5, concurrent_users=1, ramp_up_seconds=1, endpoints=["/fail"])
    tester = LoadTester(config)
    tester._running = True

    class DummyResponse:
        status_code = 500
        text = "boom"

        def raise_for_status(self):
            return None

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url):
            tester._running = False
            return DummyResponse()

    monkeypatch.setattr("app.shared.core.performance_testing.httpx.AsyncClient", lambda **kwargs: DummyClient())
    sleep_mock = AsyncMock()
    monkeypatch.setattr("app.shared.core.performance_testing.asyncio.sleep", sleep_mock)

    await tester._simulate_user(0, test_start_time=time.time())

    assert tester.results.failed_requests == 1
    assert tester.results.errors
    assert "HTTP 500" in tester.results.errors[0]
    assert sleep_mock.called

    # Exception path
    tester2 = LoadTester(config)
    tester2._running = True

    class ExplodingClient(DummyClient):
        async def get(self, url):
            tester2._running = False
            raise Exception("network down")

    monkeypatch.setattr("app.shared.core.performance_testing.httpx.AsyncClient", lambda **kwargs: ExplodingClient())
    await tester2._simulate_user(0, test_start_time=time.time())

    assert tester2.results.failed_requests == 1
    assert "network down" in tester2.results.errors[0]


@pytest.mark.asyncio
async def test_simulate_user_records_metrics(monkeypatch):
    config = LoadTestConfig(duration_seconds=1, concurrent_users=1, ramp_up_seconds=0, endpoints=["/ok", "/fail"])
    tester = LoadTester(config)
    tester._running = True

    class DummyResponse:
        def __init__(self, status_code):
            self.status_code = status_code
            self.text = "boom"

        def raise_for_status(self):
            return None

    class DummyClient:
        def __init__(self):
            self.calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url):
            self.calls += 1
            if self.calls >= 2:
                tester._running = False
            if url.endswith("/fail"):
                return DummyResponse(500)
            return DummyResponse(200)

    monkeypatch.setattr("app.shared.core.performance_testing.httpx.AsyncClient", lambda **kwargs: DummyClient())
    sleep_mock = AsyncMock()
    monkeypatch.setattr("app.shared.core.performance_testing.asyncio.sleep", sleep_mock)

    with patch("app.shared.core.performance_testing.API_REQUESTS_TOTAL") as mock_requests, \
         patch("app.shared.core.performance_testing.API_REQUEST_DURATION") as mock_duration, \
         patch("app.shared.core.performance_testing.API_ERRORS_TOTAL") as mock_errors:
        await tester._simulate_user(0, test_start_time=time.time())

        mock_requests.labels.assert_any_call(method="GET", endpoint="/ok", status_code=200)
        mock_requests.labels.assert_any_call(method="GET", endpoint="/fail", status_code=500)
        assert mock_requests.labels.return_value.inc.call_count == 2

        mock_duration.labels.assert_any_call(method="GET", endpoint="/ok")
        mock_duration.labels.assert_any_call(method="GET", endpoint="/fail")
        assert mock_duration.labels.return_value.observe.call_count == 2

        mock_errors.labels.assert_called_once_with(path="/fail", method="GET", status_code=500)
        mock_errors.labels.return_value.inc.assert_called_once()


@pytest.mark.asyncio
async def test_simulate_user_records_exception_metrics(monkeypatch):
    config = LoadTestConfig(duration_seconds=1, concurrent_users=1, ramp_up_seconds=0, endpoints=["/boom"])
    tester = LoadTester(config)
    tester._running = True

    class ExplodingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url):
            tester._running = False
            raise Exception("network down")

    monkeypatch.setattr("app.shared.core.performance_testing.httpx.AsyncClient", lambda **kwargs: ExplodingClient())
    sleep_mock = AsyncMock()
    monkeypatch.setattr("app.shared.core.performance_testing.asyncio.sleep", sleep_mock)

    with patch("app.shared.core.performance_testing.API_REQUESTS_TOTAL") as mock_requests, \
         patch("app.shared.core.performance_testing.API_REQUEST_DURATION") as mock_duration, \
         patch("app.shared.core.performance_testing.API_ERRORS_TOTAL") as mock_errors:
        await tester._simulate_user(0, test_start_time=time.time())

        mock_requests.labels.assert_called_once_with(method="GET", endpoint="/boom", status_code="exception")
        mock_duration.labels.assert_called_once_with(method="GET", endpoint="/boom")
        mock_errors.labels.assert_called_once_with(path="/boom", method="GET", status_code="exception")
@pytest.mark.asyncio
async def test_performance_benchmark_async():
    benchmark = PerformanceBenchmark("unit")

    async def noop(x):
        return x

    result = await benchmark.benchmark_async(noop, 1, iterations=3, warmup_iterations=1)

    assert result.name == "unit_noop"
    assert result.iterations == 3
    assert benchmark.results[-1] is result


def test_performance_benchmark_sync():
    benchmark = PerformanceBenchmark("unit")

    def noop(x):
        return x

    result = benchmark.benchmark_sync(noop, 1, iterations=3, warmup_iterations=1)

    assert result.name == "unit_noop"
    assert result.iterations == 3
    assert benchmark.results[-1] is result


def test_performance_regression_detector_detects(tmp_path):
    baseline_file = tmp_path / "baseline.json"
    baseline_file.write_text(
        """
{
  "benchmark_name": "baseline",
  "total_benchmarks": 1,
  "results": [
    {
      "name": "bench_a",
      "iterations": 10,
      "total_time": 1.0,
      "avg_time": 1.0,
      "median_time": 1.0,
      "min_time": 0.9,
      "max_time": 1.1,
      "throughput": 10.0
    }
  ]
}
"""
    )

    detector = PerformanceRegressionDetector(baseline_file=str(baseline_file))
    detector.load_baselines()

    current = BenchmarkResult(
        name="bench_a",
        iterations=10,
        total_time=1.3,
        avg_time=1.3,
        median_time=1.3,
        min_time=1.2,
        max_time=1.4,
        throughput=7.0,
    )

    regressions = detector.detect_regressions([current])

    assert len(regressions) >= 2
    assert any(r["regression_type"] == "average_time" for r in regressions)
    assert any(r["regression_type"] == "median_time" for r in regressions)


def test_load_baselines_file_not_found(tmp_path):
    detector = PerformanceRegressionDetector(baseline_file=str(tmp_path / "missing.json"))
    detector.load_baselines()
    assert detector.baselines == {}


def test_save_baselines_error():
    detector = PerformanceRegressionDetector(baseline_file="/nonexistent/path.json")
    with patch("app.shared.core.performance_testing.open", side_effect=OSError("nope")), \
         patch("app.shared.core.performance_testing.logger") as mock_logger:
        detector.save_baselines({"results": []})
        mock_logger.error.assert_called_once()


def test_generate_k6_script_includes_endpoints():
    config = LoadTestConfig(
        duration_seconds=10,
        concurrent_users=2,
        target_url="http://example.com",
        endpoints=["/health", "/api/v1/zombies"],
    )
    script = generate_k6_script(config)

    assert "http://example.com" in script
    assert '"/health"' in script
    assert '"/api/v1/zombies"' in script


@pytest.mark.asyncio
async def test_benchmark_health_endpoint_uses_httpx():
    class DummyResponse:
        def raise_for_status(self):
            return None

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url):
            return DummyResponse()

    async def fake_benchmark_async(self, func, *args, **kwargs):
        await func()
        return BenchmarkResult(name="health_endpoint_health_check")

    with patch("app.shared.core.performance_testing.httpx.AsyncClient", return_value=DummyClient()), \
         patch("app.shared.core.performance_testing.PerformanceBenchmark.benchmark_async", new=fake_benchmark_async):
        from app.shared.core.performance_testing import benchmark_health_endpoint
        result = await benchmark_health_endpoint(base_url="http://test")
        assert result.name == "health_endpoint_health_check"


@pytest.mark.asyncio
async def test_benchmark_cache_operations_uses_cache():
    cache = MagicMock()
    cache.set = AsyncMock()
    cache.get = AsyncMock()

    async def fake_benchmark_async(self, func, *args, **kwargs):
        await func()
        return BenchmarkResult(name="cache_operations_cache_set_get")

    with patch("app.shared.core.cache.get_cache_service", return_value=cache), \
         patch("app.shared.core.performance_testing.PerformanceBenchmark.benchmark_async", new=fake_benchmark_async):
        from app.shared.core.performance_testing import benchmark_cache_operations
        result = await benchmark_cache_operations()
        assert result.name == "cache_operations_cache_set_get"
        cache.set.assert_called_once()
        cache.get.assert_called_once()


@pytest.mark.asyncio
async def test_run_comprehensive_performance_test_aggregates_results():
    dummy_load = LoadTestResult(
        total_requests=10,
        successful_requests=9,
        throughput_rps=5.0,
        avg_response_time=0.1,
        p95_response_time=0.2,
    )
    dummy_health = BenchmarkResult(
        name="health_endpoint_health_check",
        iterations=1,
        total_time=1.0,
        avg_time=0.1,
        median_time=0.1,
        min_time=0.1,
        max_time=0.1,
        throughput=10.0,
    )
    dummy_cache = BenchmarkResult(
        name="cache_operations_cache_set_get",
        iterations=1,
        total_time=1.0,
        avg_time=0.2,
        median_time=0.2,
        min_time=0.2,
        max_time=0.2,
        throughput=5.0,
    )

    with patch(
        "app.shared.core.performance_testing.run_api_load_test",
        new_callable=AsyncMock,
        return_value=dummy_load,
    ), patch(
        "app.shared.core.performance_testing.benchmark_health_endpoint",
        new_callable=AsyncMock,
        return_value=dummy_health,
    ), patch(
        "app.shared.core.performance_testing.benchmark_cache_operations",
        new_callable=AsyncMock,
        return_value=dummy_cache,
    ), patch(
        "app.shared.core.performance_testing.PerformanceRegressionDetector.load_baselines"
    ), patch(
        "app.shared.core.performance_testing.PerformanceRegressionDetector.detect_regressions",
        return_value=[],
    ), patch(
        "app.shared.core.performance_testing.PerformanceRegressionDetector.save_baselines"
    ) as mock_save:
        summary = await run_comprehensive_performance_test()

        assert summary["load_test"]["total_requests"] == 10
        assert summary["regressions_detected"] == []
        assert summary["k6_script_available"] is True
        assert summary["total_benchmarks"] == 2
        result_names = {r["name"] for r in summary["results"]}
        assert "health_endpoint_health_check" in result_names
        assert "cache_operations_cache_set_get" in result_names
        mock_save.assert_called_once()
