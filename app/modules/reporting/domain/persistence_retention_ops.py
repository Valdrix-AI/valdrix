from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cloud import CostRecord
from app.models.tenant import Tenant
from app.shared.core.pricing import get_tier_limit, normalize_tier


def coerce_positive_int(
    value: Any,
    *,
    default: int,
    minimum: int,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= minimum else default


async def cleanup_old_cost_records(
    db: AsyncSession,
    *,
    days_retention: int,
    logger_obj: Any,
) -> dict[str, int]:
    """Delete old cost records in bounded batches to avoid long locks."""
    cutoff_date = datetime.combine(
        date.today() - timedelta(days=days_retention), datetime.min.time()
    ).replace(tzinfo=timezone.utc)
    total_deleted = 0
    batch_size = 5000
    while True:
        select_stmt = (
            select(CostRecord.id)
            .where(CostRecord.timestamp < cutoff_date)
            .limit(batch_size)
        )
        result = await db.execute(select_stmt)
        ids = result.scalars().all()
        if not ids:
            break

        delete_stmt = delete(CostRecord).where(CostRecord.id.in_(ids))
        await db.execute(delete_stmt)
        total_deleted += len(ids)
        await db.flush()

    logger_obj.info(
        "cost_retention_cleanup_complete",
        cutoff_date=str(cutoff_date),
        total_deleted=total_deleted,
    )
    return {"deleted_count": total_deleted}


async def cleanup_expired_cost_records_by_plan(
    db: AsyncSession,
    *,
    batch_size: int,
    max_batches: int,
    as_of_date: date | None,
    logger_obj: Any,
) -> dict[str, Any]:
    """
    Delete retained cost records according to tenant plan retention windows.
    """
    resolved_batch_size = coerce_positive_int(
        batch_size,
        default=5000,
        minimum=100,
    )
    resolved_max_batches = coerce_positive_int(
        max_batches,
        default=50,
        minimum=1,
    )
    target_date = as_of_date or date.today()

    distinct_plans_result = await db.execute(select(Tenant.plan).distinct())
    raw_plans = distinct_plans_result.scalars().all()

    retention_groups: dict[tuple[str, int], list[str]] = {}
    for raw_plan in raw_plans:
        normalized_tier = normalize_tier(raw_plan).value
        retention_days = get_tier_limit(normalized_tier, "retention_days")
        if retention_days is None:
            continue
        try:
            retention_days_int = int(retention_days)
        except (TypeError, ValueError):
            continue
        if retention_days_int < 1:
            continue
        retention_groups.setdefault((normalized_tier, retention_days_int), []).append(
            str(raw_plan)
        )

    total_deleted = 0
    total_batches = 0
    tier_deleted_counts: dict[str, int] = {}
    tenant_reports: dict[str, dict[str, Any]] = {}

    for (tier_name, retention_days), plan_values in sorted(retention_groups.items()):
        cutoff_date = target_date - timedelta(days=retention_days)
        tier_deleted = 0

        for _ in range(resolved_max_batches):
            select_stmt = (
                select(
                    CostRecord.id.label("id"),
                    CostRecord.tenant_id.label("tenant_id"),
                    CostRecord.recorded_at.label("recorded_at"),
                )
                .join(Tenant, Tenant.id == CostRecord.tenant_id)
                .where(
                    Tenant.plan.in_(plan_values),
                    CostRecord.recorded_at < cutoff_date,
                )
                .order_by(CostRecord.recorded_at.asc(), CostRecord.id.asc())
                .limit(resolved_batch_size)
            )
            batch_rows = (await db.execute(select_stmt)).all()
            if not batch_rows:
                break

            record_ids = [row.id for row in batch_rows]
            for row in batch_rows:
                tenant_key = str(row.tenant_id)
                recorded_at_value = row.recorded_at
                report = tenant_reports.setdefault(
                    tenant_key,
                    {
                        "tenant_id": tenant_key,
                        "tenant_tier": tier_name,
                        "retention_days": retention_days,
                        "deleted_count": 0,
                        "oldest_recorded_at": None,
                        "newest_recorded_at": None,
                    },
                )
                report["deleted_count"] += 1
                if isinstance(recorded_at_value, date):
                    recorded_at_iso = recorded_at_value.isoformat()
                    oldest = report["oldest_recorded_at"]
                    newest = report["newest_recorded_at"]
                    if oldest is None or recorded_at_iso < str(oldest):
                        report["oldest_recorded_at"] = recorded_at_iso
                    if newest is None or recorded_at_iso > str(newest):
                        report["newest_recorded_at"] = recorded_at_iso

            delete_stmt = delete(CostRecord).where(CostRecord.id.in_(record_ids))
            await db.execute(delete_stmt)
            await db.flush()

            deleted_count = len(record_ids)
            total_deleted += deleted_count
            tier_deleted += deleted_count
            total_batches += 1

        if tier_deleted:
            tier_deleted_counts[tier_name] = tier_deleted

    reports = sorted(
        tenant_reports.values(),
        key=lambda item: (str(item["tenant_tier"]), str(item["tenant_id"])),
    )
    logger_obj.info(
        "cost_retention_cleanup_complete",
        as_of_date=target_date.isoformat(),
        total_deleted=total_deleted,
        total_batches=total_batches,
        tiers=tier_deleted_counts,
        tenants_affected=len(reports),
    )
    return {
        "deleted_count": total_deleted,
        "tiers": tier_deleted_counts,
        "tenant_reports": reports,
        "batch_size": resolved_batch_size,
        "max_batches": resolved_max_batches,
        "as_of_date": target_date.isoformat(),
    }


async def finalize_cost_record_batch(
    db: AsyncSession,
    *,
    days_ago: int,
    tenant_id: Any,
    tenant_id_coercer: Any,
    logger_obj: Any,
) -> dict[str, int]:
    """Transition preliminary cost rows to final after the restatement window."""
    cutoff_date = date.today() - timedelta(days=days_ago)

    stmt = (
        update(CostRecord)
        .where(
            CostRecord.cost_status == "PRELIMINARY",
            CostRecord.recorded_at <= cutoff_date,
        )
        .values(cost_status="FINAL", is_preliminary=False)
    )

    if tenant_id:
        stmt = stmt.where(CostRecord.tenant_id == tenant_id_coercer(tenant_id))

    result = await db.execute(stmt)
    await db.flush()

    rowcount = getattr(result, "rowcount", None)
    count = int(rowcount or 0)
    logger_obj.info(
        "cost_batch_finalization_complete",
        tenant_id=tenant_id,
        cutoff_date=str(cutoff_date),
        records_finalized=count,
    )

    return {"records_finalized": count}

