# Partition Maintenance (Postgres)

Valdrix uses monthly range partitioning for high-volume tables to keep query latency stable as data grows.

Tables:
- `cost_records` (partitioned by `recorded_at` DATE)
- `audit_logs` (partitioned by `event_timestamp` TIMESTAMPTZ)

## Why This Matters

- The default partition is a safety net, not a scaling plan.
- If future partitions are not created, new data can accumulate in the default partition, causing:
  - larger indexes
  - slower p95 queries
  - harder retention/archival operations

## Operator Commands

Create partitions for the next N months:

```bash
uv run python scripts/manage_partitions.py create --table all --months-ahead 6
```

Validate partitions exist:

```bash
uv run python scripts/manage_partitions.py validate --table all --months-ahead 6
```

Create only one table:

```bash
uv run python scripts/manage_partitions.py create --table audit_logs --months-ahead 6
uv run python scripts/manage_partitions.py create --table cost_records --months-ahead 6
```

## Scheduling

Recommended cadence:
- `create`: daily (or at least weekly)
- `validate`: daily (or at least weekly) and alert if missing partitions are detected

If you run this via `pg_cron`, ensure only one instance runs at a time.
The script uses a Postgres advisory lock to prevent concurrent runs.

## Evidence Capture (Procurement / Scale Sign-off)

To capture audit-grade evidence of partition readiness:

- `POST /api/v1/audit/performance/partitioning/evidence`
- `GET /api/v1/audit/performance/partitioning/evidence`

The evidence payload includes:
- which tables are partitioned
- the child partitions detected
- which next-month partitions are missing (if any)

## Notes

- This runbook assumes Postgres. SQLite/testing does not support range partitioning.
- Retention (archive/drop) is currently only implemented for `cost_records` partitions.

