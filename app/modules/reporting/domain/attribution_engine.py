"""
Attribution Engine for rule-based cost allocation.
BE-FIN-ATTR-1: Implements the missing allocation engine identified in the Principal Engineer Review.
"""

from typing import Any, Dict, List, Optional
from decimal import Decimal
from datetime import datetime, timezone, date
import uuid
import structlog

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select

from app.models.attribution import AttributionRule, CostAllocation
from app.models.cloud import CostRecord

logger = structlog.get_logger()
VALID_RULE_TYPES = {"DIRECT", "PERCENTAGE", "FIXED"}


class AttributionEngine:
    """
    Applies attribution rules to cost records, creating CostAllocation records
    for percentage-based splits, direct allocations, and fixed allocations.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    def normalize_rule_type(self, rule_type: str) -> str:
        """Normalize rule type to uppercase for consistent matching."""
        return (rule_type or "").strip().upper()

    def validate_rule_payload(self, rule_type: str, allocation: Any) -> List[str]:
        """
        Validate allocation payload shape for a rule type.
        Returns a list of validation error messages; empty list means valid.
        """
        errors: List[str] = []
        normalized_type = self.normalize_rule_type(rule_type)
        if normalized_type not in VALID_RULE_TYPES:
            errors.append(f"rule_type must be one of {sorted(VALID_RULE_TYPES)}")
            return errors

        entries = self._allocation_entries(allocation)

        if normalized_type == "DIRECT":
            if len(entries) != 1:
                errors.append("DIRECT allocation must define exactly one bucket.")
            elif not entries[0].get("bucket"):
                errors.append("DIRECT allocation requires a non-empty 'bucket'.")

        elif normalized_type == "PERCENTAGE":
            if not entries:
                errors.append(
                    "PERCENTAGE allocation requires at least one split entry."
                )
            total_percentage = Decimal("0")
            for split in entries:
                if not split.get("bucket"):
                    errors.append(
                        "Each PERCENTAGE split requires a non-empty 'bucket'."
                    )
                percentage_raw = split.get("percentage")
                try:
                    percentage = Decimal(str(percentage_raw))
                except Exception:
                    errors.append(
                        "Each PERCENTAGE split requires numeric 'percentage'."
                    )
                    continue
                if percentage < 0:
                    errors.append("PERCENTAGE split cannot be negative.")
                total_percentage += percentage
            if entries and total_percentage != Decimal("100"):
                errors.append("PERCENTAGE split percentages must sum to 100.")

        elif normalized_type == "FIXED":
            if not entries:
                errors.append("FIXED allocation requires at least one split entry.")
            for split in entries:
                if not split.get("bucket"):
                    errors.append("Each FIXED split requires a non-empty 'bucket'.")
                amount_raw = split.get("amount")
                try:
                    amount = Decimal(str(amount_raw))
                except Exception:
                    errors.append("Each FIXED split requires numeric 'amount'.")
                    continue
                if amount < 0:
                    errors.append("FIXED split amount cannot be negative.")

        return errors

    def _allocation_entries(self, allocation: Any) -> List[Dict[str, Any]]:
        """Normalize allocation payload to a list of dict entries."""
        if isinstance(allocation, list):
            return [item for item in allocation if isinstance(item, dict)]
        if isinstance(allocation, dict):
            return [allocation]
        return []

    async def list_rules(
        self, tenant_id: uuid.UUID, include_inactive: bool = False
    ) -> List[AttributionRule]:
        """List tenant attribution rules ordered by priority."""
        query = select(AttributionRule).where(AttributionRule.tenant_id == tenant_id)
        if not include_inactive:
            query = query.where(AttributionRule.is_active)
        query = query.order_by(
            AttributionRule.priority.asc(), AttributionRule.name.asc()
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_rule(
        self, tenant_id: uuid.UUID, rule_id: uuid.UUID
    ) -> Optional[AttributionRule]:
        """Fetch one attribution rule scoped to tenant."""
        query = (
            select(AttributionRule)
            .where(AttributionRule.tenant_id == tenant_id)
            .where(AttributionRule.id == rule_id)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def create_rule(
        self,
        tenant_id: uuid.UUID,
        *,
        name: str,
        priority: int,
        rule_type: str,
        conditions: Dict[str, Any],
        allocation: Any,
        is_active: bool = True,
    ) -> AttributionRule:
        """Create and persist a tenant attribution rule."""
        normalized_type = self.normalize_rule_type(rule_type)
        rule = AttributionRule(
            tenant_id=tenant_id,
            name=name,
            priority=priority,
            rule_type=normalized_type,
            conditions=conditions,
            allocation=allocation,
            is_active=is_active,
        )
        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)
        return rule

    async def update_rule(
        self,
        tenant_id: uuid.UUID,
        rule_id: uuid.UUID,
        updates: Dict[str, Any],
    ) -> Optional[AttributionRule]:
        """Update an existing attribution rule."""
        rule = await self.get_rule(tenant_id, rule_id)
        if not rule:
            return None

        if "rule_type" in updates and isinstance(updates["rule_type"], str):
            updates["rule_type"] = self.normalize_rule_type(updates["rule_type"])

        for field in (
            "name",
            "priority",
            "rule_type",
            "conditions",
            "allocation",
            "is_active",
        ):
            if field in updates and updates[field] is not None:
                setattr(rule, field, updates[field])

        await self.db.commit()
        await self.db.refresh(rule)
        return rule

    async def delete_rule(self, tenant_id: uuid.UUID, rule_id: uuid.UUID) -> bool:
        """Delete one tenant rule and return whether it existed."""
        rule = await self.get_rule(tenant_id, rule_id)
        if not rule:
            return False
        await self.db.delete(rule)
        await self.db.commit()
        return True

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

    def match_conditions(
        self, cost_record: CostRecord, conditions: Dict[str, Any]
    ) -> bool:
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
            direct_tags = getattr(cost_record, "tags", None)
            if isinstance(direct_tags, dict):
                cost_tags = direct_tags
            else:
                metadata = (
                    cost_record.ingestion_metadata
                    if isinstance(cost_record.ingestion_metadata, dict)
                    else {}
                )
                raw_tags = metadata.get("tags", {})
                cost_tags = raw_tags if isinstance(raw_tags, dict) else {}
            condition_tags = (
                conditions["tags"] if isinstance(conditions["tags"], dict) else {}
            )
            for tag_key, tag_value in condition_tags.items():
                if cost_tags.get(tag_key) != tag_value:
                    return False

        # If no conditions failed, it's a match
        return True

    async def apply_rules(
        self, cost_record: CostRecord, rules: List[AttributionRule]
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
                direct_allocation_raw: Any = rule.allocation
                if (
                    isinstance(direct_allocation_raw, list)
                    and len(direct_allocation_raw) > 0
                ):
                    first_entry = direct_allocation_raw[0]
                    bucket = (
                        first_entry.get("bucket", "Unallocated")
                        if isinstance(first_entry, dict)
                        else "Unallocated"
                    )
                elif isinstance(direct_allocation_raw, dict):
                    bucket = direct_allocation_raw.get("bucket", "Unallocated")
                else:
                    bucket = "Unallocated"

                allocation = CostAllocation(
                    cost_record_id=cost_record.id,
                    recorded_at=cost_record.recorded_at,
                    rule_id=rule.id,
                    allocated_to=bucket,
                    amount=cost_record.cost_usd,
                    percentage=Decimal("100.00"),
                    timestamp=datetime.now(timezone.utc),
                )
                allocations.append(allocation)

            elif rule.rule_type == "PERCENTAGE":
                # Percentage-based split across multiple buckets
                percentage_allocation_raw: Any = rule.allocation
                percentage_splits: list[dict[str, Any]]
                if isinstance(percentage_allocation_raw, list):
                    percentage_splits = [
                        item
                        for item in percentage_allocation_raw
                        if isinstance(item, dict)
                    ]
                elif isinstance(percentage_allocation_raw, dict):
                    percentage_splits = [percentage_allocation_raw]
                else:
                    percentage_splits = []

                total_percentage = Decimal("0")
                for split in percentage_splits:
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
                        timestamp=datetime.now(timezone.utc),
                    )
                    allocations.append(allocation)

                # Warn if percentages don't sum to 100
                if total_percentage != Decimal("100"):
                    logger.warning(
                        "attribution_percentage_mismatch",
                        rule_id=str(rule.id),
                        total=float(total_percentage),
                    )

            elif rule.rule_type == "FIXED":
                # Fixed amount allocation (remaining goes to default bucket)
                fixed_allocation_raw: Any = rule.allocation
                fixed_splits: list[dict[str, Any]]
                if isinstance(fixed_allocation_raw, list):
                    fixed_splits = [
                        item for item in fixed_allocation_raw if isinstance(item, dict)
                    ]
                elif isinstance(fixed_allocation_raw, dict):
                    fixed_splits = [fixed_allocation_raw]
                else:
                    fixed_splits = []

                allocated_total = Decimal("0")
                for split in fixed_splits:
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
                        timestamp=datetime.now(timezone.utc),
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
                        timestamp=datetime.now(timezone.utc),
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
                    timestamp=datetime.now(timezone.utc),
                )
            )

        return allocations

    async def process_cost_record(
        self, cost_record: CostRecord, tenant_id: uuid.UUID
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
            allocations_count=len(allocations),
        )

        return allocations

    async def apply_rules_to_tenant(
        self, tenant_id: uuid.UUID, start_date: date, end_date: date
    ) -> Dict[str, int]:
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
            logger.info(
                "no_cost_records_found_for_attribution", tenant_id=str(tenant_id)
            )
            return {"records_processed": 0, "allocations_created": 0}

        # 2. Get active rules
        rules = await self.get_active_rules(tenant_id)

        # 3. Process each record
        allocations_created = 0
        for record in records:
            # Delete existing allocations for this record to avoid duplicates
            await self.db.execute(
                delete(CostAllocation).where(
                    CostAllocation.cost_record_id == record.id,
                    CostAllocation.recorded_at == record.recorded_at,
                )
            )

            allocations = await self.apply_rules(record, rules)
            for allocation in allocations:
                self.db.add(allocation)
            allocations_created += len(allocations)

        await self.db.commit()
        logger.info(
            "batch_attribution_complete",
            tenant_id=str(tenant_id),
            records_processed=len(records),
            allocations_created=allocations_created,
        )
        return {
            "records_processed": len(records),
            "allocations_created": allocations_created,
        }

    async def get_allocation_summary(
        self,
        tenant_id: uuid.UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        bucket: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get aggregated allocation summary by bucket for a tenant.
        """
        from sqlalchemy import func

        query = (
            select(
                CostAllocation.allocated_to,
                func.sum(CostAllocation.amount).label("total_amount"),
                func.count(CostAllocation.id).label("record_count"),
            )
            .join(
                CostRecord,
                (CostAllocation.cost_record_id == CostRecord.id)
                & (CostAllocation.recorded_at == CostRecord.recorded_at),
            )
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
                    "record_count": row.record_count,
                }
                for row in rows
            ],
            "total": sum(float(row.total_amount) for row in rows),
        }

        return summary

    async def get_allocation_coverage(
        self,
        tenant_id: uuid.UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        target_percentage: float = 90.0,
    ) -> Dict[str, Any]:
        """
        Compute allocation coverage KPI for a tenant and date window.

        Coverage = allocated_cost / total_cost * 100
        """
        from sqlalchemy import func

        total_query = select(
            func.coalesce(func.sum(CostRecord.cost_usd), 0).label("total_cost"),
            func.count(CostRecord.id).label("total_records"),
        ).where(CostRecord.tenant_id == tenant_id)
        if start_date:
            total_query = total_query.where(CostRecord.recorded_at >= start_date)
        if end_date:
            total_query = total_query.where(CostRecord.recorded_at <= end_date)

        total_result = await self.db.execute(total_query)
        total_row = total_result.one()
        total_cost = float(total_row.total_cost or 0)
        total_records = int(total_row.total_records or 0)

        allocated_query = (
            select(
                func.coalesce(func.sum(CostAllocation.amount), 0).label(
                    "allocated_cost"
                ),
                func.count(CostAllocation.id).label("allocation_rows"),
                func.count(func.distinct(CostAllocation.cost_record_id)).label(
                    "allocated_records"
                ),
            )
            .join(
                CostRecord,
                (CostAllocation.cost_record_id == CostRecord.id)
                & (CostAllocation.recorded_at == CostRecord.recorded_at),
            )
            .where(CostRecord.tenant_id == tenant_id)
        )
        if start_date:
            allocated_query = allocated_query.where(
                CostRecord.recorded_at >= start_date
            )
        if end_date:
            allocated_query = allocated_query.where(CostRecord.recorded_at <= end_date)

        allocated_result = await self.db.execute(allocated_query)
        allocated_row = allocated_result.one()
        raw_allocated_cost = float(allocated_row.allocated_cost or 0)
        allocated_cost = min(raw_allocated_cost, total_cost) if total_cost > 0 else 0.0
        over_allocated_cost = max(raw_allocated_cost - total_cost, 0.0)
        coverage_percentage = (
            (allocated_cost / total_cost * 100.0) if total_cost > 0 else 0.0
        )

        return {
            "target_percentage": target_percentage,
            "coverage_percentage": round(coverage_percentage, 2),
            "meets_target": coverage_percentage >= target_percentage
            if total_cost > 0
            else False,
            "status": (
                "no_data"
                if total_cost <= 0
                else ("ok" if coverage_percentage >= target_percentage else "warning")
            ),
            "total_cost": round(total_cost, 6),
            "allocated_cost": round(allocated_cost, 6),
            "unallocated_cost": round(max(total_cost - allocated_cost, 0.0), 6),
            "over_allocated_cost": round(over_allocated_cost, 6),
            "total_records": total_records,
            "allocated_records": int(allocated_row.allocated_records or 0),
            "allocation_rows": int(allocated_row.allocation_rows or 0),
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
        }

    async def get_unallocated_analysis(
        self, tenant_id: uuid.UUID, start_date: date, end_date: date
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
                func.count(CostRecord.id).label("record_count"),
            )
            .where(CostRecord.tenant_id == tenant_id)
            .where(CostRecord.recorded_at >= start_date)
            .where(CostRecord.recorded_at <= end_date)
            .where(
                (CostRecord.allocated_to.is_(None))
                | (CostRecord.allocated_to == "Unallocated")
            )
            .group_by(CostRecord.service)
            .order_by(func.sum(CostRecord.cost_usd).desc())
            .limit(5)
        )

        result = await self.db.execute(query)
        rows = result.all()

        analysis = []
        for row in rows:
            analysis.append(
                {
                    "service": row.service,
                    "amount": float(row.total_unallocated),
                    "count": row.record_count,
                    "recommendation": f"Create a DIRECT rule for service '{row.service}' to a specific team bucket.",
                }
            )

        return analysis

    async def simulate_rule(
        self,
        tenant_id: uuid.UUID,
        *,
        rule_type: str,
        conditions: Dict[str, Any],
        allocation: Any,
        start_date: date,
        end_date: date,
        sample_limit: int = 500,
    ) -> Dict[str, Any]:
        """
        Run a dry-run simulation of one rule against tenant records in a range.
        """
        query = (
            select(CostRecord)
            .where(CostRecord.tenant_id == tenant_id)
            .where(CostRecord.recorded_at >= start_date)
            .where(CostRecord.recorded_at <= end_date)
            .order_by(CostRecord.recorded_at.desc())
            .limit(sample_limit)
        )
        result = await self.db.execute(query)
        records = list(result.scalars().all())

        simulated_rule = AttributionRule(
            tenant_id=tenant_id,
            name="simulation",
            priority=1,
            rule_type=self.normalize_rule_type(rule_type),
            conditions=conditions,
            allocation=allocation,
            is_active=True,
        )

        matched_records = 0
        matched_cost = Decimal("0")
        projected_by_bucket: Dict[str, Decimal] = {}
        for record in records:
            if not self.match_conditions(record, conditions):
                continue
            matched_records += 1
            matched_cost += record.cost_usd
            allocations = await self.apply_rules(record, [simulated_rule])
            for alloc in allocations:
                projected_by_bucket[alloc.allocated_to] = (
                    projected_by_bucket.get(
                        alloc.allocated_to,
                        Decimal("0"),
                    )
                    + alloc.amount
                )

        allocation_rows = [
            {"bucket": bucket, "amount": float(amount)}
            for bucket, amount in sorted(
                projected_by_bucket.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        ]

        sampled_records = len(records)
        match_rate = (
            round((matched_records / sampled_records), 4) if sampled_records else 0.0
        )
        projected_total = float(sum(projected_by_bucket.values(), Decimal("0")))

        return {
            "sampled_records": sampled_records,
            "matched_records": matched_records,
            "match_rate": match_rate,
            "matched_cost": float(matched_cost),
            "projected_allocation_total": projected_total,
            "projected_allocations": allocation_rows,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
