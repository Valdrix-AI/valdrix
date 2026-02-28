# Enforcement Stress Evidence Protocol (2026-02-25)

This document defines the mandatory stress evidence capture and validation protocol for enforcement release readiness.

Template seed (for schema orientation only): `docs/ops/evidence/enforcement_stress_artifact_TEMPLATE.json`

## Capture Command

Run staged stress with enforcement profile:

```bash
uv run python scripts/load_test_api.py \
  --profile enforcement \
  --rounds 3 \
  --enforce-thresholds \
  --out docs/ops/evidence/enforcement_stress_artifact_2026-02-25.json
```

## Validation Command

Validate captured evidence before promotion:

```bash
uv run python scripts/verify_enforcement_stress_evidence.py \
  --evidence-path docs/ops/evidence/enforcement_stress_artifact_2026-02-25.json \
  --min-duration-seconds 30 \
  --min-concurrent-users 10 \
  --required-database-engine postgresql \
  --max-p95-seconds 2.0 \
  --max-error-rate-percent 1.0 \
  --min-throughput-rps 0.5
```

## Evidence Contract

Release evidence must include:
1. `profile=enforcement`
2. preflight enabled/passed with no failures
3. `runner=scripts/load_test_api.py`
4. `captured_at` timezone-aware ISO-8601 timestamp
5. `evaluation.overall_meets_targets=true`
6. each `runs[*]` entry includes deterministic `run_index`, `captured_at`, and `results`
7. runtime backend provenance is explicit and release-verifiable:
   - `runtime.database_engine` present and non-empty
   - matches verifier `--required-database-engine` (default `postgresql`)
8. minimum workload floor for release evidence:
   - `duration_seconds >= 30`
   - `concurrent_users >= 10`
9. required enforcement endpoint set includes at least:
   - `/api/v1/enforcement/policies`
   - `/api/v1/enforcement/ledger?limit=50`
   - `/api/v1/enforcement/exports/parity?limit=50`
10. top-level aggregates match run-level aggregates:
   - `results.total_requests == sum(runs[*].results.total_requests)`
   - `results.successful_requests == sum(runs[*].results.successful_requests)`
   - `results.failed_requests == sum(runs[*].results.failed_requests)`
11. latency/throughput projections are tamper-resistant:
   - `results.p95_response_time == max(runs[*].results.p95_response_time)`
   - `results.p99_response_time == max(runs[*].results.p99_response_time)`
   - `min_throughput_rps == min(runs[*].results.throughput_rps)`
   - `results.throughput_rps == avg(runs[*].results.throughput_rps)`
12. thresholds/evaluation contract is explicit and verifier-bound:
   - `thresholds.max_p95_seconds == verifier --max-p95-seconds`
   - `thresholds.max_error_rate_percent == verifier --max-error-rate-percent`
   - `thresholds.min_throughput_rps == verifier --min-throughput-rps`
   - `evaluation.worst_p95_seconds == results.p95_response_time`
   - `evaluation.min_throughput_rps == min_throughput_rps`
   - `len(evaluation.rounds) == rounds`

## Release Rule

Failing stress evidence blocks release promotion.

Legacy note:
Artifacts captured before runtime-provenance enforcement (without `runtime.database_engine`) are no longer release-valid and must be re-captured.

## Enterprise Gate Integration

When promoting a real staged artifact in CI, set:
1. `ENFORCEMENT_STRESS_EVIDENCE_PATH=docs/ops/evidence/enforcement_stress_artifact_2026-02-25.json`
2. `ENFORCEMENT_STRESS_EVIDENCE_MAX_AGE_HOURS=24` (or stricter)
3. `ENFORCEMENT_STRESS_EVIDENCE_MIN_DURATION_SECONDS=30` (or stricter)
4. `ENFORCEMENT_STRESS_EVIDENCE_MIN_CONCURRENT_USERS=10` (or stricter)
5. `ENFORCEMENT_STRESS_EVIDENCE_REQUIRED=true` to force fail-fast when path is absent.
6. `ENFORCEMENT_STRESS_EVIDENCE_REQUIRED_DATABASE_ENGINE=postgresql` (or stricter override only for non-release dry-runs).

This appends artifact verification to `scripts/run_enterprise_tdd_gate.py` and makes stale/malformed artifacts release-blocking.

## Single-Sprint One-Pass Gate Command

When both staged artifacts are available, run one command to enforce stress + failure-injection evidence and execute the full enterprise gate:

```bash
uv run python3 scripts/run_enforcement_release_evidence_gate.py \
  --stress-evidence-path docs/ops/evidence/enforcement_stress_artifact_2026-02-25.json \
  --failure-evidence-path docs/ops/evidence/enforcement_failure_injection_2026-02-27.json \
  --stress-max-age-hours 24 \
  --failure-max-age-hours 48 \
  --stress-min-duration-seconds 30 \
  --stress-min-concurrent-users 10 \
  --stress-required-database-engine postgresql
```

## External Benchmark Alignment

1. Grafana k6 thresholds (pass/fail load-test automation and SLO codification):  
   https://grafana.com/docs/k6/latest/using-k6/thresholds/
2. Google SRE workbook burn-rate alerting patterns (error-budget-based escalation):  
   https://sre.google/workbook/alerting-on-slos/
