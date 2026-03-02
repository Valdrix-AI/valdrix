"""
Enhanced Operational & Performance Metrics for Valdrics

Provides comprehensive Prometheus metrics for tracking system health, scale,
financial guards, and operational resilience.
Used for investor-grade "Customer Health" dashboards.
"""

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

from prometheus_client import Counter, Histogram, Gauge
import time

# --- Roadmap Compatibility Metrics ---
STUCK_JOB_COUNT = Gauge(
    "stuck_job_count", "Current number of jobs detected as stuck in scheduler sweeps"
)

LLM_BUDGET_BURN_RATE = Gauge(
    "llm_budget_burn_rate",
    "Average monthly LLM budget burn rate percentage across tenants",
)

RLS_ENFORCEMENT_LATENCY = Histogram(
    "rls_enforcement_latency",
    "Latency in seconds to apply RLS tenant context in DB session setup",
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1),
)

# --- Queue & Scheduling Metrics ---
BACKGROUND_JOBS_ENQUEUED = Counter(
    "valdrics_ops_jobs_enqueued_total",
    "Total number of background jobs enqueued",
    ["job_type", "priority"],
)

BACKGROUND_JOBS_PENDING = Gauge(
    "valdrics_ops_jobs_pending_count",
    "Current number of pending background jobs in the database",
    ["job_type"],
)

BACKGROUND_JOB_DURATION = Histogram(
    "valdrics_ops_job_duration_seconds",
    "Duration of background job execution",
    ["job_type", "status"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800),
)

# --- Scan Performance Metrics ---
SCAN_LATENCY = Histogram(
    "valdrics_ops_scan_latency_seconds",
    "Latency of cloud resource scans",
    ["provider", "region"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600),
)

SCAN_TIMEOUTS = Counter(
    "valdrics_ops_scan_timeouts_total",
    "Total number of scan timeouts",
    ["level", "provider"],  # 'plugin', 'region', 'overall'
)

SCAN_SUCCESS_TOTAL = Counter(
    "valdrics_ops_scan_success_total",
    "Total number of successful scans",
    ["provider", "region"],
)

SCAN_FAILURE_TOTAL = Counter(
    "valdrics_ops_scan_failure_total",
    "Total number of failed scans",
    ["provider", "region", "error_type"],
)

# --- Cloud API Cost Governance ---
CLOUD_API_CALLS_TOTAL = Counter(
    "valdrics_ops_cloud_api_calls_total",
    "Total expensive cloud API calls executed by the optimization engine",
    ["provider", "api"],
)

CLOUD_API_BUDGET_DECISIONS_TOTAL = Counter(
    "valdrics_ops_cloud_api_budget_decisions_total",
    "Budget-governor decisions for expensive cloud API calls",
    ["provider", "api", "decision"],  # allow | deny | would_deny
)

CLOUD_API_BUDGET_REMAINING = Gauge(
    "valdrics_ops_cloud_api_budget_remaining_calls",
    "Remaining expensive cloud API call budget for the current UTC day",
    ["provider", "api"],
)

CLOUD_API_ESTIMATED_COST_USD = Counter(
    "valdrics_ops_cloud_api_estimated_cost_usd_total",
    "Estimated cloud API cost exposure in USD from expensive telemetry calls",
    ["provider", "api"],
)

# --- API & Remediation Metrics ---
API_REQUESTS_TOTAL = Counter(
    "valdrics_ops_api_requests_total",
    "Total number of API requests",
    ["method", "endpoint", "status_code"],
)

API_REQUEST_DURATION = Histogram(
    "valdrics_ops_api_request_duration_seconds",
    "Duration of API requests",
    ["method", "endpoint"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30),
)

API_ERRORS_TOTAL = Counter(
    "valdrics_ops_api_errors_total",
    "Total number of API errors by status code and path",
    ["path", "method", "status_code"],
)

LANDING_TELEMETRY_EVENTS_TOTAL = Counter(
    "valdrics_ops_landing_telemetry_events_total",
    "Landing telemetry events received by event, section, and funnel stage",
    ["event_name", "section", "funnel_stage"],
)

