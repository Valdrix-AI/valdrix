# Disaster Recovery Runbook

This runbook reflects the deployment and infrastructure definitions currently
present in the repository.

## Supported Profiles

- Helm + Terraform on AWS/EKS with AWS RDS and ElastiCache
- Cloudflare Pages + Koyeb for the dashboard/API/worker PaaS profile

## Recovery Posture

- Current checked-in IaC supports in-region high availability for AWS RDS and ElastiCache.
- Cross-region recovery is a manual restore and redeploy exercise unless additional regional infrastructure is provisioned outside this repository.
- `.github/workflows/disaster-recovery-drill.yml` runs a repository-managed rebuild-and-verify exercise so the documented recovery path is rehearsed on versioned artifacts.

## 1. AWS RDS Database Failure

### Detection

- `/health` returns `503`
- application logs show database connectivity failures
- worker or scheduler throughput drops unexpectedly

### Recovery Steps

1. Confirm the failing profile is using AWS RDS.
2. Check RDS instance status and Multi-AZ failover state.
3. If failover is in progress, wait for promotion to complete and re-run health checks.
4. If corruption or unrecoverable failure is suspected, restore from the latest AWS RDS backup/restore point.
5. Validate application startup, migrations state, and tenant-isolated query paths after recovery.

Repository evidence:

- `terraform/modules/db/main.tf` configures AWS RDS with `multi_az = true`
- `terraform/modules/db/main.tf` configures `backup_retention_period = 30`

## 2. Kubernetes / Helm Service Failure

### Detection

- API pods fail readiness or liveness
- worker pods stop consuming tasks
- internal metrics disappear from cluster scraping

### Recovery Steps

1. Check pod status, events, and rollout health.
2. Roll back the Helm release if the failure correlates with a recent deployment.
3. Validate `/health/live`, `/health`, and `/_internal/metrics` from inside the cluster.
4. Confirm Redis and database connectivity before reopening traffic.

## 3. Cloudflare Pages or Koyeb Failure

### Detection

- dashboard pages fail to render
- backend health checks fail on the PaaS profile
- edge proxy requests stop reaching the API

### Recovery Steps

1. Identify whether the issue is isolated to Cloudflare Pages, Koyeb, or both.
2. Roll back the affected Cloudflare deployment if the dashboard release regressed.
3. Redeploy the previous immutable backend release or prior successful Koyeb deployment for both `koyeb.yaml` and `koyeb-worker.yaml` if the API or worker regressed.
4. Confirm the Koyeb runtime secrets include `SENTRY_DSN`, `OTEL_EXPORTER_OTLP_ENDPOINT`, and the audited `TRUSTED_PROXY_CIDRS` allowlist before reopening traffic.
5. Re-validate health checks, authentication flows, queue consumption, and dashboard-to-API connectivity.

## 4. Secret Exposure or Rotation Event

If recovery is triggered by secret compromise rather than infrastructure loss:

1. Follow `docs/runbooks/secret_rotation_emergency.md`.
2. Recycle affected runtime instances after rotation.
3. Validate that old credentials are rejected and new ones are in effect.

## Post-Recovery Validation

1. `/health/live` returns `200`.
2. `/health` returns dependency details without new critical failures.
3. Background processing resumes only when intended.
4. Internal metrics are available to cluster scrapers and remain blocked from public ingress.
5. Tenant-scoped export and erasure controls still behave correctly.
