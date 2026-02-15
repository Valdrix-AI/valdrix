# Acceptance Evidence Capture (Operator)

This runbook captures repeatable evidence artifacts for rollout/procurement sign-off:

- Acceptance KPI Evidence (JSON + CSV)
- Leadership KPI export (JSON + CSV)
- Savings proof export (JSON + CSV)
- Quarterly commercial proof report template (JSON + CSV)
- Integration Acceptance Runs (Slack/Jira/Teams/Workflow)
- Job SLO snapshot (best-effort; admin-only)
- Profile snapshot (persona + tier)
- Month-end close evidence (Close Package JSON/CSV + Restatements CSV)
- Realized savings evidence (JSON + CSV)
- Performance load-test evidence (JSON, audit-log snapshots)
- Ingestion persistence benchmark evidence (JSON, audit-log snapshots)
- End-to-end ingestion soak evidence (JSON, audit-log snapshots)
- DB partitioning validation evidence (JSON, audit-log snapshots)
- Identity IdP smoke-test evidence (JSON, audit-log snapshots)
- Tenant isolation verification evidence (JSON, audit-log snapshots)
- Carbon assurance evidence (JSON, audit-log snapshots)

Artifacts are written under `reports/acceptance/` (gitignored by default).

## Prerequisites

1. You need a valid bearer token:
- `VALDRIX_TOKEN` (required)

2. API base URL:
- `VALDRIX_API_URL` (optional, default `http://127.0.0.1:8000`)

## Run

```bash
export VALDRIX_API_URL="http://127.0.0.1:8000"
export VALDRIX_TOKEN="your-bearer-jwt"
uv run python scripts/capture_acceptance_evidence.py
```

Optional window override:

```bash
uv run python scripts/capture_acceptance_evidence.py \
  --start-date 2026-02-01 \
  --end-date 2026-02-13
```

## Output

The script writes a timestamped folder like:

- `reports/acceptance/20260213T235959Z/manifest.json`
- `reports/acceptance/20260213T235959Z/acceptance_kpis.json`
- `reports/acceptance/20260213T235959Z/acceptance_kpis.csv`
- `reports/acceptance/20260213T235959Z/leadership_kpis.json` (may fail if feature not enabled)
- `reports/acceptance/20260213T235959Z/leadership_kpis.csv` (may fail if feature not enabled)
- `reports/acceptance/20260213T235959Z/savings_proof.json` (may fail if feature not enabled)
- `reports/acceptance/20260213T235959Z/savings_proof.csv` (may fail if feature not enabled)
- `reports/acceptance/20260213T235959Z/commercial_quarterly_report.json` (may fail if feature not enabled)
- `reports/acceptance/20260213T235959Z/commercial_quarterly_report.csv` (may fail if feature not enabled)
- `reports/acceptance/20260213T235959Z/integration_acceptance_evidence.json`
- `reports/acceptance/20260213T235959Z/jobs_slo.json` (may fail if not admin)
- `reports/acceptance/20260213T235959Z/job_slo_evidence_capture.json` (may fail if not admin)
- `reports/acceptance/20260213T235959Z/job_slo_evidence.json` (may fail if not admin)
- `reports/acceptance/20260213T235959Z/profile.json`
- `reports/acceptance/20260213T235959Z/close_package.json` (may fail if feature not enabled)
- `reports/acceptance/20260213T235959Z/close_package.csv` (may fail if feature not enabled)
- `reports/acceptance/20260213T235959Z/restatements.csv` (may fail if feature not enabled)
- `reports/acceptance/20260213T235959Z/realized_savings.json` (may fail if feature not enabled)
- `reports/acceptance/20260213T235959Z/realized_savings.csv` (may fail if feature not enabled)
- `reports/acceptance/20260213T235959Z/performance_load_test_evidence.json` (may be empty until a load test is published)
- `reports/acceptance/20260213T235959Z/ingestion_persistence_benchmark_evidence.json` (may be empty until published)
- `reports/acceptance/20260213T235959Z/ingestion_soak_evidence.json` (may be empty until published)
- `reports/acceptance/20260213T235959Z/partitioning_evidence.json` (may be empty until captured)
- `reports/acceptance/20260213T235959Z/identity_smoke_evidence.json` (may be empty until published)
- `reports/acceptance/20260213T235959Z/sso_federation_validation_evidence.json` (may be empty until published)
- `reports/acceptance/20260213T235959Z/tenant_isolation_evidence.json` (may be empty until verification is published)
- `reports/acceptance/20260213T235959Z/carbon_assurance_evidence.json` (may be empty until evidence is captured)

## Audit-Grade KPI Snapshots (Optional)

If you want the KPI evidence persisted server-side (tenant-scoped, immutable), capture it into audit logs:

- `POST /api/v1/costs/acceptance/kpis/capture`
- `GET /api/v1/costs/acceptance/kpis/evidence`

These captured KPI snapshots are included in the compliance evidence bundle:

