#!/usr/bin/env python3
"""Run the production partition-maintenance archival path against the configured DB."""

from __future__ import annotations

import argparse
import asyncio

from app.shared.core.maintenance import PartitionMaintenanceService
from app.shared.db.session import async_session_maker


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Execute partition archival using the same maintenance service used by the scheduler."
    )
    parser.add_argument(
        "--months-old",
        type=int,
        default=13,
        help="Archive partitions older than this many months.",
    )
    parser.add_argument(
        "--months-ahead",
        type=int,
        default=3,
        help="Create future partitions this many months ahead before archiving.",
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    async with async_session_maker() as session:
        service = PartitionMaintenanceService(session)
        created = await service.create_future_partitions(months_ahead=int(args.months_ahead))
        archived = await service.archive_old_partitions(months_old=int(args.months_old))
        await session.commit()
    print(
        f"Partition maintenance complete: created={created} archived={archived} months_old={int(args.months_old)}"
    )


if __name__ == "__main__":
    asyncio.run(main())

