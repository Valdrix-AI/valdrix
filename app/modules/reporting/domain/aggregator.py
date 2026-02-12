from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, Any, Optional
from uuid import UUID
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cloud import CostRecord, CloudAccount
from app.schemas.costs import CloudUsageSummary, CostRecord as SchemaCostRecord
import structlog

logger = structlog.get_logger()

# Enterprise Safety Gates
MAX_AGGREGATION_ROWS = 1000000 # 1M rows max per query
MAX_DETAIL_ROWS = 100000       # 100K rows max for detail records
STATEMENT_TIMEOUT_MS = 5000    # 5 seconds
LARGE_DATASET_THRESHOLD = 5000 # If >5k records, suggest background job

class CostAggregator:
    """Centralizes cost aggregation logic for the platform."""
    
    @staticmethod
    async def count_records(
        db: AsyncSession,
        tenant_id: UUID,
        start_date: date,
        end_date: date
    ) -> int:
        """Quickly counts records without fetching data."""
        stmt = (
            select(func.count(CostRecord.id))
            .where(
                CostRecord.tenant_id == tenant_id,
                CostRecord.recorded_at >= start_date,
                CostRecord.recorded_at <= end_date
            )
        )
        result = await db.execute(stmt)
        return result.scalar() or 0

    @staticmethod
    async def get_data_freshness(
        db: AsyncSession,
        tenant_id: UUID,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """
        Returns data freshness indicators for the dashboard.
        BE-FIN-RECON-1: Provides visibility into PRELIMINARY vs FINAL data status.
        """
        # Count total, preliminary, and final records
        stmt = (
            select(
                func.count(CostRecord.id).label("total_records"),
                func.count(CostRecord.id).filter(CostRecord.cost_status == "PRELIMINARY").label("preliminary_count"),
                func.count(CostRecord.id).filter(CostRecord.cost_status == "FINAL").label("final_count"),
                func.max(CostRecord.recorded_at).label("latest_record_date")
            )
            .where(
                CostRecord.tenant_id == tenant_id,
                CostRecord.recorded_at >= start_date,
                CostRecord.recorded_at <= end_date
            )
        )
        
        result = await db.execute(stmt)
        row = result.one_or_none()
        
        if not row or row.total_records == 0:
            return {
                "status": "no_data",
                "total_records": 0,
                "preliminary_records": 0,
                "final_records": 0,
                "freshness_percentage": 0,
                "latest_record_date": None,
                "message": "No cost data available for the selected range."
            }
        
        final_pct = (row.final_count / row.total_records * 100) if row.total_records > 0 else 0
        
        # Determine status based on preliminary percentage
        if row.preliminary_count == 0:
            status = "final"
            message = "All cost data is finalized."
        elif row.preliminary_count > row.total_records * 0.5:
            status = "preliminary"
            message = "More than 50% of data is preliminary and may be restated within 48 hours."
        else:
            status = "mixed"
            message = f"{row.preliminary_count} records are still preliminary."
        
        return {
            "status": status,
            "total_records": row.total_records,
            "preliminary_records": row.preliminary_count,
            "final_records": row.final_count,
            "freshness_percentage": round(final_pct, 2),
            "latest_record_date": row.latest_record_date.isoformat() if row.latest_record_date else None,
            "message": message
        }

    @staticmethod
    async def get_summary(
        db: AsyncSession,
        tenant_id: UUID,
        start_date: date,
        end_date: date,
        provider: Optional[str] = None
    ) -> CloudUsageSummary:
        # Phase 5: Get accurate totals for the full range (for data integrity)
        total_stmt = (
            select(
                func.sum(CostRecord.cost_usd).label("total_cost"),
                func.count(CostRecord.id).label("total_count")
            )
            .where(
                CostRecord.tenant_id == tenant_id,
                CostRecord.recorded_at >= start_date,
                CostRecord.recorded_at <= end_date
            )
        )
        if provider:
            total_stmt = total_stmt.join(CloudAccount).where(CloudAccount.provider == provider.lower())
            
        total_result = await db.execute(total_stmt)
        total_row = total_result.one()
        full_total_cost = total_row.total_cost or Decimal("0.00")
        full_total_count = total_row.total_count or 0

        # Fetch detailed records (limited)
        stmt = (
            select(CostRecord)
            .where(
                CostRecord.tenant_id == tenant_id,
                CostRecord.recorded_at >= start_date,
                CostRecord.recorded_at <= end_date
            )
        )
        if provider:
            stmt = stmt.join(CloudAccount).where(CloudAccount.provider == provider.lower())
        
        stmt = stmt.limit(MAX_DETAIL_ROWS)
        
        result = await db.execute(stmt)
        records = result.scalars().all()
        
        is_truncated = full_total_count > MAX_DETAIL_ROWS
        if is_truncated:
            logger.warning("query_truncated", 
                           tenant_id=str(tenant_id), 
                           actual=full_total_count,
                           limit=MAX_DETAIL_ROWS)
        
        # Build detailed records for the schema
        schema_records = []
        for r in records:
            schema_records.append(SchemaCostRecord(
                date=datetime.combine(r.recorded_at, datetime.min.time(), tzinfo=timezone.utc),
                amount=r.cost_usd,
                service=r.service,
                region=r.region
            ))
            
        # Group by service for the *full* set is better done in DB if truncated
        # But for now, we'll indicate in metadata that the breakdown is partial
        by_service: dict[str, Decimal] = {}
        for r in records:
            by_service[r.service] = by_service.get(r.service, Decimal(0)) + r.cost_usd

        return CloudUsageSummary(
            tenant_id=str(tenant_id),
            provider=provider or "multi",
            start_date=start_date,
            end_date=end_date,
            total_cost=full_total_cost, # Accurate total
            records=schema_records,
            by_service=by_service,
            metadata={
                "is_truncated": is_truncated,
                "total_records_in_range": full_total_count,
                "records_returned": len(records),
                "summary": "Breakdown/records are partial" if is_truncated else "Full data"
            }
        )

    @staticmethod
    async def get_dashboard_summary(
        db: AsyncSession, 
        tenant_id: UUID, 
        start_date: date, 
        end_date: date,
        provider: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retrieves top-level summary for the dashboard.
        """
        from sqlalchemy import text
        if db.bind.dialect.name != "sqlite":
            await db.execute(text(f"SET LOCAL statement_timeout TO {STATEMENT_TIMEOUT_MS}"))

        stmt = (
            select(
                func.sum(CostRecord.cost_usd).label("total_cost"),
                func.sum(CostRecord.carbon_kg).label("total_carbon")
            )
            .where(
                CostRecord.tenant_id == tenant_id,
                CostRecord.recorded_at >= start_date,
                CostRecord.recorded_at <= end_date
            )
        )
        if provider:
            stmt = stmt.join(CloudAccount, CostRecord.account_id == CloudAccount.id).where(
                CloudAccount.provider == provider.lower()
            )

        result = await db.execute(stmt)
        row = result.one_or_none()
        
        total_cost = row.total_cost if row and row.total_cost else Decimal("0.00")
        total_carbon = row.total_carbon if row and row.total_carbon else Decimal("0.00")
        
        # Phase 21: Include basic breakdown in summary for holistic dashboard entry
        # This reduces API calls from the frontend.
        breakdown_data = await CostAggregator.get_basic_breakdown(
            db, tenant_id, start_date, end_date, provider
        )
        freshness = await CostAggregator.get_data_freshness(
            db, tenant_id, start_date, end_date
        )
        canonical_quality = await CostAggregator.get_canonical_data_quality(
            db, tenant_id, start_date, end_date, provider
        )
        
        return {
            "total_cost": float(total_cost),
            "total_carbon_kg": float(total_carbon),
            "provider": provider or "multi",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "breakdown": breakdown_data["breakdown"],
            "data_quality": {
                "freshness": freshness,
                "canonical_mapping": canonical_quality,
            },
        }

    @staticmethod
    async def get_canonical_data_quality(
        db: AsyncSession,
        tenant_id: UUID,
        start_date: date,
        end_date: date,
        provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Returns canonical mapping coverage metrics.
        """
        mapped_filter = (
            CostRecord.canonical_charge_category.is_not(None)
        ) & (func.lower(CostRecord.canonical_charge_category) != "unmapped")
        stmt = (
            select(
                func.count(CostRecord.id).label("total_records"),
                func.count(CostRecord.id).filter(mapped_filter).label("mapped_records"),
            )
            .where(
                CostRecord.tenant_id == tenant_id,
                CostRecord.recorded_at >= start_date,
                CostRecord.recorded_at <= end_date,
            )
        )

        if provider:
            stmt = stmt.join(CloudAccount, CostRecord.account_id == CloudAccount.id).where(
                CloudAccount.provider == provider.lower()
            )

        result = await db.execute(stmt)
        row = result.one_or_none()

        total_records = int(row.total_records or 0) if row else 0
        mapped_records = int(row.mapped_records or 0) if row else 0
        unmapped_records = max(total_records - mapped_records, 0)
        mapped_pct = (mapped_records / total_records * 100) if total_records > 0 else 0.0
        target_pct = 99.0

        unmapped_filter = (
            CostRecord.canonical_charge_category.is_(None)
        ) | (func.lower(CostRecord.canonical_charge_category) == "unmapped")

        top_unmapped_stmt = (
            select(
                CloudAccount.provider.label("provider"),
                CostRecord.service.label("service"),
                CostRecord.usage_type.label("usage_type"),
                func.count(CostRecord.id).label("record_count"),
                func.min(CostRecord.recorded_at).label("first_seen"),
                func.max(CostRecord.recorded_at).label("last_seen"),
            )
            .join(CloudAccount, CostRecord.account_id == CloudAccount.id)
            .where(
                CostRecord.tenant_id == tenant_id,
                CostRecord.recorded_at >= start_date,
                CostRecord.recorded_at <= end_date,
                unmapped_filter,
            )
            .group_by(CloudAccount.provider, CostRecord.service, CostRecord.usage_type)
            .order_by(func.count(CostRecord.id).desc())
            .limit(10)
        )
        if provider:
            top_unmapped_stmt = top_unmapped_stmt.where(CloudAccount.provider == provider.lower())

        top_unmapped_res = await db.execute(top_unmapped_stmt)
        top_unmapped_rows = top_unmapped_res.all()
        top_unmapped_signatures = [
            {
                "provider": str(getattr(r, "provider", "") or "unknown"),
                "service": str(getattr(r, "service", "") or "Unknown"),
                "usage_type": str(getattr(r, "usage_type", "") or "Unknown"),
                "record_count": int(getattr(r, "record_count", 0) or 0),
                "first_seen": getattr(r, "first_seen", None).isoformat()
                if getattr(r, "first_seen", None)
                else None,
                "last_seen": getattr(r, "last_seen", None).isoformat()
                if getattr(r, "last_seen", None)
                else None,
            }
            for r in top_unmapped_rows
        ]

        reasons_stmt = (
            select(CostRecord.ingestion_metadata)
            .where(
                CostRecord.tenant_id == tenant_id,
                CostRecord.recorded_at >= start_date,
                CostRecord.recorded_at <= end_date,
                unmapped_filter,
            )
            .limit(5000)
        )
        if provider:
            reasons_stmt = reasons_stmt.join(CloudAccount, CostRecord.account_id == CloudAccount.id).where(
                CloudAccount.provider == provider.lower()
            )
        reasons_res = await db.execute(reasons_stmt)
        reason_counts: dict[str, int] = {}
        sampled_unmapped_records = 0
        for metadata in reasons_res.scalars().all():
            sampled_unmapped_records += 1
            if not isinstance(metadata, dict):
                continue
            canonical_meta = metadata.get("canonical_mapping")
            if not isinstance(canonical_meta, dict):
                continue
            reason = canonical_meta.get("unmapped_reason")
            reason_key = str(reason).strip() if reason is not None else ""
            if not reason_key:
                reason_key = "unknown"
            reason_counts[reason_key] = reason_counts.get(reason_key, 0) + 1

        return {
            "status": (
                "no_data"
                if total_records == 0
                else ("warning" if mapped_pct < target_pct else "ok")
            ),
            "target_percentage": target_pct,
            "total_records": total_records,
            "mapped_records": mapped_records,
            "unmapped_records": unmapped_records,
            "mapped_percentage": round(mapped_pct, 2),
            "target_gap_percentage": round(max(target_pct - mapped_pct, 0.0), 2),
            "meets_target": mapped_pct >= target_pct if total_records > 0 else False,
            "top_unmapped_signatures": top_unmapped_signatures,
            "unmapped_reason_breakdown": reason_counts,
            "sampled_unmapped_records": sampled_unmapped_records,
        }
    
    @staticmethod
    async def get_basic_breakdown(
        db: AsyncSession,
        tenant_id: UUID,
        start_date: date,
        end_date: date,
        provider: Optional[str] = None
    ) -> Dict[str, Any]:
        """Provides a simplified breakdown for the API."""
        stmt = (
            select(
                CostRecord.service,
                func.sum(CostRecord.cost_usd).label("total_cost"),
                func.sum(CostRecord.carbon_kg).label("total_carbon")
            )
            .where(
                CostRecord.tenant_id == tenant_id,
                CostRecord.recorded_at >= start_date,
                CostRecord.recorded_at <= end_date
            )
            .group_by(CostRecord.service)
        )
        
        if provider:
            stmt = stmt.join(CloudAccount, CostRecord.account_id == CloudAccount.id).where(
                CloudAccount.provider == provider.lower()
            )
        
        # Aggregate limit (Phase 4 safety gate)
        stmt = stmt.limit(MAX_AGGREGATION_ROWS)
        
        # Set statement timeout
        from sqlalchemy import text
        if db.bind.dialect.name != "sqlite":
            await db.execute(text(f"SET LOCAL statement_timeout TO {STATEMENT_TIMEOUT_MS}"))
            
        result = await db.execute(stmt)
        rows = result.all()
        
        total_cost = Decimal("0.00")
        total_carbon = Decimal("0.00")
        breakdown = []
        
        for row in rows:
            c = row.total_cost or Decimal(0)
            target_carbon = row.total_carbon or Decimal(0)
            total_cost += c
            total_carbon += target_carbon
            
            service_name = row.service
            if not service_name or service_name.lower() == "unknown":
                service_name = "Uncategorized"
                
            breakdown.append({
                "service": service_name,
                "cost": float(c),
                "carbon_kg": float(target_carbon)
            })
            
        return {
            "total_cost": float(total_cost),
            "total_carbon_kg": float(total_carbon),
            "breakdown": breakdown
        }

    @staticmethod
    async def get_governance_report(
        db: AsyncSession,
        tenant_id: UUID,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """
        Detects untagged and unallocated costs.
        Flags customers if untagged cost > 10%.
        """
        # Query for untagged costs (metadata check)
        # Note: In production, we'd use a more optimized tags column
        stmt = (
            select(
                func.sum(CostRecord.cost_usd).label("total_untagged_cost"),
                func.count(CostRecord.id).label("untagged_count")
            )
            .where(
                CostRecord.tenant_id == tenant_id,
                CostRecord.recorded_at >= start_date,
                CostRecord.recorded_at <= end_date,
                # Simple heuristic: no ingestion_metadata or empty tags
                (CostRecord.allocated_to.is_(None)) | (CostRecord.allocated_to == 'Unallocated')
            )
        )
        
        # Get total cost for percentage calculation
        total_stmt = (
            select(func.sum(CostRecord.cost_usd))
            .where(
                CostRecord.tenant_id == tenant_id,
                CostRecord.recorded_at >= start_date,
                CostRecord.recorded_at <= end_date
            )
        )
        
        total_res = await db.execute(total_stmt)
        total_cost = total_res.scalar() or Decimal("0.01") # Avoid div by zero
        
        result = await db.execute(stmt)
        row = result.one()
        
        untagged_cost = row.total_untagged_cost or Decimal(0)
        untagged_percent = (untagged_cost / total_cost) * 100
        
        # Phase 5: Get top unallocated service insights
        from app.modules.reporting.domain.attribution_engine import AttributionEngine
        engine = AttributionEngine(db)
        insights = await engine.get_unallocated_analysis(tenant_id, start_date, end_date)
        
        return {
            "total_cost": float(total_cost),
            "unallocated_cost": float(untagged_cost),
            "unallocated_percentage": round(float(untagged_percent), 2),
            "resource_count": row.untagged_count,
            "insights": insights,
            "status": "warning" if untagged_percent > 10 else "healthy",
            "message": "High unallocated spend detected (>10%)." if untagged_percent > 10 else "Cost attribution is within healthy bounds.",
            "recommendation": "High unallocated spend detected. Implement attribution rules to improve visibility." if untagged_percent > 10 else None
        }

    @staticmethod
    async def get_cached_breakdown(
        db: AsyncSession,
        tenant_id: UUID,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """
        Query the materialized view for instant cached responses.
        Phase 4.3: Query Caching Layer
        
        Falls back to get_basic_breakdown if materialized view doesn't exist.
        """
        from sqlalchemy import text
        
        try:
            # Use a savepoint to ensure we can fallback if the view doesn't exist
            # in an already open transaction.
            async with db.begin_nested():
                # Query the materialized view directly
                stmt = text("""
                    SELECT 
                        service,
                        SUM(total_cost) as total_cost,
                        SUM(total_carbon) as total_carbon
                    FROM mv_daily_cost_aggregates
                    WHERE tenant_id = :tenant_id
                      AND cost_date >= :start_date
                      AND cost_date <= :end_date
                    GROUP BY service
                    ORDER BY total_cost DESC
                """)
                
                result = await db.execute(stmt, {
                    "tenant_id": tenant_id,
                    "start_date": start_date,
                    "end_date": end_date
                })
                rows = result.all()
            
            if not rows:
                # Fallback to direct query if no cached data
                logger.info("cache_miss_falling_back", tenant_id=str(tenant_id))
                return await CostAggregator.get_basic_breakdown(
                    db, tenant_id, start_date, end_date
                )
            
            total_cost = Decimal("0.00")
            total_carbon = Decimal("0.00")
            breakdown = []
            
            for row in rows:
                c = row.total_cost or Decimal(0)
                carbon = row.total_carbon or Decimal(0)
                total_cost += c
                total_carbon += carbon
                breakdown.append({
                    "service": row.service,
                    "cost": float(c),
                    "carbon_kg": float(carbon)
                })
            
            logger.info("cache_hit", tenant_id=str(tenant_id), services=len(breakdown))
            
            return {
                "total_cost": float(total_cost),
                "total_carbon_kg": float(total_carbon),
                "breakdown": breakdown,
                "cached": True
            }
            
        except Exception as e:
            # Materialized view may not exist yet
            logger.warning("mv_query_failed_fallback", error=str(e))
            return await CostAggregator.get_basic_breakdown(
                db, tenant_id, start_date, end_date
            )

    @staticmethod
    async def refresh_materialized_view(db: AsyncSession) -> bool:
        """
        Manually refresh the materialized view.
        Called by background job or admin endpoint.
        """
        from sqlalchemy import text
        
        try:
            if db.bind.dialect.name == "sqlite":
                logger.info("materialized_view_refresh_skipped_sqlite")
                return True

            await db.execute(text(
                "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_cost_aggregates"
            ))
            await db.commit()
            logger.info("materialized_view_refreshed")
            return True
        except Exception as e:
            logger.error("materialized_view_refresh_failed", error=str(e))
            return False
