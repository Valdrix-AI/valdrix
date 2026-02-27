#!/usr/bin/env python3
"""
Lightweight API load test runner for local/staging validation.

This wraps `app.shared.core.performance_testing.LoadTester` so we can
standardize how we measure p95/p99 for key endpoints during hardening.

Example:
  export VALDRIX_TOKEN="$(uv run python scripts/dev_bearer_token.py --email owner@valdrix.io)"
  uv run python scripts/load_test_api.py --url http://127.0.0.1:8000 --endpoint /health/live --endpoint /api/v1/costs/acceptance/kpis

Perf smoke (dashboard profile):
  uv run python scripts/load_test_api.py --profile dashboard --duration 30 --users 15 \\
    --p95-target 2.0 --max-error-rate 1.0 --out reports/performance/dashboard_smoke.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any
from datetime import date, timedelta
from datetime import datetime, timezone

import httpx

from app.shared.core.evidence_capture import sanitize_bearer_token
from app.shared.core.performance_testing import (
    LoadTestConfig,
    LoadTester,
    format_exception_message,
)
from app.shared.core.performance_evidence import (
    LoadTestThresholds,
    evaluate_load_test_result,
)

LIVENESS_ENDPOINT = "/health/live"
DEEP_HEALTH_ENDPOINT = "/health"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a small API load test.")
    parser.add_argument(
        "--url", dest="url", default="http://127.0.0.1:8000", help="Base URL"
    )
    parser.add_argument(
        "--profile",
        dest="profile",
        choices=[
            "health",
            "health_deep",
            "dashboard",
            "ops",
            "scale",
            "soak",
            "enforcement",
        ],
        default="health",
        help="Use a pre-defined endpoint profile when --endpoint is not supplied.",
    )
    parser.add_argument(
        "--endpoint",
        dest="endpoints",
        action="append",
        default=[],
        help=f"Endpoint path (repeatable). Default: {LIVENESS_ENDPOINT}",
    )
    parser.add_argument(
        "--include-deep-health",
        dest="include_deep_health",
        action="store_true",
        help=f"Include {DEEP_HEALTH_ENDPOINT} in generated profile endpoints.",
    )
    parser.add_argument(
        "--start-date", dest="start_date", default="", help="ISO date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end-date", dest="end_date", default="", help="ISO date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--provider",
        dest="provider",
        default="",
        help="Provider filter (aws/azure/gcp/...)",
    )
    parser.add_argument(
        "--duration", dest="duration", type=int, default=30, help="Duration in seconds"
    )
    parser.add_argument(
        "--users", dest="users", type=int, default=10, help="Concurrent users"
    )
    parser.add_argument(
        "--ramp", dest="ramp", type=int, default=5, help="Ramp-up seconds"
    )
    parser.add_argument(
        "--timeout",
        dest="timeout",
        type=float,
        default=15.0,
        help="Request timeout seconds",
    )
    parser.add_argument(
        "--skip-preflight",
        dest="skip_preflight",
        action="store_true",
        help="Skip preflight endpoint validation before the load run.",
    )
    parser.add_argument(
        "--allow-preflight-failures",
        dest="allow_preflight_failures",
        action="store_true",
        help="Continue load run even if preflight checks fail.",
    )
    parser.add_argument(
        "--preflight-attempts",
        dest="preflight_attempts",
        type=int,
        default=2,
        help="Number of preflight attempts per endpoint.",
    )
    parser.add_argument(
        "--preflight-timeout",
        dest="preflight_timeout",
        type=float,
        default=5.0,
        help="Timeout (seconds) per preflight request.",
    )
    parser.add_argument(
        "--rounds",
        dest="rounds",
        type=int,
        default=1,
        help="Repeat the run N times (soak). Aggregates worst-case p95/error-rate for evidence.",
    )
    parser.add_argument(
        "--pause",
        dest="pause",
        type=float,
        default=0.0,
        help="Pause in seconds between rounds (soak).",
    )
    parser.add_argument(
        "--out",
        dest="out",
        default="",
        help="Write JSON results to this path (optional)",
    )
    parser.add_argument(
        "--p95-target",
        dest="p95_target",
        type=float,
        default=None,
        help="Fail if p95 response time exceeds this value (seconds).",
    )
    parser.add_argument(
        "--max-error-rate",
        dest="max_error_rate",
        type=float,
        default=None,
        help="Fail if failed request rate exceeds this value (percent).",
    )
    parser.add_argument(
        "--min-throughput",
        dest="min_throughput",
        type=float,
        default=None,
        help="Fail if throughput is below this value (requests per second).",
    )
    parser.add_argument(
        "--enforce-thresholds",
        dest="enforce_thresholds",
        action="store_true",
        help="Exit non-zero if the evaluated thresholds are not met.",
    )
    parser.add_argument(
        "--publish",
        dest="publish",
        action="store_true",
        help="Publish the load test evidence to the tenant audit log (Pro+ admin only).",
    )
    return parser.parse_args()


def _resolve_date_window(args: argparse.Namespace) -> tuple[str, str]:
    if args.start_date and args.end_date:
        return str(args.start_date).strip(), str(args.end_date).strip()
    end = date.today()
    start = end - timedelta(days=30)
    return start.isoformat(), end.isoformat()


def _build_profile_endpoints(args: argparse.Namespace) -> list[str]:
    provider = str(args.provider or "").strip().lower()
    provider_query = f"&provider={provider}" if provider else ""
    carbon_provider_query = (
        provider_query if provider in {"aws", "azure", "gcp"} else ""
    )
    zombies_provider_query = (
        provider_query if provider in {"aws", "azure", "gcp", "saas", "license"} else ""
    )

    if args.profile == "health":
        endpoints = [LIVENESS_ENDPOINT]
    elif args.profile == "health_deep":
        endpoints = [DEEP_HEALTH_ENDPOINT]
    elif args.profile == "enforcement":
        endpoints = _build_enforcement_profile_endpoints(args)
    elif args.profile == "dashboard":
        start_date, end_date = _resolve_date_window(args)
        endpoints = [
            LIVENESS_ENDPOINT,
            f"/api/v1/costs?start_date={start_date}&end_date={end_date}{provider_query}",
            f"/api/v1/carbon?start_date={start_date}&end_date={end_date}{carbon_provider_query}",
            f"/api/v1/zombies?analyze=false{zombies_provider_query}",
        ]
    elif args.profile in {"scale", "soak"}:
        endpoints = _build_scale_profile_endpoints(args)
    else:
        # ops profile
        start_date, end_date = _resolve_date_window(args)
        endpoints = [
            LIVENESS_ENDPOINT,
            "/api/v1/costs/ingestion/sla?window_hours=24&target_success_rate_percent=95",
            (
                "/api/v1/costs/acceptance/kpis?"
                f"start_date={start_date}&end_date={end_date}"
                "&ingestion_window_hours=168"
                "&ingestion_target_success_rate_percent=95"
                "&recency_target_hours=48"
                "&chargeback_target_percent=90"
                "&max_unit_anomalies=0"
                "&response_format=json"
            ),
        ]

    if args.include_deep_health and DEEP_HEALTH_ENDPOINT not in endpoints:
        endpoints.insert(0, DEEP_HEALTH_ENDPOINT)

    return endpoints


def _build_scale_profile_endpoints(args: argparse.Namespace) -> list[str]:
    start_date, end_date = _resolve_date_window(args)
    provider = str(args.provider or "").strip().lower()
    provider_query = f"&provider={provider}" if provider else ""
    return [
        LIVENESS_ENDPOINT,
        f"/api/v1/costs?start_date={start_date}&end_date={end_date}{provider_query}",
        (
            "/api/v1/costs/acceptance/kpis?"
            f"start_date={start_date}&end_date={end_date}"
            "&ingestion_window_hours=168"
            "&ingestion_target_success_rate_percent=95"
            "&recency_target_hours=48"
            "&chargeback_target_percent=90"
            "&max_unit_anomalies=0"
            "&response_format=json"
        ),
        f"/api/v1/leadership/kpis?start_date={start_date}&end_date={end_date}&response_format=json{provider_query}",
        f"/api/v1/savings/proof?start_date={start_date}&end_date={end_date}&response_format=json{provider_query}",
        "/api/v1/leaderboards?period=30d",
    ]


def _build_enforcement_profile_endpoints(args: argparse.Namespace) -> list[str]:
    del args  # profile does not currently depend on date/provider filters.
    return [
        LIVENESS_ENDPOINT,
        "/api/v1/enforcement/policies",
        "/api/v1/enforcement/budgets",
        "/api/v1/enforcement/credits",
        "/api/v1/enforcement/approvals/queue?limit=50",
        "/api/v1/enforcement/ledger?limit=50",
        "/api/v1/enforcement/exports/parity?limit=50",
    ]


async def _run_preflight_checks(
    *,
    target_url: str,
    endpoints: list[str],
    headers: dict[str, str],
    timeout_seconds: float,
    attempts: int,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    request_timeout = max(0.1, float(timeout_seconds))
    attempts = max(1, int(attempts))

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(request_timeout, connect=min(request_timeout, 5.0)),
        headers=headers,
    ) as client:
        for endpoint in endpoints:
            passed = False
            for attempt in range(1, attempts + 1):
                started = datetime.now(timezone.utc)
                try:
                    response = await client.get(f"{target_url}{endpoint}")
                    latency_ms = max(
                        0.0,
                        (datetime.now(timezone.utc) - started).total_seconds() * 1000.0,
                    )
                    status_code = int(response.status_code)
                    preview = str(response.text or "").replace("\n", " ")[:140]
                    ok = status_code < 400
                    checks.append(
                        {
                            "endpoint": endpoint,
                            "attempt": attempt,
                            "status_code": status_code,
                            "ok": ok,
                            "latency_ms": round(latency_ms, 2),
                            "error": "" if ok else f"HTTP {status_code}: {preview}",
                        }
                    )
                    if ok:
                        passed = True
                        break
                except Exception as exc:
                    latency_ms = max(
                        0.0,
                        (datetime.now(timezone.utc) - started).total_seconds() * 1000.0,
                    )
                    checks.append(
                        {
                            "endpoint": endpoint,
                            "attempt": attempt,
                            "status_code": None,
                            "ok": False,
                            "latency_ms": round(latency_ms, 2),
                            "error": format_exception_message(exc),
                        }
                    )
                if attempt < attempts:
                    await asyncio.sleep(min(0.25, attempt * 0.1))
            if not passed:
                last = checks[-1]
                failures.append(
                    {
                        "endpoint": endpoint,
                        "error": str(last.get("error") or "preflight failed"),
                    }
                )

    return {
        "enabled": True,
        "passed": len(failures) == 0,
        "attempts_per_endpoint": attempts,
        "request_timeout_seconds": request_timeout,
        "checks": checks,
        "failures": failures,
    }


async def main() -> None:
    args = _parse_args()
    endpoints = args.endpoints or _build_profile_endpoints(args)

    headers: dict[str, str] = {}
    token = ""
    raw_token = os.getenv("VALDRIX_TOKEN", "").strip()
    if raw_token:
        try:
            token = sanitize_bearer_token(raw_token)
        except ValueError as exc:
            raise SystemExit(
                "Invalid VALDRIX_TOKEN. Ensure it's a single JWT string. "
                f"Details: {exc}"
            ) from None
        headers["Authorization"] = f"Bearer {token}"

    config = LoadTestConfig(
        duration_seconds=int(args.duration),
        concurrent_users=int(args.users),
        ramp_up_seconds=int(args.ramp),
        target_url=str(args.url).rstrip("/"),
        endpoints=endpoints,
        request_timeout=float(args.timeout),
        headers=headers,
    )

    rounds = max(1, int(args.rounds or 1))
    pause_seconds = max(0.0, float(args.pause or 0.0))
    preflight_attempts = max(1, int(args.preflight_attempts or 1))
    preflight_timeout = max(0.1, float(args.preflight_timeout or 0.1))
    skip_preflight = bool(args.skip_preflight)
    allow_preflight_failures = bool(args.allow_preflight_failures)

    preflight: dict[str, Any]
    if skip_preflight:
        preflight = {
            "enabled": False,
            "passed": None,
            "attempts_per_endpoint": 0,
            "request_timeout_seconds": preflight_timeout,
            "checks": [],
            "failures": [],
        }
    else:
        preflight = await _run_preflight_checks(
            target_url=config.target_url,
            endpoints=endpoints,
            headers=headers,
            timeout_seconds=preflight_timeout,
            attempts=preflight_attempts,
        )
        if not preflight.get("passed") and not allow_preflight_failures:
            failure_payload = {
                "profile": str(args.profile),
                "target_url": str(config.target_url),
                "endpoints": list(endpoints),
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "runner": "scripts/load_test_api.py",
                "status": "preflight_failed",
                "preflight": preflight,
                "meets_targets": False,
                "results": {
                    "total_requests": 0,
                    "successful_requests": 0,
                    "failed_requests": 0,
                    "throughput_rps": 0.0,
                    "avg_response_time": 0.0,
                    "median_response_time": 0.0,
                    "p95_response_time": 0.0,
                    "p99_response_time": 0.0,
                    "min_response_time": 0.0,
                    "max_response_time": 0.0,
                    "errors_sample": [
                        f"Preflight failed for {item['endpoint']}: {item['error']}"
                        for item in list(preflight.get("failures", []))[:10]
                    ],
                },
            }
            print(json.dumps(failure_payload, indent=2, sort_keys=True))
            if args.out:
                with open(args.out, "w", encoding="utf-8") as f:
                    json.dump(failure_payload, f, indent=2, sort_keys=True)
            raise SystemExit(
                "Preflight checks failed. Fix endpoint/auth/runtime health or re-run with --allow-preflight-failures."
            )

    def result_to_payload(result: object) -> dict[str, object]:
        return {
            "total_requests": int(getattr(result, "total_requests", 0) or 0),
            "successful_requests": int(getattr(result, "successful_requests", 0) or 0),
            "failed_requests": int(getattr(result, "failed_requests", 0) or 0),
            "throughput_rps": float(getattr(result, "throughput_rps", 0.0) or 0.0),
            "avg_response_time": float(
                getattr(result, "avg_response_time", 0.0) or 0.0
            ),
            "median_response_time": float(
                getattr(result, "median_response_time", 0.0) or 0.0
            ),
            "p95_response_time": float(
                getattr(result, "p95_response_time", 0.0) or 0.0
            ),
            "p99_response_time": float(
                getattr(result, "p99_response_time", 0.0) or 0.0
            ),
            "min_response_time": float(
                getattr(result, "min_response_time", 0.0) or 0.0
            ),
            "max_response_time": float(
                getattr(result, "max_response_time", 0.0) or 0.0
            ),
            "errors_sample": list(getattr(result, "errors", [])[:10]),
        }

    run_payloads: list[dict[str, object]] = []
    raw_results = []

    for idx in range(rounds):
        tester = LoadTester(config)
        raw = await tester.run_load_test()
        raw_results.append(raw)
        run_payloads.append(
            {
                "run_index": idx + 1,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "results": result_to_payload(raw),
            }
        )
        if pause_seconds and idx < rounds - 1:
            await asyncio.sleep(pause_seconds)

    # Aggregate worst-case evidence for procurement/perf sign-off.
    total_requests = sum(int(getattr(r, "total_requests", 0) or 0) for r in raw_results)
    successful_requests = sum(
        int(getattr(r, "successful_requests", 0) or 0) for r in raw_results
    )
    failed_requests = sum(
        int(getattr(r, "failed_requests", 0) or 0) for r in raw_results
    )
    worst_p95 = max(
        float(getattr(r, "p95_response_time", 0.0) or 0.0) for r in raw_results
    )
    worst_p99 = max(
        float(getattr(r, "p99_response_time", 0.0) or 0.0) for r in raw_results
    )
    min_throughput = min(
        float(getattr(r, "throughput_rps", 0.0) or 0.0) for r in raw_results
    )
    avg_throughput = sum(
        float(getattr(r, "throughput_rps", 0.0) or 0.0) for r in raw_results
    ) / max(1, rounds)
    min_response = min(
        float(getattr(r, "min_response_time", 0.0) or 0.0) for r in raw_results
    )
    max_response = max(
        float(getattr(r, "max_response_time", 0.0) or 0.0) for r in raw_results
    )

    errors_sample: list[str] = []
    for raw in raw_results:
        for err in list(getattr(raw, "errors", [])[:10]):
            if err not in errors_sample:
                errors_sample.append(err)
        if len(errors_sample) >= 10:
            break

    # Keep median/avg as averages to avoid misleading "worst median" values.
    avg_response_time = sum(
        float(getattr(r, "avg_response_time", 0.0) or 0.0) for r in raw_results
    ) / max(1, rounds)
    median_response_time = sum(
        float(getattr(r, "median_response_time", 0.0) or 0.0) for r in raw_results
    ) / max(1, rounds)

    results_payload = {
        "total_requests": total_requests,
        "successful_requests": successful_requests,
        "failed_requests": failed_requests,
        "throughput_rps": round(avg_throughput, 4),
        "avg_response_time": round(avg_response_time, 4),
        "median_response_time": round(median_response_time, 4),
        "p95_response_time": round(worst_p95, 4),
        "p99_response_time": round(worst_p99, 4),
        "min_response_time": round(min_response, 4),
        "max_response_time": round(max_response, 4),
        "errors_sample": errors_sample[:10],
    }

    evidence_payload: dict[str, object] = {
        "profile": str(args.profile),
        "target_url": str(config.target_url),
        "endpoints": list(endpoints),
        "duration_seconds": int(config.duration_seconds),
        "concurrent_users": int(config.concurrent_users),
        "ramp_up_seconds": int(config.ramp_up_seconds),
        "request_timeout": float(config.request_timeout),
        "results": results_payload,
        "rounds": rounds,
        "runs": run_payloads,
        "min_throughput_rps": round(min_throughput, 4),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "runner": "scripts/load_test_api.py",
        "preflight": preflight,
    }

    profile_defaults: dict[str, LoadTestThresholds] = {
        "health": LoadTestThresholds(
            max_p95_seconds=1.0, max_error_rate_percent=1.0, min_throughput_rps=1.0
        ),
        "health_deep": LoadTestThresholds(
            max_p95_seconds=4.0, max_error_rate_percent=2.0, min_throughput_rps=0.2
        ),
        "dashboard": LoadTestThresholds(
            max_p95_seconds=2.5, max_error_rate_percent=1.0, min_throughput_rps=0.5
        ),
        "ops": LoadTestThresholds(
            max_p95_seconds=2.5, max_error_rate_percent=1.0, min_throughput_rps=0.5
        ),
        "scale": LoadTestThresholds(
            max_p95_seconds=4.0, max_error_rate_percent=2.0, min_throughput_rps=0.2
        ),
        "soak": LoadTestThresholds(
            max_p95_seconds=4.0, max_error_rate_percent=2.0, min_throughput_rps=0.2
        ),
        "enforcement": LoadTestThresholds(
            max_p95_seconds=2.0, max_error_rate_percent=1.0, min_throughput_rps=0.5
        ),
    }

    thresholds: LoadTestThresholds | None = None
    enforce = bool(args.enforce_thresholds)
    explicit_thresholds = (
        args.p95_target is not None
        or args.max_error_rate is not None
        or args.min_throughput is not None
    )
    if explicit_thresholds:
        thresholds = LoadTestThresholds(
            max_p95_seconds=float(args.p95_target or 999999),
            max_error_rate_percent=float(args.max_error_rate or 100),
            min_throughput_rps=float(args.min_throughput)
            if args.min_throughput is not None
            else None,
        )
        # Keep the legacy behavior: if the operator set explicit targets, enforce them.
        enforce = True
    else:
        thresholds = profile_defaults.get(str(args.profile))

    if thresholds is not None:
        per_round = [evaluate_load_test_result(raw, thresholds) for raw in raw_results]
        evidence = (
            per_round[-1]
            if per_round
            else evaluate_load_test_result(raw_results[-1], thresholds)
        )
        evidence_payload["thresholds"] = {
            "max_p95_seconds": evidence.thresholds.max_p95_seconds,
            "max_error_rate_percent": evidence.thresholds.max_error_rate_percent,
            "min_throughput_rps": evidence.thresholds.min_throughput_rps,
        }
        evidence_payload["evaluation"] = {
            "rounds": [item.model_dump() for item in per_round],
            "overall_meets_targets": all(item.meets_targets for item in per_round)
            if per_round
            else None,
            "worst_p95_seconds": float(worst_p95),
            "min_throughput_rps": float(min_throughput),
        }
        evidence_payload["meets_targets"] = (
            all(item.meets_targets for item in per_round) if per_round else None
        )

    print(json.dumps(evidence_payload, indent=2, sort_keys=True))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(evidence_payload, f, indent=2, sort_keys=True)

    if args.publish:
        if not token:
            raise SystemExit("VALDRIX_TOKEN is required for --publish.")

        publish_url = f"{config.target_url}/api/v1/audit/performance/load-test/evidence"
        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            resp = await client.post(publish_url, json=evidence_payload)
        if resp.status_code >= 400:
            raise SystemExit(f"Publish failed ({resp.status_code}): {resp.text}")

    if thresholds is not None and enforce:
        meets = bool(evidence_payload.get("meets_targets"))
        if not meets:
            raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
