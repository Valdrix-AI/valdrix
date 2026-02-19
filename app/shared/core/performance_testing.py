"""
Load Testing and Performance Benchmarking Utilities

Provides tools for load testing APIs, benchmarking database queries,
and measuring system performance under various conditions.
"""

import asyncio
import time
import statistics
from typing import Dict, Any, List, Callable, Awaitable
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import structlog

from app.shared.core.config import get_settings
from app.shared.core.ops_metrics import (
    API_REQUEST_DURATION,
    API_REQUESTS_TOTAL,
    API_ERRORS_TOTAL,
)

logger = structlog.get_logger()
settings = get_settings()


def format_exception_message(exc: BaseException) -> str:
    """Return stable, non-empty exception text for evidence payloads."""
    exc_type = exc.__class__.__name__
    detail = str(exc).strip()
    if detail:
        return f"{exc_type}: {detail}"
    return exc_type


@dataclass
class LoadTestConfig:
    """Configuration for load testing."""

    duration_seconds: int = 60  # How long to run the test
    concurrent_users: int = 10  # Number of concurrent users
    ramp_up_seconds: int = 10  # Time to ramp up to full concurrency
    target_url: str = "http://localhost:8000"
    endpoints: List[str] = field(default_factory=lambda: ["/health/live"])
    request_timeout: float = 30.0
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class LoadTestResult:
    """Results from a load test."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_response_time: float = 0.0
    response_times: List[float] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    throughput_rps: float = 0.0  # requests per second
    avg_response_time: float = 0.0
    median_response_time: float = 0.0
    p95_response_time: float = 0.0
    p99_response_time: float = 0.0
    min_response_time: float = float("inf")
    max_response_time: float = 0.0


class LoadTester:
    """Load testing utility for APIs."""

    def __init__(self, config: LoadTestConfig):
        self.config = config
        self.results = LoadTestResult()
        self._running = False

    async def run_load_test(self) -> LoadTestResult:
        """Run the load test and return results."""
        logger.info(
            "starting_load_test",
            duration=self.config.duration_seconds,
            concurrent_users=self.config.concurrent_users,
            endpoints=self.config.endpoints,
        )

        self._running = True
        start_time = time.time()

        # Create concurrent tasks
        tasks = []
        for user_id in range(self.config.concurrent_users):
            task = asyncio.create_task(self._simulate_user(user_id, start_time))
            tasks.append(task)

        # Wait for all tasks to complete
        await asyncio.gather(*tasks, return_exceptions=True)

        end_time = time.time()
        total_duration = end_time - start_time

        # Calculate final metrics
        self._calculate_metrics(total_duration)

        logger.info(
            "load_test_completed",
            total_requests=self.results.total_requests,
            successful_requests=self.results.successful_requests,
            failed_requests=self.results.failed_requests,
            throughput_rps=self.results.throughput_rps,
            avg_response_time=self.results.avg_response_time,
            p95_response_time=self.results.p95_response_time,
        )

        return self.results

    async def _simulate_user(self, user_id: int, test_start_time: float) -> None:
        """Simulate a single user making requests."""
        from app.shared.core.http import get_http_client

        client = get_http_client()

        # Ramp up delay
        if self.config.ramp_up_seconds > 0:
            delay = (
                user_id / self.config.concurrent_users
            ) * self.config.ramp_up_seconds
            await asyncio.sleep(delay)

        time.time()

        while (
            self._running
            and (time.time() - test_start_time) < self.config.duration_seconds
        ):
            for endpoint in self.config.endpoints:
                if not self._running:
                    break

                request_start = time.time()
                try:
                    url = f"{self.config.target_url}{endpoint}"
                    response = await client.get(url, headers=self.config.headers)

                    response_time = time.time() - request_start

                    # Record metrics
                    self.results.total_requests += 1
                    self.results.total_response_time += response_time
                    self.results.response_times.append(response_time)

                    if response.status_code < 400:
                        self.results.successful_requests += 1
                    else:
                        self.results.failed_requests += 1
                        self.results.errors.append(
                            f"{endpoint} -> HTTP {response.status_code}: {response.text[:100]}"
                        )

                    API_REQUESTS_TOTAL.labels(
                        method="GET",
                        endpoint=endpoint,
                        status_code=response.status_code,
                    ).inc()
                    API_REQUEST_DURATION.labels(
                        method="GET", endpoint=endpoint
                    ).observe(response_time)
                    if response.status_code >= 400:
                        API_ERRORS_TOTAL.labels(
                            path=endpoint,
                            method="GET",
                            status_code=response.status_code,
                        ).inc()

                    # Update min/max
                    self.results.min_response_time = min(
                        self.results.min_response_time, response_time
                    )
                    self.results.max_response_time = max(
                        self.results.max_response_time, response_time
                    )

                except Exception as e:
                    response_time = time.time() - request_start
                    self.results.total_requests += 1
                    self.results.failed_requests += 1
                    self.results.errors.append(
                        f"{endpoint} -> {format_exception_message(e)}"
                    )
                    API_REQUESTS_TOTAL.labels(
                        method="GET", endpoint=endpoint, status_code="exception"
                    ).inc()
                    API_REQUEST_DURATION.labels(
                        method="GET", endpoint=endpoint
                    ).observe(response_time)
                    API_ERRORS_TOTAL.labels(
                        path=endpoint, method="GET", status_code="exception"
                    ).inc()

                # Small delay between requests to avoid overwhelming
                await asyncio.sleep(0.1)

    def _calculate_metrics(self, total_duration: float) -> None:
        """Calculate final performance metrics."""
        if self.results.total_requests == 0:
            return

        self.results.throughput_rps = self.results.total_requests / total_duration
        self.results.avg_response_time = (
            self.results.total_response_time / self.results.total_requests
        )

        if self.results.response_times:
            self.results.median_response_time = statistics.median(
                self.results.response_times
            )
            if len(self.results.response_times) >= 20:
                self.results.p95_response_time = statistics.quantiles(
                    self.results.response_times, n=20
                )[18]  # 95th percentile
            else:
                self.results.p95_response_time = self.results.median_response_time
            if len(self.results.response_times) >= 100:
                self.results.p99_response_time = statistics.quantiles(
                    self.results.response_times, n=100
                )[98]  # 99th percentile
            else:
                self.results.p99_response_time = self.results.p95_response_time

    def stop(self) -> None:
        """Stop the load test."""
        self._running = False


@dataclass
class BenchmarkResult:
    """Results from a benchmark test."""

    name: str
    iterations: int = 0
    total_time: float = 0.0
    avg_time: float = 0.0
    median_time: float = 0.0
    min_time: float = float("inf")
    max_time: float = 0.0
    throughput: float = 0.0  # operations per second


class PerformanceBenchmark:
    """Performance benchmarking utility."""

    def __init__(self, name: str = "benchmark"):
        self.name = name
        self.results: List[BenchmarkResult] = []

    async def benchmark_async(
        self,
        func: Callable[..., Awaitable[Any]],
        *args: Any,
        iterations: int = 100,
        warmup_iterations: int = 10,
        **kwargs: Any,
    ) -> BenchmarkResult:
        """Benchmark an async function."""
        # Warmup
        for _ in range(warmup_iterations):
            await func(*args, **kwargs)

        # Benchmark
        times = []
        start_time = time.time()

        for _ in range(iterations):
            iteration_start = time.perf_counter()
            await func(*args, **kwargs)
            iteration_time = time.perf_counter() - iteration_start
            times.append(iteration_time)

        total_time = time.time() - start_time

        # Calculate metrics
        result = BenchmarkResult(
            name=f"{self.name}_{func.__name__}",
            iterations=iterations,
            total_time=total_time,
            avg_time=statistics.mean(times),
            median_time=statistics.median(times),
            min_time=min(times),
            max_time=max(times),
            throughput=iterations / total_time,
        )

        self.results.append(result)

        logger.info(
            "benchmark_completed",
            name=result.name,
            iterations=result.iterations,
            avg_time=result.avg_time,
            median_time=result.median_time,
            throughput=result.throughput,
        )

        return result

    def benchmark_sync(
        self,
        func: Callable[..., Any],
        *args: Any,
        iterations: int = 100,
        warmup_iterations: int = 10,
        **kwargs: Any,
    ) -> BenchmarkResult:
        """Benchmark a sync function using a thread pool."""

        def run_warmup() -> None:
            for _ in range(warmup_iterations):
                func(*args, **kwargs)

        def run_benchmark() -> list[float]:
            times = []
            for _ in range(iterations):
                iteration_start = time.perf_counter()
                func(*args, **kwargs)
                iteration_time = time.perf_counter() - iteration_start
                times.append(iteration_time)
            return times

        # Run warmup
        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(run_warmup).result()

        # Run benchmark
        start_time = time.time()
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_benchmark)
            times = future.result()

        total_time = time.time() - start_time

        # Calculate metrics
        result = BenchmarkResult(
            name=f"{self.name}_{func.__name__}",
            iterations=iterations,
            total_time=total_time,
            avg_time=statistics.mean(times),
            median_time=statistics.median(times),
            min_time=min(times),
            max_time=max(times),
            throughput=iterations / total_time,
        )

        self.results.append(result)
        return result

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all benchmark results."""
        return {
            "benchmark_name": self.name,
            "total_benchmarks": len(self.results),
            "results": [
                {
                    "name": r.name,
                    "iterations": r.iterations,
                    "avg_time": r.avg_time,
                    "median_time": r.median_time,
                    "throughput": r.throughput,
                    "min_time": r.min_time,
                    "max_time": r.max_time,
                }
                for r in self.results
            ],
        }


