from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

import structlog
from fastapi import Response
from pydantic import ValidationError
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reporting.api.v1.costs_models import (
    AcceptanceKpiEvidenceCaptureResponse,
    AcceptanceKpiEvidenceItem,
    AcceptanceKpiEvidenceListResponse,
    AcceptanceKpisResponse,
)
from app.shared.core.auth import CurrentUser

logger = structlog.get_logger()


async def get_acceptance_kpis_impl(
    *,
    start_date: date,
    end_date: date,
    ingestion_window_hours: int,
    ingestion_target_success_rate_percent: float,
    recency_target_hours: int,
    chargeback_target_percent: float,
    max_unit_anomalies: int,
    response_format: str,
    current_user: CurrentUser,
    db: AsyncSession,
    compute_acceptance_kpis_payload: Callable[..., Awaitable[AcceptanceKpisResponse]],
    render_acceptance_kpi_csv: Callable[[AcceptanceKpisResponse], str],
) -> Any:
    payload = await compute_acceptance_kpis_payload(
        start_date=start_date,
        end_date=end_date,
        ingestion_window_hours=ingestion_window_hours,
        ingestion_target_success_rate_percent=ingestion_target_success_rate_percent,
        recency_target_hours=recency_target_hours,
        chargeback_target_percent=chargeback_target_percent,
        max_unit_anomalies=max_unit_anomalies,
        current_user=current_user,
        db=db,
    )
    if response_format == "csv":
        csv_data = render_acceptance_kpi_csv(payload)
        filename = f"acceptance-kpis-{start_date.isoformat()}-{end_date.isoformat()}.csv"
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    return payload


async def capture_acceptance_kpis_impl(
    *,
    start_date: date,
    end_date: date,
    ingestion_window_hours: int,
    ingestion_target_success_rate_percent: float,
    recency_target_hours: int,
    chargeback_target_percent: float,
    max_unit_anomalies: int,
    current_user: CurrentUser,
    db: AsyncSession,
    compute_acceptance_kpis_payload: Callable[..., Awaitable[AcceptanceKpisResponse]],
    require_tenant_id: Callable[[CurrentUser], UUID],
) -> AcceptanceKpiEvidenceCaptureResponse:
    from uuid import uuid4

    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLogger,
    )

    payload = await compute_acceptance_kpis_payload(
        start_date=start_date,
        end_date=end_date,
        ingestion_window_hours=ingestion_window_hours,
        ingestion_target_success_rate_percent=ingestion_target_success_rate_percent,
        recency_target_hours=recency_target_hours,
        chargeback_target_percent=chargeback_target_percent,
        max_unit_anomalies=max_unit_anomalies,
        current_user=current_user,
        db=db,
    )

    tenant_id = require_tenant_id(current_user)
    run_id = str(uuid4())
    audit = AuditLogger(db=db, tenant_id=tenant_id, correlation_id=run_id)
    event = await audit.log(
        event_type=AuditEventType.ACCEPTANCE_KPIS_CAPTURED,
        actor_id=current_user.id,
        actor_email=current_user.email,
        resource_type="acceptance_kpis",
        resource_id=f"{payload.start_date}:{payload.end_date}",
        details={
            "run_id": run_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "thresholds": {
                "ingestion_window_hours": ingestion_window_hours,
                "ingestion_target_success_rate_percent": ingestion_target_success_rate_percent,
                "recency_target_hours": recency_target_hours,
                "chargeback_target_percent": chargeback_target_percent,
                "max_unit_anomalies": max_unit_anomalies,
            },
            "acceptance_kpis": payload.model_dump(),
        },
        success=True,
        request_method="POST",
        request_path="/api/v1/costs/acceptance/kpis/capture",
    )
    await db.commit()

    return AcceptanceKpiEvidenceCaptureResponse(
        status="captured",
        event_id=str(event.id),
        run_id=run_id,
        captured_at=event.event_timestamp.isoformat(),
        acceptance_kpis=payload,
    )


async def list_acceptance_kpi_evidence_impl(
    *,
    limit: int,
    current_user: CurrentUser,
    db: AsyncSession,
    require_tenant_id: Callable[[CurrentUser], UUID],
) -> AcceptanceKpiEvidenceListResponse:
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLog,
    )

    tenant_id = require_tenant_id(current_user)
    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .where(AuditLog.event_type == AuditEventType.ACCEPTANCE_KPIS_CAPTURED.value)
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(limit))
    )
    rows = (await db.execute(stmt)).scalars().all()

    items: list[AcceptanceKpiEvidenceItem] = []
    for row in rows:
        details = row.details or {}
        raw = details.get("acceptance_kpis")
        if not isinstance(raw, dict):
            continue
        try:
            acceptance_kpis = AcceptanceKpisResponse.model_validate(raw)
        except (ValidationError, TypeError, ValueError):
            logger.warning(
                "acceptance_kpi_evidence_invalid_payload",
                event_id=str(row.id),
                tenant_id=str(tenant_id),
            )
            continue

        items.append(
            AcceptanceKpiEvidenceItem(
                event_id=str(row.id),
                run_id=row.correlation_id,
                captured_at=row.event_timestamp.isoformat(),
                actor_id=str(row.actor_id) if row.actor_id else None,
                actor_email=row.actor_email,
                success=bool(row.success),
                acceptance_kpis=acceptance_kpis,
            )
        )

    return AcceptanceKpiEvidenceListResponse(total=len(items), items=items)
