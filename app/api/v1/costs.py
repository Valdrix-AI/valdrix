from datetime import date
from uuid import UUID
from typing import Annotated, Any, Literal
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, asc
import structlog
from pydantic import BaseModel

from app.core.auth import CurrentUser, requires_role, require_tenant_access
from app.core.dependencies import requires_feature
from app.db.session import get_db
from app.models.background_job import JobType
from app.services.jobs.processor import enqueue_job
from app.core.rate_limit import rate_limit, analysis_limit, standard_limit
from app.services.costs.aggregator import CostAggregator

class CostAnalysisResponse(BaseModel):
    job_id: UUID
    status: str

router = APIRouter(tags=["Costs & Analysis"])
logger = structlog.get_logger()


@router.get("")
async def get_costs(
    start_date: date,
    end_date: date,
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    provider: str | None = Query(None, description="Filter by cloud provider (aws, azure, gcp)"),
    db: AsyncSession = Depends(get_db),
):
    """Retrieves aggregated cloud costs and carbon for a date range."""
    # Bound date range to max 366 days (Issue #44)
    if (end_date - start_date).days > 366:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 1 year")
    
    if provider is None:
        return await CostAggregator.get_cached_breakdown(
            db, tenant_id, start_date, end_date
        )
        
    return await CostAggregator.get_basic_breakdown(
        db, tenant_id, start_date, end_date, provider
    )


