from datetime import date
from decimal import Decimal
from typing import List, Dict, Any, Optional
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
        """Fetches and aggregates cost records for a tenant."""
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
        
        # Limit rows (Phase 4 safety gate)
        stmt = stmt.limit(MAX_DETAIL_ROWS)
            
        # Set statement timeout for this execution
        from sqlalchemy import text
        await db.execute(text(f"SET statement_timeout TO {STATEMENT_TIMEOUT_MS}"))
        
        result = await db.execute(stmt)
        records = result.scalars().all()
        
        if len(records) >= MAX_DETAIL_ROWS:
            logger.warning("query_hit_safety_limit", 
                           tenant_id=str(tenant_id), 
                           limit=MAX_DETAIL_ROWS)
        
        # Aggregate logic (DRY)
        total_cost = Decimal("0.00")
        by_service = {}
        schema_records = []
        
        for r in records:
            total_cost += r.cost_usd
            by_service[r.service] = by_service.get(r.service, Decimal(0)) + r.cost_usd
            schema_records.append(SchemaCostRecord(
                date=r.recorded_at,
                amount=r.cost_usd,
                service=r.service,
                region=r.region
            ))
            
        return CloudUsageSummary(
            tenant_id=str(tenant_id),
            provider=provider or "multi",
            start_date=start_date,
            end_date=end_date,
            total_cost=total_cost,
            records=schema_records,
            by_service=by_service
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
        
        return {
            "total_cost": float(total_cost),
            "total_carbon_kg": float(total_carbon),
            "provider": provider or "multi",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
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
        await db.execute(text(f"SET statement_timeout TO {STATEMENT_TIMEOUT_MS}"))
            
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
                (CostRecord.allocated_to == None) | (CostRecord.allocated_to == 'Unallocated')
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
        
        return {
            "total_cost": float(total_cost),
            "unallocated_cost": float(untagged_cost),
            "unallocated_percentage": round(float(untagged_percent), 2),
            "resource_count": row.untagged_count,
            "status": "warning" if untagged_percent > 10 else "healthy",
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
            await db.execute(text(
                "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_cost_aggregates"
            ))
            await db.commit()
            logger.info("materialized_view_refreshed")
            return True
        except Exception as e:
            logger.error("materialized_view_refresh_failed", error=str(e))
            return False
