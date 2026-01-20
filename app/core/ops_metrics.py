"""
Operational & Performance Metrics for Valdrix

Defines Prometheus metrics for tracking system health, scale, and financial guards.
Used for investor-grade "Customer Health" dashboards.
"""

from prometheus_client import Counter, Histogram, Gauge

# --- Queue & Scheduling Metrics ---
BACKGROUND_JOBS_ENQUEUED = Counter(
    "valdrix_ops_jobs_enqueued_total",
    "Total number of background jobs enqueued",
    ["job_type", "priority"]
)

BACKGROUND_JOBS_PENDING = Gauge(
    "valdrix_ops_jobs_pending_count",
    "Current number of pending background jobs in the database",
    ["job_type"]
)

# --- Scan Performance Metrics ---
SCAN_LATENCY = Histogram(
    "valdrix_ops_scan_latency_seconds",
    "Latency of cloud resource scans",
    ["provider", "region"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600)
)

SCAN_TIMEOUTS = Counter(
    "valdrix_ops_scan_timeouts_total",
    "Total number of scan timeouts",
    ["level"] # 'plugin', 'region', 'overall'
)

# --- API & Remediation Metrics ---
API_ERRORS_TOTAL = Counter(
    "valdrix_ops_api_errors_total",
    "Total number of API errors by status code and path",
    ["path", "method", "status_code"]
)

REMEDIATION_DURATION_SECONDS = Histogram(
    "valdrix_ops_remediation_duration_seconds",
    "Duration of remediation execution in seconds",
    ["action", "provider"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600)
)

# --- LLM & Financial Metrics ---
LLM_SPEND_USD = Counter(
    "valdrix_ops_llm_spend_usd_total",
    "Total LLM spend tracked in USD",
    ["tenant_tier", "provider", "model"]
)

LLM_PRE_AUTH_DENIALS = Counter(
    "valdrix_ops_llm_pre_auth_denials_total",
    "Total number of LLM requests denied by financial guardrails",
    ["reason", "tenant_tier"]
)

# --- RLS & Security Ops ---
RLS_CONTEXT_MISSING = Counter(
    "valdrix_ops_rls_context_missing_total",
    "Total number of database queries executed without RLS context in request lifecycle",
    ["statement_type"]
)
