"""
Cost Persistence Service - Phase 11: Scalability & Polish

Handles idempotent storage of normalized cost data into the database.
Supports both daily and hourly granularity.
"""

from typing import Any, AsyncIterable
from datetime import date, datetime, timedelta, timezone
import uuid
from decimal import Decimal
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
from app.models.cloud import CostRecord
from app.schemas.costs import CloudUsageSummary
from app.shared.core.async_utils import maybe_await
from app.modules.reporting.domain.canonicalization import map_canonical_charge_category

logger = structlog.get_logger()

class CostPersistenceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _coerce_uuid(value: str | uuid.UUID, field_name: str) -> uuid.UUID:
        """Normalize UUID inputs from API/schema layers into DB-safe UUID objects."""
        if isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(str(value))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid UUID for {field_name}: {value}") from exc

    @staticmethod
    def _coerce_uuid_if_valid(value: str | uuid.UUID) -> str | uuid.UUID:
        """Best-effort UUID coercion for mixed UUID/non-UUID call sites."""
        if isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(str(value))
        except (TypeError, ValueError):
            return value

    async def save_summary(
        self, 
        summary: CloudUsageSummary, 
        account_id: str,
        reconciliation_run_id: uuid.UUID | None = None,
        is_preliminary: bool = True
    ) -> dict[str, int]:
        """
        Saves a CloudUsageSummary to the database.
        Uses PostgreSQL ON CONFLICT DO UPDATE for idempotency.
        """
        records_saved = 0
        total_processed = len(summary.records)
        tenant_uuid = self._coerce_uuid(summary.tenant_id, "tenant_id")
        account_uuid = self._coerce_uuid(account_id, "account_id")
        
        # Batch size for database performance
        BATCH_SIZE = 500
        
        for i in range(0, total_processed, BATCH_SIZE):
            batch = summary.records[i : i + BATCH_SIZE]
            
            # Prepare values for bulk insert
            values = []
            for r in batch:
                summary_source = "summary_import"
                if isinstance(summary.metadata, dict):
                    summary_source = str(summary.metadata.get("source_adapter") or summary_source)

                canonical_mapping = map_canonical_charge_category(
                    provider=summary.provider,
                    service=r.service,
                    usage_type=r.usage_type,
                )

                # Forensic Lineage (FinOps Audit Phase 1)
                # We store the hash of the raw record if a specific ID isn't provided
                ingestion_meta = {
                    "source_id": str(uuid.uuid4()), # CostRecord schema doesn't have ID, always generate new
                    "ingestion_timestamp": datetime.now(timezone.utc).isoformat(),
                    "api_request_id": str(reconciliation_run_id) if reconciliation_run_id else None,
                    "canonical_mapping": {
                        "category": canonical_mapping.category,
                        "subcategory": canonical_mapping.subcategory,
                        "is_mapped": canonical_mapping.is_mapped,
                        "confidence": canonical_mapping.confidence,
                        "version": canonical_mapping.mapping_version,
                        "unmapped_reason": canonical_mapping.unmapped_reason,
                    },
                    "source_adapter": summary_source,
                }
                
                values.append({
                    "tenant_id": tenant_uuid,
                    "account_id": account_uuid,
                    "service": r.service or "Unknown",
                    "region": r.region or "Global",
                    "cost_usd": r.amount,
                    "amount_raw": r.amount_raw,
                    "currency": r.currency,
                    "recorded_at": r.date.date(), # Partition-aligned date column
                    "timestamp": r.date,           # New hourly/timestamp column
                    "usage_type": r.usage_type,
                    "canonical_charge_category": canonical_mapping.category,
                    "canonical_charge_subcategory": canonical_mapping.subcategory,
                    "canonical_mapping_version": canonical_mapping.mapping_version,
                    "is_preliminary": is_preliminary,
                    "cost_status": "PRELIMINARY" if is_preliminary else "FINAL",
                    "reconciliation_run_id": reconciliation_run_id,
                    "ingestion_metadata": ingestion_meta
                })
            
            # BE-COST-2: Check for significant cost adjustments (>2%)
            if not is_preliminary:
                await self._check_for_significant_adjustments(tenant_uuid, account_uuid, values)
                
            await self._bulk_upsert(values)
            records_saved += len(values)

        # Item 13: Explicitly flush at the end of a full summary save
        await self.db.flush()
        
        logger.info("cost_persistence_success", 
                    tenant_id=str(tenant_uuid), 
                    account_id=str(account_uuid), 
                    records=records_saved)
        
        return {"records_saved": records_saved}

    async def save_records_stream(
        self, 
        records: AsyncIterable[dict[str, Any]], 
        tenant_id: str, 
        account_id: str
    ) -> dict[str, int]:
        """
        Consumes an async stream of cost records and saves them in batches.
        Prevents memory spikes for massive accounts.
        """
        records_saved = 0
        batch = []
        BATCH_SIZE = 500
        tenant_uuid = self._coerce_uuid(tenant_id, "tenant_id")
        account_uuid = self._coerce_uuid(account_id, "account_id")

        async for r in records:
            source_adapter = str(r.get("source_adapter") or "unknown_stream")
            canonical_mapping = map_canonical_charge_category(
                provider=r.get("provider"),
                service=r.get("service"),
                usage_type=r.get("usage_type"),
            )
            ingestion_meta = {
                "source_id": str(r.get("source_id") or uuid.uuid4()),
                "ingestion_timestamp": datetime.now(timezone.utc).isoformat(),
                "source_adapter": source_adapter,
                "canonical_mapping": {
                    "unmapped_reason": canonical_mapping.unmapped_reason,
                },
            }
            if isinstance(r.get("tags"), dict):
                ingestion_meta["tags"] = r["tags"]

            batch.append({
                "tenant_id": tenant_uuid,
                "account_id": account_uuid,
                "service": r.get("service") or "Unknown",
                "region": r.get("region") or "Global",
                "cost_usd": r.get("cost_usd"),
                "amount_raw": r.get("amount_raw"),
                "currency": r.get("currency"),
                "recorded_at": r["timestamp"].date(),
                "timestamp": r["timestamp"],
                "usage_type": r.get("usage_type", "Usage"),
                "canonical_charge_category": canonical_mapping.category,
                "canonical_charge_subcategory": canonical_mapping.subcategory,
                "canonical_mapping_version": canonical_mapping.mapping_version,
                "ingestion_metadata": ingestion_meta,
            })

            if len(batch) >= BATCH_SIZE:
                await self._bulk_upsert(batch)
                records_saved += len(batch)
                batch = []

        if batch:
            await self._bulk_upsert(batch)
            records_saved += len(batch)

        logger.info("cost_stream_persistence_success", 
                    tenant_id=str(tenant_uuid), 
                    account_id=str(account_uuid), 
                    records=records_saved)
        
        return {"records_saved": records_saved}

    async def _bulk_upsert(self, values: list[dict[str, Any]]) -> None:
        """Helper for PostgreSQL ON CONFLICT DO UPDATE bulk insert."""
        if not values:
            return
        bind_url = str(getattr(getattr(self.db, "bind", None), "url", ""))
        if not bind_url:
            bind = await maybe_await(self.db.get_bind())
            bind_url = str(getattr(bind, "url", ""))
        if "postgresql" in bind_url:
            stmt = pg_insert(CostRecord).values(values)
            stmt = stmt.on_conflict_do_update(
                constraint="uix_account_cost_granularity",
                set_={
                    "cost_usd": stmt.excluded.cost_usd,
                    "amount_raw": stmt.excluded.amount_raw,
                    "currency": stmt.excluded.currency,
                    "usage_type": stmt.excluded.usage_type,
                    "canonical_charge_category": stmt.excluded.canonical_charge_category,
                    "canonical_charge_subcategory": stmt.excluded.canonical_charge_subcategory,
                    "canonical_mapping_version": stmt.excluded.canonical_mapping_version,
                    "is_preliminary": stmt.excluded.is_preliminary,
                    "cost_status": stmt.excluded.cost_status,
                    "reconciliation_run_id": stmt.excluded.reconciliation_run_id,
                    "ingestion_metadata": stmt.excluded.ingestion_metadata,
                }
            )
            await self.db.execute(stmt)
        else:
            # Fallback for SQLite/Testing: Manual Idempotency
            # We use session methods directly to avoid driver-level conflicts
            for val in values:
                # Use a fresh select to avoid session state issues
                select_stmt = select(CostRecord).where(
                    CostRecord.account_id == val["account_id"],
                    CostRecord.recorded_at == val["recorded_at"],
                    CostRecord.timestamp == val["timestamp"],
                    CostRecord.service == val["service"],
                    CostRecord.region == val["region"],
                    CostRecord.usage_type == val["usage_type"]
                )
                # Use scalar() which is safer
                res = await self.db.execute(select_stmt)
                scalars_result = await maybe_await(res.scalars())
                existing = await maybe_await(scalars_result.first())
                
                if existing:
                    if val.get("cost_usd") is not None:
                        existing.cost_usd = Decimal(str(val["cost_usd"]))
                    if val.get("amount_raw") is not None:
                        existing.amount_raw = Decimal(str(val["amount_raw"]))
                    if val.get("currency") is not None:
                        existing.currency = str(val["currency"])
                    if val.get("usage_type") is not None:
                        existing.usage_type = val["usage_type"]
                    if val.get("canonical_charge_category") is not None:
                        existing.canonical_charge_category = val["canonical_charge_category"]
                    if "canonical_charge_subcategory" in val:
                        existing.canonical_charge_subcategory = val["canonical_charge_subcategory"]
                    if val.get("canonical_mapping_version") is not None:
                        existing.canonical_mapping_version = val["canonical_mapping_version"]
                    existing.is_preliminary = bool(val.get("is_preliminary", existing.is_preliminary))
                    existing.cost_status = str(val.get("cost_status") or existing.cost_status)
                    existing.reconciliation_run_id = val.get("reconciliation_run_id")
                    existing.ingestion_metadata = val.get("ingestion_metadata")
                else:
                    self.db.add(CostRecord(**val))
            
            await self.db.flush()

    async def _check_for_significant_adjustments(
        self, 
        tenant_id: uuid.UUID, 
        account_id: uuid.UUID, 
        new_records: list[dict[str, Any]]
    ) -> None:
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
            CostRecord.recorded_at.in_(dates),
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

    async def clear_range(
        self, tenant_id: str, account_id: str, start_date: Any, end_date: Any
    ) -> None:
        """Clears existing records for a tenant/account range to allow re-ingestion."""
        tenant_scoped = self._coerce_uuid_if_valid(tenant_id)
        account_scoped = self._coerce_uuid_if_valid(account_id)
        stmt = delete(CostRecord).where(
            CostRecord.tenant_id == tenant_scoped,
            CostRecord.account_id == account_scoped,
            CostRecord.timestamp >= start_date,
            CostRecord.timestamp <= end_date
        )
        await self.db.execute(stmt)

    async def cleanup_old_records(self, days_retention: int = 365) -> dict[str, int]:
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
            select_stmt = select(CostRecord.id).where(CostRecord.timestamp < cutoff_date).limit(batch_size)
            result = await self.db.execute(select_stmt)
            ids = result.scalars().all()
            
            if not ids:
                break
                
            # 2. Delete this batch
            delete_stmt = delete(CostRecord).where(CostRecord.id.in_(ids))
            await self.db.execute(delete_stmt)
            
            total_deleted += len(ids)
            await self.db.flush() # Flush each batch to DB but don't commit outer transaction
        
        logger.info("cost_retention_cleanup_complete", cutoff_date=str(cutoff_date), total_deleted=total_deleted)
        return {"deleted_count": total_deleted}
    async def finalize_batch(
        self, days_ago: int = 2, tenant_id: str | None = None
    ) -> dict[str, int]:
        """
        Transition cost records from PRELIMINARY to FINAL after the restatement window.
        AWS typically finalizes costs within 24-48 hours.
        """
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

        if tenant_id:
            stmt = stmt.where(CostRecord.tenant_id == self._coerce_uuid_if_valid(tenant_id))
        
        result = await self.db.execute(stmt)
        await self.db.flush()
        
        rowcount = getattr(result, "rowcount", None)
        count = int(rowcount or 0)
        logger.info(
            "cost_batch_finalization_complete",
            tenant_id=tenant_id,
            cutoff_date=str(cutoff_date),
            records_finalized=count
        )
        
        return {"records_finalized": count}
