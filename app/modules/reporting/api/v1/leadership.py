"""
Leadership KPI Export API

This endpoint is optimized for executive/procurement reporting:
- deterministic, ledger-backed aggregates
- optional audit-grade evidence capture into immutable audit logs
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.governance.domain.security.audit_log import AuditEventType, AuditLogger
from app.shared.core.auth import CurrentUser
from app.shared.core.pricing import FeatureFlag, PricingTier, normalize_tier
from app.shared.core.dependencies import requires_feature
from app.shared.db.session import get_db
from app.modules.reporting.domain.commercial_reports import (
    CommercialProofReportService,
    QuarterlyCommercialProofResponse,
)
from app.modules.reporting.domain.leadership_kpis import (
    LeadershipKpiService,
    LeadershipKpisResponse,
)

logger = structlog.get_logger()
router = APIRouter(tags=["Leadership"])


def _require_tenant_id(user: CurrentUser) -> UUID:
    if user.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")
    return user.tenant_id


@router.get("/kpis", response_model=LeadershipKpisResponse)
async def get_leadership_kpis(
    start_date: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end_date: date = Query(default_factory=date.today),
    provider: Optional[str] = Query(
        default=None, pattern="^(aws|azure|gcp|saas|license|platform|hybrid)$"
    ),
    include_preliminary: bool = Query(default=False),
    top_services_limit: int = Query(default=10, ge=1, le=50),
    response_format: str = Query(default="json", pattern="^(json|csv)$"),
    current_user: CurrentUser = Depends(requires_feature(FeatureFlag.COST_TRACKING)),
    db: AsyncSession = Depends(get_db),
) -> Any:
    tenant_id = _require_tenant_id(current_user)
    tier = normalize_tier(getattr(current_user, "tier", PricingTier.FREE))

    try:
        payload = await LeadershipKpiService(db).compute(
            tenant_id=tenant_id,
            tier=tier,
            start_date=start_date,
            end_date=end_date,
            provider=provider.strip().lower() if provider else None,
            include_preliminary=bool(include_preliminary),
            top_services_limit=int(top_services_limit),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if response_format == "csv":
        csv_data = LeadershipKpiService.render_csv(payload)
        filename = (
            f"leadership-kpis-{start_date.isoformat()}-{end_date.isoformat()}.csv"
        )
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    return payload


class LeadershipKpiEvidenceItem(LeadershipKpisResponse):
    event_id: str
    run_id: str | None
    captured_at: str
    actor_id: str | None
    actor_email: str | None
    success: bool


class LeadershipKpiEvidenceListResponse(BaseModel):
    total: int
    items: list[LeadershipKpiEvidenceItem]


class LeadershipKpiEvidenceCaptureResponse(BaseModel):
    status: str
    event_id: str
    run_id: str
    captured_at: str
    leadership_kpis: LeadershipKpisResponse


@router.post("/kpis/capture", response_model=LeadershipKpiEvidenceCaptureResponse)
async def capture_leadership_kpis(
    start_date: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end_date: date = Query(default_factory=date.today),
    provider: Optional[str] = Query(
        default=None, pattern="^(aws|azure|gcp|saas|license|platform|hybrid)$"
    ),
    include_preliminary: bool = Query(default=False),
    top_services_limit: int = Query(default=10, ge=1, le=50),
    current_user: CurrentUser = Depends(
        requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
    ),
    db: AsyncSession = Depends(get_db),
) -> LeadershipKpiEvidenceCaptureResponse:
    """
    Capture leadership KPI export evidence as an immutable audit log record.

    This is intended for procurement/commercial proof packs (audit-grade).
    """
    from uuid import uuid4

    tenant_id = _require_tenant_id(current_user)
    tier = normalize_tier(getattr(current_user, "tier", PricingTier.FREE))

    try:
        payload = await LeadershipKpiService(db).compute(
            tenant_id=tenant_id,
            tier=tier,
            start_date=start_date,
            end_date=end_date,
            provider=provider.strip().lower() if provider else None,
            include_preliminary=bool(include_preliminary),
            top_services_limit=int(top_services_limit),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    run_id = str(uuid4())
    audit = AuditLogger(db=db, tenant_id=tenant_id, correlation_id=run_id)
    event = await audit.log(
        event_type=AuditEventType.LEADERSHIP_KPIS_CAPTURED,
        actor_id=current_user.id,
        actor_email=current_user.email,
        resource_type="leadership_kpis",
        resource_id=f"{payload.start_date}:{payload.end_date}",
        details={
            "run_id": run_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "thresholds": {
                "provider": provider.strip().lower() if provider else None,
                "include_preliminary": bool(include_preliminary),
                "top_services_limit": int(top_services_limit),
            },
            "leadership_kpis": payload.model_dump(),
        },
        success=True,
        request_method="POST",
        request_path="/api/v1/leadership/kpis/capture",
    )
    await db.commit()

    return LeadershipKpiEvidenceCaptureResponse(
        status="captured",
        event_id=str(event.id),
        run_id=run_id,
        captured_at=event.event_timestamp.isoformat(),
        leadership_kpis=payload,
    )


@router.get("/kpis/evidence", response_model=LeadershipKpiEvidenceListResponse)
async def list_leadership_kpi_evidence(
    limit: int = Query(default=100, ge=1, le=500),
    current_user: CurrentUser = Depends(
        requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
    ),
    db: AsyncSession = Depends(get_db),
) -> LeadershipKpiEvidenceListResponse:
    """
    List persisted leadership KPI evidence snapshots for this tenant.
    """
    from app.modules.governance.domain.security.audit_log import AuditLog

    tenant_id = _require_tenant_id(current_user)
    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .where(AuditLog.event_type == AuditEventType.LEADERSHIP_KPIS_CAPTURED.value)
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(limit))
    )
    rows = (await db.execute(stmt)).scalars().all()

    items: list[LeadershipKpiEvidenceItem] = []
    for row in rows:
        details = row.details or {}
        raw = details.get("leadership_kpis")
        if not isinstance(raw, dict):
            continue
        try:
            leadership = LeadershipKpisResponse.model_validate(raw)
        except Exception:
            logger.warning(
                "leadership_kpi_evidence_invalid_payload",
                event_id=str(row.id),
                tenant_id=str(tenant_id),
            )
            continue

        items.append(
            LeadershipKpiEvidenceItem(
                event_id=str(row.id),
                run_id=row.correlation_id,
                captured_at=row.event_timestamp.isoformat(),
                actor_id=str(row.actor_id) if row.actor_id else None,
                actor_email=row.actor_email,
                success=bool(row.success),
                **leadership.model_dump(),
            )
        )

    return LeadershipKpiEvidenceListResponse(total=len(items), items=items)


class QuarterlyCommercialProofEvidenceItem(QuarterlyCommercialProofResponse):
    event_id: str
    run_id: str | None
    captured_at: str
    actor_id: str | None
    actor_email: str | None
    success: bool


class QuarterlyCommercialProofEvidenceListResponse(BaseModel):
    total: int
    items: list[QuarterlyCommercialProofEvidenceItem]


class QuarterlyCommercialProofEvidenceCaptureResponse(BaseModel):
    status: str
    event_id: str
    run_id: str
    captured_at: str
    report: QuarterlyCommercialProofResponse


@router.get("/reports/quarterly", response_model=QuarterlyCommercialProofResponse)
async def get_quarterly_commercial_report(
    period: str = Query(default="previous", pattern="^(current|previous)$"),
    year: int | None = Query(default=None, ge=2000, le=2100),
    quarter: int | None = Query(default=None, ge=1, le=4),
    as_of: date | None = Query(
        default=None,
        description="Anchor date for current/previous period calculations.",
    ),
    provider: Optional[str] = Query(
        default=None, pattern="^(aws|azure|gcp|saas|license|platform|hybrid)$"
    ),
    response_format: str = Query(default="json", pattern="^(json|csv)$"),
    current_user: CurrentUser = Depends(
        requires_feature(FeatureFlag.COMPLIANCE_EXPORTS)
    ),
    db: AsyncSession = Depends(get_db),
) -> Any:
    tenant_id = _require_tenant_id(current_user)
    tier = normalize_tier(getattr(current_user, "tier", PricingTier.FREE))

    try:
        report = await CommercialProofReportService(db).quarterly_report(
            tenant_id=tenant_id,
            tier=tier,
            period=str(period),
            year=year,
            quarter=quarter,
            as_of=as_of,
            provider=provider.strip().lower() if provider else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if response_format == "csv":
        csv_data = CommercialProofReportService.render_quarterly_csv(report)
        filename = f"commercial-quarterly-{report.year}-Q{report.quarter}.csv"
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    return report


@router.post(
    "/reports/quarterly/capture",
    response_model=QuarterlyCommercialProofEvidenceCaptureResponse,
)
async def capture_quarterly_commercial_report(
    period: str = Query(default="previous", pattern="^(current|previous)$"),
    year: int | None = Query(default=None, ge=2000, le=2100),
    quarter: int | None = Query(default=None, ge=1, le=4),
    as_of: date | None = Query(default=None),
    provider: Optional[str] = Query(
        default=None, pattern="^(aws|azure|gcp|saas|license|platform|hybrid)$"
    ),
    current_user: CurrentUser = Depends(
        requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
    ),
    db: AsyncSession = Depends(get_db),
) -> QuarterlyCommercialProofEvidenceCaptureResponse:
    """
    Capture a quarterly commercial proof report snapshot as immutable audit evidence.
    """
    from uuid import uuid4

    tenant_id = _require_tenant_id(current_user)
    tier = normalize_tier(getattr(current_user, "tier", PricingTier.FREE))

    try:
        report = await CommercialProofReportService(db).quarterly_report(
            tenant_id=tenant_id,
            tier=tier,
            period=str(period),
            year=year,
            quarter=quarter,
            as_of=as_of,
            provider=provider.strip().lower() if provider else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    run_id = str(uuid4())
    audit = AuditLogger(db=db, tenant_id=tenant_id, correlation_id=run_id)
    event = await audit.log(
        event_type=AuditEventType.COMMERCIAL_QUARTERLY_REPORT_CAPTURED,
        actor_id=current_user.id,
        actor_email=current_user.email,
        resource_type="commercial_quarterly_report",
        resource_id=f"{report.year}-Q{report.quarter}",
        details={
            "run_id": run_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "thresholds": {
                "period": str(period),
                "year": year,
                "quarter": quarter,
                "as_of": as_of.isoformat() if as_of else None,
                "provider": provider.strip().lower() if provider else None,
            },
            "quarterly_report": report.model_dump(),
        },
        success=True,
        request_method="POST",
        request_path="/api/v1/leadership/reports/quarterly/capture",
    )
    await db.commit()

    return QuarterlyCommercialProofEvidenceCaptureResponse(
        status="captured",
        event_id=str(event.id),
        run_id=run_id,
        captured_at=event.event_timestamp.isoformat(),
        report=report,
    )


@router.get(
    "/reports/quarterly/evidence",
    response_model=QuarterlyCommercialProofEvidenceListResponse,
)
async def list_quarterly_commercial_report_evidence(
    limit: int = Query(default=100, ge=1, le=500),
    current_user: CurrentUser = Depends(
        requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
    ),
    db: AsyncSession = Depends(get_db),
) -> QuarterlyCommercialProofEvidenceListResponse:
    from app.modules.governance.domain.security.audit_log import AuditLog

    tenant_id = _require_tenant_id(current_user)
    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .where(
            AuditLog.event_type
            == AuditEventType.COMMERCIAL_QUARTERLY_REPORT_CAPTURED.value
        )
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(limit))
    )
    rows = (await db.execute(stmt)).scalars().all()

    items: list[QuarterlyCommercialProofEvidenceItem] = []
    for row in rows:
        details = row.details or {}
        raw = details.get("quarterly_report")
        if not isinstance(raw, dict):
            continue
        try:
            report = QuarterlyCommercialProofResponse.model_validate(raw)
        except Exception:
            logger.warning(
                "quarterly_commercial_report_evidence_invalid_payload",
                event_id=str(row.id),
                tenant_id=str(tenant_id),
            )
            continue

        items.append(
            QuarterlyCommercialProofEvidenceItem(
                event_id=str(row.id),
                run_id=row.correlation_id,
                captured_at=row.event_timestamp.isoformat(),
                actor_id=str(row.actor_id) if row.actor_id else None,
                actor_email=row.actor_email,
                success=bool(row.success),
                **report.model_dump(),
            )
        )

    return QuarterlyCommercialProofEvidenceListResponse(total=len(items), items=items)