# Pre-configured benchmark scenarios
async def benchmark_health_endpoint(
    base_url: str = "http://localhost:8000",
) -> BenchmarkResult:
    """Benchmark the health endpoint."""
    benchmark = PerformanceBenchmark("health_endpoint")

    from app.shared.core.http import get_http_client

    client = get_http_client()

    async def health_check() -> None:
        response = await client.get(f"{base_url}/health")
        response.raise_for_status()

    return await benchmark.benchmark_async(health_check, iterations=50)


async def benchmark_cache_operations() -> BenchmarkResult:
    """Benchmark cache operations."""
    from app.shared.core.cache import get_cache_service

    benchmark = PerformanceBenchmark("cache_operations")
    cache = get_cache_service()

    async def cache_set_get() -> None:
        key = f"benchmark_{time.time()}"
        await cache.set(key, "test_value", ttl=timedelta(seconds=60))
        await cache.get(key)

    return await benchmark.benchmark_async(cache_set_get, iterations=100)


# Performance regression detection
class PerformanceRegressionDetector:
    """Detect performance regressions by comparing benchmarks."""

    def __init__(self, baseline_file: str = "performance_baseline.json"):
        self.baseline_file = baseline_file
        self.baselines: Dict[str, BenchmarkResult] = {}

    def load_baselines(self) -> None:
        """Load baseline performance data."""
        try:
            import json

            with open(self.baseline_file, "r") as f:
                data = json.load(f)
                for item in data.get("results", []):
                    result = BenchmarkResult(**item)
                    self.baselines[result.name] = result
        except FileNotFoundError:
            logger.warning("baseline_file_not_found", file=self.baseline_file)
        except Exception as e:
            logger.error("failed_to_load_baselines", error=str(e))

    def save_baselines(self, benchmark_summary: Dict[str, Any]) -> None:
        """Save current results as new baselines."""
        try:
            import json

            with open(self.baseline_file, "w") as f:
                json.dump(benchmark_summary, f, indent=2, default=str)
            logger.info("baselines_saved", file=self.baseline_file)
        except Exception as e:
            logger.error("failed_to_save_baselines", error=str(e))

    def detect_regressions(
        self, current_results: List[BenchmarkResult]
    ) -> List[Dict[str, Any]]:
        """Detect performance regressions compared to baselines."""
        regressions = []

        for result in current_results:
            baseline = self.baselines.get(result.name)
            if not baseline:
                continue

            # Check for significant regressions (20% slower)
            regression_threshold = 1.20

            if result.avg_time > baseline.avg_time * regression_threshold:
                regressions.append(
                    {
                        "benchmark": result.name,
                        "regression_type": "average_time",
                        "baseline": baseline.avg_time,
                        "current": result.avg_time,
                        "degradation": (result.avg_time / baseline.avg_time - 1) * 100,
                        "threshold_percent": (regression_threshold - 1) * 100,
                    }
                )

            if result.median_time > baseline.median_time * regression_threshold:
                regressions.append(
                    {
                        "benchmark": result.name,
                        "regression_type": "median_time",
                        "baseline": baseline.median_time,
                        "current": result.median_time,
                        "degradation": (result.median_time / baseline.median_time - 1)
                        * 100,
                        "threshold_percent": (regression_threshold - 1) * 100,
                    }
                )

        return regressions


