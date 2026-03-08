# Rollback Plan

This plan covers the deployment surfaces that are currently checked into the
repository.

## Rollback Principles

- Application rollback should use immutable release artifacts or prior known-good deployments.
- Database rollback is not assumed to be universally reversible.
- For destructive or forward-only schema changes, backup/restore is the primary recovery path.

## 1. Database Schema Recovery

Use `alembic downgrade -1` only after confirming the specific migration is
reversible and the change has been covered by the one-step downgrade smoke test
in CI.

For destructive or uncertain migrations:

1. Restore from the most recent compatible backup/restore point.
2. Redeploy an application version that matches that schema state.
3. Re-run validation on `/health/live` and `/health`.

## 2. Kubernetes / Helm Rollback

For the Helm deployment profile:

1. Roll back to the prior Helm revision.
2. Confirm API and worker pods become ready.
3. Re-check internal metrics scraping via `/_internal/metrics`.

## 3. PaaS Rollback

For the Cloudflare Pages + Koyeb profile:

1. Restore the prior Cloudflare Pages deployment for the dashboard if the frontend regressed.
2. Redeploy the previous immutable backend release or prior successful commit on Koyeb.
3. Verify `/health/live` and key dashboard/API flows after rollback.

## 4. Infrastructure Rollback

For Terraform-managed infrastructure:

1. Review the last known-good revision in Git.
2. Apply that reviewed Terraform state intentionally; do not assume blind reversibility.
3. Validate RDS, Redis, and ingress health before reopening traffic.

## 5. Emergency Soft Kill

To stop scheduler-driven background processing without tearing down the whole API:

1. Set `ENABLE_SCHEDULER=false`.
2. Restart API instances.
3. Verify logs show the scheduler was disabled by configuration.
