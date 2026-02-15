"""
Audit Log API Endpoints

Provides:
- GET /audit/logs - Paginated audit logs (admin-only)
"""

from typing import Annotated, Any, Optional, List, Literal, cast
from uuid import UUID
from datetime import datetime, timezone, timedelta, date, time
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, asc, text
from pydantic import BaseModel, ConfigDict, Field
import structlog

from app.shared.core.auth import CurrentUser, requires_role
from app.shared.core.dependencies import requires_feature
from app.shared.core.pricing import FeatureFlag
from app.shared.db.session import get_db
from app.modules.governance.domain.security.audit_log import AuditLog
from app.models.carbon_factors import CarbonFactorSet, CarbonFactorUpdateLog

logger = structlog.get_logger()
router = APIRouter(tags=["Audit"])


_CSV_FORMULA_PREFIXES = ("=", "+", "@", "\t")


def _sanitize_csv_cell(value: Any) -> str:
    """
    Prevent CSV formula injection when exported files are opened in spreadsheet tools.

    Note: we intentionally do NOT treat '-' as a formula prefix because negative values
    are valid and common in financial exports.
    """
    if value is None:
        return ""
    text = str(value)
    if not text:
        return ""
    if text.startswith(_CSV_FORMULA_PREFIXES):
        return "'" + text
    return text


def _rowcount(result: Any) -> int:
    raw_count = getattr(result, "rowcount", None)
    return raw_count if isinstance(raw_count, int) else 0


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
    provider: str = "aws"
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


@router.get("/logs", response_model=List[AuditLogResponse])
async def get_audit_logs(
    user: Annotated[
        CurrentUser,
        Depends(requires_feature(FeatureFlag.AUDIT_LOGS, required_role="admin")),
    ],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    sort_by: Literal["event_timestamp", "event_type", "actor_email"] = Query(
        "event_timestamp"
    ),
    order: Literal["asc", "desc"] = Query("desc"),
) -> list[AuditLogResponse]:
    """
    Get paginated audit logs for tenant.

    Admin-only. Sensitive details are masked by default.
    """
    try:
        if sort_by == "actor_email":
            raise HTTPException(
                status_code=400,
                detail="Sorting by actor_email is not supported for encrypted audit data.",
            )

        sort_column = getattr(AuditLog, sort_by)
        order_func = desc if order == "desc" else asc

        query = (
            select(AuditLog)
            .where(AuditLog.tenant_id == user.tenant_id)
            .order_by(order_func(sort_column))
        )

        if event_type:
            query = query.where(AuditLog.event_type == event_type)

        query = query.offset(offset).limit(limit)

        result = await db.execute(query)
        logs = result.scalars().all()

        return [
            AuditLogResponse(
                id=log.id,
                event_type=log.event_type,
                event_timestamp=log.event_timestamp,
                actor_email=log.actor_email,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                success=log.success,
                correlation_id=log.correlation_id,
            )
            for log in logs
        ]

    except HTTPException:
        raise
    except Exception as e:
        logger.error("audit_logs_fetch_failed", error=str(e))
        raise HTTPException(500, "Failed to fetch audit logs") from e


