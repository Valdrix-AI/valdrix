# Data Retention Policy

This policy describes retention controls that are currently evidenced by the
repository. Where retention is not automatically enforced by code, the policy
states that explicitly instead of implying automation.

## Repository-Backed Retention Controls

| Data Class | Retention Posture | Enforcement Source |
|---|---|---|
| Background job terminal-state records | Automated retention purge | Scheduler maintenance sweep and background-job retention settings |
| Tenant cost records | Automated plan-aware retention purge | Scheduler maintenance sweep and `CostPersistenceService.cleanup_expired_records_by_plan` |
| Tenant-scoped operational data | Removed on approved tenant erasure request | `DELETE /api/v1/audit/data-erasure-request` and `docs/runbooks/tenant_data_lifecycle.md` |
| AWS RDS backups (Terraform profile) | 30-day backup retention | `terraform/modules/db/main.tf` |
| Export/audit artifacts generated for operators | Retained according to artifact storage policy outside app runtime | Manual/operator managed |

## Automated Controls

The application currently enforces automated retention for:

- background-job terminal states through background job retention controls
- tenant cost records, using the tenant plan's configured `retention_days`

Cost-record purge evidence is written as structured `system.maintenance` audit
events with `resource_type=cost_records_retention`, so operators can export a
deterministic purge report through the audit log surface.

## Tenant Erasure Requests

Tenant-scoped deletion requests are handled through:

- `DELETE /api/v1/audit/data-erasure-request?confirmation=DELETE ALL MY DATA`
- `docs/runbooks/tenant_data_lifecycle.md`

This path is the supported customer-data deletion control documented in the
repository today.

## Policy Limits

- Data classes not covered by an automated purge job remain governed by tenant
  erasure workflows, infrastructure backup retention, or documented manual
  operator procedures.

## Review

Update this policy whenever a new retention job, export artifact lifecycle, or
backup policy is added to the codebase or infrastructure definitions.