# K6-style load test script generator
def generate_k6_script(config: LoadTestConfig) -> str:
    """Generate a K6 load testing script."""
    endpoints_str = "\n".join([f'    "{endpoint}",' for endpoint in config.endpoints])

    script = f"""
import http from 'k6/http';
import {{ check, sleep }} from 'k6';

export let options = {{
    duration: '{config.duration_seconds}s',
    vus: {config.concurrent_users},
    thresholds: {{
        http_req_duration: ['p(95)<500', 'p(99)<1000'],
        http_req_failed: ['rate<0.1'],
    }},
}};

const BASE_URL = '{config.target_url}';
const endpoints = [
{endpoints_str}
];

export default function () {{
    const endpoint = endpoints[Math.floor(Math.random() * endpoints.length)];
    const response = http.get(`${{BASE_URL}}${{endpoint}}`);

    check(response, {{
        'status is 2xx or 4xx': (r) => r.status >= 200 && r.status < 500,
        'response time < 1000ms': (r) => r.timings.duration < 1000,
    }});

    sleep(0.1);
}}
"""
    return script


# Example usage functions
async def run_api_load_test(
    target_url: str = "http://localhost:8000",
    duration: int = 30,
    concurrent_users: int = 5,
) -> LoadTestResult:
    """Run a basic API load test."""
    config = LoadTestConfig(
        duration_seconds=duration,
        concurrent_users=concurrent_users,
        target_url=target_url,
        endpoints=["/health", "/api/v1/zombies"],  # Test key endpoints
    )

    tester = LoadTester(config)
    return await tester.run_load_test()


