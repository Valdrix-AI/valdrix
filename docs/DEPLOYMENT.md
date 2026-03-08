# Valdrics Deployment Guide

Last verified: **2026-03-07**

## Supported Deployment Profiles

Supported deployment profiles are documented below.

This repository currently contains two supported deployment profiles:

1. `Helm + Terraform (AWS/EKS)`
2. `Cloudflare Pages + Koyeb`

Choose one profile and operate it consistently. Do not mix assumptions from one
profile into the other during incident response or compliance review.

## Shared Runtime Contract

All production profiles should satisfy these checks:

- `ENVIRONMENT=production`
- `ENABLE_SCHEDULER=true` unless intentionally disabled for incident control
- liveness probe: `/health/live`
- dependency health/readiness: `/health`
- internal-only metrics: `/_internal/metrics`
- immutable image or deployment versioning
- any forecasting break-glass expiry must remain within the configured max break-glass window

## Profile A: Helm + Terraform (AWS/EKS)

Repository evidence:

- Helm chart: `helm/valdrics/`
- Infrastructure modules: `terraform/`

Expected posture:

- API replicas >= 2
- ExternalSecrets enabled for production values
- AWS RDS Multi-AZ and automated backups
- ElastiCache Multi-AZ replication group

Core operator steps:

1. Provision infrastructure with Terraform.
2. Publish an immutable application image.
3. Deploy with Helm values that preserve the production defaults.
4. Validate `/health/live`, `/health`, and cluster-internal `/_internal/metrics`.

## Profile B: Cloudflare Pages + Koyeb

Repository evidence:

- Dashboard adapter/config: `dashboard/svelte.config.js`
- Backend API manifest: `koyeb.yaml`
- Backend worker manifest: `koyeb-worker.yaml`

Core operator steps:

1. Deploy the dashboard to Cloudflare Pages.
2. Deploy the API to Koyeb using the checked-in `Dockerfile`.
3. Deploy the Celery worker to Koyeb using `koyeb-worker.yaml`.
4. Configure runtime secrets through the platform secret store, including `SENTRY_DSN`, `OTEL_EXPORTER_OTLP_ENDPOINT`, and `TRUSTED_PROXY_CIDRS`.
5. Validate dashboard-to-API connectivity, worker connectivity to Redis, and API health endpoints.

## Verification Checklist

- `/health/live` returns `200`
- `/health` reflects dependency state accurately
- `/_internal/metrics` is reachable only by internal scrapers
- workers and scheduler start only when expected
- rollback path is documented for the chosen profile

## Related Runbooks

- `docs/ROLLBACK_PLAN.md`
- `docs/runbooks/disaster_recovery.md`
- `docs/runbooks/tenant_data_lifecycle.md`
