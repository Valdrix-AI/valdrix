# Month-End Close (Operator Runbook)

Valdrix “month-end close” is a deterministic reconciliation package meant for finance/procurement sign-off:

- Close status (ready / not-ready reasons)
- Lifecycle counts (preliminary vs final)
- Discrepancy detection summary
- Restatement history snapshot
- Integrity hash for tamper-evident evidence

## Prerequisites

- Tenant must be on a tier that includes `close_workflow` (typically Pro/Enterprise).
- Billing ledger ingestion should be running and finalization should have progressed (preliminary -> final).

## UI (Fastest)

1. Open `Ops Center` in the dashboard.
2. In **Reconciliation Close Workflow**:
   - Select the period (start/end).
   - Optionally filter by provider (AWS/Azure/GCP/SaaS/License).
3. Click:
   - `Preview Close Status`
   - `Download Close JSON`
   - `Download Close CSV`
   - `Download Restatements CSV`

## API (Automation-Friendly)

- Preview / export close package:
  - `GET /api/v1/costs/reconciliation/close-package?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&response_format=json|csv&enforce_finalized=false`
- Export restatement history:
  - `GET /api/v1/costs/reconciliation/restatements?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&response_format=csv`
- Export restatement run summaries (grouped by ingestion_batch_id):
  - `GET /api/v1/costs/reconciliation/restatement-runs?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&response_format=csv`

## Evidence Bundle (Recommended)

Capture an audit-safe bundle under `reports/acceptance/`:

```bash
export VALDRIX_API_URL="http://127.0.0.1:8000"
export VALDRIX_TOKEN="your-bearer-jwt"
uv run python scripts/capture_acceptance_evidence.py \
  --close-start-date 2026-01-01 \
  --close-end-date 2026-01-31 \
  --close-provider all
```

This produces (among other artifacts):

- `close_package.json`
- `close_package.csv`
- `restatements.csv`

## Notes

- `enforce_finalized=false` is useful for readiness previews; it reports that a close is not ready instead of hard-failing.
- Close package CSV is never stored inside audit logs (too large); it is captured as an operator artifact instead.
