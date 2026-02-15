#!/usr/bin/env python3
"""
End-to-end ingestion soak runner (Performance/Scale sign-off).

This script exercises the real background job execution path:
enqueue -> job processor -> adapter streaming -> persistence.

It is meant for operator-driven evidence capture in a staging/prod-like environment.

Example (local worker processing):
  uv run python scripts/soak_ingestion_jobs.py --jobs 5 --workers 2 --publish
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from uuid import UUID

import httpx
from sqlalchemy import text

from app.models.background_job import JobStatus, JobType
from app.modules.governance.domain.jobs.processor import JobProcessor, enqueue_job
from app.shared.core.evidence_capture import sanitize_bearer_token
from app.shared.db.session import async_session_maker


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an end-to-end cost ingestion soak test."
    )
    parser.add_argument(
        "--tenant-id",
        dest="tenant_id",
        default=os.getenv("VALDRIX_TENANT_ID", "").strip(),
        help="Tenant UUID. If omitted, uses the first tenant in DB (dev convenience).",
    )
    parser.add_argument(
        "--jobs",
        dest="jobs",
        type=int,
        default=5,
        help="Number of ingestion jobs to enqueue",
    )
    parser.add_argument(
        "--workers", dest="workers", type=int, default=1, help="Number of local workers"
    )
    parser.add_argument(
        "--batch-limit",
        dest="batch_limit",
        type=int,
        default=10,
        help="Max jobs per worker polling iteration",
    )
    parser.add_argument(
        "--start-date", dest="start_date", default="", help="ISO date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end-date", dest="end_date", default="", help="ISO date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--p95-target",
        dest="p95_target",
        type=float,
        default=None,
        help="Optional p95 duration target (seconds). Stored as evidence threshold.",
    )
    parser.add_argument(
        "--max-error-rate",
        dest="max_error_rate",
        type=float,
        default=None,
        help="Optional max error rate target (percent). Stored as evidence threshold.",
    )
    parser.add_argument(
        "--out",
        dest="out",
        default="",
        help="Write JSON results to this path (optional)",
    )
    parser.add_argument(
        "--publish",
        dest="publish",
        action="store_true",
        help="Publish evidence to /api/v1/audit/performance/ingestion/soak/evidence (admin only).",
    )
    parser.add_argument(
        "--api-url",
        dest="api_url",
        default=os.getenv("VALDRIX_API_URL", "http://127.0.0.1:8000").strip(),
        help="API base URL for --publish",
    )
    return parser.parse_args()


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    q = max(0.0, min(1.0, float(q)))
    sorted_values = sorted(values)
    idx = int(round((len(sorted_values) - 1) * q))
    return float(sorted_values[idx])


@dataclass(frozen=True)
class _JobRun:
    job_id: str
    status: str
    duration_seconds: float | None
    ingested_records: int | None
    error: str | None


async def _resolve_tenant_id(raw: str) -> UUID:
    if raw:
        return UUID(raw)

    async with async_session_maker() as db:
        value = await db.scalar(
            text("SELECT id::text FROM tenants ORDER BY id LIMIT 1")
        )
        if not isinstance(value, str) or not value.strip():
            raise SystemExit(
                "No tenants found in DB. Provide --tenant-id or VALDRIX_TENANT_ID."
            )
        return UUID(value.strip())


async def _enqueue_jobs(
    *,
    tenant_id: UUID,
    jobs: int,
    start_date: date | None,
    end_date: date | None,
) -> list[str]:
    payload = None
    if start_date is not None and end_date is not None:
        payload = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }

    job_ids: list[str] = []
    async with async_session_maker() as db:
        for _ in range(max(1, int(jobs))):
            job = await enqueue_job(
                db=db,
                tenant_id=tenant_id,
                job_type=JobType.COST_INGESTION,
                payload=payload,
                max_attempts=1,  # Evidence runs should fail fast (avoid backoff noise).
            )
            job_ids.append(str(job.id))
    return job_ids


async def _pending_count(tenant_id: UUID, job_type: str) -> int:
    async with async_session_maker() as db:
        value = await db.scalar(
            text(
                """
                SELECT COUNT(*)::int
                FROM background_jobs
                WHERE tenant_id = :tenant_id
                  AND job_type = :job_type
                  AND status IN ('pending','running')
                  AND COALESCE(is_deleted, false) = false
                """
            ),
            {"tenant_id": str(tenant_id), "job_type": str(job_type)},
        )
        return int(value or 0)


async def _worker_loop(*, tenant_id: UUID, job_type: str, batch_limit: int) -> None:
    async with async_session_maker() as db:
        processor = JobProcessor(db)
        while True:
            results = await processor.process_pending_jobs(
                limit=int(batch_limit),
                tenant_id=tenant_id,
                job_type=job_type,
            )
            if int(results.get("processed", 0) or 0) > 0:
                continue
            # No jobs processed this iteration. If nothing is pending/running, stop.
            if await _pending_count(tenant_id, job_type) == 0:
                break
            await asyncio.sleep(0.25)


async def _collect_job_runs(job_ids: list[str]) -> list[_JobRun]:
    if not job_ids:
        return []

    async with async_session_maker() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT id::text, status, started_at, completed_at, error_message, result
                    FROM background_jobs
                    WHERE id::text = ANY(:ids)
                    ORDER BY id::text ASC
                    """
                ),
                {"ids": list(job_ids)},
            )
        ).all()

    runs: list[_JobRun] = []
    for row in rows:
        job_id = str(row[0])
        status = str(row[1] or "")
        started_at = row[2]
        completed_at = row[3]
        error_message = row[4]
        result = row[5]

        duration: float | None = None
        if isinstance(started_at, datetime) and isinstance(completed_at, datetime):
            duration = max(0.0, (completed_at - started_at).total_seconds())

        ingested: int | None = None
        if isinstance(result, dict):
            raw_ingested = result.get("ingested")
            if isinstance(raw_ingested, int):
                ingested = raw_ingested
            elif raw_ingested is not None:
                try:
                    ingested = int(raw_ingested)
                except Exception:
                    ingested = None

        runs.append(
            _JobRun(
                job_id=job_id,
                status=status,
                duration_seconds=duration,
                ingested_records=ingested,
                error=str(error_message) if error_message else None,
            )
        )
    return runs


