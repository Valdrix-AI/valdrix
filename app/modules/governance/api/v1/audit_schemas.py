from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

class AuditLogResponse(BaseModel):
    id: UUID
    event_type: str
    event_timestamp: datetime
    actor_email: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    success: bool
    correlation_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class LoadTestEvidenceResults(BaseModel):
    total_requests: int
    successful_requests: int
    failed_requests: int
    throughput_rps: float
    avg_response_time: float
    median_response_time: float
    p95_response_time: float
    p99_response_time: float
    min_response_time: float
    max_response_time: float
    errors_sample: list[str] = Field(default_factory=list)


class LoadTestEvidencePayload(BaseModel):
    profile: str = "custom"
    target_url: str
    endpoints: list[str] = Field(default_factory=list)
    duration_seconds: int
    concurrent_users: int
    ramp_up_seconds: int
    request_timeout: float
    results: LoadTestEvidenceResults
    # Optional soak/rounds metadata (v4 perf sign-off).
    rounds: int | None = None
    runs: list[dict[str, Any]] | None = None
    min_throughput_rps: float | None = None
    thresholds: dict[str, Any] | None = None
    evaluation: dict[str, Any] | None = None
    meets_targets: bool | None = None
    captured_at: str | None = None
    runner: str = "scripts/load_test_api.py"


class LoadTestEvidenceItem(BaseModel):
    event_id: str
    run_id: str | None
    captured_at: str
    actor_id: str | None
    actor_email: str | None
    success: bool
    load_test: LoadTestEvidencePayload


class LoadTestEvidenceListResponse(BaseModel):
    total: int
    items: list[LoadTestEvidenceItem]


class LoadTestEvidenceCaptureResponse(BaseModel):
    status: str
    event_id: str
    run_id: str
    captured_at: str
    load_test: LoadTestEvidencePayload


class PartitioningTableStatus(BaseModel):
    table: str
    exists: bool
    partitioned: bool | None = None
    partitions: list[str] = Field(default_factory=list)
    expected_partitions: list[str] = Field(default_factory=list)
    missing_partitions: list[str] = Field(default_factory=list)


class PartitioningEvidencePayload(BaseModel):
    dialect: str
    partitioning_supported: bool
    tables: list[PartitioningTableStatus] = Field(default_factory=list)
    captured_at: str | None = None
    runner: str = "api.v1.audit.partitioning"


class PartitioningEvidenceItem(BaseModel):
    event_id: str
    run_id: str | None
    captured_at: str
    actor_id: str | None
    actor_email: str | None
    success: bool
    partitioning: PartitioningEvidencePayload


class PartitioningEvidenceListResponse(BaseModel):
    total: int
    items: list[PartitioningEvidenceItem]


class PartitioningEvidenceCaptureResponse(BaseModel):
    status: str
    event_id: str
    run_id: str
    captured_at: str
    partitioning: PartitioningEvidencePayload


class IngestionPersistenceEvidencePayload(BaseModel):
    """
    Operator-captured ingestion persistence benchmark evidence.

    This is meant to validate the core write path at higher volumes (10x+)
    without requiring a full end-to-end ingestion run.
    """

    runner: str = "scripts/benchmark_ingestion_persistence.py"
    provider: str = "multi"
    account_id: str | None = None
    records_requested: int
    records_saved: int
    duration_seconds: float
    records_per_second: float
    services: int | None = None
    regions: int | None = None
    cleanup: bool = True
    started_at: str | None = None
    completed_at: str | None = None
    thresholds: dict[str, Any] | None = None
    meets_targets: bool | None = None


class IngestionSoakEvidenceJobRun(BaseModel):
    job_id: str
    status: str
    duration_seconds: float | None = None
    ingested_records: int | None = None
    error: str | None = None


class IngestionSoakEvidenceResults(BaseModel):
    jobs_total: int
    jobs_succeeded: int
    jobs_failed: int
    success_rate_percent: float
    avg_duration_seconds: float | None = None
    median_duration_seconds: float | None = None
    p95_duration_seconds: float | None = None
    p99_duration_seconds: float | None = None
    min_duration_seconds: float | None = None
    max_duration_seconds: float | None = None
    errors_sample: list[str] = Field(default_factory=list)


