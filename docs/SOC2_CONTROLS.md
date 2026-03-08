# SOC 2 Control Evidence Map

This document maps repository-backed controls to SOC 2 preparation evidence.
It is intentionally evidence-first: only controls with checked-in code,
configuration, or runbooks are marked as implemented here.

## Scope

- Application: FastAPI API, SvelteKit dashboard, background workers
- Infrastructure: Helm chart, Terraform modules, GitHub Actions workflows
- Operations evidence: runbooks, audit/export paths, observability config

## Control Map

| Control ID | Control | Repository Evidence | Status |
|---|---|---|---|
| CC1.3 | Ownership and change accountability | `CODEOWNERS`, `.github/workflows/ci.yml` | Implemented |
| CC2.1 | Internal communication and logging | `app/shared/core/logging.py`, `prometheus/alerts.yml`, `grafana/dashboards/` | Implemented |
| CC2.3 | Security and recovery policies | `docs/runbooks/disaster_recovery.md`, `docs/runbooks/tenant_data_lifecycle.md`, `docs/runbooks/secret_rotation_emergency.md` | Implemented |
| CC3.1 | Risk identification and technical review | `docs/FULL_CODEBASE_AUDIT.md`, `docs/ops/`, `scripts/verify_exception_governance.py` | Implemented |
| CC4.1 | Monitoring activities | `/_internal/metrics`, `prometheus/prometheus.yml`, `prometheus/alerts.yml` | Implemented |
| CC5.1 | Preventive/detective controls | `app/shared/core/rate_limit.py`, `app/shared/core/circuit_breaker.py`, `app/shared/core/timeout.py` | Implemented |
| CC5.2 | Technology access controls | `app/shared/core/auth.py`, `app/shared/db/session.py`, migrations with tenant/RLS controls | Implemented |
| CC6.1 | Access architecture | `app/shared/core/auth.py`, `app/shared/db/session.py`, `docs/runbooks/tenant_data_lifecycle.md` | Implemented |
| CC6.4 | Access removal and tenant data removal | `docs/runbooks/tenant_data_lifecycle.md`, `app/modules/governance/api/v1/audit_access.py`, `app/modules/governance/api/v1/settings/account.py` | Implemented |
| CC7.1 | Vulnerability management | `.github/workflows/ci.yml`, `.github/workflows/sbom.yml`, `.github/workflows/security-scan.yml` | Implemented |
| CC7.2 | Security monitoring and traceability | `app/shared/core/tracing.py`, `app/shared/core/security_metrics.py`, `app/shared/core/ops_metrics.py` | Implemented |
| CC7.4 | Incident response and recovery | `docs/runbooks/disaster_recovery.md`, `docs/ROLLBACK_PLAN.md` | Implemented |
| CC8.1 | Change management | Git history, `CODEOWNERS`, GitHub Actions checks, `scripts/run_enterprise_tdd_gate.py` | Implemented |
| CC9.2 | Business continuity and backups | `terraform/modules/db/main.tf`, `docs/runbooks/disaster_recovery.md` | Implemented |

## Implemented Control Evidence

### Identity, Authorization, and Tenant Isolation

- Authentication and token validation: `app/shared/core/auth.py`
- Tenant-aware DB session and RLS enforcement hooks: `app/shared/db/session.py`
- Tenant-scoped data erasure/export path: `app/modules/governance/api/v1/audit_access.py`
- Owner-only tenant closure and access revocation path: `app/modules/governance/api/v1/settings/account.py`

### Observability and Monitoring

- Structured logging: `app/shared/core/logging.py`
- Metrics contract and internal-only metrics path: `app/shared/core/ops_metrics.py`, `app/main.py`
- Alerting rules and dashboards: `prometheus/alerts.yml`, `grafana/dashboards/finops-overview.json`

### Deployment and Supply Chain

- CI, lint, tests, and coverage: `.github/workflows/ci.yml`
- SBOM and provenance controls: `.github/workflows/sbom.yml`
- Runtime lockfile discipline: `Dockerfile`, `scripts/verify_dependency_locking.py`

### Recovery and Data Handling

- Rollback guidance: `docs/ROLLBACK_PLAN.md`
- Disaster recovery runbook: `docs/runbooks/disaster_recovery.md`
- Tenant data lifecycle and erasure operations: `docs/runbooks/tenant_data_lifecycle.md`
- AWS RDS backup retention and HA posture: `terraform/modules/db/main.tf`

## Known Gaps

- Evidence collection for human processes (security training, vendor review sign-off, access review cadence) is outside this repository and must be maintained separately for audit readiness.

## Usage Notes

- Treat this file as an evidence index, not a policy substitute.
- Update links and status any time code paths, workflows, or runbooks change.