LANDING_TELEMETRY_INGEST_OUTCOMES_TOTAL = Counter(
    "valdrics_ops_landing_telemetry_ingest_outcomes_total",
    "Landing telemetry ingestion outcomes",
    ["outcome"],  # accepted|rejected_timestamp
)

ENFORCEMENT_RESERVATION_RECONCILIATIONS_TOTAL = Counter(
    "valdrics_ops_enforcement_reservation_reconciliations_total",
    "Total reservation reconciliation actions in the enforcement control plane",
    ["trigger", "status"],  # trigger: manual|auto, status: matched|overage|savings|auto_release
)

ENFORCEMENT_RESERVATION_DRIFT_USD_TOTAL = Counter(
    "valdrics_ops_enforcement_reservation_drift_usd_total",
    "Absolute reservation reconciliation drift observed in USD",
    ["direction"],  # direction: overage|savings
)

ENFORCEMENT_APPROVAL_TOKEN_EVENTS_TOTAL = Counter(
    "valdrics_ops_enforcement_approval_token_events_total",
    "Approval token security events in enforcement workflow",
    ["event"],  # consumed, replay_detected, expired, and mismatch classifications
)

ENFORCEMENT_RECONCILIATION_SWEEP_RUNS_TOTAL = Counter(
    "valdrics_ops_enforcement_reconciliation_sweep_runs_total",
    "Scheduled enforcement reconciliation sweep runs by outcome",
    ["status"],  # success | failure | skipped_disabled
)

ENFORCEMENT_RECONCILIATION_ALERTS_TOTAL = Counter(
    "valdrics_ops_enforcement_reconciliation_alerts_total",
    "Enforcement reconciliation alerts emitted by alert type and severity",
    ["alert_type", "severity"],  # sla_release|drift_exception, warning|error
)

ENFORCEMENT_GATE_DECISIONS_TOTAL = Counter(
    "valdrics_ops_enforcement_gate_decisions_total",
    "Enforcement gate decisions by source, decision type, and evaluation path",
    ["source", "decision", "path"],  # path: normal|failsafe
)

ENFORCEMENT_GATE_DECISION_REASONS_TOTAL = Counter(
    "valdrics_ops_enforcement_gate_decision_reasons_total",
    "Enforcement gate decision reason-code distribution",
    ["source", "reason"],
)

ENFORCEMENT_GATE_LATENCY_SECONDS = Histogram(
    "valdrics_ops_enforcement_gate_latency_seconds",
    "End-to-end latency of enforcement gate evaluation",
    ["source", "path"],  # path: normal|failsafe
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)

ENFORCEMENT_GATE_FAILURES_TOTAL = Counter(
    "valdrics_ops_enforcement_gate_failures_total",
    "Enforcement gate failures before deterministic fail-safe fallback",
    ["source", "failure_type"],  # timeout|evaluation_error|lock_timeout|lock_contended
)

ENFORCEMENT_GATE_LOCK_EVENTS_TOTAL = Counter(
    "valdrics_ops_enforcement_gate_lock_events_total",
    "Enforcement gate serialization lock events by source and event",
    ["source", "event"],  # acquired|contended|timeout|not_acquired|error
)

ENFORCEMENT_GATE_LOCK_WAIT_SECONDS = Histogram(
    "valdrics_ops_enforcement_gate_lock_wait_seconds",
    "Wait time spent acquiring the enforcement gate serialization lock",
    ["source", "outcome"],  # acquired|timeout|error
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)

ENFORCEMENT_EXPORT_EVENTS_TOTAL = Counter(
    "valdrics_ops_enforcement_export_events_total",
    "Enforcement export events by artifact and outcome",
    ["artifact", "outcome"],  # parity|archive|bundle, success|mismatch|rejected_limit
)

ENFORCEMENT_APPROVAL_QUEUE_BACKLOG = Gauge(
    "valdrics_ops_enforcement_approval_queue_backlog",
    "Current number of pending approvals visible to the caller",
    ["viewer_role"],
)

TURNSTILE_VERIFICATION_EVENTS_TOTAL = Counter(
    "valdrics_ops_turnstile_verification_events_total",
    "Turnstile verification events by surface and outcome",
    ["surface", "outcome"],
)

