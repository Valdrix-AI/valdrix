"""
Shared Prometheus Metrics for Scheduler Service
"""

from prometheus_client import Counter, Histogram

# Total scheduled job runs
SCHEDULER_JOB_RUNS = Counter(
    "valdrix_scheduler_job_runs_total",
    "Total number of scheduled job runs",
    ["job_name", "status"],
)

# Duration of scheduled jobs
SCHEDULER_JOB_DURATION = Histogram(
    "valdrix_scheduler_job_duration_seconds",
    "Duration of scheduled jobs in seconds",
    ["job_name"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600],
)

# Number of deadlocks detected (used in orchestrator_production)
SCHEDULER_DEADLOCK_DETECTED = Counter(
    "valdrix_scheduler_deadlock_detected_total",
    "Number of deadlocks detected",
    ["cohort"],
)

# Background jobs enqueued specifically by the scheduler
BACKGROUND_JOBS_ENQUEUED_SCHEDULER = Counter(
    "valdrix_scheduler_jobs_enqueued_total",
    "Background jobs enqueued by scheduler",
    ["job_type", "cohort"],
)
