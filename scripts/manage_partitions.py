#!/usr/bin/env python3
"""
Partition Maintenance Script (Postgres)

Automates the creation and maintenance of monthly partitions for high-volume tables.
Designed to be run via pg_cron or as a scheduled job.

Supported partitioned tables:
- cost_records (recorded_at DATE)
- audit_logs (event_timestamp TIMESTAMPTZ)

Usage:
  # Create partitions for the next 3 months (both tables)
  python scripts/manage_partitions.py create --table all --months-ahead 3

  # Validate that the next 6 months partitions exist
  python scripts/manage_partitions.py validate --table all --months-ahead 6

  # (Optional) Archive old cost_records partitions older than 13 months
  python scripts/manage_partitions.py archive --months-old 13

  # (Optional) Drop archived cost_records partitions older than 25 months
  python scripts/manage_partitions.py drop --months-old 25
"""

import argparse
import asyncio
import json
from datetime import date
from contextlib import asynccontextmanager
from dateutil.relativedelta import relativedelta
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.db.session import async_session_maker

logger = structlog.get_logger()
PARTITION_MAINTENANCE_LOCK_ID = 87234091
_SUPPORTED_TABLES = {"cost_records", "audit_logs"}

# ENV check is delegated to async_session_maker and get_settings()


async def get_db_session():
    """Create an async database session using the unified factory."""
    return async_session_maker()


@asynccontextmanager
async def _partition_maintenance_lock(db: AsyncSession):
    """
    Acquire a global advisory lock to prevent concurrent partition maintenance runs.
    """
    result = await db.execute(
        text("SELECT pg_try_advisory_lock(:lock_id)"),
        {"lock_id": PARTITION_MAINTENANCE_LOCK_ID},
    )
    acquired = bool(result.scalar())
    if not acquired:
        raise RuntimeError("another partition maintenance process is already running")

    try:
        yield
    finally:
        await db.execute(
            text("SELECT pg_advisory_unlock(:lock_id)"),
            {"lock_id": PARTITION_MAINTENANCE_LOCK_ID},
        )
        await db.commit()


def _normalize_table(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "all":
        return "all"
    if normalized not in _SUPPORTED_TABLES:
        supported = ", ".join(sorted(_SUPPORTED_TABLES))
        raise ValueError(
            f"Unsupported table '{value}'. Use one of: {supported} or 'all'"
        )
    return normalized


async def create_partition(db: AsyncSession, table: str, year: int, month: int) -> bool:
    """
    Create a monthly partition for a supported partitioned table.

    Example: cost_records_2026_01 for January 2026.
    """
    table = _normalize_table(table)
    if table == "all":
        raise ValueError("create_partition expects a single table, not 'all'")
    partition_name = f"{table}_{year}_{month:02d}"
    start_date = date(year, month, 1)
    end_date = start_date + relativedelta(months=1)

    # Check if partition already exists
    check_sql = text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_tables 
            WHERE tablename = :partition_name
        )
    """)
    result = await db.execute(check_sql, {"partition_name": partition_name})
    exists = result.scalar()

    if exists:
        logger.info("partition_already_exists", partition=partition_name)
        return False

    # Create the partition
    create_sql = text(f"""
        CREATE TABLE IF NOT EXISTS {partition_name} 
        PARTITION OF {table} 
        FOR VALUES FROM ('{start_date.isoformat()}') TO ('{end_date.isoformat()}')
    """)

    try:
        await db.execute(create_sql)
        await db.commit()
        logger.info(
            "partition_created",
            partition=partition_name,
            start=str(start_date),
            end=str(end_date),
        )
        return True
    except Exception as e:
        logger.error(
            "partition_creation_failed", partition=partition_name, error=str(e)
        )
        await db.rollback()
        return False


async def archive_partition(db: AsyncSession, year: int, month: int) -> bool:
    """
    Move a partition to the archive table.

    This detaches the partition from the main table and renames it.
    """
    partition_name = f"cost_records_{year}_{month:02d}"
    archive_name = f"cost_records_archive_{year}_{month:02d}"

    # Check if partition exists
    check_sql = text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_tables 
            WHERE tablename = :partition_name
        )
    """)
    result = await db.execute(check_sql, {"partition_name": partition_name})
    exists = result.scalar()

    if not exists:
        logger.warning("partition_not_found_for_archive", partition=partition_name)
        return False

    try:
        # Detach partition
        detach_sql = text(f"ALTER TABLE cost_records DETACH PARTITION {partition_name}")
        await db.execute(detach_sql)

        # Rename to archive
        rename_sql = text(f"ALTER TABLE {partition_name} RENAME TO {archive_name}")
        await db.execute(rename_sql)

        await db.commit()
        logger.info("partition_archived", original=partition_name, archive=archive_name)
        return True
    except Exception as e:
        logger.error("partition_archive_failed", partition=partition_name, error=str(e))
        await db.rollback()
        return False