async def main() -> None:
    args = _parse_args()
    tenant_id = await _resolve_tenant_id(str(args.tenant_id or "").strip())
    jobs = max(1, int(args.jobs or 1))
    workers = max(1, int(args.workers or 1))
    batch_limit = max(1, int(args.batch_limit or 1))

    start_date: date | None = None
    end_date: date | None = None
    if args.start_date or args.end_date:
        if not args.start_date or not args.end_date:
            raise SystemExit(
                "Both --start-date and --end-date must be provided for backfill windows."
            )
        start_date = date.fromisoformat(str(args.start_date).strip())
        end_date = date.fromisoformat(str(args.end_date).strip())
        if start_date > end_date:
            raise SystemExit("--start-date must be <= --end-date")

    job_ids = await _enqueue_jobs(
        tenant_id=tenant_id, jobs=jobs, start_date=start_date, end_date=end_date
    )

    soak_started_at = datetime.now(timezone.utc)
    start_ts = time.perf_counter()
    await asyncio.gather(
        *[
            _worker_loop(
                tenant_id=tenant_id,
                job_type=JobType.COST_INGESTION.value,
                batch_limit=batch_limit,
            )
            for _ in range(workers)
        ]
    )
    wall_seconds = max(0.0, time.perf_counter() - start_ts)
    soak_completed_at = datetime.now(timezone.utc)

    runs = await _collect_job_runs(job_ids)
    durations = [
        float(r.duration_seconds)
        for r in runs
        if isinstance(r.duration_seconds, (int, float))
    ]
    failures = [
        r
        for r in runs
        if r.status in {JobStatus.FAILED.value, JobStatus.DEAD_LETTER.value}
    ]
    succeeded = [r for r in runs if r.status == JobStatus.COMPLETED.value]

    errors_sample: list[str] = []
    for item in failures:
        if item.error and item.error not in errors_sample:
            errors_sample.append(item.error)
        if len(errors_sample) >= 10:
            break

    success_rate = 0.0
    if runs:
        success_rate = round((len(succeeded) / len(runs)) * 100.0, 4)

    results = {
        "jobs_total": len(runs),
        "jobs_succeeded": len(succeeded),
        "jobs_failed": len(failures),
        "success_rate_percent": success_rate,
        "avg_duration_seconds": round(statistics.mean(durations), 4)
        if durations
        else None,
        "median_duration_seconds": round(statistics.median(durations), 4)
        if durations
        else None,
        "p95_duration_seconds": round(_quantile(durations, 0.95) or 0.0, 4)
        if durations
        else None,
        "p99_duration_seconds": round(_quantile(durations, 0.99) or 0.0, 4)
        if durations
        else None,
        "min_duration_seconds": round(min(durations), 4) if durations else None,
        "max_duration_seconds": round(max(durations), 4) if durations else None,
        "errors_sample": errors_sample[:10],
    }

    thresholds: dict[str, float] | None = None
    meets_targets: bool | None = None
    max_error_rate = args.max_error_rate
    p95_target = args.p95_target
    if p95_target is not None or max_error_rate is not None:
        thresholds = {}
        if p95_target is not None:
            thresholds["max_p95_duration_seconds"] = float(p95_target)
        if max_error_rate is not None:
            thresholds["max_error_rate_percent"] = float(max_error_rate)

        error_rate = 100.0 - success_rate if runs else 0.0
        meets = True
        if p95_target is not None and results["p95_duration_seconds"] is not None:
            meets = meets and float(results["p95_duration_seconds"]) <= float(
                p95_target
            )
        if max_error_rate is not None:
            meets = meets and float(error_rate) <= float(max_error_rate)
        meets_targets = bool(meets)

    evidence_payload: dict[str, object] = {
        "runner": "scripts/soak_ingestion_jobs.py",
        "jobs_enqueued": int(jobs),
        "workers": int(workers),
        "batch_limit": int(batch_limit),
        "window": {
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
        },
        "results": results,
        "runs": [asdict(item) for item in runs],
        "thresholds": thresholds,
        "meets_targets": meets_targets,
        "captured_at": soak_completed_at.isoformat(),
        "notes": {
            "tenant_id": str(tenant_id),
            "wall_duration_seconds": round(wall_seconds, 4),
            "started_at": soak_started_at.isoformat(),
            "completed_at": soak_completed_at.isoformat(),
        },
    }

    print(json.dumps(evidence_payload, indent=2, sort_keys=True))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fp:
            json.dump(evidence_payload, fp, indent=2, sort_keys=True)

    if args.publish:
        raw_token = os.getenv("VALDRIX_TOKEN", "").strip()
        try:
            token = sanitize_bearer_token(raw_token)
        except ValueError as exc:
            raise SystemExit(
                "Invalid VALDRIX_TOKEN. Ensure it's a single JWT string. "
                f"Details: {exc}"
            ) from None
        if not token:
            raise SystemExit("VALDRIX_TOKEN is required for --publish.")
        api_url = str(args.api_url or "").strip().rstrip("/")
        publish_url = f"{api_url}/api/v1/audit/performance/ingestion/soak/evidence"
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            resp = await client.post(publish_url, json=evidence_payload)
        if resp.status_code >= 400:
            raise SystemExit(f"Publish failed ({resp.status_code}): {resp.text}")


if __name__ == "__main__":
    asyncio.run(main())
