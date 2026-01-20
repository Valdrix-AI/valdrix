"""
Cost Persistence Service - Phase 11: Scalability & Polish

Handles idempotent storage of normalized cost data into the database.
Supports both daily and hourly granularity.
"""

from typing import Any, Dict, AsyncIterable, List
from datetime import date, datetime, timedelta, timezone
import uuid
from decimal import Decimal
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
from app.models.cloud import CostRecord
from app.schemas.costs import CloudUsageSummary

logger = structlog.get_logger()

class CostPersistenceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_summary(
        self, 
        summary: CloudUsageSummary, 
        account_id: str,
        reconciliation_run_id: uuid.UUID | None = None,
        is_preliminary: bool = True
    ) -> dict:
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
                # Forensic Lineage (FinOps Audit Phase 1)
                # We store the hash of the raw record if a specific ID isn't provided
                ingestion_meta = {
                    "source_id": str(uuid.uuid4()), # CostRecord schema doesn't have ID, always generate new
                    "ingestion_timestamp": datetime.now(timezone.utc).isoformat(),
                    "api_request_id": str(reconciliation_run_id) if reconciliation_run_id else None
                }
                
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
                    "usage_type": r.usage_type,
                    "is_preliminary": is_preliminary,
                    "cost_status": "PRELIMINARY" if is_preliminary else "FINAL",
                    "reconciliation_run_id": reconciliation_run_id,
                    "ingestion_metadata": ingestion_meta
                })
            
            # PostgreSQL-specific Upsert logic (Atomic Ops)
            stmt = insert(CostRecord).values(values)
            stmt = stmt.on_conflict_do_update(
                constraint="uix_account_cost_granularity",
                set_={
                    "cost_usd": stmt.excluded.cost_usd,
                    "amount_raw": stmt.excluded.amount_raw,
                    "currency": stmt.excluded.currency,
                    "is_preliminary": stmt.excluded.is_preliminary,
                    "cost_status": stmt.excluded.cost_status,
                    "reconciliation_run_id": stmt.excluded.reconciliation_run_id,
                    "ingestion_metadata": stmt.excluded.ingestion_metadata
                }
            )
            
            # BE-COST-2: Check for significant cost adjustments (>2%)
            if not is_preliminary:
                await self._check_for_significant_adjustments(batch, summary.tenant_id, account_id)
                
            await self.db.execute(stmt)
            records_saved += len(values)

        # Item 13: Explicitly commit at the end of a full summary save
        await self.db.commit()
        
        logger.info("cost_persistence_success", 
                    tenant_id=summary.tenant_id, 
                    account_id=account_id, 
                    records=records_saved)
        
        return {"records_saved": records_saved}

    async def save_records_stream(
        self, 
        records: AsyncIterable[Dict[str, Any]], 
        tenant_id: str, 
        account_id: str
    ) -> dict:
        """
        Consumes an async stream of cost records and saves them in batches.
        Prevents memory spikes for massive accounts.
        """
        records_saved = 0
        batch = []
        BATCH_SIZE = 500

        async for r in records:
            batch.append({
                "tenant_id": tenant_id,
                "account_id": account_id,
                "service": r.get("service") or "Unknown",
                "region": r.get("region") or "Global",
                "cost_usd": r.get("cost_usd"),
                "amount_raw": r.get("amount_raw"),
                "currency": r.get("currency"),
                "recorded_at": r["timestamp"].date(),
                "timestamp": r["timestamp"],
                "usage_type": r.get("usage_type", "Usage")
            })

            if len(batch) >= BATCH_SIZE:
                await self._bulk_upsert(batch)
                records_saved += len(batch)
                batch = []

        if batch:
            await self._bulk_upsert(batch)
            records_saved += len(batch)

        logger.info("cost_stream_persistence_success", 
                    tenant_id=tenant_id, 
                    account_id=account_id, 
                    records=records_saved)
        
        return {"records_saved": records_saved}

    async def _bulk_upsert(self, values: List[Dict[str, Any]]):
        """Helper for PostgreSQL ON CONFLICT DO UPDATE bulk insert."""
        if not values:
            return
        stmt = insert(CostRecord).values(values)
        stmt = stmt.on_conflict_do_update(
            constraint="uix_account_cost_granularity",
            set_={
                "cost_usd": stmt.excluded.cost_usd,
                "amount_raw": stmt.excluded.amount_raw,
                "currency": stmt.excluded.currency,
                "usage_type": stmt.excluded.usage_type
            }
        )
        await self.db.execute(stmt)

    async def _check_for_significant_adjustments(
        self, 
        tenant_id: str, 
        account_id: str, 
        new_records: List[Dict[str, Any]]
    ):
        """
        Alerts if updated costs differ by >2% from existing records.
        Essential for financial reconciliation (Phase 2).
        Now logs to Forensic Audit Trail (Phase 1.1).
        """
        if not new_records:
            return

        from app.models.cost_audit import CostAuditLog

        # 1. Fetch existing costs for these specific records to detect deltas
        dates = {r["timestamp"].date() for r in new_records}
        services = {r.get("service", "Unknown") for r in new_records}
        
        stmt = select(
            CostRecord.id,
            CostRecord.timestamp,
            CostRecord.service,
            CostRecord.region,
            CostRecord.cost_usd
        ).where(
            CostRecord.tenant_id == tenant_id,
            CostRecord.account_id == account_id,
            CostRecord.timestamp.in_(dates),
            CostRecord.service.in_(services)
        )
        
        result = await self.db.execute(stmt)
        existing = {
            (r.timestamp.date(), r.service, r.region): (r.id, float(r.cost_usd)) 
            for r in result.all()
        }

        audit_logs = []
        for nr in new_records:
            key = (nr["timestamp"].date(), nr.get("service", "Unknown"), nr.get("region", "Global"))
            existing_data = existing.get(key)
            if not existing_data:
                continue
                
            record_id, old_cost = existing_data
            new_cost = float(nr.get("cost_usd") or 0)

            if old_cost is not None and old_cost > 0:
                delta = abs(new_cost - old_cost) / old_cost
                
                # Log to forensic audit trail if ANY change occurred
                if delta > 0:
                    audit_logs.append(
                        CostAuditLog(
                            cost_record_id=record_id,
                            cost_recorded_at=key[0],
                            old_cost=Decimal(str(old_cost)),
                            new_cost=Decimal(str(new_cost)),
                            reason="RE-INGESTION",
                            ingestion_batch_id=nr.get("reconciliation_run_id")
                        )
                    )

                if delta > 0.02: # 2% threshold for alerts
                    logger.critical(
                        "significant_cost_adjustment_detected",
                        tenant_id=tenant_id,
                        account_id=account_id,
                        service=key[1],
                        date=str(key[0]),
                        old_cost=old_cost,
                        new_cost=new_cost,
                        delta_percent=round(delta * 100, 2),
                        record_id=str(record_id)
                    )
        
        if audit_logs:
            self.db.add_all(audit_logs)
            await self.db.flush() # Ensure logs are sent before main records are updated

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
        Deletes cost records older than the specified retention period in small batches.
        Optimized for space reclamation without long-running database locks.
        """
        from datetime import timezone
        cutoff_date = datetime.combine(
            date.today() - timedelta(days=days_retention), 
            datetime.min.time()
        ).replace(tzinfo=timezone.utc)
        total_deleted = 0
        batch_size = 5000 # Configurable batch size
        while True:
            # 1. Fetch a batch of IDs to delete
            stmt = select(CostRecord.id).where(CostRecord.timestamp < cutoff_date).limit(batch_size)
            result = await self.db.execute(stmt)
            ids = result.scalars().all()
            
            if not ids:
                break
                
            # 2. Delete this batch
            stmt = delete(CostRecord).where(CostRecord.id.in_(ids))
            await self.db.execute(stmt)
            
            total_deleted += len(ids)
            await self.db.commit() # Commit each batch to free locks and logs
        
        logger.info("cost_retention_cleanup_complete", cutoff_date=str(cutoff_date), total_deleted=total_deleted)
        return {"deleted_count": total_deleted}
    async def finalize_batch(self, days_ago: int = 2) -> Dict[str, int]:
        """
        Transition cost records from PRELIMINARY to FINAL after the restatement window.
        AWS typically finalizes costs within 24-48 hours.
        """
        from sqlalchemy import update
        cutoff_date = date.today() - timedelta(days=days_ago)
        
        stmt = (
            update(CostRecord)
            .where(
                CostRecord.cost_status == "PRELIMINARY",
                CostRecord.recorded_at <= cutoff_date
            )
            .values(
                cost_status="FINAL",
                is_preliminary=False
            )
        )
        
        result = await self.db.execute(stmt)
        await self.db.commit()
        
        count = result.rowcount
        logger.info("cost_batch_finalization_complete", 
                    cutoff_date=str(cutoff_date), 
                    records_finalized=count)
        
        return {"records_finalized": count}