REMEDIATION_DURATION_SECONDS = Histogram(
    "valdrics_ops_remediation_duration_seconds",
    "Duration of remediation execution in seconds",
    ["action", "provider"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600),
)

REMEDIATION_FAILURE = Counter(
    "valdrics_ops_remediation_failure_total",
    "Total number of remediation failures",
    ["action", "provider", "error_type"],
)

REMEDIATION_SUCCESS_TOTAL = Counter(
    "valdrics_ops_remediation_success_total",
    "Total number of successful remediations",
    ["action", "provider"],
)

# --- LLM & Financial Metrics ---
LLM_SPEND_USD = Counter(
    "valdrics_ops_llm_spend_usd_total",
    "Total LLM spend tracked in USD",
    ["tenant_tier", "provider", "model"],
)

LLM_PRE_AUTH_DENIALS = Counter(
    "valdrics_ops_llm_pre_auth_denials_total",
    "Total number of LLM requests denied by financial guardrails",
    ["reason", "tenant_tier"],
)

LLM_FAIR_USE_DENIALS = Counter(
    "valdrics_ops_llm_fair_use_denials_total",
    "Total number of LLM requests denied by fair-use throughput guardrails",
    ["gate", "tenant_tier"],
)

LLM_FAIR_USE_EVALUATIONS = Counter(
    "valdrics_ops_llm_fair_use_evaluations_total",
    "Total fair-use evaluations by gate and outcome",
    ["gate", "outcome", "tenant_tier"],
)

LLM_FAIR_USE_OBSERVED = Gauge(
    "valdrics_ops_llm_fair_use_observed",
    "Observed usage value at fair-use gate checks",
    ["gate", "tenant_tier"],
)

LLM_REQUEST_DURATION = Histogram(
    "valdrics_ops_llm_request_duration_seconds",
    "Duration of LLM API requests",
    ["provider", "model"],
    buckets=(0.5, 1, 2, 5, 10, 30, 60),
)

LLM_TOKENS_TOTAL = Counter(
    "valdrics_ops_llm_tokens_total",
    "Total number of LLM tokens processed",
    ["provider", "model", "token_type"],  # input, output
)

LLM_AUTH_ABUSE_SIGNALS = Counter(
    "valdrics_ops_llm_auth_abuse_signals_total",
    "Authenticated LLM abuse signals by actor type and client IP bucket",
    ["tenant_tier", "actor_type", "ip_bucket"],
)

LLM_AUTH_IP_RISK_SCORE = Gauge(
    "valdrics_ops_llm_auth_ip_risk_score",
    "Latest authenticated LLM client IP risk score by tier and actor",
    ["tenant_tier", "actor_type"],
)

# --- Circuit Breaker Metrics ---
CIRCUIT_BREAKER_STATE = Gauge(
    "valdrics_ops_circuit_breaker_state",
    "Current state of circuit breakers (0=closed, 1=open, 2=half_open)",
    ["circuit_name"],
)

CIRCUIT_BREAKER_FAILURES = Counter(
    "valdrics_ops_circuit_breaker_failures_total",
    "Total number of circuit breaker failures",
    ["circuit_name"],
)

CIRCUIT_BREAKER_RECOVERIES = Counter(
    "valdrics_ops_circuit_breaker_recoveries_total",
    "Total number of circuit breaker recoveries",
    ["circuit_name"],
)

# --- Retry & Resilience Metrics ---
OPERATION_RETRIES_TOTAL = Counter(
    "valdrics_ops_operation_retries_total",
    "Total number of operation retries",
    ["operation_type", "attempt"],
)

OPERATION_TIMEOUTS_TOTAL = Counter(
    "valdrics_ops_operation_timeouts_total",
    "Total number of operation timeouts",
    ["operation_type"],
)

# --- Database Metrics ---
DB_CONNECTIONS_ACTIVE = Gauge(
    "valdrics_ops_db_connections_active",
    "Current number of active database connections",
    ["pool_name"],
)

DB_CONNECTIONS_IDLE = Gauge(
    "valdrics_ops_db_connections_idle",
    "Current number of idle database connections",
    ["pool_name"],
)

