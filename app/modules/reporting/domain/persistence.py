"""
Cost Persistence Service - Phase 11: Scalability & Polish

Handles idempotent storage of normalized cost data into the database.
Supports both daily and hourly granularity.
"""

from typing import Any, AsyncIterable
from datetime import date, datetime, timezone
import uuid
from decimal import Decimal, InvalidOperation
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
from app.models.cloud import CostRecord
from app.schemas.costs import CloudUsageSummary
from app.modules.reporting.domain.canonicalization import map_canonical_charge_category
from app.modules.reporting.domain.persistence_retention_ops import (
    cleanup_expired_cost_records_by_plan as _cleanup_expired_cost_records_by_plan_impl,
    cleanup_old_cost_records as _cleanup_old_cost_records_impl,
    finalize_cost_record_batch as _finalize_cost_record_batch_impl,
)
from app.modules.reporting.domain.persistence_adjustment_ops import (
    check_for_significant_adjustments as _check_for_significant_adjustments_impl,
)
from app.modules.reporting.domain.persistence_upsert_ops import (
    bulk_upsert as _bulk_upsert_impl,
)

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
        is_preliminary: bool = True,
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
                    summary_source = str(
                        summary.metadata.get("source_adapter") or summary_source
                    )

                canonical_mapping = map_canonical_charge_category(
                    provider=summary.provider,
                    service=r.service,
                    usage_type=r.usage_type,
                )

                # Forensic Lineage (FinOps Audit Phase 1)
                # We store the hash of the raw record if a specific ID isn't provided
                ingestion_meta = {
                    "source_id": str(
                        uuid.uuid4()
                    ),  # CostRecord schema doesn't have ID, always generate new
                    "ingestion_timestamp": datetime.now(timezone.utc).isoformat(),
                    "api_request_id": str(reconciliation_run_id)
                    if reconciliation_run_id
                    else None,
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
                tags = getattr(r, "tags", None) if hasattr(r, "tags") else None
                if isinstance(tags, dict) and tags:
                    ingestion_meta["tags"] = tags

                values.append(
                    {
                        "tenant_id": tenant_uuid,
                        "account_id": account_uuid,
                        "service": r.service or "Unknown",
                        "region": r.region or "Global",
                        "resource_id": str(getattr(r, "resource_id", "") or ""),
                        "usage_amount": getattr(r, "usage_amount", None),
                        "usage_unit": getattr(r, "usage_unit", None),
                        "cost_usd": r.amount,
                        "amount_raw": r.amount_raw,
                        "currency": r.currency,
                        "recorded_at": r.date.date(),  # Partition-aligned date column
                        "timestamp": r.date,  # New hourly/timestamp column
                        "usage_type": r.usage_type,
                        "canonical_charge_category": canonical_mapping.category,
                        "canonical_charge_subcategory": canonical_mapping.subcategory,
                        "canonical_mapping_version": canonical_mapping.mapping_version,
                        "is_preliminary": is_preliminary,
                        "cost_status": "PRELIMINARY" if is_preliminary else "FINAL",
                        "reconciliation_run_id": reconciliation_run_id,
                        "ingestion_metadata": ingestion_meta,
                        "tags": tags if isinstance(tags, dict) and tags else None,
                    }
                )

            # BE-COST-2: Check for significant cost adjustments (>2%)
            if not is_preliminary:
                await self._check_for_significant_adjustments(
                    tenant_uuid, account_uuid, values
                )

            await self._bulk_upsert(values)
            records_saved += len(values)

        # Item 13: Explicitly flush at the end of a full summary save
        await self.db.flush()

        logger.info(
            "cost_persistence_success",
            tenant_id=str(tenant_uuid),
            account_id=str(account_uuid),
            records=records_saved,
        )

        return {"records_saved": records_saved}

    async def save_records_stream(
        self,
        records: AsyncIterable[dict[str, Any]],
        tenant_id: str | uuid.UUID,
        account_id: str | uuid.UUID,
        reconciliation_run_id: uuid.UUID | None = None,
        is_preliminary: bool = True,
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
            if reconciliation_run_id is not None:
                ingestion_meta["api_request_id"] = str(reconciliation_run_id)
            if isinstance(r.get("tags"), dict):
                ingestion_meta["tags"] = r["tags"]
            resource_id = r.get("resource_id")
            if resource_id not in (None, ""):
                ingestion_meta["resource_id"] = str(resource_id)
            usage_amount = r.get("usage_amount")
            if usage_amount is not None:
                ingestion_meta["usage_amount"] = usage_amount
            usage_unit = r.get("usage_unit")
            if usage_unit not in (None, ""):
                ingestion_meta["usage_unit"] = str(usage_unit)

            usage_amount_dec: Decimal | None = None
            if usage_amount is not None:
                try:
                    usage_amount_dec = Decimal(str(usage_amount))
                except (InvalidOperation, TypeError, ValueError):
                    usage_amount_dec = None

            batch.append(
                {
                    "tenant_id": tenant_uuid,
                    "account_id": account_uuid,
                    "service": r.get("service") or "Unknown",
                    "region": r.get("region") or "Global",
                    "resource_id": str(resource_id)
                    if resource_id not in (None, "")
                    else "",
                    "usage_amount": usage_amount_dec,
                    "usage_unit": str(usage_unit)
                    if usage_unit not in (None, "")
                    else None,
                    "cost_usd": r.get("cost_usd"),
                    "amount_raw": r.get("amount_raw"),
                    "currency": r.get("currency"),
                    "recorded_at": r["timestamp"].date(),
                    "timestamp": r["timestamp"],
                    "usage_type": r.get("usage_type", "Usage"),
                    "canonical_charge_category": canonical_mapping.category,
                    "canonical_charge_subcategory": canonical_mapping.subcategory,
                    "canonical_mapping_version": canonical_mapping.mapping_version,
                    "is_preliminary": bool(is_preliminary),
                    "cost_status": "PRELIMINARY" if is_preliminary else "FINAL",
                    "reconciliation_run_id": reconciliation_run_id,
                    "ingestion_metadata": ingestion_meta,
                    "tags": r.get("tags")
                    if isinstance(r.get("tags"), dict) and r.get("tags")
                    else None,
                }
            )

            if len(batch) >= BATCH_SIZE:
                # Performance: significant adjustment checks are finance-grade signals and only apply
                # when ingesting FINAL rows. Preliminary ingestion/backfills should remain fast.
                if not bool(is_preliminary):
                    await self._check_for_significant_adjustments(
                        tenant_uuid, account_uuid, batch
                    )
                await self._bulk_upsert(batch)
                records_saved += len(batch)
                batch = []

        if batch:
            if not bool(is_preliminary):
                await self._check_for_significant_adjustments(
                    tenant_uuid, account_uuid, batch
                )
            await self._bulk_upsert(batch)
            records_saved += len(batch)

        logger.info(
            "cost_stream_persistence_success",
            tenant_id=str(tenant_uuid),
            account_id=str(account_uuid),
            records=records_saved,
        )

        return {"records_saved": records_saved}

    async def _bulk_upsert(self, values: list[dict[str, Any]]) -> None:
        """Helper for PostgreSQL ON CONFLICT DO UPDATE bulk insert."""
        await _bulk_upsert_impl(self.db, values)

    async def _check_for_significant_adjustments(
        self,
        tenant_id: uuid.UUID,
        account_id: uuid.UUID,
        new_records: list[dict[str, Any]],
    ) -> None:
        """
        Alerts if updated costs differ by >2% from existing records.
        Essential for financial reconciliation (Phase 2).
        Now logs to Forensic Audit Trail (Phase 1.1).
        """
        await _check_for_significant_adjustments_impl(
            self.db,
            tenant_id=tenant_id,
            account_id=account_id,
            new_records=new_records,
            logger_obj=logger,
        )

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
            CostRecord.timestamp <= end_date,
        )
        await self.db.execute(stmt)

    async def cleanup_old_records(self, days_retention: int = 365) -> dict[str, int]:
        """
        Deletes cost records older than the specified retention period in small batches.
        Optimized for space reclamation without long-running database locks.
        """
        return await _cleanup_old_cost_records_impl(
            self.db,
            days_retention=days_retention,
            logger_obj=logger,
        )

    async def cleanup_expired_records_by_plan(
        self,
        *,
        batch_size: int = 5000,
        max_batches: int = 50,
        as_of_date: date | None = None,
    ) -> dict[str, Any]:
        """
        Deletes retained cost records according to the tenant's pricing tier.

        This keeps runtime enforcement aligned with the commercial retention
        contract instead of using a single global retention threshold.
        """
        return await _cleanup_expired_cost_records_by_plan_impl(
            self.db,
            batch_size=batch_size,
            max_batches=max_batches,
            as_of_date=as_of_date,
            logger_obj=logger,
        )

    async def finalize_batch(
        self, days_ago: int = 2, tenant_id: str | None = None
    ) -> dict[str, int]:
        """
        Transition cost records from PRELIMINARY to FINAL after the restatement window.
        AWS typically finalizes costs within 24-48 hours.
        """
        return await _finalize_cost_record_batch_impl(
            self.db,
            days_ago=days_ago,
            tenant_id=tenant_id,
            tenant_id_coercer=self._coerce_uuid_if_valid,
            logger_obj=logger,
        )
