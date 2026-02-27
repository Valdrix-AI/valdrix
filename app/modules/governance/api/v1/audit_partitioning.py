from datetime import date, datetime, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.governance.api.v1.audit_schemas import (
    PartitioningEvidenceCaptureResponse,
    PartitioningEvidenceItem,
    PartitioningEvidenceListResponse,
    PartitioningEvidencePayload,
    PartitioningTableStatus,
)
from app.shared.core.auth import CurrentUser
from app.shared.core.dependencies import requires_feature
from app.shared.core.pricing import FeatureFlag
from app.shared.db.session import get_db

logger = structlog.get_logger()
router = APIRouter(tags=["Audit"])


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