@router.get("/logs/{log_id}")
async def get_audit_log_detail(
    log_id: UUID,
    user: Annotated[
        CurrentUser,
        Depends(requires_feature(FeatureFlag.AUDIT_LOGS, required_role="admin")),
    ],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get single audit log entry with full details."""
    try:
        result = await db.execute(
            select(AuditLog).where(
                AuditLog.id == log_id, AuditLog.tenant_id == user.tenant_id
            )
        )
        log = result.scalar_one_or_none()

        if not log:
            raise HTTPException(404, "Audit log not found")

        return {
            "id": str(log.id),
            "event_type": log.event_type,
            "event_timestamp": log.event_timestamp.isoformat(),
            "actor_id": str(log.actor_id) if log.actor_id else None,
            "actor_email": log.actor_email,
            "actor_ip": log.actor_ip,
            "correlation_id": log.correlation_id,
            "request_method": log.request_method,
            "request_path": log.request_path,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "details": log.details,  # Already masked by AuditLogger
            "success": log.success,
            "error_message": log.error_message,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("audit_log_detail_failed", error=str(e))
        raise HTTPException(500, "Failed to fetch audit log") from e


@router.get("/event-types")
async def get_event_types(
    _: Annotated[
        CurrentUser,
        Depends(requires_feature(FeatureFlag.AUDIT_LOGS, required_role="admin")),
    ],
) -> dict[str, list[str]]:
    """Get list of available audit event types for filtering."""
    from app.modules.governance.domain.security.audit_log import AuditEventType

    return {"event_types": [e.value for e in AuditEventType]}


@router.post(
    "/performance/load-test/evidence", response_model=LoadTestEvidenceCaptureResponse
)
async def capture_load_test_evidence(
    payload: LoadTestEvidencePayload,
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
) -> LoadTestEvidenceCaptureResponse:
    """
    Persist a load-test evidence snapshot into the tenant audit log.

    Intended for operator-driven performance sign-off (procurement evidence).
    """
    from uuid import uuid4

    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLogger,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    run_id = str(uuid4())
    audit = AuditLogger(db=db, tenant_id=tenant_id, correlation_id=run_id)
    event = await audit.log(
        event_type=AuditEventType.PERFORMANCE_LOAD_TEST_CAPTURED,
        actor_id=user.id,
        actor_email=user.email,
        resource_type="load_test",
        resource_id=str(payload.profile or "custom"),
        details={
            "run_id": run_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "load_test": payload.model_dump(),
        },
        success=True,
        request_method="POST",
        request_path="/api/v1/audit/performance/load-test/evidence",
    )
    await db.commit()

    return LoadTestEvidenceCaptureResponse(
        status="captured",
        event_id=str(event.id),
        run_id=run_id,
        captured_at=event.event_timestamp.isoformat(),
        load_test=payload,
    )


@router.get(
    "/performance/load-test/evidence", response_model=LoadTestEvidenceListResponse
)
async def list_load_test_evidence(
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=2000),
) -> LoadTestEvidenceListResponse:
    """
    List persisted load-test evidence snapshots for this tenant (latest first).
    """
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLog,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .where(
            AuditLog.event_type == AuditEventType.PERFORMANCE_LOAD_TEST_CAPTURED.value
        )
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(limit))
    )
    rows = (await db.execute(stmt)).scalars().all()

    items: list[LoadTestEvidenceItem] = []
    for row in rows:
        details = row.details or {}
        raw = details.get("load_test")
        if not isinstance(raw, dict):
            continue
        try:
            load_test = LoadTestEvidencePayload.model_validate(raw)
        except Exception:
            logger.warning(
                "load_test_evidence_invalid_payload",
                event_id=str(row.id),
                tenant_id=str(tenant_id),
            )
            continue

        items.append(
            LoadTestEvidenceItem(
                event_id=str(row.id),
                run_id=row.correlation_id,
                captured_at=row.event_timestamp.isoformat(),
                actor_id=str(row.actor_id) if row.actor_id else None,
                actor_email=row.actor_email,
                success=bool(row.success),
                load_test=load_test,
            )
        )

    return LoadTestEvidenceListResponse(total=len(items), items=items)


async def _compute_partitioning_evidence(
    db: AsyncSession,
) -> PartitioningEvidencePayload:
    dialect = "unknown"
    if getattr(db, "bind", None) is not None:
        dialect = str(
            getattr(getattr(db.bind, "dialect", None), "name", "") or "unknown"
        )

    table_names: set[str] = set()
    try:
        if dialect == "sqlite":
            rows = (
                (
                    await db.execute(
                        text("SELECT name FROM sqlite_master WHERE type='table'")
                    )
                )
                .scalars()
                .all()
            )
            table_names = {str(row) for row in rows}
        elif dialect == "postgresql":
            rows = (
                (
                    await db.execute(
                        text(
                            "SELECT tablename FROM pg_tables WHERE schemaname = current_schema()"
                        )
                    )
                )
                .scalars()
                .all()
            )
            table_names = {str(row) for row in rows}
        else:
            rows = (
                (
                    await db.execute(
                        text(
                            "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()"
                        )
                    )
                )
                .scalars()
                .all()
            )
            table_names = {str(row) for row in rows}
    except Exception:
        table_names = set()

    tables_to_check = ["audit_logs", "cost_records"]
    statuses: list[PartitioningTableStatus] = []

    captured_at = datetime.now(timezone.utc).isoformat()
    if dialect != "postgresql":
        for table in tables_to_check:
            exists = table in table_names
            statuses.append(
                PartitioningTableStatus(
                    table=table,
                    exists=exists,
                    partitioned=False if exists else None,
                    partitions=[],
                )
            )
        return PartitioningEvidencePayload(
            dialect=dialect,
            partitioning_supported=False,
            tables=statuses,
            captured_at=captured_at,
        )

    for table in tables_to_check:
        exists = table in table_names
        if not exists:
            statuses.append(
                PartitioningTableStatus(
                    table=table, exists=False, partitioned=None, partitions=[]
                )
            )
            continue

        relkind = await db.scalar(
            text(
                """
                SELECT c.relkind
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = current_schema() AND c.relname = :table
                """
            ),
            {"table": table},
        )
        partitioned = str(relkind or "") == "p"
        partitions: list[str] = []
        if partitioned:
            rows = (
                await db.execute(
                    text(
                        """
                        SELECT child.relname
                        FROM pg_inherits
                        JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
                        JOIN pg_class child ON pg_inherits.inhrelid = child.oid
                        WHERE parent.relname = :table
                        ORDER BY child.relname ASC
                        """
                    ),
                    {"table": table},
                )
            ).all()
            partitions = [str(row[0]) for row in rows if row and row[0]]

        expected_partitions: list[str] = []
        missing_partitions: list[str] = []
        if partitioned:
            today = date.today()

            def _month_start(value: date, offset_months: int) -> date:
                base = (value.year * 12) + (value.month - 1) + int(offset_months)
                year = base // 12
                month = (base % 12) + 1
                return date(year, month, 1)

            # Validate that partitions exist for current month + a small future window.
            future_months = 3
            expected_partitions = [
                f"{table}_{_month_start(today, i).year}_{_month_start(today, i).month:02d}"
                for i in range(future_months + 1)
            ]
            partition_set = set(partitions)
            missing_partitions = [
                name for name in expected_partitions if name not in partition_set
            ]

        statuses.append(
            PartitioningTableStatus(
                table=table,
                exists=True,
                partitioned=partitioned,
                partitions=partitions,
                expected_partitions=expected_partitions,
                missing_partitions=missing_partitions,
            )
        )

    return PartitioningEvidencePayload(
        dialect=dialect,
        partitioning_supported=True,
        tables=statuses,
        captured_at=captured_at,
    )


@router.post(
    "/performance/partitioning/evidence",
    response_model=PartitioningEvidenceCaptureResponse,
)
async def capture_partitioning_evidence(
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
) -> PartitioningEvidenceCaptureResponse:
    """
    Capture a DB partitioning/retention readiness snapshot as audit evidence.

    Notes:
    - In SQLite/testing, this records that partitioning is not applicable.
    - In Postgres, this checks whether `audit_logs` / `cost_records` are partitioned and lists partitions.
    """
    from uuid import uuid4

    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLogger,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    payload = await _compute_partitioning_evidence(db)
    run_id = str(uuid4())
    audit = AuditLogger(db=db, tenant_id=tenant_id, correlation_id=run_id)
    event = await audit.log(
        event_type=AuditEventType.PERFORMANCE_PARTITIONING_CAPTURED,
        actor_id=user.id,
        actor_email=user.email,
        resource_type="partitioning",
        resource_id=str(payload.dialect),
        details={
            "run_id": run_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "partitioning": payload.model_dump(),
        },
        success=True,
        request_method="POST",
        request_path="/api/v1/audit/performance/partitioning/evidence",
    )
    await db.commit()

    return PartitioningEvidenceCaptureResponse(
        status="captured",
        event_id=str(event.id),
        run_id=run_id,
        captured_at=event.event_timestamp.isoformat(),
        partitioning=payload,
    )


@router.get(
    "/performance/partitioning/evidence",
    response_model=PartitioningEvidenceListResponse,
)
async def list_partitioning_evidence(
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=2000),
) -> PartitioningEvidenceListResponse:
    """
    List DB partitioning/retention readiness snapshots for this tenant (latest first).
    """
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLog,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .where(
            AuditLog.event_type
            == AuditEventType.PERFORMANCE_PARTITIONING_CAPTURED.value
        )
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(limit))
    )
    rows = (await db.execute(stmt)).scalars().all()

    items: list[PartitioningEvidenceItem] = []
    for row in rows:
        details = row.details or {}
        raw = details.get("partitioning")
        if not isinstance(raw, dict):
            continue
        try:
            partitioning = PartitioningEvidencePayload.model_validate(raw)
        except Exception:
            logger.warning(
                "partitioning_evidence_invalid_payload",
                event_id=str(row.id),
                tenant_id=str(tenant_id),
            )
            continue

        items.append(
            PartitioningEvidenceItem(
                event_id=str(row.id),
                run_id=row.correlation_id,
                captured_at=row.event_timestamp.isoformat(),
                actor_id=str(row.actor_id) if row.actor_id else None,
                actor_email=row.actor_email,
                success=bool(row.success),
                partitioning=partitioning,
            )
        )

    return PartitioningEvidenceListResponse(total=len(items), items=items)


@router.post(
    "/performance/ingestion/persistence/evidence",
    response_model=IngestionPersistenceEvidenceCaptureResponse,
)
async def capture_ingestion_persistence_evidence(
    payload: IngestionPersistenceEvidencePayload,
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
) -> IngestionPersistenceEvidenceCaptureResponse:
    """
    Persist ingestion persistence benchmark evidence into the tenant audit log.

    Intended for operator-driven performance sign-off (10x ingestion write-path proof).
    """
    from uuid import uuid4

    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLogger,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    run_id = str(uuid4())
    audit = AuditLogger(db=db, tenant_id=tenant_id, correlation_id=run_id)
    event = await audit.log(
        event_type=AuditEventType.PERFORMANCE_INGESTION_PERSISTENCE_CAPTURED,
        actor_id=user.id,
        actor_email=user.email,
        resource_type="ingestion_persistence",
        resource_id=str(payload.provider or "unknown"),
        details={
            "run_id": run_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "benchmark": payload.model_dump(),
        },
        success=bool(payload.meets_targets)
        if payload.meets_targets is not None
        else True,
        request_method="POST",
        request_path="/api/v1/audit/performance/ingestion/persistence/evidence",
    )
    await db.commit()

    return IngestionPersistenceEvidenceCaptureResponse(
        status="captured",
        event_id=str(event.id),
        run_id=run_id,
        captured_at=event.event_timestamp.isoformat(),
        benchmark=payload,
    )


@router.get(
    "/performance/ingestion/persistence/evidence",
    response_model=IngestionPersistenceEvidenceListResponse,
)
async def list_ingestion_persistence_evidence(
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=2000),
) -> IngestionPersistenceEvidenceListResponse:
    """
    List persisted ingestion benchmark evidence snapshots for this tenant (latest first).
    """
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLog,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .where(
            AuditLog.event_type
            == AuditEventType.PERFORMANCE_INGESTION_PERSISTENCE_CAPTURED.value
        )
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(limit))
    )
    rows = (await db.execute(stmt)).scalars().all()

    items: list[IngestionPersistenceEvidenceItem] = []
    for row in rows:
        details = row.details or {}
        raw = details.get("benchmark")
        if not isinstance(raw, dict):
            continue
        try:
            benchmark = IngestionPersistenceEvidencePayload.model_validate(raw)
        except Exception:
            logger.warning(
                "ingestion_persistence_evidence_invalid_payload",
                event_id=str(row.id),
                tenant_id=str(tenant_id),
            )
            continue

        items.append(
            IngestionPersistenceEvidenceItem(
                event_id=str(row.id),
                run_id=row.correlation_id,
                captured_at=row.event_timestamp.isoformat(),
                actor_id=str(row.actor_id) if row.actor_id else None,
                actor_email=row.actor_email,
                success=bool(row.success),
                benchmark=benchmark,
            )
        )

    return IngestionPersistenceEvidenceListResponse(total=len(items), items=items)


@router.post(
    "/performance/ingestion/soak/evidence",
    response_model=IngestionSoakEvidenceCaptureResponse,
)
async def capture_ingestion_soak_evidence(
    payload: IngestionSoakEvidencePayload,
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
) -> IngestionSoakEvidenceCaptureResponse:
    """
    Persist end-to-end ingestion soak evidence into the tenant audit log.

    Intended for operator-driven performance + reliability sign-off ("10x ingestion" readiness).
    """
    from uuid import uuid4

    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLogger,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    run_id = str(uuid4())
    audit = AuditLogger(db=db, tenant_id=tenant_id, correlation_id=run_id)
    success = (
        bool(payload.meets_targets)
        if payload.meets_targets is not None
        else bool(payload.results.jobs_failed == 0)
    )
    event = await audit.log(
        event_type=AuditEventType.PERFORMANCE_INGESTION_SOAK_CAPTURED,
        actor_id=user.id,
        actor_email=user.email,
        resource_type="ingestion_soak",
        resource_id=str(payload.jobs_enqueued),
        details={
            "run_id": run_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "ingestion_soak": payload.model_dump(),
        },
        success=success,
        request_method="POST",
        request_path="/api/v1/audit/performance/ingestion/soak/evidence",
    )
    await db.commit()

    return IngestionSoakEvidenceCaptureResponse(
        status="captured",
        event_id=str(event.id),
        run_id=run_id,
        captured_at=event.event_timestamp.isoformat(),
        ingestion_soak=payload,
    )


@router.get(
    "/performance/ingestion/soak/evidence",
    response_model=IngestionSoakEvidenceListResponse,
)
async def list_ingestion_soak_evidence(
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=2000),
) -> IngestionSoakEvidenceListResponse:
    """List persisted ingestion soak evidence snapshots for this tenant (latest first)."""
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLog,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .where(
            AuditLog.event_type
            == AuditEventType.PERFORMANCE_INGESTION_SOAK_CAPTURED.value
        )
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(limit))
    )
    rows = (await db.execute(stmt)).scalars().all()

    items: list[IngestionSoakEvidenceItem] = []
    for row in rows:
        details = row.details or {}
        raw = details.get("ingestion_soak")
        if not isinstance(raw, dict):
            continue
        try:
            evidence = IngestionSoakEvidencePayload.model_validate(raw)
        except Exception:
            logger.warning(
                "ingestion_soak_evidence_invalid_payload",
                event_id=str(row.id),
                tenant_id=str(tenant_id),
            )
            continue

        items.append(
            IngestionSoakEvidenceItem(
                event_id=str(row.id),
                run_id=row.correlation_id,
                captured_at=row.event_timestamp.isoformat(),
                actor_id=str(row.actor_id) if row.actor_id else None,
                actor_email=row.actor_email,
                success=bool(row.success),
                ingestion_soak=evidence,
            )
        )

    return IngestionSoakEvidenceListResponse(total=len(items), items=items)


@router.post(
    "/identity/idp-smoke/evidence",
    response_model=IdentityIdpSmokeEvidenceCaptureResponse,
)
async def capture_identity_idp_smoke_evidence(
    payload: IdentityIdpSmokeEvidencePayload,
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
) -> IdentityIdpSmokeEvidenceCaptureResponse:
    """
    Persist IdP interoperability smoke-test evidence into the tenant audit log.

    This endpoint is meant to store operator-run evidence (Okta/Entra/etc) without transmitting secrets.
    """
    from uuid import uuid4

    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLogger,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    run_id = str(uuid4())
    audit = AuditLogger(db=db, tenant_id=tenant_id, correlation_id=run_id)
    event = await audit.log(
        event_type=AuditEventType.IDENTITY_IDP_SMOKE_CAPTURED,
        actor_id=user.id,
        actor_email=user.email,
        resource_type="identity_idp_smoke",
        resource_id=str(payload.idp or ""),
        details={
            "run_id": run_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "identity_smoke": payload.model_dump(),
        },
        success=bool(payload.passed),
        request_method="POST",
        request_path="/api/v1/audit/identity/idp-smoke/evidence",
    )
    await db.commit()

    return IdentityIdpSmokeEvidenceCaptureResponse(
        status="captured",
        event_id=str(event.id),
        run_id=run_id,
        captured_at=event.event_timestamp.isoformat(),
        identity_smoke=payload,
    )


@router.get(
    "/identity/idp-smoke/evidence",
    response_model=IdentityIdpSmokeEvidenceListResponse,
)
async def list_identity_idp_smoke_evidence(
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=2000),
) -> IdentityIdpSmokeEvidenceListResponse:
    """List persisted IdP interoperability smoke-test evidence snapshots (latest first)."""
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLog,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .where(AuditLog.event_type == AuditEventType.IDENTITY_IDP_SMOKE_CAPTURED.value)
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(limit))
    )
    rows = (await db.execute(stmt)).scalars().all()

    items: list[IdentityIdpSmokeEvidenceItem] = []
    for row in rows:
        details = row.details or {}
        raw = details.get("identity_smoke")
        if not isinstance(raw, dict):
            continue
        try:
            evidence = IdentityIdpSmokeEvidencePayload.model_validate(raw)
        except Exception:
            logger.warning(
                "identity_idp_smoke_evidence_invalid_payload",
                event_id=str(row.id),
                tenant_id=str(tenant_id),
            )
            continue

        items.append(
            IdentityIdpSmokeEvidenceItem(
                event_id=str(row.id),
                run_id=row.correlation_id,
                captured_at=row.event_timestamp.isoformat(),
                actor_id=str(row.actor_id) if row.actor_id else None,
                actor_email=row.actor_email,
                success=bool(row.success),
                identity_smoke=evidence,
            )
        )

    return IdentityIdpSmokeEvidenceListResponse(total=len(items), items=items)


@router.post(
    "/identity/sso-federation/evidence",
    response_model=SsoFederationValidationEvidenceCaptureResponse,
)
async def capture_sso_federation_validation_evidence(
    payload: SsoFederationValidationEvidencePayload,
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
) -> SsoFederationValidationEvidenceCaptureResponse:
    """
    Persist SSO federation validation evidence into the tenant audit log.

    This stores operator-run configuration validation (no secrets) to support onboarding/procurement sign-off.
    """
    from uuid import uuid4

    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLogger,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    run_id = str(uuid4())
    audit = AuditLogger(db=db, tenant_id=tenant_id, correlation_id=run_id)
    event = await audit.log(
        event_type=AuditEventType.IDENTITY_SSO_FEDERATION_VALIDATION_CAPTURED,
        actor_id=user.id,
        actor_email=user.email,
        resource_type="identity_sso_federation_validation",
        resource_id=str(payload.federation_mode or ""),
        details={
            "run_id": run_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "sso_federation_validation": payload.model_dump(),
        },
        success=bool(payload.passed),
        request_method="POST",
        request_path="/api/v1/audit/identity/sso-federation/evidence",
    )
    await db.commit()

    return SsoFederationValidationEvidenceCaptureResponse(
        status="captured",
        event_id=str(event.id),
        run_id=run_id,
        captured_at=event.event_timestamp.isoformat(),
        sso_federation_validation=payload,
    )


@router.get(
    "/identity/sso-federation/evidence",
    response_model=SsoFederationValidationEvidenceListResponse,
)
async def list_sso_federation_validation_evidence(
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=2000),
) -> SsoFederationValidationEvidenceListResponse:
    """List persisted SSO federation validation evidence snapshots (latest first)."""
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLog,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .where(
            AuditLog.event_type
            == AuditEventType.IDENTITY_SSO_FEDERATION_VALIDATION_CAPTURED.value
        )
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(limit))
    )
    rows = (await db.execute(stmt)).scalars().all()

    items: list[SsoFederationValidationEvidenceItem] = []
    for row in rows:
        details = row.details or {}
        raw = details.get("sso_federation_validation")
        if not isinstance(raw, dict):
            continue
        try:
            evidence = SsoFederationValidationEvidencePayload.model_validate(raw)
        except Exception:
            logger.warning(
                "sso_federation_validation_evidence_invalid_payload",
                event_id=str(row.id),
                tenant_id=str(tenant_id),
            )
            continue

        items.append(
            SsoFederationValidationEvidenceItem(
                event_id=str(row.id),
                run_id=row.correlation_id,
                captured_at=row.event_timestamp.isoformat(),
                actor_id=str(row.actor_id) if row.actor_id else None,
                actor_email=row.actor_email,
                success=bool(row.success),
                sso_federation_validation=evidence,
            )
        )

    return SsoFederationValidationEvidenceListResponse(total=len(items), items=items)


@router.post("/jobs/slo/evidence", response_model=JobSLOEvidenceCaptureResponse)
async def capture_job_slo_evidence(
    payload: JobSLOEvidenceCaptureRequest,
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
) -> JobSLOEvidenceCaptureResponse:
    """
    Persist job reliability + backlog evidence into the tenant audit log.

    This is computed server-side (audit-grade) and intended for availability/reliability sign-off.
    """
    from uuid import uuid4

    from app.modules.governance.domain.jobs.metrics import (
        compute_job_backlog_snapshot,
        compute_job_slo,
    )
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLogger,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    run_id = str(uuid4())
    computed_slo = await compute_job_slo(
        db,
        tenant_id=tenant_id,
        window_hours=int(payload.window_hours),
        target_success_rate_percent=float(payload.target_success_rate_percent),
    )
    backlog = await compute_job_backlog_snapshot(db, tenant_id=tenant_id)
    computed_payload = {
        **computed_slo,
        "backlog": backlog,
    }
    evidence = JobSLOEvidencePayload.model_validate(computed_payload)

    audit = AuditLogger(db=db, tenant_id=tenant_id, correlation_id=run_id)
    event = await audit.log(
        event_type=AuditEventType.JOBS_SLO_CAPTURED,
        actor_id=user.id,
        actor_email=user.email,
        resource_type="jobs",
        resource_id=f"{payload.window_hours}h",
        details={
            "run_id": run_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "job_slo": evidence.model_dump(),
        },
        success=bool(evidence.overall_meets_slo),
        request_method="POST",
        request_path="/api/v1/audit/jobs/slo/evidence",
    )
    await db.commit()

    return JobSLOEvidenceCaptureResponse(
        status="captured",
        event_id=str(event.id),
        run_id=run_id,
        captured_at=event.event_timestamp.isoformat(),
        job_slo=evidence,
    )


@router.get("/jobs/slo/evidence", response_model=JobSLOEvidenceListResponse)
async def list_job_slo_evidence(
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=2000),
) -> JobSLOEvidenceListResponse:
    """List persisted job SLO evidence snapshots for this tenant (latest first)."""
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLog,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .where(AuditLog.event_type == AuditEventType.JOBS_SLO_CAPTURED.value)
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(limit))
    )
    rows = (await db.execute(stmt)).scalars().all()

    items: list[JobSLOEvidenceItem] = []
    for row in rows:
        details = row.details or {}
        raw = details.get("job_slo")
        if not isinstance(raw, dict):
            continue
        try:
            job_slo = JobSLOEvidencePayload.model_validate(raw)
        except Exception:
            logger.warning(
                "job_slo_evidence_invalid_payload",
                event_id=str(row.id),
                tenant_id=str(tenant_id),
            )
            continue

        items.append(
            JobSLOEvidenceItem(
                event_id=str(row.id),
                run_id=row.correlation_id,
                captured_at=row.event_timestamp.isoformat(),
                actor_id=str(row.actor_id) if row.actor_id else None,
                actor_email=row.actor_email,
                success=bool(row.success),
                job_slo=job_slo,
            )
        )

    return JobSLOEvidenceListResponse(total=len(items), items=items)


@router.post(
    "/tenancy/isolation/evidence", response_model=TenantIsolationEvidenceCaptureResponse
)
async def capture_tenant_isolation_evidence(
    payload: TenantIsolationEvidencePayload,
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
) -> TenantIsolationEvidenceCaptureResponse:
    """
    Persist a tenant isolation verification evidence snapshot into the tenant audit log.

    Intended for enterprise procurement/security reviews.
    """
    from uuid import uuid4

    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLogger,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    run_id = str(uuid4())
    audit = AuditLogger(db=db, tenant_id=tenant_id, correlation_id=run_id)
    event = await audit.log(
        event_type=AuditEventType.TENANCY_ISOLATION_VERIFICATION_CAPTURED,
        actor_id=user.id,
        actor_email=user.email,
        resource_type="tenancy",
        resource_id="tenant_isolation_verification",
        details={
            "run_id": run_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "tenant_isolation": payload.model_dump(),
        },
        success=bool(payload.passed),
        request_method="POST",
        request_path="/api/v1/audit/tenancy/isolation/evidence",
    )
    await db.commit()

    return TenantIsolationEvidenceCaptureResponse(
        status="captured",
        event_id=str(event.id),
        run_id=run_id,
        captured_at=event.event_timestamp.isoformat(),
        tenant_isolation=payload,
    )


@router.get(
    "/tenancy/isolation/evidence", response_model=TenantIsolationEvidenceListResponse
)
async def list_tenant_isolation_evidence(
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=2000),
) -> TenantIsolationEvidenceListResponse:
    """List persisted tenant isolation evidence snapshots for this tenant (latest first)."""
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLog,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .where(
            AuditLog.event_type
            == AuditEventType.TENANCY_ISOLATION_VERIFICATION_CAPTURED.value
        )
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(limit))
    )
    rows = (await db.execute(stmt)).scalars().all()

    items: list[TenantIsolationEvidenceItem] = []
    for row in rows:
        details = row.details or {}
        raw = details.get("tenant_isolation")
        if not isinstance(raw, dict):
            continue
        try:
            tenant_isolation = TenantIsolationEvidencePayload.model_validate(raw)
        except Exception:
            logger.warning(
                "tenant_isolation_evidence_invalid_payload",
                event_id=str(row.id),
                tenant_id=str(tenant_id),
            )
            continue

        items.append(
            TenantIsolationEvidenceItem(
                event_id=str(row.id),
                run_id=row.correlation_id,
                captured_at=row.event_timestamp.isoformat(),
                actor_id=str(row.actor_id) if row.actor_id else None,
                actor_email=row.actor_email,
                success=bool(row.success),
                tenant_isolation=tenant_isolation,
            )
        )

    return TenantIsolationEvidenceListResponse(total=len(items), items=items)


@router.post(
    "/carbon/assurance/evidence", response_model=CarbonAssuranceEvidenceCaptureResponse
)
async def capture_carbon_assurance_evidence(
    request: CarbonAssuranceEvidenceCaptureRequest,
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
) -> CarbonAssuranceEvidenceCaptureResponse:
    """Capture an auditable carbon methodology + factor snapshot into the tenant audit log."""
    from uuid import uuid4

    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLogger,
    )
    from app.modules.reporting.domain.carbon_factors import CarbonFactorService
    from app.modules.reporting.domain.calculator import carbon_assurance_snapshot

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    run_id = str(uuid4())
    active_factor_set_id: str | None = None
    active_factor_set_status: str | None = None
    factor_payload: dict[str, Any] | None = None
    try:
        factor_service = CarbonFactorService(db)
        active_factor_set = await factor_service.ensure_active()
        factor_payload = await factor_service.get_active_payload()
        active_factor_set_id = str(active_factor_set.id)
        active_factor_set_status = str(active_factor_set.status)
    except Exception as exc:  # noqa: BLE001
        # We still capture evidence using static calculator payload if factor-set
        # infrastructure is temporarily unavailable.
        logger.warning(
            "carbon_assurance_factor_payload_fallback",
            tenant_id=str(tenant_id),
            error=str(exc),
        )

    snapshot = carbon_assurance_snapshot(factor_payload)
    payload = CarbonAssuranceEvidencePayload(
        runner=str(request.runner or "api"),
        notes=str(request.notes) if request.notes else None,
        captured_at=datetime.now(timezone.utc).isoformat(),
        snapshot=snapshot,
        factor_set_id=active_factor_set_id,
        factor_set_status=active_factor_set_status,
    )

    audit = AuditLogger(db=db, tenant_id=tenant_id, correlation_id=run_id)
    event = await audit.log(
        event_type=AuditEventType.CARBON_ASSURANCE_SNAPSHOT_CAPTURED,
        actor_id=user.id,
        actor_email=user.email,
        resource_type="carbon",
        resource_id="carbon_assurance_snapshot",
        details={
            "run_id": run_id,
            "captured_at": payload.captured_at,
            "carbon_assurance": payload.model_dump(),
        },
        success=True,
        request_method="POST",
        request_path="/api/v1/audit/carbon/assurance/evidence",
    )
    await db.commit()

    return CarbonAssuranceEvidenceCaptureResponse(
        status="captured",
        event_id=str(event.id),
        run_id=run_id,
        captured_at=event.event_timestamp.isoformat(),
        carbon_assurance=payload,
    )


@router.get(
    "/carbon/assurance/evidence", response_model=CarbonAssuranceEvidenceListResponse
)
async def list_carbon_assurance_evidence(
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=2000),
) -> CarbonAssuranceEvidenceListResponse:
    """List persisted carbon assurance evidence snapshots for this tenant (latest first)."""
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLog,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .where(
            AuditLog.event_type
            == AuditEventType.CARBON_ASSURANCE_SNAPSHOT_CAPTURED.value
        )
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(limit))
    )
    rows = (await db.execute(stmt)).scalars().all()

    items: list[CarbonAssuranceEvidenceItem] = []
    for row in rows:
        details = row.details or {}
        raw = details.get("carbon_assurance")
        if not isinstance(raw, dict):
            continue
        try:
            carbon_assurance = CarbonAssuranceEvidencePayload.model_validate(raw)
        except Exception:
            logger.warning(
                "carbon_assurance_evidence_invalid_payload",
                event_id=str(row.id),
                tenant_id=str(tenant_id),
            )
            continue

        items.append(
            CarbonAssuranceEvidenceItem(
                event_id=str(row.id),
                run_id=row.correlation_id,
                captured_at=row.event_timestamp.isoformat(),
                actor_id=str(row.actor_id) if row.actor_id else None,
                actor_email=row.actor_email,
                success=bool(row.success),
                carbon_assurance=carbon_assurance,
            )
        )

    return CarbonAssuranceEvidenceListResponse(total=len(items), items=items)


@router.get("/export")
async def export_audit_logs(
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
    start_date: Optional[datetime] = Query(None, description="Start of date range"),
    end_date: Optional[datetime] = Query(None, description="End of date range"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
) -> Any:
    """
    Export audit logs as CSV for the tenant.
    GDPR/SOC2: Provides audit trail export for compliance.
    """
    from fastapi.responses import StreamingResponse
    import csv
    import io

    try:
        query = (
            select(AuditLog)
            .where(AuditLog.tenant_id == user.tenant_id)
            .order_by(desc(AuditLog.event_timestamp))
        )

        if start_date:
            query = query.where(AuditLog.event_timestamp >= start_date)
        if end_date:
            query = query.where(AuditLog.event_timestamp <= end_date)
        if event_type:
            query = query.where(AuditLog.event_type == event_type)

        # Limit export to 10,000 records for performance
        query = query.limit(10000)

        result = await db.execute(query)
        logs = result.scalars().all()

        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "id",
                "event_type",
                "event_timestamp",
                "actor_email",
                "resource_type",
                "resource_id",
                "success",
                "correlation_id",
            ]
        )

        for log in logs:
            writer.writerow(
                [
                    str(log.id),
                    _sanitize_csv_cell(log.event_type),
                    _sanitize_csv_cell(log.event_timestamp.isoformat()),
                    _sanitize_csv_cell(log.actor_email or ""),
                    _sanitize_csv_cell(log.resource_type or ""),
                    _sanitize_csv_cell(str(log.resource_id) if log.resource_id else ""),
                    _sanitize_csv_cell(str(log.success)),
                    _sanitize_csv_cell(log.correlation_id or ""),
                ]
            )

        output.seek(0)

        logger.info(
            "audit_logs_exported", tenant_id=str(user.tenant_id), record_count=len(logs)
        )

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=audit_logs_{user.tenant_id}.csv"
            },
        )

    except Exception as e:
        logger.error("audit_export_failed", error=str(e))
        raise HTTPException(500, "Failed to export audit logs") from e


@router.get("/compliance-pack")
async def export_compliance_pack(
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="owner")
        ),
    ],
    db: AsyncSession = Depends(get_db),
    start_date: Optional[datetime] = Query(
        None, description="Start of date range (UTC)"
    ),
    end_date: Optional[datetime] = Query(None, description="End of date range (UTC)"),
    evidence_limit: int = Query(
        200, ge=1, le=2000, description="Max integration evidence records"
    ),
    include_focus_export: bool = Query(
        default=False,
        description="Include a bounded FOCUS v1.3 core cost export CSV inside the compliance pack.",
    ),
    focus_provider: Optional[str] = Query(
        default=None,
        description="Optional provider filter for the bundled FOCUS export (aws|azure|gcp|saas|license|platform|hybrid).",
    ),
    focus_include_preliminary: bool = Query(
        default=False,
        description="Include PRELIMINARY cost records in the bundled FOCUS export (otherwise FINAL only).",
    ),
    focus_max_rows: int = Query(
        default=50000,
        ge=1,
        le=200000,
        description="Maximum number of cost rows to include in the bundled FOCUS export (prevents huge ZIPs).",
    ),
    focus_start_date: Optional[date] = Query(
        default=None,
        description="FOCUS export start date (YYYY-MM-DD). Defaults to last 30 days.",
    ),
    focus_end_date: Optional[date] = Query(
        default=None,
        description="FOCUS export end date (YYYY-MM-DD). Defaults to today.",
    ),
    include_savings_proof: bool = Query(
        default=False,
        description="Include a Savings Proof report (JSON + CSV) inside the compliance pack.",
    ),
    savings_provider: Optional[str] = Query(
        default=None,
        description="Optional provider filter for the bundled Savings Proof report (aws|azure|gcp|saas|license|platform|hybrid).",
    ),
    savings_start_date: Optional[date] = Query(
        default=None,
        description="Savings Proof start date (YYYY-MM-DD). Defaults to last 30 days.",
    ),
    savings_end_date: Optional[date] = Query(
        default=None,
        description="Savings Proof end date (YYYY-MM-DD). Defaults to today.",
    ),
    include_realized_savings: bool = Query(
        default=False,
        description="Include realized savings evidence (JSON + CSV) inside the compliance pack.",
    ),
    realized_provider: Optional[str] = Query(
        default=None,
        description="Optional provider filter for realized savings evidence (aws|azure|gcp|saas|license|platform|hybrid).",
    ),
    realized_start_date: Optional[date] = Query(
        default=None,
        description="Realized savings window start date (YYYY-MM-DD). Defaults to savings_start_date if provided, otherwise last 30 days.",
    ),
    realized_end_date: Optional[date] = Query(
        default=None,
        description="Realized savings window end date (YYYY-MM-DD). Defaults to savings_end_date if provided, otherwise today.",
    ),
    realized_limit: int = Query(
        default=5000,
        ge=1,
        le=200000,
        description="Maximum number of realized savings evidence rows included (prevents huge ZIPs).",
    ),
    include_close_package: bool = Query(
        default=False,
        description="Include a reconciliation close package (JSON + CSV) inside the compliance pack.",
    ),
    close_provider: Optional[str] = Query(
        default=None,
        description="Optional provider filter for the bundled close package (aws|azure|gcp|saas|license|platform|hybrid).",
    ),
    close_start_date: Optional[date] = Query(
        default=None,
        description="Close package start date (YYYY-MM-DD). Defaults to last 30 days.",
    ),
    close_end_date: Optional[date] = Query(
        default=None,
        description="Close package end date (YYYY-MM-DD). Defaults to today.",
    ),
    close_enforce_finalized: bool = Query(
        default=True,
        description="If true, fail close package generation when PRELIMINARY data exists in the period.",
    ),
    close_max_restatements: int = Query(
        default=5000,
        ge=0,
        le=200000,
        description="Maximum number of restatement entries included in the close package details (0 includes none).",
    ),
) -> Any:
    """
    Export a compliance evidence bundle (ZIP) for the tenant.

    Intended for enterprise reviews: includes audit logs export plus key tenant-scoped
    configuration snapshots, without leaking secrets/tokens.
    """
    from fastapi.responses import Response
    import csv
    import io
    import json
    import zipfile
    from pathlib import Path
    from uuid import uuid4

    from sqlalchemy import desc, select

    from app.models.notification_settings import NotificationSettings
    from app.models.remediation_settings import RemediationSettings
    from app.models.tenant_identity_settings import TenantIdentitySettings
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLogger,
    )
    from app.shared.core.config import get_settings

    exported_at = datetime.now(timezone.utc)
    run_id = str(uuid4())

    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")

    # Record the export request (SOC2 evidence: export access is auditable).
    try:
        audit_logger = AuditLogger(
            db, cast(UUID, user.tenant_id), correlation_id=run_id
        )
        await audit_logger.log(
            event_type=AuditEventType.EXPORT_REQUESTED,
            actor_id=user.id,
            actor_email=user.email,
            request_method="GET",
            request_path="/api/v1/audit/compliance-pack",
            details={
                "export_type": "compliance_pack",
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "evidence_limit": int(evidence_limit),
            },
            success=True,
        )
        # Commit early so the export request is persisted even if bundle generation fails.
        await db.commit()
    except Exception as exc:
        logger.warning("compliance_pack_audit_log_failed", error=str(exc))
        await db.rollback()

    # --- Snapshot tenant-scoped settings (secrets/tokens redacted) ---
    notif = (
        await db.execute(
            select(NotificationSettings).where(
                NotificationSettings.tenant_id == user.tenant_id
            )
        )
    ).scalar_one_or_none()
    notif_snapshot: dict[str, Any] = {
        "exists": bool(notif),
        "slack_enabled": bool(getattr(notif, "slack_enabled", True)) if notif else True,
        "slack_channel_override": getattr(notif, "slack_channel_override", None)
        if notif
        else None,
        "jira_enabled": bool(getattr(notif, "jira_enabled", False)) if notif else False,
        "jira_base_url": getattr(notif, "jira_base_url", None) if notif else None,
        "jira_email": getattr(notif, "jira_email", None) if notif else None,
        "jira_project_key": getattr(notif, "jira_project_key", None) if notif else None,
        "jira_issue_type": (getattr(notif, "jira_issue_type", None) or "Task")
        if notif
        else "Task",
        "has_jira_api_token": bool(getattr(notif, "jira_api_token", None))
        if notif
        else False,
        "teams_enabled": bool(getattr(notif, "teams_enabled", False))
        if notif
        else False,
        "has_teams_webhook_url": bool(getattr(notif, "teams_webhook_url", None))
        if notif
        else False,
        "workflow_github_enabled": bool(
            getattr(notif, "workflow_github_enabled", False)
        )
        if notif
        else False,
        "workflow_github_owner": getattr(notif, "workflow_github_owner", None)
        if notif
        else None,
        "workflow_github_repo": getattr(notif, "workflow_github_repo", None)
        if notif
        else None,
        "workflow_github_workflow_id": getattr(
            notif, "workflow_github_workflow_id", None
        )
        if notif
        else None,
        "workflow_github_ref": (getattr(notif, "workflow_github_ref", None) or "main")
        if notif
        else "main",
        "workflow_has_github_token": bool(getattr(notif, "workflow_github_token", None))
        if notif
        else False,
        "workflow_gitlab_enabled": bool(
            getattr(notif, "workflow_gitlab_enabled", False)
        )
        if notif
        else False,
        "workflow_gitlab_base_url": (
            getattr(notif, "workflow_gitlab_base_url", None) or "https://gitlab.com"
        )
        if notif
        else "https://gitlab.com",
        "workflow_gitlab_project_id": getattr(notif, "workflow_gitlab_project_id", None)
        if notif
        else None,
        "workflow_gitlab_ref": (getattr(notif, "workflow_gitlab_ref", None) or "main")
        if notif
        else "main",
        "workflow_has_gitlab_trigger_token": bool(
            getattr(notif, "workflow_gitlab_trigger_token", None)
        )
        if notif
        else False,
        "workflow_webhook_enabled": bool(
            getattr(notif, "workflow_webhook_enabled", False)
        )
        if notif
        else False,
        "workflow_webhook_url": getattr(notif, "workflow_webhook_url", None)
        if notif
        else None,
        "workflow_has_webhook_bearer_token": bool(
            getattr(notif, "workflow_webhook_bearer_token", None)
        )
        if notif
        else False,
        "digest_schedule": getattr(notif, "digest_schedule", "daily")
        if notif
        else "daily",
        "digest_hour": int(getattr(notif, "digest_hour", 9)) if notif else 9,
        "digest_minute": int(getattr(notif, "digest_minute", 0)) if notif else 0,
        "alert_on_budget_warning": bool(getattr(notif, "alert_on_budget_warning", True))
        if notif
        else True,
        "alert_on_budget_exceeded": bool(
            getattr(notif, "alert_on_budget_exceeded", True)
        )
        if notif
        else True,
        "alert_on_zombie_detected": bool(
            getattr(notif, "alert_on_zombie_detected", True)
        )
        if notif
        else True,
    }

    remediation_settings = (
        await db.execute(
            select(RemediationSettings).where(
                RemediationSettings.tenant_id == user.tenant_id
            )
        )
    ).scalar_one_or_none()
    remediation_snapshot: dict[str, Any] = {
        "exists": bool(remediation_settings),
        "auto_pilot_enabled": bool(
            getattr(remediation_settings, "auto_pilot_enabled", False)
        )
        if remediation_settings
        else False,
        "simulation_mode": bool(getattr(remediation_settings, "simulation_mode", True))
        if remediation_settings
        else True,
        "min_confidence_threshold": float(
            getattr(remediation_settings, "min_confidence_threshold", 0.95)
        )
        if remediation_settings
        else 0.95,
        "max_deletions_per_hour": int(
            getattr(remediation_settings, "max_deletions_per_hour", 10)
        )
        if remediation_settings
        else 10,
        "hard_cap_enabled": bool(
            getattr(remediation_settings, "hard_cap_enabled", False)
        )
        if remediation_settings
        else False,
        "monthly_hard_cap_usd": float(
            getattr(remediation_settings, "monthly_hard_cap_usd", 0.0)
        )
        if remediation_settings
        else 0.0,
        "policy_enabled": bool(getattr(remediation_settings, "policy_enabled", True))
        if remediation_settings
        else True,
        "policy_block_production_destructive": bool(
            getattr(remediation_settings, "policy_block_production_destructive", True)
        )
        if remediation_settings
        else True,
        "policy_require_gpu_override": bool(
            getattr(remediation_settings, "policy_require_gpu_override", True)
        )
        if remediation_settings
        else True,
        "policy_low_confidence_warn_threshold": float(
            getattr(remediation_settings, "policy_low_confidence_warn_threshold", 0.90)
        )
        if remediation_settings
        else 0.90,
        "policy_violation_notify_slack": bool(
            getattr(remediation_settings, "policy_violation_notify_slack", True)
        )
        if remediation_settings
        else True,
        "policy_violation_notify_jira": bool(
            getattr(remediation_settings, "policy_violation_notify_jira", False)
        )
        if remediation_settings
        else False,
        "policy_escalation_required_role": str(
            getattr(remediation_settings, "policy_escalation_required_role", "owner")
        )
        if remediation_settings
        else "owner",
    }

    identity_settings = (
        await db.execute(
            select(TenantIdentitySettings).where(
                TenantIdentitySettings.tenant_id == user.tenant_id
            )
        )
    ).scalar_one_or_none()
    identity_snapshot: dict[str, Any] = {
        "exists": bool(identity_settings),
        "sso_enabled": bool(getattr(identity_settings, "sso_enabled", False))
        if identity_settings
        else False,
        "allowed_email_domains": list(
            getattr(identity_settings, "allowed_email_domains", []) or []
        )
        if identity_settings
        else [],
        "scim_enabled": bool(getattr(identity_settings, "scim_enabled", False))
        if identity_settings
        else False,
        "has_scim_token": bool(getattr(identity_settings, "scim_bearer_token", None))
        if identity_settings
        else False,
        "scim_last_rotated_at": identity_settings.scim_last_rotated_at.isoformat()
        if identity_settings and identity_settings.scim_last_rotated_at
        else None,
        "scim_group_mappings": list(
            getattr(identity_settings, "scim_group_mappings", []) or []
        )
        if identity_settings
        else [],
    }

    # --- Integration acceptance evidence (audit-grade) ---
    accepted_event_types = [
        AuditEventType.INTEGRATION_TEST_SLACK.value,
        AuditEventType.INTEGRATION_TEST_JIRA.value,
        AuditEventType.INTEGRATION_TEST_TEAMS.value,
        AuditEventType.INTEGRATION_TEST_WORKFLOW.value,
        AuditEventType.INTEGRATION_TEST_SUITE.value,
    ]
    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == user.tenant_id)
        .where(AuditLog.event_type.in_(accepted_event_types))
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(evidence_limit))
    )
    evidence_rows = (await db.execute(stmt)).scalars().all()
    integration_evidence = [
        {
            "event_id": str(row.id),
            "run_id": row.correlation_id,
            "event_type": row.event_type,
            "timestamp": row.event_timestamp.isoformat(),
            "success": bool(row.success),
            "channel": str(
                (row.details or {}).get("channel", row.resource_id or "unknown")
            ),
            "status_code": (row.details or {}).get("status_code"),
            "message": (row.details or {}).get("result_message", row.error_message),
        }
        for row in evidence_rows
    ]

    # --- Acceptance KPI evidence snapshots (audit-grade) ---
    acceptance_stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == user.tenant_id)
        .where(AuditLog.event_type == AuditEventType.ACCEPTANCE_KPIS_CAPTURED.value)
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(evidence_limit))
    )
    acceptance_rows = (await db.execute(acceptance_stmt)).scalars().all()
    acceptance_kpi_evidence: list[dict[str, Any]] = []
    for row in acceptance_rows:
        details = row.details or {}
        acceptance_payload = details.get("acceptance_kpis")
        if not isinstance(acceptance_payload, dict):
            continue
        acceptance_kpi_evidence.append(
            {
                "event_id": str(row.id),
                "run_id": row.correlation_id,
                "timestamp": row.event_timestamp.isoformat(),
                "success": bool(row.success),
                "actor_email": row.actor_email,
                "thresholds": details.get("thresholds", {}),
                "acceptance_kpis": acceptance_payload,
            }
        )

    # --- Leadership KPI evidence snapshots (audit-grade) ---
    leadership_stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == user.tenant_id)
        .where(AuditLog.event_type == AuditEventType.LEADERSHIP_KPIS_CAPTURED.value)
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(evidence_limit))
    )
    leadership_rows = (await db.execute(leadership_stmt)).scalars().all()
    leadership_kpi_evidence: list[dict[str, Any]] = []
    for row in leadership_rows:
        details = row.details or {}
        leadership_payload = details.get("leadership_kpis")
        if not isinstance(leadership_payload, dict):
            continue
        leadership_kpi_evidence.append(
            {
                "event_id": str(row.id),
                "run_id": row.correlation_id,
                "timestamp": row.event_timestamp.isoformat(),
                "success": bool(row.success),
                "actor_email": row.actor_email,
                "thresholds": details.get("thresholds", {}),
                "leadership_kpis": leadership_payload,
            }
        )

    # --- Quarterly commercial proof report evidence snapshots (audit-grade) ---
    quarterly_stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == user.tenant_id)
        .where(
            AuditLog.event_type
            == AuditEventType.COMMERCIAL_QUARTERLY_REPORT_CAPTURED.value
        )
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(evidence_limit))
    )
    quarterly_rows = (await db.execute(quarterly_stmt)).scalars().all()
    quarterly_commercial_proof_evidence: list[dict[str, Any]] = []
    for row in quarterly_rows:
        details = row.details or {}
        report_payload = details.get("quarterly_report")
        if not isinstance(report_payload, dict):
            continue
        quarterly_commercial_proof_evidence.append(
            {
                "event_id": str(row.id),
                "run_id": row.correlation_id,
                "timestamp": row.event_timestamp.isoformat(),
                "success": bool(row.success),
                "actor_email": row.actor_email,
                "thresholds": details.get("thresholds", {}),
                "quarterly_report": report_payload,
            }
        )

    # --- Identity IdP smoke-test evidence snapshots (audit-grade) ---
    identity_smoke_stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == user.tenant_id)
        .where(AuditLog.event_type == AuditEventType.IDENTITY_IDP_SMOKE_CAPTURED.value)
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(evidence_limit))
    )
    identity_smoke_rows = (await db.execute(identity_smoke_stmt)).scalars().all()
    identity_smoke_evidence: list[dict[str, Any]] = []
    for row in identity_smoke_rows:
        details = row.details or {}
        smoke_payload = details.get("identity_smoke")
        if not isinstance(smoke_payload, dict):
            continue
        identity_smoke_evidence.append(
            {
                "event_id": str(row.id),
                "run_id": row.correlation_id,
                "timestamp": row.event_timestamp.isoformat(),
                "success": bool(row.success),
                "actor_email": row.actor_email,
                "identity_smoke": smoke_payload,
            }
        )

    # --- SSO federation validation evidence snapshots (audit-grade) ---
    sso_validation_stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == user.tenant_id)
        .where(
            AuditLog.event_type
            == AuditEventType.IDENTITY_SSO_FEDERATION_VALIDATION_CAPTURED.value
        )
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(evidence_limit))
    )
    sso_validation_rows = (await db.execute(sso_validation_stmt)).scalars().all()
    sso_federation_validation_evidence: list[dict[str, Any]] = []
    for row in sso_validation_rows:
        details = row.details or {}
        validation_payload = details.get("sso_federation_validation")
        if not isinstance(validation_payload, dict):
            continue
        sso_federation_validation_evidence.append(
            {
                "event_id": str(row.id),
                "run_id": row.correlation_id,
                "timestamp": row.event_timestamp.isoformat(),
                "success": bool(row.success),
                "actor_email": row.actor_email,
                "sso_federation_validation": validation_payload,
            }
        )

    # --- Performance load-test evidence snapshots (audit-grade) ---
    perf_stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == user.tenant_id)
        .where(
            AuditLog.event_type == AuditEventType.PERFORMANCE_LOAD_TEST_CAPTURED.value
        )
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(evidence_limit))
    )
    perf_rows = (await db.execute(perf_stmt)).scalars().all()
    performance_load_test_evidence: list[dict[str, Any]] = []
    for row in perf_rows:
        details = row.details or {}
        perf_payload = details.get("load_test")
        if not isinstance(perf_payload, dict):
            continue
        performance_load_test_evidence.append(
            {
                "event_id": str(row.id),
                "run_id": row.correlation_id,
                "timestamp": row.event_timestamp.isoformat(),
                "success": bool(row.success),
                "actor_email": row.actor_email,
                "load_test": perf_payload,
            }
        )

    # --- Ingestion persistence benchmark evidence snapshots (audit-grade) ---
    ingest_stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == user.tenant_id)
        .where(
            AuditLog.event_type
            == AuditEventType.PERFORMANCE_INGESTION_PERSISTENCE_CAPTURED.value
        )
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(evidence_limit))
    )
    ingest_rows = (await db.execute(ingest_stmt)).scalars().all()
    ingestion_persistence_benchmark_evidence: list[dict[str, Any]] = []
    for row in ingest_rows:
        details = row.details or {}
        bench_payload = details.get("benchmark")
        if not isinstance(bench_payload, dict):
            continue
        ingestion_persistence_benchmark_evidence.append(
            {
                "event_id": str(row.id),
                "run_id": row.correlation_id,
                "timestamp": row.event_timestamp.isoformat(),
                "success": bool(row.success),
                "actor_email": row.actor_email,
                "benchmark": bench_payload,
            }
        )

    # --- Ingestion soak evidence snapshots (audit-grade) ---
    soak_stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == user.tenant_id)
        .where(
            AuditLog.event_type
            == AuditEventType.PERFORMANCE_INGESTION_SOAK_CAPTURED.value
        )
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(evidence_limit))
    )
    soak_rows = (await db.execute(soak_stmt)).scalars().all()
    ingestion_soak_evidence: list[dict[str, Any]] = []
    for row in soak_rows:
        details = row.details or {}
        soak_payload = details.get("ingestion_soak")
        if not isinstance(soak_payload, dict):
            continue
        ingestion_soak_evidence.append(
            {
                "event_id": str(row.id),
                "run_id": row.correlation_id,
                "timestamp": row.event_timestamp.isoformat(),
                "success": bool(row.success),
                "actor_email": row.actor_email,
                "ingestion_soak": soak_payload,
            }
        )

    # --- Partitioning validation evidence snapshots (audit-grade) ---
    partition_stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == user.tenant_id)
        .where(
            AuditLog.event_type
            == AuditEventType.PERFORMANCE_PARTITIONING_CAPTURED.value
        )
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(evidence_limit))
    )
    partition_rows = (await db.execute(partition_stmt)).scalars().all()
    partitioning_evidence: list[dict[str, Any]] = []
    for row in partition_rows:
        details = row.details or {}
        partition_payload = details.get("partitioning")
        if not isinstance(partition_payload, dict):
            continue
        partitioning_evidence.append(
            {
                "event_id": str(row.id),
                "run_id": row.correlation_id,
                "timestamp": row.event_timestamp.isoformat(),
                "success": bool(row.success),
                "actor_email": row.actor_email,
                "partitioning": partition_payload,
            }
        )

    # --- Job SLO + backlog evidence snapshots (audit-grade) ---
    job_slo_stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == user.tenant_id)
        .where(AuditLog.event_type == AuditEventType.JOBS_SLO_CAPTURED.value)
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(evidence_limit))
    )
    job_slo_rows = (await db.execute(job_slo_stmt)).scalars().all()
    job_slo_evidence: list[dict[str, Any]] = []
    for row in job_slo_rows:
        details = row.details or {}
        job_slo_payload = details.get("job_slo")
        if not isinstance(job_slo_payload, dict):
            continue
        job_slo_evidence.append(
            {
                "event_id": str(row.id),
                "run_id": row.correlation_id,
                "timestamp": row.event_timestamp.isoformat(),
                "success": bool(row.success),
                "actor_email": row.actor_email,
                "job_slo": job_slo_payload,
            }
        )

    # --- Tenancy isolation verification evidence snapshots (audit-grade) ---
    tenancy_stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == user.tenant_id)
        .where(
            AuditLog.event_type
            == AuditEventType.TENANCY_ISOLATION_VERIFICATION_CAPTURED.value
        )
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(evidence_limit))
    )
    tenancy_rows = (await db.execute(tenancy_stmt)).scalars().all()
    tenant_isolation_evidence: list[dict[str, Any]] = []
    for row in tenancy_rows:
        details = row.details or {}
        tenant_payload = details.get("tenant_isolation")
        if not isinstance(tenant_payload, dict):
            continue
        tenant_isolation_evidence.append(
            {
                "event_id": str(row.id),
                "run_id": row.correlation_id,
                "timestamp": row.event_timestamp.isoformat(),
                "success": bool(row.success),
                "actor_email": row.actor_email,
                "tenant_isolation": tenant_payload,
            }
        )

    # --- Carbon assurance evidence snapshots (audit-grade) ---
    carbon_stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == user.tenant_id)
        .where(
            AuditLog.event_type
            == AuditEventType.CARBON_ASSURANCE_SNAPSHOT_CAPTURED.value
        )
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(evidence_limit))
    )
    carbon_rows = (await db.execute(carbon_stmt)).scalars().all()
    carbon_assurance_evidence: list[dict[str, Any]] = []
    for row in carbon_rows:
        details = row.details or {}
        carbon_payload = details.get("carbon_assurance")
        if not isinstance(carbon_payload, dict):
            continue
        carbon_assurance_evidence.append(
            {
                "event_id": str(row.id),
                "run_id": row.correlation_id,
                "timestamp": row.event_timestamp.isoformat(),
                "success": bool(row.success),
                "actor_email": row.actor_email,
                "carbon_assurance": carbon_payload,
            }
        )

    # --- Carbon factor lifecycle evidence (global, non-tenant data) ---
    factor_set_rows = (
        (
            await db.execute(
                select(CarbonFactorSet)
                .order_by(desc(CarbonFactorSet.created_at))
                .limit(int(evidence_limit))
            )
        )
        .scalars()
        .all()
    )
    carbon_factor_sets: list[dict[str, Any]] = []
    for factor_set_row in factor_set_rows:
        carbon_factor_sets.append(
            {
                "id": str(factor_set_row.id),
                "status": str(factor_set_row.status),
                "is_active": bool(factor_set_row.is_active),
                "factor_source": str(factor_set_row.factor_source),
                "factor_version": str(factor_set_row.factor_version),
                "factor_timestamp": factor_set_row.factor_timestamp.isoformat(),
                "methodology_version": str(factor_set_row.methodology_version),
                "factors_checksum_sha256": str(factor_set_row.factors_checksum_sha256),
                "created_at": factor_set_row.created_at.isoformat(),
                "activated_at": factor_set_row.activated_at.isoformat()
                if factor_set_row.activated_at
                else None,
                "deactivated_at": factor_set_row.deactivated_at.isoformat()
                if factor_set_row.deactivated_at
                else None,
                "created_by_user_id": str(factor_set_row.created_by_user_id)
                if factor_set_row.created_by_user_id
                else None,
                "payload": factor_set_row.payload
                if isinstance(factor_set_row.payload, dict)
                else {},
            }
        )

    factor_update_rows = (
        (
            await db.execute(
                select(CarbonFactorUpdateLog)
                .order_by(desc(CarbonFactorUpdateLog.recorded_at))
                .limit(int(evidence_limit))
            )
        )
        .scalars()
        .all()
    )
    carbon_factor_update_logs: list[dict[str, Any]] = []
    for factor_update_row in factor_update_rows:
        carbon_factor_update_logs.append(
            {
                "id": str(factor_update_row.id),
                "recorded_at": factor_update_row.recorded_at.isoformat(),
                "action": str(factor_update_row.action),
                "message": factor_update_row.message,
                "old_factor_set_id": str(factor_update_row.old_factor_set_id)
                if factor_update_row.old_factor_set_id
                else None,
                "new_factor_set_id": str(factor_update_row.new_factor_set_id)
                if factor_update_row.new_factor_set_id
                else None,
                "old_checksum_sha256": factor_update_row.old_checksum_sha256,
                "new_checksum_sha256": factor_update_row.new_checksum_sha256,
                "details": factor_update_row.details
                if isinstance(factor_update_row.details, dict)
                else {},
                "actor_user_id": str(factor_update_row.actor_user_id)
                if factor_update_row.actor_user_id
                else None,
            }
        )

    # --- Audit logs CSV export ---
    audit_query = (
        select(AuditLog)
        .where(AuditLog.tenant_id == user.tenant_id)
        .order_by(desc(AuditLog.event_timestamp))
    )
    if start_date:
        audit_query = audit_query.where(AuditLog.event_timestamp >= start_date)
    if end_date:
        audit_query = audit_query.where(AuditLog.event_timestamp <= end_date)
    audit_query = audit_query.limit(10000)
    audit_rows = (await db.execute(audit_query)).scalars().all()

    audit_csv = io.StringIO()
    writer = csv.writer(audit_csv)
    writer.writerow(
        [
            "id",
            "event_type",
            "event_timestamp",
            "actor_email",
            "resource_type",
            "resource_id",
            "success",
            "correlation_id",
        ]
    )
    for row in audit_rows:
        writer.writerow(
            [
                str(row.id),
                _sanitize_csv_cell(row.event_type),
                _sanitize_csv_cell(row.event_timestamp.isoformat()),
                _sanitize_csv_cell(row.actor_email or ""),
                _sanitize_csv_cell(row.resource_type or ""),
                _sanitize_csv_cell(str(row.resource_id) if row.resource_id else ""),
                _sanitize_csv_cell(str(row.success)),
                _sanitize_csv_cell(row.correlation_id or ""),
            ]
        )
    audit_csv.seek(0)

    app_settings = get_settings()

    def _project_root() -> Path:
        """
        Best-effort project root discovery.

        Compliance pack exports should not depend on the current working directory,
        especially in containerized deployments.
        """
        here = Path(__file__).resolve()
        for candidate in (here, *here.parents):
            if (candidate / "pyproject.toml").is_file():
                return candidate
        return Path.cwd()

    def _read_doc(rel_path: str) -> str | None:
        try:
            return (_project_root() / rel_path).read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            logger.warning(
                "compliance_pack_doc_read_failed", path=rel_path, error=str(exc)
            )
            return None

    scim_doc = _read_doc("docs/integrations/scim.md")
    idp_reference_doc = _read_doc("docs/integrations/idp_reference_configs.md")
    sso_doc = _read_doc("docs/integrations/sso.md")
    teams_doc = _read_doc("docs/integrations/microsoft_teams.md")
    compliance_pack_doc = _read_doc("docs/compliance/compliance_pack.md")
    focus_doc = _read_doc("docs/compliance/focus_export.md")
    acceptance_doc = _read_doc("docs/ops/acceptance_evidence_capture.md")
    close_runbook_doc = _read_doc("docs/runbooks/month_end_close.md")
    tenant_lifecycle_doc = _read_doc("docs/runbooks/tenant_data_lifecycle.md")
    partition_maintenance_doc = _read_doc("docs/runbooks/partition_maintenance.md")
    licensing_doc = _read_doc("docs/licensing.md")
    license_text = _read_doc("LICENSE")
    trademark_policy_doc = _read_doc("TRADEMARK_POLICY.md")
    commercial_license_doc = _read_doc("COMMERCIAL_LICENSE.md")

    included_files: list[str] = [
        "audit_logs.csv",
        "notification_settings.json",
        "remediation_settings.json",
        "identity_settings.json",
        "integration_acceptance_evidence.json",
        "acceptance_kpis_evidence.json",
        "leadership_kpis_evidence.json",
        "quarterly_commercial_proof_evidence.json",
        "identity_smoke_evidence.json",
        "sso_federation_validation_evidence.json",
        "performance_load_test_evidence.json",
        "ingestion_persistence_benchmark_evidence.json",
        "ingestion_soak_evidence.json",
        "partitioning_evidence.json",
        "job_slo_evidence.json",
        "tenant_isolation_evidence.json",
        "carbon_assurance_evidence.json",
        "carbon_factor_sets.json",
        "carbon_factor_update_logs.json",
    ]
    focus_export_info: dict[str, Any] = {
        "included": bool(include_focus_export),
        "provider": None,
        "include_preliminary": bool(focus_include_preliminary),
        "max_rows": int(focus_max_rows),
        "rows_written": 0,
        "truncated": False,
        "window": {
            "start_date": None,
            "end_date": None,
        },
        "status": "skipped" if not include_focus_export else "pending",
        "error": None,
    }
    savings_proof_info: dict[str, Any] = {
        "included": bool(include_savings_proof),
        "provider": None,
        "window": {
            "start_date": None,
            "end_date": None,
        },
        "status": "skipped" if not include_savings_proof else "pending",
        "error": None,
    }
    realized_savings_info: dict[str, Any] = {
        "included": bool(include_realized_savings),
        "provider": None,
        "limit": int(realized_limit),
        "window": {
            "start_date": None,
            "end_date": None,
        },
        "status": "skipped" if not include_realized_savings else "pending",
        "error": None,
        "rows_written": 0,
    }
    close_package_info: dict[str, Any] = {
        "included": bool(include_close_package),
        "provider": None,
        "enforce_finalized": bool(close_enforce_finalized),
        "max_restatements": int(close_max_restatements),
        "window": {
            "start_date": None,
            "end_date": None,
        },
        "status": "skipped" if not include_close_package else "pending",
        "error": None,
    }

    if scim_doc is not None:
        included_files.append("docs/integrations/scim.md")
    if idp_reference_doc is not None:
        included_files.append("docs/integrations/idp_reference_configs.md")
    if sso_doc is not None:
        included_files.append("docs/integrations/sso.md")
    if teams_doc is not None:
        included_files.append("docs/integrations/microsoft_teams.md")
    if compliance_pack_doc is not None:
        included_files.append("docs/compliance/compliance_pack.md")
    if focus_doc is not None:
        included_files.append("docs/compliance/focus_export.md")
    if acceptance_doc is not None:
        included_files.append("docs/ops/acceptance_evidence_capture.md")
    if close_runbook_doc is not None:
        included_files.append("docs/runbooks/month_end_close.md")
    if tenant_lifecycle_doc is not None:
        included_files.append("docs/runbooks/tenant_data_lifecycle.md")
    if partition_maintenance_doc is not None:
        included_files.append("docs/runbooks/partition_maintenance.md")
    if licensing_doc is not None:
        included_files.append("docs/licensing.md")
    if license_text is not None:
        included_files.append("LICENSE")
    if trademark_policy_doc is not None:
        included_files.append("TRADEMARK_POLICY.md")
    if commercial_license_doc is not None:
        included_files.append("COMMERCIAL_LICENSE.md")

    _focus_supported_providers = {
        "aws",
        "azure",
        "gcp",
        "saas",
        "license",
        "platform",
        "hybrid",
    }
    normalized_focus_provider: str | None = None
    if focus_provider is not None:
        candidate = focus_provider.strip().lower()
        if not candidate:
            normalized_focus_provider = None
        elif candidate not in _focus_supported_providers:
            supported = ", ".join(sorted(_focus_supported_providers))
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported focus_provider '{focus_provider}'. Use one of: {supported}",
            )
        else:
            normalized_focus_provider = candidate
    focus_export_info["provider"] = normalized_focus_provider

    focus_window_start = (
        focus_start_date or (start_date or (exported_at - timedelta(days=30))).date()
    )
    focus_window_end = focus_end_date or (end_date or exported_at).date()
    if focus_window_start > focus_window_end:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")
    focus_export_info["window"] = {
        "start_date": focus_window_start.isoformat(),
        "end_date": focus_window_end.isoformat(),
    }

    # Savings Proof window/provider validation
    _savings_supported_providers = {
        "aws",
        "azure",
        "gcp",
        "saas",
        "license",
        "platform",
        "hybrid",
    }
    normalized_savings_provider: str | None = None
    if savings_provider is not None:
        candidate = savings_provider.strip().lower()
        if not candidate:
            normalized_savings_provider = None
        elif candidate not in _savings_supported_providers:
            supported = ", ".join(sorted(_savings_supported_providers))
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported savings_provider '{savings_provider}'. Use one of: {supported}",
            )
        else:
            normalized_savings_provider = candidate
    savings_window_start = savings_start_date or focus_window_start
    savings_window_end = savings_end_date or focus_window_end
    if savings_window_start > savings_window_end:
        raise HTTPException(
            status_code=400, detail="savings_start_date must be <= savings_end_date"
        )
    savings_proof_info["provider"] = normalized_savings_provider
    savings_proof_info["window"] = {
        "start_date": savings_window_start.isoformat(),
        "end_date": savings_window_end.isoformat(),
    }

    # Realized savings evidence window/provider validation (executed_at window)
    _realized_supported_providers = {
        "aws",
        "azure",
        "gcp",
        "saas",
        "license",
        "platform",
        "hybrid",
    }
    normalized_realized_provider: str | None = None
    if realized_provider is not None:
        candidate = realized_provider.strip().lower()
        if not candidate:
            normalized_realized_provider = None
        elif candidate not in _realized_supported_providers:
            supported = ", ".join(sorted(_realized_supported_providers))
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported realized_provider '{realized_provider}'. Use one of: {supported}",
            )
        else:
            normalized_realized_provider = candidate

    realized_window_start = realized_start_date or savings_window_start
    realized_window_end = realized_end_date or savings_window_end
    if realized_window_start > realized_window_end:
        raise HTTPException(
            status_code=400, detail="realized_start_date must be <= realized_end_date"
        )
    realized_savings_info["provider"] = normalized_realized_provider
    realized_savings_info["window"] = {
        "start_date": realized_window_start.isoformat(),
        "end_date": realized_window_end.isoformat(),
    }

    # Close package window/provider validation
    _close_supported_providers = {
        "aws",
        "azure",
        "gcp",
        "saas",
        "license",
        "platform",
        "hybrid",
    }
    normalized_close_provider: str | None = None
    if close_provider is not None:
        candidate = close_provider.strip().lower()
        if not candidate:
            normalized_close_provider = None
        elif candidate not in _close_supported_providers:
            supported = ", ".join(sorted(_close_supported_providers))
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported close_provider '{close_provider}'. Use one of: {supported}",
            )
        else:
            normalized_close_provider = candidate
    close_window_start = close_start_date or focus_window_start
    close_window_end = close_end_date or focus_window_end
    if close_window_start > close_window_end:
        raise HTTPException(
            status_code=400, detail="close_start_date must be <= close_end_date"
        )
    close_package_info["provider"] = normalized_close_provider
    close_package_info["window"] = {
        "start_date": close_window_start.isoformat(),
        "end_date": close_window_end.isoformat(),
    }

    manifest = {
        "exported_at": exported_at.isoformat(),
        "run_id": run_id,
        "tenant_id": str(user.tenant_id),
        "actor_id": str(user.id),
        "actor_email": user.email,
        "environment": app_settings.ENVIRONMENT,
        "app_version": app_settings.VERSION,
        "window": {
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
        },
        "focus_export": focus_export_info,
        "savings_proof": savings_proof_info,
        "close_package": close_package_info,
        "leadership_kpis": {
            "count": len(leadership_kpi_evidence),
            "limit": int(evidence_limit),
        },
        "quarterly_commercial_proof_reports": {
            "count": len(quarterly_commercial_proof_evidence),
            "limit": int(evidence_limit),
        },
        "identity_idp_smoke_tests": {
            "count": len(identity_smoke_evidence),
            "limit": int(evidence_limit),
        },
        "sso_federation_validation": {
            "count": len(sso_federation_validation_evidence),
            "limit": int(evidence_limit),
        },
        "performance_load_tests": {
            "count": len(performance_load_test_evidence),
            "limit": int(evidence_limit),
        },
        "ingestion_persistence_benchmarks": {
            "count": len(ingestion_persistence_benchmark_evidence),
            "limit": int(evidence_limit),
        },
        "ingestion_soak_runs": {
            "count": len(ingestion_soak_evidence),
            "limit": int(evidence_limit),
        },
        "partitioning_validation": {
            "count": len(partitioning_evidence),
            "limit": int(evidence_limit),
        },
        "job_slo_evidence": {
            "count": len(job_slo_evidence),
            "limit": int(evidence_limit),
        },
        "tenant_isolation_verifications": {
            "count": len(tenant_isolation_evidence),
            "limit": int(evidence_limit),
        },
        "carbon_assurance": {
            "count": len(carbon_assurance_evidence),
            "limit": int(evidence_limit),
        },
        "carbon_factors": {
            "factor_sets_count": len(carbon_factor_sets),
            "update_logs_count": len(carbon_factor_update_logs),
            "limit": int(evidence_limit),
        },
        "included_files": included_files,
        "notes": [
            "Secrets/tokens are redacted. Only boolean 'has_*' fields are included for encrypted credentials.",
            "Audit log export is capped at 10,000 records for performance.",
            "Bundled FOCUS export is bounded by focus_max_rows. Use /api/v1/costs/export/focus for full streaming export.",
            "Bundled Savings Proof prefers finance-grade realized savings evidence when available, otherwise falls back to estimated savings.",
            "Realized savings exports are bounded by realized_limit and filtered by executed_at window; missing rows usually indicate insufficient finalized ledger coverage for the baseline/measurement windows.",
            "Bundled close package restatement entries may be truncated via close_max_restatements.",
            "Carbon factor exports are global methodology artifacts (not tenant-scoped billing data).",
            "Key runbooks/licensing docs are included for procurement review under docs/.",
        ],
    }

    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("audit_logs.csv", audit_csv.getvalue())
        zf.writestr(
            "notification_settings.json",
            json.dumps(notif_snapshot, indent=2, sort_keys=True),
        )
        zf.writestr(
            "remediation_settings.json",
            json.dumps(remediation_snapshot, indent=2, sort_keys=True),
        )
        zf.writestr(
            "identity_settings.json",
            json.dumps(identity_snapshot, indent=2, sort_keys=True),
        )
        zf.writestr(
            "integration_acceptance_evidence.json",
            json.dumps(integration_evidence, indent=2, sort_keys=True),
        )
        zf.writestr(
            "acceptance_kpis_evidence.json",
            json.dumps(acceptance_kpi_evidence, indent=2, sort_keys=True),
        )
        zf.writestr(
            "leadership_kpis_evidence.json",
            json.dumps(leadership_kpi_evidence, indent=2, sort_keys=True),
        )
        zf.writestr(
            "quarterly_commercial_proof_evidence.json",
            json.dumps(quarterly_commercial_proof_evidence, indent=2, sort_keys=True),
        )
        zf.writestr(
            "identity_smoke_evidence.json",
            json.dumps(identity_smoke_evidence, indent=2, sort_keys=True),
        )
        zf.writestr(
            "sso_federation_validation_evidence.json",
            json.dumps(sso_federation_validation_evidence, indent=2, sort_keys=True),
        )
        zf.writestr(
            "performance_load_test_evidence.json",
            json.dumps(performance_load_test_evidence, indent=2, sort_keys=True),
        )
        zf.writestr(
            "ingestion_persistence_benchmark_evidence.json",
            json.dumps(
                ingestion_persistence_benchmark_evidence, indent=2, sort_keys=True
            ),
        )
        zf.writestr(
            "ingestion_soak_evidence.json",
            json.dumps(ingestion_soak_evidence, indent=2, sort_keys=True),
        )
        zf.writestr(
            "partitioning_evidence.json",
            json.dumps(partitioning_evidence, indent=2, sort_keys=True),
        )
        zf.writestr(
            "job_slo_evidence.json",
            json.dumps(job_slo_evidence, indent=2, sort_keys=True),
        )
        zf.writestr(
            "tenant_isolation_evidence.json",
            json.dumps(tenant_isolation_evidence, indent=2, sort_keys=True),
        )
        zf.writestr(
            "carbon_assurance_evidence.json",
            json.dumps(carbon_assurance_evidence, indent=2, sort_keys=True),
        )
        zf.writestr(
            "carbon_factor_sets.json",
            json.dumps(carbon_factor_sets, indent=2, sort_keys=True),
        )
        zf.writestr(
            "carbon_factor_update_logs.json",
            json.dumps(carbon_factor_update_logs, indent=2, sort_keys=True),
        )
        if scim_doc is not None:
            zf.writestr("docs/integrations/scim.md", scim_doc)
        if idp_reference_doc is not None:
            zf.writestr("docs/integrations/idp_reference_configs.md", idp_reference_doc)
        if sso_doc is not None:
            zf.writestr("docs/integrations/sso.md", sso_doc)
        if teams_doc is not None:
            zf.writestr("docs/integrations/microsoft_teams.md", teams_doc)
        if compliance_pack_doc is not None:
            zf.writestr("docs/compliance/compliance_pack.md", compliance_pack_doc)
        if focus_doc is not None:
            zf.writestr("docs/compliance/focus_export.md", focus_doc)
        if acceptance_doc is not None:
            zf.writestr("docs/ops/acceptance_evidence_capture.md", acceptance_doc)
        if close_runbook_doc is not None:
            zf.writestr("docs/runbooks/month_end_close.md", close_runbook_doc)
        if tenant_lifecycle_doc is not None:
            zf.writestr("docs/runbooks/tenant_data_lifecycle.md", tenant_lifecycle_doc)
        if partition_maintenance_doc is not None:
            zf.writestr(
                "docs/runbooks/partition_maintenance.md", partition_maintenance_doc
            )
        if licensing_doc is not None:
            zf.writestr("docs/licensing.md", licensing_doc)
        if license_text is not None:
            zf.writestr("LICENSE", license_text)
        if trademark_policy_doc is not None:
            zf.writestr("TRADEMARK_POLICY.md", trademark_policy_doc)
        if commercial_license_doc is not None:
            zf.writestr("COMMERCIAL_LICENSE.md", commercial_license_doc)

        if include_focus_export:
            try:
                from app.modules.reporting.domain.focus_export import (
                    FocusV13ExportService,
                    FOCUS_V13_CORE_COLUMNS,
                )

                export_service = FocusV13ExportService(db)
                rows_written = 0
                truncated = False

                with zf.open("exports/focus-v1.3-core.csv", "w") as fp:
                    if "exports/focus-v1.3-core.csv" not in included_files:
                        included_files.append("exports/focus-v1.3-core.csv")
                    text_fp = io.TextIOWrapper(fp, encoding="utf-8", newline="")
                    focus_writer = csv.writer(text_fp)
                    focus_writer.writerow(FOCUS_V13_CORE_COLUMNS)

                    async for focus_row in export_service.export_rows(
                        tenant_id=cast(UUID, user.tenant_id),
                        start_date=focus_window_start,
                        end_date=focus_window_end,
                        provider=normalized_focus_provider,
                        include_preliminary=bool(focus_include_preliminary),
                    ):
                        focus_row_dict = (
                            focus_row
                            if isinstance(focus_row, dict)
                            else dict(focus_row._mapping)
                            if hasattr(focus_row, "_mapping")
                            else {}
                        )
                        focus_writer.writerow(
                            [
                                _sanitize_csv_cell(focus_row_dict.get(col, ""))
                                for col in FOCUS_V13_CORE_COLUMNS
                            ]
                        )
                        rows_written += 1
                        if rows_written % 1000 == 0:
                            text_fp.flush()
                        if rows_written >= int(focus_max_rows):
                            truncated = True
                            break
                    text_fp.flush()

                focus_export_info.update(
                    {
                        "rows_written": rows_written,
                        "truncated": truncated,
                        "status": "ok",
                    }
                )
            except Exception as exc:
                focus_export_info.update(
                    {
                        "status": "error",
                        "error": str(exc),
                    }
                )
                # Keep the pack usable even if the export fails.
                zf.writestr(
                    "exports/focus-v1.3-core.error.json",
                    json.dumps(
                        {
                            "status": "error",
                            "error": str(exc),
                            "hint": "Use GET /api/v1/costs/export/focus for direct export.",
                        },
                        indent=2,
                        sort_keys=True,
                    ),
                )
                # Ensure manifest lists the error artifact.
                if "exports/focus-v1.3-core.error.json" not in included_files:
                    included_files.append("exports/focus-v1.3-core.error.json")

        if include_savings_proof:
            try:
                from app.modules.reporting.domain.savings_proof import (
                    SavingsProofService,
                )

                service = SavingsProofService(db)
                payload = await service.generate(
                    tenant_id=cast(UUID, user.tenant_id),
                    tier=str(getattr(user, "tier", "")),
                    start_date=savings_window_start,
                    end_date=savings_window_end,
                    provider=normalized_savings_provider,
                )
                json_path = "exports/savings-proof.json"
                csv_path = "exports/savings-proof.csv"
                if json_path not in included_files:
                    included_files.append(json_path)
                if csv_path not in included_files:
                    included_files.append(csv_path)
                zf.writestr(
                    json_path,
                    json.dumps(payload.model_dump(), indent=2, sort_keys=True),
                )
                zf.writestr(csv_path, SavingsProofService.render_csv(payload))

                # Drilldowns (Commercial proof v3): strategy type and remediation action.
                drilldowns: list[tuple[str, str]] = [
                    ("strategy_type", "strategy-type"),
                    ("remediation_action", "remediation-action"),
                ]
                for dim, dim_slug in drilldowns:
                    drill_json_path = f"exports/savings-proof-drilldown-{dim_slug}.json"
                    drill_csv_path = f"exports/savings-proof-drilldown-{dim_slug}.csv"
                    if drill_json_path not in included_files:
                        included_files.append(drill_json_path)
                    if drill_csv_path not in included_files:
                        included_files.append(drill_csv_path)

                    drill_payload = await service.drilldown(
                        tenant_id=cast(UUID, user.tenant_id),
                        tier=str(getattr(user, "tier", "")),
                        start_date=savings_window_start,
                        end_date=savings_window_end,
                        provider=normalized_savings_provider,
                        dimension=dim,
                        limit=200,
                    )
                    zf.writestr(
                        drill_json_path,
                        json.dumps(
                            drill_payload.model_dump(), indent=2, sort_keys=True
                        ),
                    )
                    zf.writestr(
                        drill_csv_path,
                        SavingsProofService.render_drilldown_csv(drill_payload),
                    )

                savings_proof_info.update({"status": "ok"})
            except Exception as exc:
                savings_proof_info.update({"status": "error", "error": str(exc)})
                error_path = "exports/savings-proof.error.json"
                zf.writestr(
                    error_path,
                    json.dumps(
                        {
                            "status": "error",
                            "error": str(exc),
                            "hint": "Use GET /api/v1/savings/proof for direct export.",
                        },
                        indent=2,
                        sort_keys=True,
                    ),
                )
                if error_path not in included_files:
                    included_files.append(error_path)

        if include_realized_savings:
            try:
                from app.models.realized_savings import RealizedSavingsEvent
                from app.models.remediation import RemediationRequest

                realized_start_dt = datetime.combine(
                    realized_window_start, time.min, tzinfo=timezone.utc
                )
                realized_end_dt = datetime.combine(
                    realized_window_end, time.max, tzinfo=timezone.utc
                )

                realized_stmt = (
                    select(RealizedSavingsEvent, RemediationRequest.executed_at)
                    .join(
                        RemediationRequest,
                        RealizedSavingsEvent.remediation_request_id
                        == RemediationRequest.id,
                    )
                    .where(
                        RealizedSavingsEvent.tenant_id == user.tenant_id,
                        RemediationRequest.executed_at.is_not(None),
                        RemediationRequest.executed_at >= realized_start_dt,
                        RemediationRequest.executed_at <= realized_end_dt,
                    )
                    .order_by(RealizedSavingsEvent.computed_at.desc())
                    .limit(int(realized_limit))
                )
                if normalized_realized_provider:
                    realized_stmt = realized_stmt.where(
                        RealizedSavingsEvent.provider
                        == normalized_realized_provider
                    )

                rows = list((await db.execute(realized_stmt)).all())
                items: list[dict[str, Any]] = []
                for event, executed_at in rows:
                    items.append(
                        {
                            "remediation_request_id": str(event.remediation_request_id),
                            "provider": str(event.provider),
                            "account_id": str(event.account_id)
                            if event.account_id
                            else None,
                            "resource_id": str(event.resource_id)
                            if event.resource_id
                            else None,
                            "region": str(event.region) if event.region else None,
                            "method": str(event.method),
                            "executed_at": executed_at.isoformat()
                            if isinstance(executed_at, datetime)
                            else None,
                            "baseline_start_date": event.baseline_start_date.isoformat(),
                            "baseline_end_date": event.baseline_end_date.isoformat(),
                            "measurement_start_date": event.measurement_start_date.isoformat(),
                            "measurement_end_date": event.measurement_end_date.isoformat(),
                            "baseline_avg_daily_cost_usd": float(
                                event.baseline_avg_daily_cost_usd or 0
                            ),
                            "measurement_avg_daily_cost_usd": float(
                                event.measurement_avg_daily_cost_usd or 0
                            ),
                            "realized_monthly_savings_usd": float(
                                event.realized_monthly_savings_usd or 0
                            ),
                            "confidence_score": float(event.confidence_score)
                            if event.confidence_score is not None
                            else None,
                            "computed_at": event.computed_at.isoformat(),
                        }
                    )

                json_path = "exports/realized-savings.json"
                csv_path = "exports/realized-savings.csv"
                if json_path not in included_files:
                    included_files.append(json_path)
                if csv_path not in included_files:
                    included_files.append(csv_path)

                zf.writestr(json_path, json.dumps(items, indent=2, sort_keys=True))

                fieldnames = [
                    "remediation_request_id",
                    "provider",
                    "account_id",
                    "resource_id",
                    "region",
                    "method",
                    "executed_at",
                    "baseline_start_date",
                    "baseline_end_date",
                    "measurement_start_date",
                    "measurement_end_date",
                    "baseline_avg_daily_cost_usd",
                    "measurement_avg_daily_cost_usd",
                    "realized_monthly_savings_usd",
                    "confidence_score",
                    "computed_at",
                ]
                buf = io.StringIO()
                realized_csv_writer: csv.DictWriter[str] = csv.DictWriter(
                    buf, fieldnames=fieldnames
                )
                realized_csv_writer.writeheader()
                for item in items:
                    realized_csv_writer.writerow(item)
                zf.writestr(csv_path, buf.getvalue())

                realized_savings_info.update(
                    {"status": "ok", "rows_written": len(items)}
                )
            except Exception as exc:
                realized_savings_info.update({"status": "error", "error": str(exc)})
                error_path = "exports/realized-savings.error.json"
                zf.writestr(
                    error_path,
                    json.dumps(
                        {
                            "status": "error",
                            "error": str(exc),
                            "hint": "Use GET /api/v1/savings/realized/events for direct export.",
                        },
                        indent=2,
                        sort_keys=True,
                    ),
                )
                if error_path not in included_files:
                    included_files.append(error_path)

        if include_close_package:
            try:
                from app.modules.reporting.domain.reconciliation import (
                    CostReconciliationService,
                )

                close_service = CostReconciliationService(db)
                package = await close_service.generate_close_package(
                    tenant_id=cast(UUID, user.tenant_id),
                    start_date=close_window_start,
                    end_date=close_window_end,
                    enforce_finalized=bool(close_enforce_finalized),
                    provider=normalized_close_provider,
                    max_restatement_entries=int(close_max_restatements),
                )
                close_csv = package.pop("csv", "")
                json_path = "exports/close-package.json"
                csv_path = "exports/close-package.csv"
                if json_path not in included_files:
                    included_files.append(json_path)
                if csv_path not in included_files:
                    included_files.append(csv_path)
                zf.writestr(
                    json_path,
                    json.dumps(package, indent=2, sort_keys=True, default=str),
                )
                zf.writestr(csv_path, close_csv)
                close_package_info.update({"status": "ok"})
            except Exception as exc:
                close_package_info.update({"status": "error", "error": str(exc)})
                error_path = "exports/close-package.error.json"
                zf.writestr(
                    error_path,
                    json.dumps(
                        {
                            "status": "error",
                            "error": str(exc),
                            "hint": "Use GET /api/v1/costs/reconciliation/close-package for direct export.",
                        },
                        indent=2,
                        sort_keys=True,
                    ),
                )
                if error_path not in included_files:
                    included_files.append(error_path)

        # Write manifest last so it can include bundled export stats.
        if "manifest.json" not in included_files:
            included_files.insert(0, "manifest.json")
        manifest["included_files"] = included_files
        manifest["focus_export"] = focus_export_info
        manifest["savings_proof"] = savings_proof_info
        manifest["realized_savings"] = realized_savings_info
        manifest["close_package"] = close_package_info
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
    bundle.seek(0)

    filename = (
        f"compliance-pack-{user.tenant_id}-{exported_at.strftime('%Y%m%dT%H%M%SZ')}.zip"
    )
    return Response(
        content=bundle.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/data-erasure-request")
async def request_data_erasure(
    user: Annotated[CurrentUser, Depends(requires_role("owner"))],
    db: AsyncSession = Depends(get_db),
    confirmation: str = Query(..., description="Type 'DELETE ALL MY DATA' to confirm"),
) -> dict[str, Any]:
    """
    GDPR Article 17 - Right to Erasure (Right to be Forgotten).

    Initiates a data erasure request for the tenant.
    Owner role required. Irreversible action.
    """
    if confirmation != "DELETE ALL MY DATA":
        raise HTTPException(
            status_code=400,
            detail="Confirmation text must exactly match 'DELETE ALL MY DATA'",
        )

    try:
        from app.models.tenant import User
        from app.models.tenant import Tenant
        from app.models.cloud import CostRecord, CloudAccount
        from app.models.remediation import RemediationRequest
        from app.models.anomaly_marker import AnomalyMarker
        from app.models.aws_connection import AWSConnection
        from app.models.azure_connection import AzureConnection
        from app.models.gcp_connection import GCPConnection
        from app.models.llm import LLMUsage, LLMBudget
        from app.models.notification_settings import NotificationSettings
        from app.models.background_job import BackgroundJob
        from app.models.carbon_settings import CarbonSettings
        from app.models.remediation_settings import RemediationSettings
        from app.models.discovered_account import DiscoveredAccount
        from app.models.attribution import AttributionRule, CostAllocation
        from app.models.cost_audit import CostAuditLog
        from app.models.optimization import StrategyRecommendation
        from sqlalchemy import delete

        tenant_id = user.tenant_id

        tenant_row = await db.execute(
            select(Tenant).where(Tenant.id == tenant_id).with_for_update()
        )
        if tenant_row.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Tenant not found")

        # Log the request before execution
        logger.critical(
            "gdpr_data_erasure_initiated",
            tenant_id=str(tenant_id),
            requested_by=user.email,
        )

        # Delete in order of dependencies
        deleted_counts = {}

        # 1. Delete dependent cost data (audit logs for records)
        await db.execute(
            delete(CostAuditLog).where(
                CostAuditLog.cost_record_id.in_(
                    select(CostRecord.id).where(CostRecord.tenant_id == tenant_id)
                )
            )
        )

        # 2. Delete attribution allocations before cost records (FK dependency)
        await db.execute(
            delete(CostAllocation).where(
                CostAllocation.cost_record_id.in_(
                    select(CostRecord.id).where(CostRecord.tenant_id == tenant_id)
                )
            )
        )

        # 3. Delete cost records (largest table)
        result = await db.execute(
            delete(CostRecord).where(CostRecord.tenant_id == tenant_id)
        )
        deleted_counts["cost_records"] = _rowcount(result)

        # 4. Delete anomaly markers
        result = await db.execute(
            delete(AnomalyMarker).where(AnomalyMarker.tenant_id == tenant_id)
        )
        deleted_counts["anomaly_markers"] = _rowcount(result)

        # 5. Delete remediation and discovery data
        result = await db.execute(
            delete(RemediationRequest).where(RemediationRequest.tenant_id == tenant_id)
        )
        deleted_counts["remediation_requests"] = _rowcount(result)

        result = await db.execute(
            delete(StrategyRecommendation).where(
                StrategyRecommendation.tenant_id == tenant_id
            )
        )
        deleted_counts["strategy_recommendations"] = _rowcount(result)

        # Optimization strategies are global catalog entries, not tenant-owned records.
        # Tenant data erasure must only remove tenant-specific recommendations.
        deleted_counts["optimization_strategies"] = 0

        await db.execute(
            delete(RemediationSettings).where(
                RemediationSettings.tenant_id == tenant_id
            )
        )

        result = await db.execute(
            delete(DiscoveredAccount).where(
                DiscoveredAccount.management_connection_id.in_(
                    select(AWSConnection.id).where(AWSConnection.tenant_id == tenant_id)
                )
            )
        )
        deleted_counts["discovered_accounts"] = _rowcount(result)

        # 6. Delete Cloud Connections and Attribution
        await db.execute(
            delete(AWSConnection).where(AWSConnection.tenant_id == tenant_id)
        )
        await db.execute(
            delete(AzureConnection).where(AzureConnection.tenant_id == tenant_id)
        )
        await db.execute(
            delete(GCPConnection).where(GCPConnection.tenant_id == tenant_id)
        )

        await db.execute(
            delete(AttributionRule).where(AttributionRule.tenant_id == tenant_id)
        )

        # 7. Delete LLM Usage and Budgets
        result = await db.execute(
            delete(LLMUsage).where(LLMUsage.tenant_id == tenant_id)
        )
        deleted_counts["llm_usage_records"] = _rowcount(result)

        await db.execute(delete(LLMBudget).where(LLMBudget.tenant_id == tenant_id))

        # 8. Delete Notification and Carbon settings
        await db.execute(
            delete(NotificationSettings).where(
                NotificationSettings.tenant_id == tenant_id
            )
        )
        await db.execute(
            delete(CarbonSettings).where(CarbonSettings.tenant_id == tenant_id)
        )

        # 9. Delete Background Jobs
        result = await db.execute(
            delete(BackgroundJob).where(BackgroundJob.tenant_id == tenant_id)
        )
        deleted_counts["background_jobs"] = _rowcount(result)

        # 10. Delete Cloud accounts (Meta)
        result = await db.execute(
            delete(CloudAccount).where(CloudAccount.tenant_id == tenant_id)
        )
        deleted_counts["cloud_accounts"] = _rowcount(result)

        # 11. Delete users (except the requesting user - they delete last)
        result = await db.execute(
            delete(User).where(User.tenant_id == tenant_id, User.id != user.id)
        )
        deleted_counts["other_users"] = _rowcount(result)

        # 6. Audit logs preserved (required for compliance) but marked
        # We don't delete audit logs - they are required for SOC2

        await db.commit()

        logger.critical(
            "gdpr_data_erasure_complete",
            tenant_id=str(tenant_id),
            deleted_counts=deleted_counts,
        )

        return {
            "status": "erasure_complete",
            "message": "All tenant data has been deleted. Audit logs are preserved for compliance.",
            "deleted_counts": deleted_counts,
            "next_steps": [
                "Your account will remain active until you close it via /api/v1/settings/account",
                "Audit logs are retained for 90 days per SOC2 requirements",
                "Contact support@valdrix.com for any questions",
            ],
        }

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("gdpr_erasure_failed", error=str(e), tenant_id=str(user.tenant_id))
        raise HTTPException(500, "Data erasure failed. Please contact support.") from e
