#!/usr/bin/env python3
"""
Cost ingestion persistence benchmark (synthetic).

Goal:
- Provide a repeatable, production-leaning harness to validate the write path
  (`CostPersistenceService.save_records_stream`) at higher volumes.

Notes:
- This script writes real rows to `cost_records` for a dedicated CloudAccount.
- By default it cleans up inserted rows afterwards to keep dev databases tidy.
- It is intentionally tokenless/HTTP-free: it measures DB persistence throughput only.

Example:
  uv run python scripts/benchmark_ingestion_persistence.py --records 100000 --min-rps 1500 \\
    --out reports/performance/ingestion_persistence.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import os
import httpx
from sqlalchemy import delete, select

from app.models.cloud import CloudAccount, CostRecord
from app.models.tenant import Tenant
from app.modules.reporting.domain.persistence import CostPersistenceService
from app.shared.core.evidence_capture import sanitize_bearer_token
from app.shared.db.session import async_session_maker


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark the cost persistence write path."
    )
    parser.add_argument(
        "--url",
        dest="url",
        default=os.environ.get("VALDRIX_API_URL", "http://127.0.0.1:8000"),
        help="Base URL (used only for --publish).",
    )
    parser.add_argument(
        "--records",
        dest="records",
        type=int,
        default=50_000,
        help="Number of records to write",
    )
    parser.add_argument(
        "--services", dest="services", type=int, default=25, help="Service cardinality"
    )
    parser.add_argument(
        "--regions", dest="regions", type=int, default=5, help="Region cardinality"
    )
    parser.add_argument(
        "--min-rps",
        dest="min_rps",
        type=float,
        default=None,
        help="Fail if records/sec < this",
    )
    parser.add_argument(
        "--backfill-runs",
        dest="backfill_runs",
        type=int,
        default=0,
        help="Repeat ingestion over the same synthetic window to stress backfill/replay updates.",
    )
    parser.add_argument(
        "--min-backfill-rps",
        dest="min_backfill_rps",
        type=float,
        default=None,
        help="Fail if any backfill run records/sec < this (requires --backfill-runs).",
    )
    parser.add_argument(
        "--provider",
        dest="provider",
        default="aws",
        help="Provider label for the benchmark CloudAccount (aws|azure|gcp|saas|license|platform|hybrid).",
    )
    parser.add_argument(
        "--tenant-id",
        dest="tenant_id",
        default="",
        help="Tenant UUID to use (default: first tenant in DB)",
    )
    parser.add_argument(
        "--account-id",
        dest="account_id",
        default="",
        help="CloudAccount UUID to use (default: create a dedicated benchmark account)",
    )
    parser.add_argument(
        "--no-cleanup",
        dest="no_cleanup",
        action="store_true",
        help="Keep inserted cost_records + benchmark CloudAccount (default: cleanup).",
    )
    parser.add_argument(
        "--out",
        dest="out",
        default="",
        help="Write JSON results to this path (optional).",
    )
    parser.add_argument(
        "--publish",
        dest="publish",
        action="store_true",
        help="Publish the benchmark evidence to the tenant audit log (requires VALDRIX_TOKEN).",
    )
    return parser.parse_args()


async def _resolve_tenant_id(db) -> UUID:
    row = await db.scalar(select(Tenant.id).limit(1))
    if not row:
        raise SystemExit(
            "No tenants found in DB. Complete onboarding/seed a tenant first."
        )
    return UUID(str(row))


async def _resolve_or_create_account(
    db,
    tenant_id: UUID,
    account_id: str | None,
    *,
    provider: str,
) -> tuple[UUID, bool]:
    if account_id:
        parsed = UUID(account_id)
        existing = await db.scalar(
            select(CloudAccount.id).where(
                CloudAccount.id == parsed, CloudAccount.tenant_id == tenant_id
            )
        )
        if existing:
            return parsed, False

    benchmark_account_id = uuid4()
    account = CloudAccount(
        id=benchmark_account_id,
        tenant_id=tenant_id,
        provider=str(provider or "aws").strip().lower() or "aws",
        name="benchmark-ingestion-persistence",
        is_active=True,
    )
    db.add(account)
    await db.commit()
    return benchmark_account_id, True


async def _synthetic_records(
    *,
    total: int,
    services: int,
    regions: int,
    provider: str,
    base_timestamp: datetime,
    run_label: str,
) -> AsyncGenerator[dict[str, object], None]:
    service_mod = max(1, int(services))
    region_mod = max(1, int(regions))
    for i in range(int(total)):
        ts = base_timestamp + timedelta(seconds=i)
        yield {
            "provider": str(provider or "aws").strip().lower() or "aws",
            "service": f"svc-{i % service_mod}",
            "region": f"region-{i % region_mod}",
            "usage_type": "benchmark",
            "cost_usd": 0.01,
            "amount_raw": None,
            "currency": "USD",
            "timestamp": ts,
            "source_adapter": "benchmark_persistence",
            "tags": {"run": run_label},
        }


async def main() -> None:
    args = _parse_args()
    cleanup = not bool(args.no_cleanup)
    backfill_runs = max(0, int(args.backfill_runs or 0))

    async with async_session_maker() as db:
        tenant_id = (
            UUID(args.tenant_id)
            if str(args.tenant_id).strip()
            else await _resolve_tenant_id(db)
        )
        account_id, created_account = await _resolve_or_create_account(
            db,
            tenant_id,
            str(args.account_id).strip() or None,
            provider=str(args.provider or "aws"),
        )

        persistence = CostPersistenceService(db)

        provider = str(args.provider or "aws").strip().lower() or "aws"
        # Use a stable base timestamp so backfill runs replay the same uniqueness window.
        base_timestamp = (datetime.now(timezone.utc) - timedelta(days=1)).replace(
            microsecond=0
        )

        started_at = datetime.now(timezone.utc)
        runs: list[dict[str, object]] = []

        def stream_for(run_label: str) -> AsyncGenerator[dict[str, object], None]:
            return _synthetic_records(
                total=args.records,
                services=args.services,
                regions=args.regions,
                provider=provider,
                base_timestamp=base_timestamp,
                run_label=run_label,
            )

        # Initial ingest run.
        start = time.perf_counter()
        save_result = await persistence.save_records_stream(
            records=stream_for("benchmark.initial"),
            tenant_id=str(tenant_id),
            account_id=str(account_id),
        )
        duration = time.perf_counter() - start
        saved = int(save_result.get("records_saved", 0) or 0)
        rps = saved / duration if duration > 0 else 0.0
        runs.append(
            {
                "kind": "initial",
                "records_saved": saved,
                "duration_seconds": round(duration, 4),
                "records_per_second": round(rps, 4),
            }
        )

        backfill_rps_values: list[float] = []
        for idx in range(backfill_runs):
            start = time.perf_counter()
            backfill_result = await persistence.save_records_stream(
                records=stream_for(f"benchmark.backfill.{idx + 1}"),
                tenant_id=str(tenant_id),
                account_id=str(account_id),
            )
            backfill_duration = time.perf_counter() - start
            backfill_saved = int(backfill_result.get("records_saved", 0) or 0)
            backfill_rps = (
                backfill_saved / backfill_duration if backfill_duration > 0 else 0.0
            )
            backfill_rps_values.append(backfill_rps)
            runs.append(
                {
                    "kind": "backfill",
                    "backfill_index": idx + 1,
                    "records_saved": backfill_saved,
                    "duration_seconds": round(backfill_duration, 4),
                    "records_per_second": round(backfill_rps, 4),
                }
            )

        completed_at = datetime.now(timezone.utc)

        thresholds: dict[str, float] | None = None
        meets_targets: bool | None = None
        has_thresholds = args.min_rps is not None or args.min_backfill_rps is not None
        if has_thresholds:
            thresholds = {}
            meets_targets = True
            if args.min_rps is not None:
                thresholds["min_initial_records_per_second"] = float(args.min_rps)
                meets_targets = bool(meets_targets and rps >= float(args.min_rps))
            if args.min_backfill_rps is not None and backfill_runs > 0:
                thresholds["min_backfill_records_per_second"] = float(
                    args.min_backfill_rps
                )
                meets_targets = bool(
                    meets_targets
                    and all(
                        value >= float(args.min_backfill_rps)
                        for value in backfill_rps_values
                    )
                )

        payload: dict[str, object] = {
            "tenant_id": str(tenant_id),
            "account_id": str(account_id),
            "provider": provider,
            "records_requested": int(args.records),
            "records_saved": saved,
            "duration_seconds": round(duration, 4),
            "records_per_second": round(rps, 4),
            "services": int(args.services),
            "regions": int(args.regions),
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "cleanup": cleanup,
            "thresholds": thresholds,
            "meets_targets": meets_targets,
            "runner": "scripts/benchmark_ingestion_persistence.py",
            "backfill_runs": backfill_runs if backfill_runs > 0 else None,
            "runs": runs if backfill_runs > 0 else None,
        }

        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, sort_keys=True)

        if cleanup:
            await db.execute(
                delete(CostRecord).where(CostRecord.account_id == account_id)
            )
            if created_account:
                await db.execute(
                    delete(CloudAccount).where(CloudAccount.id == account_id)
                )
            await db.commit()

        print(json.dumps(payload, indent=2, sort_keys=True))

        if args.publish:
            raw_token = os.environ.get("VALDRIX_TOKEN", "").strip()
            try:
                token = sanitize_bearer_token(raw_token)
            except ValueError as exc:
                raise SystemExit(
                    "Invalid VALDRIX_TOKEN. Ensure it's a single JWT string. "
                    f"Details: {exc}"
                ) from None
            if not token:
                raise SystemExit("VALDRIX_TOKEN is required for --publish.")
            base_url = str(args.url).rstrip("/")
            publish_url = (
                f"{base_url}/api/v1/audit/performance/ingestion/persistence/evidence"
            )
            headers = {"Authorization": f"Bearer {token}"}
            async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
                resp = await client.post(publish_url, json=payload)
            if resp.status_code >= 400:
                raise SystemExit(f"Publish failed ({resp.status_code}): {resp.text}")

        if has_thresholds and meets_targets is False:
            raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
