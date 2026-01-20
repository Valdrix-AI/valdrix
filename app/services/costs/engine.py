import logging
import uuid
from typing import List, Dict, Any
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from app.models.cloud import CostRecord
from app.models.attribution import AttributionRule, CostAllocation
from decimal import Decimal

logger = logging.getLogger(__name__)

class AttributionEngine:
    """
    Core engine for cost attribution and allocation.
    Matches unallocated CostRecords against prioritized AttributionRules.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def apply_rules_to_tenant(self, tenant_id: uuid.UUID):
        """
        Fetches all unallocated records for a tenant and applies active rules.
        """
        # 1. Fetch active rules for tenant, sorted by priority
        rules_stmt = select(AttributionRule).where(
            AttributionRule.tenant_id == tenant_id,
            AttributionRule.is_active == True
        ).order_by(AttributionRule.priority.asc())
        
        result = await self.db.execute(rules_stmt)
        rules = result.scalars().all()
        
        if not rules:
            logger.info("no_attribution_rules_found", tenant_id=str(tenant_id))
            # Optional: Bucket everything to "Unallocated"
            await self._bucket_to_unallocated(tenant_id)
            return

        # 2. Fetch unallocated cost records
        records_stmt = select(CostRecord).where(
            CostRecord.tenant_id == tenant_id,
            CostRecord.attribution_id == None
        )
        
        result = await self.db.execute(records_stmt)
        records = result.scalars().all()
        
        if not records:
            logger.info("no_unallocated_records_found", tenant_id=str(tenant_id))
            return

        logger.info("starting_attribution_run", 
                    tenant_id=str(tenant_id), 
                    rules_count=len(rules), 
                    records_count=len(records))

        allocated_count = 0
        
        # 3. Simple matching loop (Phase 2 MVP)
        # Note: In a production enterprise system, this would be optimized for large datasets
        for record in records:
            matched = False
            for rule in rules:
                if self._matches(record, rule.conditions):
                    await self._allocate(record, rule)
                    matched = True
                    allocated_count += 1
                    break # First match wins based on priority
            
            if not matched:
                record.allocated_to = "Unallocated"
        
        await self.db.commit()
        logger.info("attribution_run_complete", 
                    tenant_id=str(tenant_id), 
                    allocated_count=allocated_count)

    def _matches(self, record: CostRecord, conditions: Dict[str, Any]) -> bool:
        """
        Basic condition matching logic.
        Supports matching on service and exact tag values.
        """
        # Match service
        if "service" in conditions and conditions["service"] != record.service:
            return False
            
        # Match region
        if "region" in conditions and conditions["region"] != record.region:
            return False

        # Match tags (assuming tags are available in ingestion_metadata for now)
        if "tags" in conditions:
            record_tags = (record.ingestion_metadata or {}).get("tags", {})
            for key, val in conditions["tags"].items():
                if record_tags.get(key) != val:
                    return False
        
        return True

    async def _allocate(self, record: CostRecord, rule: AttributionRule):
        """
        Applies the allocation rule to the record.
        Creates entries in cost_allocations for forensics and split reporting.
        """
        record.attribution_id = rule.id
        allocations = []
        
        if rule.rule_type == "DIRECT":
            # Direct allocation to a single bucket
            bucket = rule.allocation.get("bucket", "Default")
            record.allocated_to = bucket
            allocations.append(
                CostAllocation(
                    cost_record_id=record.id,
                    recorded_at=record.recorded_at,
                    rule_id=rule.id,
                    allocated_to=bucket,
                    amount=record.cost_usd,
                    percentage=Decimal("100.00"),
                    timestamp=record.timestamp or datetime.now(timezone.utc)
                )
            )
        
        elif rule.rule_type == "PERCENTAGE":
            # Split allocation across multiple buckets (e.g. Shared DB split)
            target_allocations = rule.allocation # List[Dict] e.g. [{"bucket": "A", "percent": 30}, ...]
            
            if not isinstance(target_allocations, list):
                logger.error("invalid_percentage_allocation_format", rule_id=str(rule.id))
                record.allocated_to = "Error-Invalid-Format"
                return

            total_allocated_amt = Decimal("0")
            for i, target in enumerate(target_allocations):
                bucket = target.get("bucket", "Default")
                pct_val = target.get("percent", 0)
                pct = Decimal(str(pct_val))
                
                # Last bucket takes the remainder to handle floating point precision
                if i == len(target_allocations) - 1:
                    amt = record.cost_usd - total_allocated_amt
                else:
                    amt = (record.cost_usd * pct / Decimal("100")).quantize(Decimal("1.00000000"))
                
                total_allocated_amt += amt
                
                allocations.append(
                    CostAllocation(
                        cost_record_id=record.id,
                        recorded_at=record.recorded_at,
                        rule_id=rule.id,
                        allocated_to=bucket,
                        amount=amt,
                        percentage=pct,
                        timestamp=record.timestamp or datetime.now(timezone.utc)
                    )
                )
            record.allocated_to = "Split"

        if allocations:
            self.db.add_all(allocations)

    async def _bucket_to_unallocated(self, tenant_id: uuid.UUID):
        """
        Marks all unallocated records for a tenant as 'Unallocated'.
        """
        stmt = (
            update(CostRecord)
            .where(
                CostRecord.tenant_id == tenant_id,
                CostRecord.attribution_id == None
            )
            .values(allocated_to="Unallocated")
        )
        await self.db.execute(stmt)
        await self.db.commit()
