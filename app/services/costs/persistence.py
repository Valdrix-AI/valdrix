"""
Cost Persistence Service - Phase 11: Scalability & Polish

Handles idempotent storage of normalized cost data into the database.
Supports both daily and hourly granularity.
"""

from typing import Any
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
from app.models.cloud import CostRecord
from app.schemas.costs import CloudUsageSummary

logger = structlog.get_logger()

class CostPersistenceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_summary(self, summary: CloudUsageSummary, account_id: str) -> dict:
        """
        Saves a CloudUsageSummary to the database.
        Uses PostgreSQL ON CONFLICT DO UPDATE for idempotency.
        """
        records_saved = 0
        total_processed = len(summary.records)
        
        # Batch size for database performance
        BATCH_SIZE = 500
        
        for i in range(0, total_processed, BATCH_SIZE):
            batch = summary.records[i : i + BATCH_SIZE]
            
            # Prepare values for bulk insert
            values = []
            for r in batch:
                values.append({
                    "tenant_id": summary.tenant_id,
                    "account_id": account_id,
                    "service": r.service or "Unknown",
                    "region": r.region or "Global",
                    "cost_usd": r.amount,
                    "amount_raw": r.amount_raw,
                    "currency": r.currency,
                    "recorded_at": r.date.date(), # Legacy date column
                    "timestamp": r.date,           # New hourly/timestamp column
                    "usage_type": r.usage_type
                })
            
            # PostgreSQL-specific Upsert logic (Atomic Ops)
            stmt = insert(CostRecord).values(values)
            stmt = stmt.on_conflict_do_update(
                constraint="uix_account_cost_granularity",
                set_={
                    "cost_usd": stmt.excluded.cost_usd,
                    "amount_raw": stmt.excluded.amount_raw,
                    "currency": stmt.excluded.currency
                }
            )
            await self.db.execute(stmt)
            records_saved += len(values)

        # No internal commit - caller should handle transaction boundaries
        logger.info("cost_persistence_success", 
                    tenant_id=summary.tenant_id, 
                    account_id=account_id, 
                    records=records_saved)
        
        return {"records_saved": records_saved}

    async def clear_range(self, account_id: str, start_date: Any, end_date: Any):
        """Clears existing records to allow re-ingestion."""
        stmt = delete(CostRecord).where(
            CostRecord.account_id == account_id,
            CostRecord.timestamp >= start_date,
            CostRecord.timestamp <= end_date
        )
        await self.db.execute(stmt)

    async def cleanup_old_records(self, days_retention: int = 365) -> Dict[str, int]:
        """
        Deletes cost records older than the specified retention period.
        Optimized for space reclamation on free-tier databases.
        """
        cutoff_date = date.today() - timedelta(days=days_retention)
        
        # Batch delete to avoid transaction timeouts on large tables
        # Using a simple DELETE for MVP (Zero-Budget)
        stmt = delete(CostRecord).where(CostRecord.timestamp < cutoff_date)
        
        result = await self.db.execute(stmt)
        deleted_count = result.rowcount
        
        logger.info("cost_retention_cleanup", cutoff_date=str(cutoff_date), deleted=deleted_count)
        return {"deleted_count": deleted_count}