async def drop_archived_partition(db: AsyncSession, year: int, month: int) -> bool:
    """
    Permanently delete an archived partition.

    WARNING: This is irreversible. Ensure backups exist before calling.
    """
    archive_name = f"cost_records_archive_{year}_{month:02d}"

    # Check if archive exists
    check_sql = text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_tables 
            WHERE tablename = :archive_name
        )
    """)
    result = await db.execute(check_sql, {"archive_name": archive_name})
    exists = result.scalar()

    if not exists:
        logger.warning("archive_not_found_for_drop", archive=archive_name)
        return False

    try:
        drop_sql = text(f"DROP TABLE {archive_name}")
        await db.execute(drop_sql)
        await db.commit()
        logger.info("archive_dropped", archive=archive_name)
        return True
    except Exception as e:
        logger.error("archive_drop_failed", archive=archive_name, error=str(e))
        await db.rollback()
        return False


async def create_future_partitions(*, table: str, months_ahead: int = 3) -> int:
    """Create partitions for the next N months."""
    table = _normalize_table(table)
    db = await get_db_session()
    today = date.today()

    created = 0
    async with _partition_maintenance_lock(db):
        targets = []
        for i in range(months_ahead + 1):
            targets.append(today + relativedelta(months=i))

        tables = sorted(_SUPPORTED_TABLES) if table == "all" else [table]
        for t in tables:
            for target_date in targets:
                if await create_partition(db, t, target_date.year, target_date.month):
                    created += 1

    await db.close()
    logger.info(
        "future_partitions_created",
        table=table,
        count=created,
        months_ahead=months_ahead,
    )
    return created


async def validate_future_partitions(
    *, table: str, months_ahead: int = 3
) -> dict[str, object]:
    """
    Validate that monthly partitions exist for the next N months.

    Returns a structured report that can be used as evidence or operator output.
    """
    table = _normalize_table(table)
    db = await get_db_session()
    today = date.today()

    targets = []
    for i in range(months_ahead + 1):
        targets.append(today + relativedelta(months=i))

    tables = sorted(_SUPPORTED_TABLES) if table == "all" else [table]
    missing: dict[str, list[str]] = {}
    existing: dict[str, list[str]] = {}
    async with _partition_maintenance_lock(db):
        for t in tables:
            existing[t] = []
            missing[t] = []
            for target_date in targets:
                partition_name = f"{t}_{target_date.year}_{target_date.month:02d}"
                exists = await db.scalar(
                    text(
                        """
                        SELECT EXISTS (
                            SELECT 1 FROM pg_tables
                            WHERE schemaname = current_schema()
                              AND tablename = :partition_name
                        )
                        """
                    ),
                    {"partition_name": partition_name},
                )
                if bool(exists):
                    existing[t].append(partition_name)
                else:
                    missing[t].append(partition_name)

    await db.close()
    report = {
        "table": table,
        "months_ahead": int(months_ahead),
        "expected_months": [d.isoformat() for d in targets],
        "missing": missing,
        "existing": existing,
        "ok": all(len(missing[t]) == 0 for t in missing),
    }
    logger.info("partition_validation_complete", **report)
    return report


async def archive_old_partitions(months_old: int = 13):
    """Archive all partitions older than the specified cutoff (N months)."""
    db = await get_db_session()
    today = date.today()
    cutoff = today - relativedelta(months=months_old)

    archived = 0
    # Archive all partitions older than cutoff
    # We query pg_tables to find all candidate partitions
    async with _partition_maintenance_lock(db):
        check_sql = text("""
            SELECT tablename FROM pg_tables 
            WHERE tablename LIKE 'cost_records_%' 
            AND tablename NOT LIKE 'cost_records_archive_%'
        """)
        result = await db.execute(check_sql)
        all_partitions = result.scalars().all()

        for table_name in all_partitions:
            # Expected format: cost_records_YYYY_MM
            try:
                parts = table_name.split("_")
                if len(parts) != 4:
                    continue
                y, m = int(parts[2]), int(parts[3])
                table_date = date(y, m, 1)

                if table_date < cutoff:
                    if await archive_partition(db, y, m):
                        archived += 1
            except (ValueError, IndexError):
                continue

    await db.close()
    logger.info("old_partitions_archived", count=archived, months_old=months_old)
    return archived


async def drop_old_archives(months_old: int = 25):
    """Drop all archived partitions older than the specified cutoff (N months)."""
    db = await get_db_session()
    today = date.today()
    cutoff = today - relativedelta(months=months_old)

    dropped = 0
    # Drop all archives older than cutoff
    async with _partition_maintenance_lock(db):
        check_sql = text("""
            SELECT tablename FROM pg_tables 
            WHERE tablename LIKE 'cost_records_archive_%'
        """)
        result = await db.execute(check_sql)
        all_archives = result.scalars().all()

        for table_name in all_archives:
            # Expected format: cost_records_archive_YYYY_MM
            try:
                parts = table_name.split("_")
                if len(parts) != 5:
                    continue
                y, m = int(parts[3]), int(parts[4])
                table_date = date(y, m, 1)

                if table_date < cutoff:
                    if await drop_archived_partition(db, y, m):
                        dropped += 1
            except (ValueError, IndexError):
                continue

    await db.close()
    logger.info("old_archives_dropped", count=dropped, months_old=months_old)
    return dropped


def main():
    parser = argparse.ArgumentParser(
        description="Manage Postgres partitions for high-volume tables"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Create command
    create_parser = subparsers.add_parser("create", help="Create future partitions")
    create_parser.add_argument(
        "--table",
        type=str,
        default="all",
        help="Partitioned table to manage (cost_records, audit_logs, all). Default: all",
    )
    create_parser.add_argument(
        "--months-ahead", type=int, default=3, help="Months ahead to create"
    )

    # Validate command
    validate_parser = subparsers.add_parser(
        "validate", help="Validate that future partitions exist"
    )
    validate_parser.add_argument(
        "--table",
        type=str,
        default="all",
        help="Partitioned table to validate (cost_records, audit_logs, all). Default: all",
    )
    validate_parser.add_argument(
        "--months-ahead", type=int, default=3, help="Months ahead to validate"
    )

    # Archive command
    archive_parser = subparsers.add_parser("archive", help="Archive old partitions")
    archive_parser.add_argument(
        "--months-old",
        type=int,
        default=13,
        help="Archive partitions older than N months",
    )

    # Drop command
    drop_parser = subparsers.add_parser("drop", help="Drop archived partitions")
    drop_parser.add_argument(
        "--months-old", type=int, default=25, help="Drop archives older than N months"
    )

    args = parser.parse_args()

    if args.command == "create":
        asyncio.run(
            create_future_partitions(
                table=str(args.table), months_ahead=int(args.months_ahead)
            )
        )
    elif args.command == "validate":
        report = asyncio.run(
            validate_future_partitions(
                table=str(args.table), months_ahead=int(args.months_ahead)
            )
        )
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.command == "archive":
        asyncio.run(archive_old_partitions(args.months_old))
    elif args.command == "drop":
        asyncio.run(drop_old_archives(args.months_old))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