class IngestionSoakEvidencePayload(BaseModel):
    """
    Operator-captured end-to-end ingestion soak evidence.

    This complements the write-path benchmark by exercising the full job execution path
    (enqueue -> job processor -> adapter streaming -> persistence).
    """

    runner: str = "scripts/soak_ingestion_jobs.py"
    jobs_enqueued: int
    workers: int = 1
    batch_limit: int | None = None
    window: dict[str, Any] | None = None
    results: IngestionSoakEvidenceResults
    runs: list[IngestionSoakEvidenceJobRun] = Field(default_factory=list)
    thresholds: dict[str, Any] | None = None
    meets_targets: bool | None = None
    captured_at: str | None = None
    notes: str | dict[str, Any] | None = None


class IdentityIdpSmokeEvidenceCheck(BaseModel):
    name: str
    passed: bool
    status_code: int | None = None
    detail: str | None = None
    duration_ms: float | None = None


class IdentityIdpSmokeEvidencePayload(BaseModel):
    """
    Operator-captured IdP interoperability smoke test evidence.

    This is intended for enterprise onboarding sign-off (Okta/Entra/etc) and should never
    include secrets. Scripts should only publish boolean/metadata signals.
    """

    runner: str = "scripts/smoke_test_scim_idp.py"
    idp: str | None = None
    scim_base_url: str | None = None
    write_mode: bool = False
    passed: bool
    checks: list[IdentityIdpSmokeEvidenceCheck] = Field(default_factory=list)
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float | None = None
    notes: str | dict[str, Any] | None = None


class IdentityIdpSmokeEvidenceItem(BaseModel):
    event_id: str
    run_id: str | None
    captured_at: str
    actor_id: str | None
    actor_email: str | None
    success: bool
    identity_smoke: IdentityIdpSmokeEvidencePayload


class IdentityIdpSmokeEvidenceListResponse(BaseModel):
    total: int
    items: list[IdentityIdpSmokeEvidenceItem]


class IdentityIdpSmokeEvidenceCaptureResponse(BaseModel):
    status: str
    event_id: str
    run_id: str
    captured_at: str
    identity_smoke: IdentityIdpSmokeEvidencePayload


class SsoFederationValidationEvidencePayload(BaseModel):
    """
    Operator-captured SSO federation validation evidence.

    This should not include secrets. It captures deterministic config checks plus the
    computed callback/discovery URLs needed for Supabase SSO configuration.
    """

    runner: str = "scripts/smoke_test_sso_federation.py"
    passed: bool
    federation_mode: str | None = None
    frontend_url: str | None = None
    expected_redirect_url: str | None = None
    discovery_endpoint: str | None = None
    checks: list[IdentityIdpSmokeEvidenceCheck] = Field(default_factory=list)
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float | None = None
    notes: str | dict[str, Any] | None = None


class SsoFederationValidationEvidenceItem(BaseModel):
    event_id: str
    run_id: str | None
    captured_at: str
    actor_id: str | None
    actor_email: str | None
    success: bool
    sso_federation_validation: SsoFederationValidationEvidencePayload


class SsoFederationValidationEvidenceListResponse(BaseModel):
    total: int
    items: list[SsoFederationValidationEvidenceItem]


class SsoFederationValidationEvidenceCaptureResponse(BaseModel):
    status: str
    event_id: str
    run_id: str
    captured_at: str
    sso_federation_validation: SsoFederationValidationEvidencePayload


class JobSLOEvidenceCaptureRequest(BaseModel):
    window_hours: int = Field(default=24 * 7, ge=1, le=24 * 30)
    target_success_rate_percent: float = Field(default=95.0, ge=0.0, le=100.0)


class JobBacklogEvidenceSnapshot(BaseModel):
    captured_at: str
    pending: int
    running: int
    completed: int
    failed: int
    dead_letter: int
    oldest_pending_scheduled_for: str | None = None
    oldest_pending_age_seconds: float | None = None


class JobSLOMetricEvidence(BaseModel):
    job_type: str
    window_hours: int
    target_success_rate_percent: float
    total_jobs: int
    successful_jobs: int
    failed_jobs: int
    success_rate_percent: float
    meets_slo: bool
    latest_completed_at: str | None = None
    avg_duration_seconds: float | None = None
    p95_duration_seconds: float | None = None