- `GET /api/v1/audit/compliance-pack` (contains `acceptance_kpis_evidence.json`)
- `GET /api/v1/audit/compliance-pack?include_realized_savings=true` (adds `exports/realized-savings.json` + `exports/realized-savings.csv`)

Job reliability evidence can also be captured and persisted into audit logs:

- `POST /api/v1/audit/jobs/slo/evidence`
- `GET /api/v1/audit/jobs/slo/evidence`

This evidence is bundled in the compliance pack as `job_slo_evidence.json`.

## Automated Daily Acceptance Suite Capture (Recommended)

Valdrix also runs a daily, tenant-scoped acceptance capture sweep via the scheduler:

- Enqueues background jobs: `acceptance_suite_capture`
- Schedule: **daily 05:00 UTC** (see `SchedulerOrchestrator.start()`).
- Evidence stored in immutable audit logs:
  - `acceptance.kpis_captured`
  - `integration_test.*` in **passive** mode (connectivity checks only; no Slack messages / Jira issues created).

This gives you continuous “production sign-off” evidence without manual operator steps.

## Performance Evidence (Optional)

Run a small load test and publish the evidence into audit logs:

```bash
export VALDRIX_TOKEN="your-bearer-jwt"
uv run python scripts/load_test_api.py --profile ops --duration 30 --users 10 \
  --p95-target 2.0 --max-error-rate 1.0 --publish
```

Soak variant (multiple rounds, captures per-round results in evidence):

```bash
export VALDRIX_TOKEN="your-bearer-jwt"
uv run python scripts/load_test_api.py --profile soak --rounds 5 --pause 2 --duration 30 --users 10 \
  --p95-target 2.0 --max-error-rate 1.0 --publish
```

### GitHub Actions Performance Gate (Manual) (Recommended)

If you want a repeatable, reviewable performance check for staging/prod sign-off, use the manual workflow:

- Workflow: `Performance Gate (Manual)`
- File: `.github/workflows/performance-gate.yml`

It runs `scripts/load_test_api.py` with enforced thresholds and uploads the JSON as a GitHub Actions artifact (`perf-gate-evidence`).

Published performance evidence is included in the compliance pack:

- `GET /api/v1/audit/compliance-pack` (contains `performance_load_test_evidence.json`)

DB partitioning validation evidence can also be captured (useful for “10x readiness” sign-off on Postgres):

- `POST /api/v1/audit/performance/partitioning/evidence`
- `GET /api/v1/audit/performance/partitioning/evidence`

End-to-end ingestion soak evidence can be published after running a soak run:

```bash
export VALDRIX_TOKEN="your-bearer-jwt"
export VALDRIX_TENANT_ID="your-tenant-uuid"
uv run python scripts/soak_ingestion_jobs.py --jobs 5 --workers 2 --batch-limit 10 \
  --p95-target 60 --max-error-rate 5 --publish
```

Evidence endpoints:

- `POST /api/v1/audit/performance/ingestion/soak/evidence`
- `GET /api/v1/audit/performance/ingestion/soak/evidence`

## Identity Interop Evidence (Optional)

Run an IdP interoperability smoke test (SCIM) and publish evidence into audit logs:

```bash
export VALDRIX_SCIM_BASE_URL="https://<your-valdrix-host>/scim/v2"
export VALDRIX_SCIM_TOKEN="tenant-scim-token"
export VALDRIX_TOKEN="your-bearer-jwt"  # admin; required for --publish
uv run python scripts/smoke_test_scim_idp.py --write --publish --idp okta
```

Evidence endpoints:

- `POST /api/v1/audit/identity/idp-smoke/evidence`
- `GET /api/v1/audit/identity/idp-smoke/evidence`

## Tenancy Isolation Evidence (Optional)

Run the focused tenant isolation regression suite and publish evidence into audit logs:

```bash
export VALDRIX_TOKEN="your-bearer-jwt"
uv run python scripts/verify_tenant_isolation.py --publish
```

Published tenancy evidence is included in the compliance pack:

- `GET /api/v1/audit/compliance-pack` (contains `tenant_isolation_evidence.json`)

## Carbon Assurance Evidence (Optional)

Capture a carbon methodology + factor snapshot into audit logs:

```bash
export VALDRIX_TOKEN="your-bearer-jwt"
uv run python scripts/capture_carbon_assurance_evidence.py --notes "pre-prod signoff"
```

Published carbon assurance evidence is included in the compliance pack:

- `GET /api/v1/audit/compliance-pack` (contains `carbon_assurance_evidence.json`)

## Month-End Close Window Defaults

Close package evidence defaults to the **previous full calendar month**.

Override the close window/provider:

```bash
uv run python scripts/capture_acceptance_evidence.py \
  --close-start-date 2026-01-01 \
  --close-end-date 2026-01-31 \
  --close-provider aws
```

## Security Notes

- Tokens are not written to disk.
- JSON payloads are redacted for common secret keys (token/secret/password/api_key patterns).
- Treat `reports/acceptance/` as operational evidence (safe to share with auditors), but review before distribution.
