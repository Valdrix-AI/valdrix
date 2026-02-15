from datetime import date, timedelta
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reporting.domain.attribution_engine import AttributionEngine
from app.shared.core.auth import CurrentUser
from app.shared.core.dependencies import requires_feature
from app.shared.core.pricing import FeatureFlag
from app.shared.db.session import get_db
from app.modules.governance.domain.security.audit_log import AuditEventType, AuditLogger

router = APIRouter(tags=["Attribution"])


def _tenant_id_or_403(current_user: CurrentUser) -> UUID:
    if current_user.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")
    return current_user.tenant_id


class RuleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    priority: int = Field(default=100, ge=1, le=10_000)
    rule_type: Literal["DIRECT", "PERCENTAGE", "FIXED"]
    conditions: Dict[str, Any] = Field(default_factory=dict)
    allocation: Dict[str, Any] | List[Dict[str, Any]]
    is_active: bool = True


class RuleCreateRequest(RuleBase):
    pass


class RuleUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    priority: Optional[int] = Field(default=None, ge=1, le=10_000)
    rule_type: Optional[Literal["DIRECT", "PERCENTAGE", "FIXED"]] = None
    conditions: Optional[Dict[str, Any]] = None
    allocation: Optional[Dict[str, Any] | List[Dict[str, Any]]] = None
    is_active: Optional[bool] = None


class RuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    priority: int
    rule_type: str
    conditions: Dict[str, Any]
    allocation: Dict[str, Any] | List[Dict[str, Any]]
    is_active: bool


class RuleSimulationRequest(BaseModel):
    rule_type: Literal["DIRECT", "PERCENTAGE", "FIXED"]
    conditions: Dict[str, Any] = Field(default_factory=dict)
    allocation: Dict[str, Any] | List[Dict[str, Any]]
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    sample_limit: int = Field(default=500, ge=1, le=5000)


class ApplyAttributionRequest(BaseModel):
    start_date: date
    end_date: date


@router.get("/rules", response_model=List[RuleRead])
async def list_rules(
    include_inactive: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(requires_feature(FeatureFlag.CHARGEBACK)),
) -> List[RuleRead]:
    tenant_id = _tenant_id_or_403(current_user)
    engine = AttributionEngine(db)
    rules = await engine.list_rules(tenant_id, include_inactive=include_inactive)
    return [RuleRead.model_validate(rule) for rule in rules]


@router.post("/rules", response_model=RuleRead)
async def create_rule(
    request: Request,
    payload: RuleCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(
        requires_feature(FeatureFlag.CHARGEBACK, "admin")
    ),
) -> RuleRead:
    tenant_id = _tenant_id_or_403(current_user)
    engine = AttributionEngine(db)
    errors = engine.validate_rule_payload(payload.rule_type, payload.allocation)
    if errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))

    rule = await engine.create_rule(
        tenant_id,
        name=payload.name,
        priority=payload.priority,
        rule_type=payload.rule_type,
        conditions=payload.conditions,
        allocation=payload.allocation,
        is_active=payload.is_active,
    )
    audit = AuditLogger(db, tenant_id=tenant_id)
    await audit.log(
        event_type=AuditEventType.ATTRIBUTION_RULE_CREATED,
        actor_id=current_user.id,
        actor_email=current_user.email,
        resource_type="attribution_rule",
        resource_id=str(rule.id),
        details={
            "name": payload.name,
            "priority": payload.priority,
            "rule_type": payload.rule_type,
            "is_active": payload.is_active,
        },
        request_method=request.method,
        request_path=str(request.url.path),
    )
    await db.commit()
    return RuleRead.model_validate(rule)


