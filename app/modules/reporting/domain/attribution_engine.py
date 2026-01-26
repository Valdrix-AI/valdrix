"""
Attribution Engine for rule-based cost allocation.
BE-FIN-ATTR-1: Implements the missing allocation engine identified in the Principal Engineer Review.
"""
from typing import List, Dict, Any, Optional
from decimal import Decimal
from datetime import datetime, timezone, date
import uuid
import structlog

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.attribution import AttributionRule, CostAllocation
from app.models.cloud import CostRecord

logger = structlog.get_logger()


class AttributionEngine:
    """
    Applies attribution rules to cost records, creating CostAllocation records
    for percentage-based splits, direct allocations, and fixed allocations.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active_rules(self, tenant_id: uuid.UUID) -> List[AttributionRule]:
        """
        Retrieve all active attribution rules for a tenant, ordered by priority.
        Lower priority numbers are evaluated first.
        """
        query = (
            select(AttributionRule)
            .where(AttributionRule.tenant_id == tenant_id)
            .where(AttributionRule.is_active)
            .order_by(AttributionRule.priority.asc())
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    def match_conditions(self, cost_record: CostRecord, conditions: Dict[str, Any]) -> bool:
        """
        Check if a cost record matches the rule conditions.
        Supports matching on: service, region, account_id, tags.
        """
        # Service match
        if "service" in conditions:
            if cost_record.service != conditions["service"]:
                return False

        # Region match
        if "region" in conditions:
            if cost_record.region != conditions["region"]:
                return False

        # Account match
        if "account_id" in conditions:
            if cost_record.account_id != conditions["account_id"]:
                return False

        # Tags match (all specified tags must match)
        if "tags" in conditions:
            cost_tags = cost_record.tags or {}
            for tag_key, tag_value in conditions["tags"].items():
                if cost_tags.get(tag_key) != tag_value:
                    return False

        # If no conditions failed, it's a match
        return True

    async def apply_rules(
        self,
        cost_record: CostRecord,
        rules: List[AttributionRule]
    ) -> List[CostAllocation]:
        """
        Apply attribution rules to a cost record and return CostAllocation records.
        First matching rule wins (rules are pre-sorted by priority).
        """
        allocations = []

        for rule in rules:
            if not self.match_conditions(cost_record, rule.conditions):
                continue

            # Rule matches - create allocations based on rule type
            if rule.rule_type == "DIRECT":
                # Direct allocation to a single bucket
                allocation_config = rule.allocation
                if isinstance(allocation_config, list) and len(allocation_config) > 0:
                    bucket = allocation_config[0].get("bucket", "Unallocated")
                elif isinstance(allocation_config, dict):
                    bucket = allocation_config.get("bucket", "Unallocated")
                else:
                    bucket = "Unallocated"

                allocation = CostAllocation(
                    cost_record_id=cost_record.id,
                    recorded_at=cost_record.recorded_at,
                    rule_id=rule.id,
                    allocated_to=bucket,
                    amount=cost_record.cost_usd,
                    percentage=Decimal("100.00"),
                    timestamp=datetime.now(timezone.utc)
                )
                allocations.append(allocation)

            elif rule.rule_type == "PERCENTAGE":
                # Percentage-based split across multiple buckets
                allocation_config = rule.allocation
                if not isinstance(allocation_config, list):
                    allocation_config = [allocation_config]

                total_percentage = Decimal("0")
                for split in allocation_config:
                    bucket = split.get("bucket", "Unallocated")
                    pct = Decimal(str(split.get("percentage", 0)))
                    total_percentage += pct

                    split_amount = (cost_record.cost_usd * pct) / Decimal("100")
                    allocation = CostAllocation(
                        cost_record_id=cost_record.id,
                        recorded_at=cost_record.recorded_at,
                        rule_id=rule.id,
                        allocated_to=bucket,
                        amount=split_amount,
                        percentage=pct,
                        timestamp=datetime.now(timezone.utc)
                    )
                    allocations.append(allocation)

                # Warn if percentages don't sum to 100
                if total_percentage != Decimal("100"):
                    logger.warning(
                        "attribution_percentage_mismatch",
                        rule_id=str(rule.id),
                        total=float(total_percentage)
                    )

            elif rule.rule_type == "FIXED":
                # Fixed amount allocation (remaining goes to default bucket)
                allocation_config = rule.allocation
                if not isinstance(allocation_config, list):
                    allocation_config = [allocation_config]

                allocated_total = Decimal("0")
                for split in allocation_config:
                    bucket = split.get("bucket", "Unallocated")
                    fixed_amount = Decimal(str(split.get("amount", 0)))
                    allocated_total += fixed_amount

                    allocation = CostAllocation(
                        cost_record_id=cost_record.id,
                        recorded_at=cost_record.recorded_at,
                        rule_id=rule.id,
                        allocated_to=bucket,
                        amount=fixed_amount,
                        percentage=None,
                        timestamp=datetime.now(timezone.utc)
                    )
                    allocations.append(allocation)

                # Remaining goes to "Unallocated"
                remaining = cost_record.cost_usd - allocated_total
                if remaining > Decimal("0"):
                    allocation = CostAllocation(
                        cost_record_id=cost_record.id,
                        recorded_at=cost_record.recorded_at,
                        rule_id=rule.id,
                        allocated_to="Unallocated",
                        amount=remaining,
                        percentage=None,
                        timestamp=datetime.now(timezone.utc)
                    )
                    allocations.append(allocation)

            # First matching rule wins - stop processing
            break

        # If no rule matched, create a default allocation
        if not allocations:
            allocations.append(
                CostAllocation(
                    cost_record_id=cost_record.id,
                    recorded_at=cost_record.recorded_at,
                    rule_id=None,
                    allocated_to="Unallocated",
                    amount=cost_record.cost_usd,
                    percentage=Decimal("100.00"),
                    timestamp=datetime.now(timezone.utc)
                )
            )

        return allocations

    async def process_cost_record(
        self,
        cost_record: CostRecord,
        tenant_id: uuid.UUID
    ) -> List[CostAllocation]:
        """
        Full pipeline: Get rules for tenant, apply to cost record, persist allocations.
        """
        rules = await self.get_active_rules(tenant_id)
        allocations = await self.apply_rules(cost_record, rules)

        # Persist allocations
        for allocation in allocations:
            self.db.add(allocation)

        await self.db.commit()

        logger.info(
            "attribution_applied",
            cost_record_id=str(cost_record.id),
            allocations_count=len(allocations)
        )

        return allocations

    async def apply_rules_to_tenant(
        self,
        tenant_id: uuid.UUID,
        start_date: date,
        end_date: date
    ) -> None:
        """
        Batch apply attribution rules to all cost records for a tenant within a date range.
        Used for recalculation or historical reconciliation.
        """
        # 1. Fetch all cost records in range
        query = (
            select(CostRecord)
            .where(CostRecord.tenant_id == tenant_id)
            .where(CostRecord.recorded_at >= start_date)
            .where(CostRecord.recorded_at <= end_date)
        )
        result = await self.db.execute(query)
        records = result.scalars().all()

        if not records:
            logger.info("no_cost_records_found_for_attribution", tenant_id=str(tenant_id))
            return

        # 2. Get active rules
        rules = await self.get_active_rules(tenant_id)

        # 3. Process each record
        for record in records:
            # Delete existing allocations for this record to avoid duplicates
            from sqlalchemy import delete
            await self.db.execute(
                delete(CostAllocation).where(CostAllocation.cost_record_id == record.id)
            )

            allocations = await self.apply_rules(record, rules)
            for allocation in allocations:
                self.db.add(allocation)

        await self.db.commit()
        logger.info(
            "batch_attribution_complete",
            tenant_id=str(tenant_id),
            records_processed=len(records)
        )

    async def get_allocation_summary(
        self,
        tenant_id: uuid.UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        bucket: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get aggregated allocation summary by bucket for a tenant.
        """
        from sqlalchemy import func

        query = (
            select(
                CostAllocation.allocated_to,
                func.sum(CostAllocation.amount).label("total_amount"),
                func.count(CostAllocation.id).label("record_count")
            )
            .join(CostRecord, 
                  (CostAllocation.cost_record_id == CostRecord.id) & 
                  (CostAllocation.recorded_at == CostRecord.recorded_at))
            .where(CostRecord.tenant_id == tenant_id)
            .group_by(CostAllocation.allocated_to)
            .order_by(func.sum(CostAllocation.amount).desc())
        )

        if start_date:
            query = query.where(CostAllocation.timestamp >= start_date)
        if end_date:
            query = query.where(CostAllocation.timestamp <= end_date)
        if bucket:
            query = query.where(CostAllocation.allocated_to == bucket)

        result = await self.db.execute(query)
        rows = result.all()

        summary = {
            "buckets": [
                {
                    "name": row.allocated_to,
                    "total_amount": float(row.total_amount),
                    "record_count": row.record_count
                }
                for row in rows
            ],
            "total": sum(float(row.total_amount) for row in rows)
        }

        return summary
    async def get_unallocated_analysis(
        self,
        tenant_id: uuid.UUID,
        start_date: date,
        end_date: date
    ) -> List[Dict[str, Any]]:
        """
        Identify top services contributing to unallocated spend.
        Provides recommendations for attribution rules.
        """
        from sqlalchemy import func
        
        query = (
            select(
                CostRecord.service,
                func.sum(CostRecord.cost_usd).label("total_unallocated"),
                func.count(CostRecord.id).label("record_count")
            )
            .where(CostRecord.tenant_id == tenant_id)
            .where(CostRecord.recorded_at >= start_date)
            .where(CostRecord.recorded_at <= end_date)
            .where((CostRecord.allocated_to.is_(None)) | (CostRecord.allocated_to == "Unallocated"))
            .group_by(CostRecord.service)
            .order_by(func.sum(CostRecord.cost_usd).desc())
            .limit(5)
        )
        
        result = await self.db.execute(query)
        rows = result.all()
        
        analysis = []
        for row in rows:
            analysis.append({
                "service": row.service,
                "amount": float(row.total_unallocated),
                "count": row.record_count,
                "recommendation": f"Create a DIRECT rule for service '{row.service}' to a specific team bucket."
            })
            
        return analysis