DB_QUERY_DURATION = Histogram(
    "valdrics_ops_db_query_duration_seconds",
    "Duration of database queries",
    ["operation_type"],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, 5),
)

DB_DEADLOCKS_TOTAL = Counter(
    "valdrics_ops_db_deadlocks_total", "Total number of database deadlocks detected"
)

# --- Cache Metrics ---
CACHE_HITS_TOTAL = Counter(
    "valdrics_ops_cache_hits_total", "Total number of cache hits", ["cache_type"]
)

CACHE_MISSES_TOTAL = Counter(
    "valdrics_ops_cache_misses_total", "Total number of cache misses", ["cache_type"]
)

CACHE_ERRORS_TOTAL = Counter(
    "valdrics_ops_cache_errors_total",
    "Total number of cache errors",
    ["cache_type", "error_type"],
)

# --- RLS & Security Ops ---
RLS_CONTEXT_MISSING = Counter(
    "valdrics_ops_rls_context_missing_total",
    "Total number of database queries executed without RLS context in request lifecycle",
    ["statement_type"],
)

SECURITY_VIOLATIONS_TOTAL = Counter(
    "valdrics_ops_security_violations_total",
    "Total number of security violations detected",
    ["violation_type", "severity"],
)

# --- System Health Metrics ---
MEMORY_USAGE_BYTES = Gauge(
    "valdrics_ops_memory_usage_bytes", "Current memory usage in bytes", ["process"]
)

CPU_USAGE_PERCENT = Gauge(
    "valdrics_ops_cpu_usage_percent", "Current CPU usage percentage", ["process"]
)

# --- Business Metrics ---
TENANTS_ACTIVE = Gauge("valdrics_ops_tenants_active", "Current number of active tenants")

COST_SAVINGS_TOTAL = Counter(
    "valdrics_ops_cost_savings_total",
    "Total cost savings identified through optimization",
    ["provider", "optimization_type"],
)

ZOMBIES_DETECTED = Counter(
    "valdrics_ops_zombies_detected_total",
    "Total number of zombie resources detected",
    ["provider", "account_id", "resource_type"],
)

POTENTIAL_SAVINGS = Gauge(
    "valdrics_ops_potential_savings_monthly",
    "Estimated monthly savings from identified zombies",
    ["provider", "account_id"],
)


# Utility functions for metrics
F = TypeVar("F", bound=Callable[..., Any])


def time_operation(operation_name: str) -> Callable[[F], F]:
    """Decorator to time operations and record metrics."""

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time

                # Record success metrics
                if "db" in operation_name.lower():
                    DB_QUERY_DURATION.labels(operation_type=operation_name).observe(
                        duration
                    )
                elif "api" in operation_name.lower():
                    # API metrics are handled by middleware
                    pass
                elif "cache" in operation_name.lower():
                    # Cache metrics handled elsewhere
                    pass

                return result
            except Exception:
                duration = time.time() - start_time

                # Record error metrics
                if "db" in operation_name.lower():
                    DB_QUERY_DURATION.labels(
                        operation_type=f"{operation_name}_error"
                    ).observe(duration)

                raise

        return cast(F, wrapper)

    return decorator


def record_circuit_breaker_metrics(
    circuit_name: str, state: str, failures: int, successes: int
) -> None:
    """Record circuit breaker metrics."""
    # Map state to numeric value
    state_value = {"closed": 0, "open": 1, "half_open": 2}.get(state, 0)
    CIRCUIT_BREAKER_STATE.labels(circuit_name=circuit_name).set(state_value)

    if failures > 0:
        CIRCUIT_BREAKER_FAILURES.labels(circuit_name=circuit_name).inc(failures)

    if successes > 0:
        CIRCUIT_BREAKER_RECOVERIES.labels(circuit_name=circuit_name).inc(successes)


def record_retry_metrics(operation_type: str, attempt: int) -> None:
    """Record retry metrics."""
    OPERATION_RETRIES_TOTAL.labels(
        operation_type=operation_type, attempt=str(attempt)
    ).inc()


def record_timeout_metrics(operation_type: str) -> None:
    """Record timeout metrics."""
    OPERATION_TIMEOUTS_TOTAL.labels(operation_type=operation_type).inc()
