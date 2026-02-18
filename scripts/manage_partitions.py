#!/usr/bin/env python3
"""
Partition Maintenance CLI (Postgres)
Wrapper around PartitionMaintenanceService.
"""

import argparse
import asyncio
import json
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.db.session import async_session_maker
from app.shared.core.maintenance import PartitionMaintenanceService

logger = structlog.get_logger()

async def create_partitions(months_ahead: int):
    async with async_session_maker() as session:
        service = PartitionMaintenanceService(session)
        created = await service.create_future_partitions(months_ahead=months_ahead)
        await session.commit()
        print(f"Partitions created: {created}")

async def validate_partitions(months_ahead: int):
    # For validation, we use a simple check loop
    from datetime import date
    from dateutil.relativedelta import relativedelta
    from sqlalchemy import text
    
    async with async_session_maker() as session:
        today = date.today()
        report = {"existing": {}, "missing": {}, "ok": True}
        
        for table in PartitionMaintenanceService.SUPPORTED_TABLES:
            report["existing"][table] = []
            report["missing"][table] = []
            prefix = "p" if table == "audit_logs" else ""
            
            for i in range(months_ahead + 1):
                target_date = today + relativedelta(months=i)
                name = f"{table}_{prefix}{target_date.year}_{target_date.month:02d}"
                
                exists = await session.scalar(
                    text("SELECT EXISTS (SELECT 1 FROM pg_tables WHERE tablename = :name AND schemaname = current_schema())"),
                    {"name": name}
                )
                if exists:
                    report["existing"][table].append(name)
                else:
                    report["missing"][table].append(name)
                    report["ok"] = False
        
        print(json.dumps(report, indent=2))

def main():
    parser = argparse.ArgumentParser(description="Manage Postgres partitions")
    subparsers = parser.add_subparsers(dest="command")
    
    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--months-ahead", type=int, default=3)
    
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--months-ahead", type=int, default=3)
    
    args = parser.parse_args()
    
    if args.command == "create":
        asyncio.run(create_partitions(args.months_ahead))
    elif args.command == "validate":
        asyncio.run(validate_partitions(args.months_ahead))
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
