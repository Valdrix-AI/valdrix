"""
Security & Reliability Metrics for Valdrix

Defines custom Prometheus counters for monitoring security events
and remediation reliability.
"""

from prometheus_client import Counter

# Security Metrics
CSRF_ERRORS = Counter(
    "valdrix_security_csrf_errors_total",
    "Total number of CSRF validation failures",
[    "path", "method"]
)

RATE_LIMIT_EXCEEDED = Counter(
    "valdrix_security_rate_limit_exceeded_total",
    "Total number of requests blocked by rate limiting",
    ["path", "method", "tier"]
)

# Remediation Metrics
REMEDIATION_TOTAL = Counter(
    "valdrix_remediation_execution_total",
    "Total number of remediation actions executed",
    ["status", "resource_type", "action"]
)

# Authentication Metrics  
AUTH_FAILURES = Counter(
    "valdrix_security_auth_failures_total",
    "Total number of authentication failures",
    ["reason"]
)
