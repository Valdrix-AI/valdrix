# Tenant Data Lifecycle Runbook

Last updated: February 12, 2026

## Purpose

Operational steps for tenant data export and data erasure workflows.

## Roles

- Owner: can initiate tenant-level data erasure request.
- Admin: can access audit export endpoints where policy allows.

## Data Export

### Audit Export

Endpoint:

- `GET /api/v1/audit/export`

Operational checks:

1. Confirm caller role authorization.
2. Validate tenant context.
3. Verify export file generation completed.
4. Record export request in audit trail.

## Data Erasure (GDPR-style Request)

Endpoint:

- `DELETE /api/v1/audit/data-erasure-request?confirmation=DELETE ALL MY DATA`

Operational checks:

1. Verify owner role.
2. Verify exact confirmation phrase.
3. Ensure tenant exists and row lock acquired.
4. Execute dependency-safe deletion sequence.
5. Confirm transaction commit.
6. Validate summary counts in response and logs.

## Post-Execution Validation

1. Tenant-scoped cost and connection records are no longer queryable.
2. No cross-tenant records were affected.
3. Audit evidence for the action exists.
4. Incident channel notified if deletion fails.

## Failure Handling

1. Roll back transaction on any exception.
2. Capture structured error log with tenant context.
3. Escalate to operations/security on repeated failures.
