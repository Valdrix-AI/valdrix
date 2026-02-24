"""
Audit Log API Endpoints

Provides:
- GET /audit/logs - Paginated audit logs (admin-only)
"""

from typing import Annotated, Any, Optional, List, Literal
from uuid import UUID
from datetime import datetime, timezone, date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, asc, text
import structlog

from app.modules.governance.api.v1.audit_schemas import (  # noqa: F401
    AuditLogResponse,
    CarbonAssuranceEvidenceCaptureRequest,
    CarbonAssuranceEvidenceCaptureResponse,
    CarbonAssuranceEvidenceItem,
    CarbonAssuranceEvidenceListResponse,
    CarbonAssuranceEvidencePayload,
    IdentityIdpSmokeEvidenceCaptureResponse,
    IdentityIdpSmokeEvidenceCheck,
    IdentityIdpSmokeEvidenceItem,
    IdentityIdpSmokeEvidenceListResponse,
    IdentityIdpSmokeEvidencePayload,
    IngestionPersistenceEvidenceCaptureResponse,
    IngestionPersistenceEvidenceItem,
    IngestionPersistenceEvidenceListResponse,
    IngestionPersistenceEvidencePayload,
    IngestionSoakEvidenceCaptureResponse,
    IngestionSoakEvidenceItem,
    IngestionSoakEvidenceJobRun,
    IngestionSoakEvidenceListResponse,
    IngestionSoakEvidencePayload,
    IngestionSoakEvidenceResults,
    JobBacklogEvidenceSnapshot,
    JobSLOEvidenceCaptureRequest,
    JobSLOEvidenceCaptureResponse,
    JobSLOEvidenceItem,
    JobSLOEvidenceListResponse,
    JobSLOEvidencePayload,
    JobSLOMetricEvidence,
    LoadTestEvidenceCaptureResponse,
    LoadTestEvidenceItem,
    LoadTestEvidenceListResponse,
    LoadTestEvidencePayload,
    LoadTestEvidenceResults,
    PartitioningEvidenceCaptureResponse,
    PartitioningEvidenceItem,
    PartitioningEvidenceListResponse,
    PartitioningEvidencePayload,
    PartitioningTableStatus,
    SsoFederationValidationEvidenceCaptureResponse,
    SsoFederationValidationEvidenceItem,
    SsoFederationValidationEvidenceListResponse,
    SsoFederationValidationEvidencePayload,
    TenantIsolationEvidenceCaptureResponse,
    TenantIsolationEvidenceItem,
    TenantIsolationEvidenceListResponse,
    TenantIsolationEvidencePayload,
)
from app.shared.core.auth import CurrentUser, requires_role
from app.shared.core.dependencies import requires_feature
from app.shared.core.pricing import FeatureFlag
from app.shared.db.session import get_db
from app.modules.governance.domain.security.audit_log import AuditLog
from app.modules.governance.domain.security.compliance_pack_bundle import (
    export_compliance_pack_bundle,
)
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
    return await export_compliance_pack_bundle(
        user=user,
        db=db,
        start_date=start_date,
        end_date=end_date,
        evidence_limit=evidence_limit,
        include_focus_export=include_focus_export,
        focus_provider=focus_provider,
        focus_include_preliminary=focus_include_preliminary,
        focus_max_rows=focus_max_rows,
        focus_start_date=focus_start_date,
        focus_end_date=focus_end_date,
        include_savings_proof=include_savings_proof,
        savings_provider=savings_provider,
        savings_start_date=savings_start_date,
        savings_end_date=savings_end_date,
        include_realized_savings=include_realized_savings,
        realized_provider=realized_provider,
        realized_start_date=realized_start_date,
        realized_end_date=realized_end_date,
        realized_limit=realized_limit,
        include_close_package=include_close_package,
        close_provider=close_provider,
        close_start_date=close_start_date,
        close_end_date=close_end_date,
        close_enforce_finalized=close_enforce_finalized,
        close_max_restatements=close_max_restatements,
        sanitize_csv_cell=_sanitize_csv_cell,
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
        from app.models.saas_connection import SaaSConnection
        from app.models.license_connection import LicenseConnection
        from app.models.platform_connection import PlatformConnection
        from app.models.hybrid_connection import HybridConnection
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
            delete(SaaSConnection).where(SaaSConnection.tenant_id == tenant_id)
        )
        await db.execute(
            delete(LicenseConnection).where(LicenseConnection.tenant_id == tenant_id)
        )
        await db.execute(
            delete(PlatformConnection).where(PlatformConnection.tenant_id == tenant_id)
        )
        await db.execute(
            delete(HybridConnection).where(HybridConnection.tenant_id == tenant_id)
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