@router.get("/governance")
async def get_cost_governance(
    start_date: date,
    end_date: date,
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieves the cost governance report (untagged/unallocated costs).
    Series-A Compliance: Flags customers with high unallocated spend.
    """
    # Bound date range
    if (end_date - start_date).days > 366:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Date range cannot exceed 1 year")
        
    return await CostAggregator.get_governance_report(
        db, tenant_id, start_date, end_date
    )


@router.get("/freshness")
async def get_data_freshness(
    start_date: date,
    end_date: date,
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
):
    """
    Returns data freshness indicators for the dashboard.
    BE-FIN-RECON-1: Provides visibility into PRELIMINARY vs FINAL data status.
    
    Status values:
    - "final": All data is finalized
    - "preliminary": >50% data is preliminary (may be restated)
    - "mixed": Some preliminary records exist
    - "no_data": No records in range
    """
    return await CostAggregator.get_data_freshness(
        db, tenant_id, start_date, end_date
    )


@router.post("/analyze", response_model=CostAnalysisResponse)
@analysis_limit
async def analyze_costs(
    request: Request,
    start_date: date,
    end_date: date,
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_feature("llm_analysis"))],
    db: AsyncSession = Depends(get_db),
):
    """
    Enqueues an AI-powered analysis of cloud costs.
    Returns a Job ID that can be tracked via the Jobs API.
    """
    # 1. Date Range Validation (Issue #44)
    if (end_date - start_date).days > 90:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="AI analysis range cannot exceed 90 days")

    # 2. Check for existing data (Optimization)
    count = await CostAggregator.count_records(db, tenant_id, start_date, end_date)
    if count == 0:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No cost data available for analysis period.")

    logger.info("enqueuing_finops_analysis", 
                tenant_id=str(tenant_id),
                start=start_date, 
                end=end_date)

    # 3. Enqueue Job
    job = await enqueue_job(
        db=db,
        job_type=JobType.FINOPS_ANALYSIS,
        tenant_id=tenant_id,
        payload={
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        }
    )

    return CostAnalysisResponse(job_id=job.id, status=job.status)


@router.get("/llm/usage")
async def get_llm_usage(
    # Get LLM usage history for the tenant
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    sort_by: Literal["created_at", "total_tokens", "cost_usd"] = Query("created_at"),
    order: Literal["asc", "desc"] = Query("desc")
):
    """Get LLM usage history for the tenant."""
    sort_column = getattr(LLMUsage, sort_by)
    order_func = desc if order == "desc" else asc

    result = await db.execute(
        select(LLMUsage)
        .where(LLMUsage.tenant_id == tenant_id)
        .order_by(order_func(sort_column))
        .limit(limit)
    )
    records = result.scalars().all()

    return {
        "usage": [
            {
                "id": str(r.id),
                "model": r.model,
                "provider": r.provider,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "total_tokens": r.total_tokens,
                "cost_usd": float(r.cost_usd) if r.cost_usd else 0,
                "request_type": r.request_type,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ],
        "count": len(records),
    }


# =============================================================================
# Phase 1.1 & 1.3: Cost History & Data Lineage APIs
# =============================================================================

@router.get("/history/{cost_record_id}")
async def get_cost_history(
    cost_record_id: UUID,
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
):
    """
    Phase 1.1: Show cost change history for a specific record.
    Returns: "Cost for Jan 10 was $X on Jan 10, updated to $Y on Jan 12"
    """
    from app.models.cost_audit import CostAuditLog
    from app.models.cloud import CostRecord
    
    # Get the current cost record
    record_result = await db.execute(
        select(CostRecord).where(
            CostRecord.id == cost_record_id,
            CostRecord.tenant_id == tenant_id
        )
    )
    record = record_result.scalar_one_or_none()
    
    if not record:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Cost record not found")
    
    # Get all audit logs for this record
    audit_result = await db.execute(
        select(CostAuditLog)
        .where(
            CostAuditLog.cost_record_id == cost_record_id,
            CostAuditLog.cost_recorded_at == record.recorded_at
        )
        .order_by(asc(CostAuditLog.recorded_at))
    )
    audits = audit_result.scalars().all()
    
    timeline = []
    for audit in audits:
        timeline.append({
            "date": audit.recorded_at.isoformat(),
            "old_cost": float(audit.old_cost),
            "new_cost": float(audit.new_cost),
            "change_percent": round(
                (float(audit.new_cost - audit.old_cost) / float(audit.old_cost)) * 100, 2
            ) if audit.old_cost else 0,
            "reason": audit.reason,
            "batch_id": str(audit.ingestion_batch_id) if audit.ingestion_batch_id else None
        })
    
    return {
        "cost_record_id": str(cost_record_id),
        "service": record.service,
        "recorded_at": record.recorded_at.isoformat() if hasattr(record.recorded_at, 'isoformat') else str(record.recorded_at),
        "current_cost": float(record.cost_usd),
        "is_preliminary": record.is_preliminary,
        "timeline": timeline,
        "restatement_count": len(timeline)
    }


@router.get("/lineage/summary")
async def get_ingestion_summary(
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$", description="Month in YYYY-MM format"),
):
    """
    Phase 1.3: Monthly ingestion summary report.
    Shows records processed, deduplicated, and restated.
    """
    from sqlalchemy import func, extract
    from app.models.cloud import CostRecord
    from app.models.cost_audit import CostAuditLog
    
    year, month_num = month.split("-")
    
    # Total records for the month
    total_result = await db.execute(
        select(func.count(CostRecord.id))
        .where(
            CostRecord.tenant_id == tenant_id,
            extract("year", CostRecord.recorded_at) == int(year),
            extract("month", CostRecord.recorded_at) == int(month_num)
        )
    )
    total_records = total_result.scalar() or 0
    
    # Records with ingestion metadata (processed)
    processed_result = await db.execute(
        select(func.count(CostRecord.id))
        .where(
            CostRecord.tenant_id == tenant_id,
            extract("year", CostRecord.recorded_at) == int(year),
            extract("month", CostRecord.recorded_at) == int(month_num),
            CostRecord.ingestion_metadata.isnot(None)
        )
    )
    processed_records = processed_result.scalar() or 0
    
    # Restatements for the month (from audit logs)
    restated_result = await db.execute(
        select(func.count(CostAuditLog.id))
        .join(CostRecord, sa.and_(
            CostAuditLog.cost_record_id == CostRecord.id,
            CostAuditLog.cost_recorded_at == CostRecord.recorded_at
        ))
        .where(
            CostRecord.tenant_id == tenant_id,
            extract("year", CostAuditLog.cost_recorded_at) == int(year),
            extract("month", CostAuditLog.cost_recorded_at) == int(month_num)
        )
    )
    restated_count = restated_result.scalar() or 0
    
    # Average restatement delta
    avg_delta_result = await db.execute(
        select(func.avg(CostAuditLog.new_cost - CostAuditLog.old_cost))
        .join(CostRecord, sa.and_(
            CostAuditLog.cost_record_id == CostRecord.id,
            CostAuditLog.cost_recorded_at == CostRecord.recorded_at
        ))
        .where(
            CostRecord.tenant_id == tenant_id,
            extract("year", CostAuditLog.cost_recorded_at) == int(year),
            extract("month", CostAuditLog.cost_recorded_at) == int(month_num)
        )
    )
    avg_delta = avg_delta_result.scalar() or 0
    
    return {
        "month": month,
        "total_records": total_records,
        "processed_with_metadata": processed_records,
        "restated_count": restated_count,
        "average_restatement_delta_usd": round(float(avg_delta), 4) if avg_delta else 0,
        "data_quality_score": round((1 - (restated_count / max(total_records, 1))) * 100, 1)
    }


# =============================================================================
# Phase 3.2: Anomaly Markers for Forecast Tuning
# =============================================================================

@router.get("/anomaly-markers")
async def list_anomaly_markers(
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
):
    """List all anomaly markers for forecast tuning."""
    from app.models.anomaly_marker import AnomalyMarker
    
    result = await db.execute(
        select(AnomalyMarker)
        .where(AnomalyMarker.tenant_id == tenant_id)
        .order_by(desc(AnomalyMarker.start_date))
    )
    markers = result.scalars().all()
    
    return {
        "markers": [
            {
                "id": str(m.id),
                "label": m.label,
                "marker_type": m.marker_type,
                "start_date": m.start_date.isoformat(),
                "end_date": m.end_date.isoformat(),
                "service_filter": m.service_filter,
                "description": m.description,
                "exclude_from_training": m.exclude_from_training,
                "created_at": m.created_at.isoformat() if m.created_at else None
            }
            for m in markers
        ],
        "count": len(markers)
    }


class AnomalyMarkerCreate(BaseModel):
    label: str
    marker_type: str = "EXPECTED_SPIKE"
    start_date: date
    end_date: date
    service_filter: str | None = None
    description: str | None = None
    exclude_from_training: bool = True


@router.post("/anomaly-markers")
async def create_anomaly_marker(
    body: AnomalyMarkerCreate,
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db),
):
    """
    Phase 3.2: Create an anomaly marker.
    Mark a date range as expected anomaly (Black Friday, batch job, etc.)
    """
    from app.models.anomaly_marker import AnomalyMarker
    
    marker = AnomalyMarker(
        tenant_id=tenant_id,
        label=body.label,
        marker_type=body.marker_type,
        start_date=body.start_date,
        end_date=body.end_date,
        service_filter=body.service_filter,
        description=body.description,
        exclude_from_training=body.exclude_from_training,
        created_by=user.id
    )
    db.add(marker)
    await db.commit()
    await db.refresh(marker)
    
    logger.info("anomaly_marker_created", 
                marker_id=str(marker.id), 
                label=body.label,
                tenant_id=str(tenant_id))
    
    return {"id": str(marker.id), "message": "Anomaly marker created"}


@router.delete("/anomaly-markers/{marker_id}")
async def delete_anomaly_marker(
    marker_id: UUID,
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db),
):
    """Delete an anomaly marker."""
    from app.models.anomaly_marker import AnomalyMarker
    from fastapi import HTTPException
    
    result = await db.execute(
        select(AnomalyMarker).where(
            AnomalyMarker.id == marker_id,
            AnomalyMarker.tenant_id == tenant_id
        )
    )
    marker = result.scalar_one_or_none()
    
    if not marker:
        raise HTTPException(status_code=404, detail="Anomaly marker not found")
    
    await db.delete(marker)
    await db.commit()
    
    return {"message": "Anomaly marker deleted"}


# ==================== Attribution Rules API ====================
# BE-FIN-ATTR-1: Attribution engine endpoints for rule-based cost allocation

class AttributionRuleCreate(BaseModel):
    """Request body for creating an attribution rule."""
    name: str
    rule_type: Literal["DIRECT", "PERCENTAGE", "FIXED"] = "DIRECT"
    priority: int = 100
    conditions: dict  # e.g., {"service": "AmazonS3", "tags": {"Team": "Ops"}}
    allocation: list  # e.g., [{"bucket": "Ops", "percentage": 100}]


class AttributionRuleResponse(BaseModel):
    """Response for attribution rule."""
    id: UUID
    name: str
    rule_type: str
    priority: int
    conditions: dict
    allocation: list
    is_active: bool


@router.post("/attribution/rules")
async def create_attribution_rule(
    body: AttributionRuleCreate,
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new attribution rule for cost allocation.
    
    Rule types:
    - DIRECT: Allocate 100% to a single bucket
    - PERCENTAGE: Split costs across multiple buckets by percentage
    - FIXED: Allocate fixed amounts, remainder goes to 'Unallocated'
    """
    from app.models.attribution import AttributionRule
    
    rule = AttributionRule(
        tenant_id=tenant_id,
        name=body.name,
        rule_type=body.rule_type,
        priority=body.priority,
        conditions=body.conditions,
        allocation=body.allocation,
        is_active=True
    )
    
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    
    logger.info("attribution_rule_created", rule_id=str(rule.id), name=body.name)
    
    return AttributionRuleResponse(
        id=rule.id,
        name=rule.name,
        rule_type=rule.rule_type,
        priority=rule.priority,
        conditions=rule.conditions,
        allocation=rule.allocation,
        is_active=rule.is_active
    )


@router.get("/attribution/rules")
async def list_attribution_rules(
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
):
    """List all attribution rules for the tenant."""
    from app.models.attribution import AttributionRule
    
    result = await db.execute(
        select(AttributionRule)
        .where(AttributionRule.tenant_id == tenant_id)
        .order_by(AttributionRule.priority.asc())
    )
    rules = result.scalars().all()
    
    return [
        AttributionRuleResponse(
            id=r.id,
            name=r.name,
            rule_type=r.rule_type,
            priority=r.priority,
            conditions=r.conditions,
            allocation=r.allocation,
            is_active=r.is_active
        )
        for r in rules
    ]


@router.get("/attribution/summary")
async def get_allocation_summary(
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    start_date: date | None = None,
    end_date: date | None = None,
    bucket: str | None = Query(None, description="Filter by specific allocation bucket"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get aggregated cost allocation summary by bucket.
    Shows how costs are distributed across teams/projects/buckets.
    """
    from app.services.costs.attribution_engine import AttributionEngine
    from datetime import datetime, timezone
    
    engine = AttributionEngine(db)
    
    start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc) if start_date else None
    end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc) if end_date else None
    
    summary = await engine.get_allocation_summary(
        tenant_id=tenant_id,
        start_date=start_dt,
        end_date=end_dt,
        bucket=bucket
    )
    
    return summary


@router.delete("/attribution/rules/{rule_id}")
async def delete_attribution_rule(
    rule_id: UUID,
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db),
):
    """Delete an attribution rule."""
    from app.models.attribution import AttributionRule
    from fastapi import HTTPException
    
    result = await db.execute(
        select(AttributionRule).where(
            AttributionRule.id == rule_id,
            AttributionRule.tenant_id == tenant_id
        )
    )
    rule = result.scalar_one_or_none()
    
    if not rule:
        raise HTTPException(status_code=404, detail="Attribution rule not found")
    
    await db.delete(rule)
    await db.commit()
    
    logger.info("attribution_rule_deleted", rule_id=str(rule_id))
    
    return {"message": "Attribution rule deleted"}
