# Compliance Pack (Procurement / Audit Bundle)

Valdrics provides a tenant-scoped **compliance pack ZIP** that bundles:

- An audit log export
- Redacted tenant configuration snapshots (no secrets)
- Audit-grade evidence snapshots (performance, ingestion, identity, tenancy, carbon, integrations)
- Key runbooks and licensing documents for procurement review

This is designed to support enterprise review cycles without requiring internal access to your production systems.

## Endpoint

`GET /api/v1/audit/compliance-pack`

Auth / tier:
- Requires `compliance_exports` feature (Pro+)
- Requires role: `owner`

## What’s Included (Always)

Top-level files:
- `manifest.json` (counts, included files list, and optional export stats)
- `audit_logs.csv` (capped to 10,000 rows for performance)
- `notification_settings.json` (redacted: only `has_*` booleans for encrypted tokens)
- `remediation_settings.json`
- `identity_settings.json`

Evidence snapshots (from audit logs, bounded by `evidence_limit`):
- `integration_acceptance_evidence.json`
- `acceptance_kpis_evidence.json`
- `leadership_kpis_evidence.json`
- `quarterly_commercial_proof_evidence.json`
- `identity_smoke_evidence.json`
- `performance_load_test_evidence.json`
- `ingestion_persistence_benchmark_evidence.json`
- `ingestion_soak_evidence.json`
- `partitioning_evidence.json`
- `job_slo_evidence.json`
- `tenant_isolation_evidence.json`
- `carbon_assurance_evidence.json`
- `carbon_factor_sets.json`
- `carbon_factor_update_logs.json`

Bundled docs (for procurement review):
- `docs/integrations/scim.md`
- `docs/integrations/idp_reference_configs.md`
- `docs/integrations/sso.md`
- `docs/compliance/compliance_pack.md`
- `docs/compliance/focus_export.md`
- `docs/ops/acceptance_evidence_capture.md`
- `docs/runbooks/month_end_close.md`
- `docs/runbooks/tenant_data_lifecycle.md`
- `docs/runbooks/partition_maintenance.md`
- `docs/licensing.md`
- `LICENSE`
- `TRADEMARK_POLICY.md`
- `COMMERCIAL_LICENSE.md`

## Optional Exports (Additive)

Use query params to include additional exports under `exports/`:

FOCUS v1.3 core CSV (bounded):
- `include_focus_export=true`
- Output: `exports/focus-v1.3-core.csv`
- If export fails: `exports/focus-v1.3-core.error.json`

Savings Proof (JSON + CSV) and drilldowns:
- `include_savings_proof=true`
- Output:
  - `exports/savings-proof.json`
  - `exports/savings-proof.csv`
  - `exports/savings-proof-drilldown-strategy-type.json`
  - `exports/savings-proof-drilldown-strategy-type.csv`
  - `exports/savings-proof-drilldown-remediation-action.json`
  - `exports/savings-proof-drilldown-remediation-action.csv`
- If export fails: `exports/savings-proof.error.json`

Realized savings exports (bounded):
- `include_realized_savings=true`
- Output:
  - `exports/realized-savings.json`
  - `exports/realized-savings.csv`
- If export fails: `exports/realized-savings.error.json`

Close package exports (JSON + CSV) (bounded):
- `include_close_package=true`
- Output:
  - `exports/close-package.json`
  - `exports/close-package.csv`
- If export fails: `exports/close-package.error.json`

## Key Query Parameters

General:
- `start_date`, `end_date` (UTC datetimes): filter the exported `audit_logs.csv`
- `evidence_limit` (default `200`, max `2000`): bounds evidence snapshots in the ZIP

FOCUS export (when `include_focus_export=true`):
- `focus_provider` (optional): `aws|azure|gcp|saas|license|platform|hybrid`
- `focus_include_preliminary` (default `false`)
- `focus_start_date`, `focus_end_date` (dates): default last 30 days
- `focus_max_rows` (default `50000`, max `200000`)

Savings proof (when `include_savings_proof=true`):
- `savings_provider` (optional)
- `savings_start_date`, `savings_end_date` (dates): default last 30 days

Realized savings (when `include_realized_savings=true`):
- `realized_provider` (optional)
- `realized_start_date`, `realized_end_date` (dates): defaults to the savings window when provided
- `realized_limit` (default `5000`, max `200000`)

Close package (when `include_close_package=true`):
- `close_provider` (optional)
- `close_start_date`, `close_end_date` (dates): default last 30 days
- `close_enforce_finalized` (default `true`)
- `close_max_restatements` (default `5000`, set `0` to omit details)

## Recommended Procurement Flow (Practical)

1. Capture operational evidence:
   - `uv run python scripts/capture_acceptance_evidence.py`
2. Publish audit-grade evidence (performance, ingestion soak, identity smoke) where applicable:
   - See `docs/ops/acceptance_evidence_capture.md`
3. Export a compliance pack:
   - `GET /api/v1/audit/compliance-pack?include_focus_export=true&include_savings_proof=true&include_realized_savings=true&include_close_package=true`
4. Attach the ZIP and the acceptance evidence folder to your rollout/procurement ticket.

## Security Notes

- The export request itself is audit-logged.
- Secrets/tokens are **not** included in the ZIP. The pack exposes only `has_*` booleans for encrypted credentials.
- Evidence snapshots are bounded and intentionally omit large artifacts (for example “close CSV”) to keep ZIP sizes reasonable.