async def run_comprehensive_performance_test() -> Dict[str, Any]:
    """Run comprehensive performance tests."""
    logger.info("starting_comprehensive_performance_test")

    # API load test
    load_result = await run_api_load_test()

    # Individual benchmarks
    benchmark = PerformanceBenchmark("comprehensive")

    # Health endpoint benchmark
    health_result = await benchmark_health_endpoint()

    # Cache benchmark
    cache_result = await benchmark_cache_operations()

    # Collect results for regression detection/summary
    benchmark.results.extend([health_result, cache_result])

    # Detect regressions
    detector = PerformanceRegressionDetector()
    detector.load_baselines()

    all_results = benchmark.results
    regressions = detector.detect_regressions(all_results)

    summary = benchmark.get_summary()
    summary.update(
        {
            "load_test": {
                "total_requests": load_result.total_requests,
                "successful_requests": load_result.successful_requests,
                "throughput_rps": load_result.throughput_rps,
                "avg_response_time": load_result.avg_response_time,
                "p95_response_time": load_result.p95_response_time,
            },
            "regressions_detected": regressions,
            "k6_script_available": True,
        }
    )

    # Save new baselines if no regressions
    if not regressions:
        detector.save_baselines(summary)

    logger.info(
        "comprehensive_performance_test_completed",
        load_test_requests=load_result.total_requests,
        regressions_found=len(regressions),
    )

    return summary