@router.patch("/rules/{rule_id}", response_model=RuleRead)
async def update_rule(
    request: Request,
    rule_id: UUID,
    payload: RuleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(
        requires_feature(FeatureFlag.CHARGEBACK, "admin")
    ),
) -> RuleRead:
    tenant_id = _tenant_id_or_403(current_user)
    engine = AttributionEngine(db)
    existing_rule = await engine.get_rule(tenant_id, rule_id)
    if not existing_rule:
        raise HTTPException(status_code=404, detail="Attribution rule not found")

    updates = payload.model_dump(exclude_unset=True)
    if "rule_type" in updates or "allocation" in updates:
        rule_type = str(updates.get("rule_type", existing_rule.rule_type))
        allocation = updates.get("allocation", existing_rule.allocation)
        errors = engine.validate_rule_payload(rule_type, allocation)
        if errors:
            raise HTTPException(status_code=422, detail="; ".join(errors))

    updated = await engine.update_rule(tenant_id, rule_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Attribution rule not found")
    audit = AuditLogger(db, tenant_id=tenant_id)
    await audit.log(
        event_type=AuditEventType.ATTRIBUTION_RULE_UPDATED,
        actor_id=current_user.id,
        actor_email=current_user.email,
        resource_type="attribution_rule",
        resource_id=str(rule_id),
        details={"updates": updates},
        request_method=request.method,
        request_path=str(request.url.path),
    )
    await db.commit()
    return RuleRead.model_validate(updated)


@router.delete("/rules/{rule_id}")
async def delete_rule(
    request: Request,
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(
        requires_feature(FeatureFlag.CHARGEBACK, "admin")
    ),
) -> Dict[str, Any]:
    tenant_id = _tenant_id_or_403(current_user)
    engine = AttributionEngine(db)
    deleted = await engine.delete_rule(tenant_id, rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Attribution rule not found")
    audit = AuditLogger(db, tenant_id=tenant_id)
    await audit.log(
        event_type=AuditEventType.ATTRIBUTION_RULE_DELETED,
        actor_id=current_user.id,
        actor_email=current_user.email,
        resource_type="attribution_rule",
        resource_id=str(rule_id),
        details={},
        request_method=request.method,
        request_path=str(request.url.path),
    )
    await db.commit()
    return {"status": "deleted", "rule_id": str(rule_id)}


@router.post("/simulate")
async def simulate_rule(
    request: Request,
    payload: RuleSimulationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(requires_feature(FeatureFlag.CHARGEBACK)),
) -> Dict[str, Any]:
    tenant_id = _tenant_id_or_403(current_user)
    engine = AttributionEngine(db)
    errors = engine.validate_rule_payload(payload.rule_type, payload.allocation)
    if errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))

    end_date = payload.end_date or date.today()
    start_date = payload.start_date or (end_date - timedelta(days=30))
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")

    response = await engine.simulate_rule(
        tenant_id,
        rule_type=payload.rule_type,
        conditions=payload.conditions,
        allocation=payload.allocation,
        start_date=start_date,
        end_date=end_date,
        sample_limit=payload.sample_limit,
    )
    audit = AuditLogger(db, tenant_id=tenant_id)
    await audit.log(
        event_type=AuditEventType.ATTRIBUTION_RULE_SIMULATED,
        actor_id=current_user.id,
        actor_email=current_user.email,
        resource_type="attribution_rule",
        resource_id=None,
        details={
            "rule_type": payload.rule_type,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "matched_records": response.get("matched_records"),
        },
        request_method=request.method,
        request_path=str(request.url.path),
    )
    await db.commit()
    return response


@router.post("/apply")
async def apply_rules(
    request: Request,
    payload: ApplyAttributionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(
        requires_feature(FeatureFlag.CHARGEBACK, "admin")
    ),
) -> Dict[str, Any]:
    tenant_id = _tenant_id_or_403(current_user)
    if payload.start_date > payload.end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")

    engine = AttributionEngine(db)
    stats = await engine.apply_rules_to_tenant(
        tenant_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    audit = AuditLogger(db, tenant_id=tenant_id)
    await audit.log(
        event_type=AuditEventType.ATTRIBUTION_RULES_APPLIED,
        actor_id=current_user.id,
        actor_email=current_user.email,
        resource_type="attribution_rules",
        resource_id=None,
        details={
            "start_date": payload.start_date.isoformat(),
            "end_date": payload.end_date.isoformat(),
            **stats,
        },
        request_method=request.method,
        request_path=str(request.url.path),
    )
    await db.commit()
    return {"status": "completed", **stats}


@router.get("/coverage")
async def get_coverage_kpis(
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    target_percentage: float = Query(default=90.0, ge=0.0, le=100.0),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(requires_feature(FeatureFlag.CHARGEBACK)),
) -> Dict[str, Any]:
    """
    Return allocation coverage KPIs (chargeback/showback readiness).

    This is also available under /api/v1/costs/attribution/coverage, but this endpoint keeps the
    attribution surface self-contained for API consumers.
    """
    tenant_id = _tenant_id_or_403(current_user)
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")
    return await AttributionEngine(db).get_allocation_coverage(
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date,
        target_percentage=target_percentage,
    )


@router.get("/unallocated-analysis")
async def get_unallocated_analysis(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(requires_feature(FeatureFlag.CHARGEBACK)),
) -> Dict[str, Any]:
    """
    Identify the top unallocated services and recommend the next rules to add.
    """
    tenant_id = _tenant_id_or_403(current_user)
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")
    engine = AttributionEngine(db)
    analysis = await engine.get_unallocated_analysis(tenant_id, start_date, end_date)
    return {
        "status": "success",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "items": analysis,
    }
