#!/usr/bin/env python3
"""
Cost Record Partition Management Script

Automates the creation and maintenance of monthly partitions for the cost_records table.
Designed to be run via pg_cron or as a scheduled job.

Usage:
    # Create partitions for the next 3 months
    python scripts/manage_partitions.py create --months-ahead 3
    
    # Archive partitions older than 13 months
    python scripts/manage_partitions.py archive --months-old 13
    
    # Drop archived partitions older than 25 months
    python scripts/manage_partitions.py drop --months-old 25
"""

import argparse
import asyncio
from datetime import date
from dateutil.relativedelta import relativedelta
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os

logger = structlog.get_logger()

# ENV mandated for production safety to prevent accidental targeting of local DB
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    logger.error("missing_required_environment_variable", variable="DATABASE_URL")
    print("CRITICAL: DATABASE_URL environment variable not set. Aborting for safety.")
    import sys
    sys.exit(1)

async def get_db_session():
    """Create an async database session."""
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return async_session()


async def create_partition(db: AsyncSession, year: int, month: int) -> bool:
    """
    Create a monthly partition for cost_records.
    
    Example: cost_records_2026_01 for January 2026
    """
    partition_name = f"cost_records_{year}_{month:02d}"
    start_date = date(year, month, 1)
    end_date = (start_date + relativedelta(months=1))
    
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
        PARTITION OF cost_records 
        FOR VALUES FROM ('{start_date.isoformat()}') TO ('{end_date.isoformat()}')
    """)
    
    try:
        await db.execute(create_sql)
        await db.commit()
        logger.info("partition_created", partition=partition_name, start=str(start_date), end=str(end_date))
        return True
    except Exception as e:
        logger.error("partition_creation_failed", partition=partition_name, error=str(e))
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


async def create_future_partitions(months_ahead: int = 3):
    """Create partitions for the next N months."""
    db = await get_db_session()
    today = date.today()
    
    created = 0
    for i in range(months_ahead + 1):
        target_date = today + relativedelta(months=i)
        if await create_partition(db, target_date.year, target_date.month):
            created += 1
    
    await db.close()
    logger.info("future_partitions_created", count=created, months_ahead=months_ahead)
    return created


async def archive_old_partitions(months_old: int = 13):
    """Archive partitions older than N months."""
    db = await get_db_session()
    today = date.today()
    cutoff = today - relativedelta(months=months_old)
    
    archived = 0
    # Archive from cutoff going back 12 months
    for i in range(12):
        target_date = cutoff - relativedelta(months=i)
        if await archive_partition(db, target_date.year, target_date.month):
            archived += 1
    
    await db.close()
    logger.info("old_partitions_archived", count=archived, months_old=months_old)
    return archived


async def drop_old_archives(months_old: int = 25):
    """Drop archived partitions older than N months."""
    db = await get_db_session()
    today = date.today()
    cutoff = today - relativedelta(months=months_old)
    
    dropped = 0
    # Drop from cutoff going back 12 months
    for i in range(12):
        target_date = cutoff - relativedelta(months=i)
        if await drop_archived_partition(db, target_date.year, target_date.month):
            dropped += 1
    
    await db.close()
    logger.info("old_archives_dropped", count=dropped, months_old=months_old)
    return dropped


def main():
    parser = argparse.ArgumentParser(description="Manage cost_records partitions")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Create command
    create_parser = subparsers.add_parser("create", help="Create future partitions")
    create_parser.add_argument("--months-ahead", type=int, default=3, help="Months ahead to create")
    
    # Archive command
    archive_parser = subparsers.add_parser("archive", help="Archive old partitions")
    archive_parser.add_argument("--months-old", type=int, default=13, help="Archive partitions older than N months")
    
    # Drop command
    drop_parser = subparsers.add_parser("drop", help="Drop archived partitions")
    drop_parser.add_argument("--months-old", type=int, default=25, help="Drop archives older than N months")
    
    args = parser.parse_args()
    
    if args.command == "create":
        asyncio.run(create_future_partitions(args.months_ahead))
    elif args.command == "archive":
        asyncio.run(archive_old_partitions(args.months_old))
    elif args.command == "drop":
        asyncio.run(drop_old_archives(args.months_old))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