class JobSLOEvidencePayload(BaseModel):
    window_hours: int
    target_success_rate_percent: float
    overall_meets_slo: bool
    metrics: list[JobSLOMetricEvidence] = Field(default_factory=list)
    backlog: JobBacklogEvidenceSnapshot


class JobSLOEvidenceItem(BaseModel):
    event_id: str
    run_id: str | None
    captured_at: str
    actor_id: str | None
    actor_email: str | None
    success: bool
    job_slo: JobSLOEvidencePayload


class JobSLOEvidenceListResponse(BaseModel):
    total: int
    items: list[JobSLOEvidenceItem]


class JobSLOEvidenceCaptureResponse(BaseModel):
    status: str
    event_id: str
    run_id: str
    captured_at: str
    job_slo: JobSLOEvidencePayload
    # Optional backfill/replay stress evidence (repeat ingestion over the same window).
    backfill_runs: int | None = None
    runs: list[dict[str, Any]] | None = None


class IngestionPersistenceEvidenceItem(BaseModel):
    event_id: str
    run_id: str | None
    captured_at: str
    actor_id: str | None
    actor_email: str | None
    success: bool
    benchmark: IngestionPersistenceEvidencePayload


class IngestionPersistenceEvidenceListResponse(BaseModel):
    total: int
    items: list[IngestionPersistenceEvidenceItem]


class IngestionSoakEvidenceItem(BaseModel):
    event_id: str
    run_id: str | None
    captured_at: str
    actor_id: str | None
    actor_email: str | None
    success: bool
    ingestion_soak: IngestionSoakEvidencePayload


class IngestionSoakEvidenceListResponse(BaseModel):
    total: int
    items: list[IngestionSoakEvidenceItem]


class IngestionSoakEvidenceCaptureResponse(BaseModel):
    status: str
    event_id: str
    run_id: str
    captured_at: str
    ingestion_soak: IngestionSoakEvidencePayload


class IngestionPersistenceEvidenceCaptureResponse(BaseModel):
    status: str
    event_id: str
    run_id: str
    captured_at: str
    benchmark: IngestionPersistenceEvidencePayload


class TenantIsolationEvidencePayload(BaseModel):
    """
    Operator-captured tenant isolation evidence.

    This is intentionally lightweight: it records what checks/tests were run
    and whether they passed, without persisting secrets or large artifacts.
    """

    runner: str = "scripts/verify_tenant_isolation.py"
    checks: list[str] = Field(default_factory=list)
    passed: bool
    pytest_exit_code: int | None = None
    duration_seconds: float | None = None
    git_sha: str | None = None
    captured_at: str | None = None
    notes: str | None = None
    stdout_snippet: str | None = None
    stderr_snippet: str | None = None


class TenantIsolationEvidenceItem(BaseModel):
    event_id: str
    run_id: str | None
    captured_at: str
    actor_id: str | None
    actor_email: str | None
    success: bool
    tenant_isolation: TenantIsolationEvidencePayload


class TenantIsolationEvidenceListResponse(BaseModel):
    total: int
    items: list[TenantIsolationEvidenceItem]


class TenantIsolationEvidenceCaptureResponse(BaseModel):
    status: str
    event_id: str
    run_id: str
    captured_at: str
    tenant_isolation: TenantIsolationEvidencePayload


class CarbonAssuranceEvidenceCaptureRequest(BaseModel):
    runner: str = "api"
    notes: str | None = None


class CarbonAssuranceEvidencePayload(BaseModel):
    runner: str
    notes: str | None = None
    captured_at: str
    snapshot: dict[str, Any]
    factor_set_id: str | None = None
    factor_set_status: str | None = None


class CarbonAssuranceEvidenceItem(BaseModel):
    event_id: str
    run_id: str | None
    captured_at: str
    actor_id: str | None
    actor_email: str | None
    success: bool
    carbon_assurance: CarbonAssuranceEvidencePayload


class CarbonAssuranceEvidenceListResponse(BaseModel):
    total: int
    items: list[CarbonAssuranceEvidenceItem]


class CarbonAssuranceEvidenceCaptureResponse(BaseModel):
    status: str
    event_id: str
    run_id: str
    captured_at: str
    carbon_assurance: CarbonAssuranceEvidencePayload


