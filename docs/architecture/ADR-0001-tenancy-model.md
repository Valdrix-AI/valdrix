# ADR-0001: Tenancy Model

- Status: Accepted
- Date: February 12, 2026
- Owners: Platform, Security, Billing

## Context

Valdrics is SaaS-first and must support enterprise tenant isolation, predictable cost scaling, and compliance evidence. A tenancy decision made late is expensive to reverse.

## Decision

Adopt a hybrid tenancy model:

- Shared control plane:
  - API layer
  - auth integration
  - billing/orchestration
  - governance policy orchestration
- Tenant-isolated data plane:
  - strict tenant scoping in queries
  - database row-level boundaries
  - connection and credential boundaries per tenant
  - migration safety checks for cross-tenant leakage

## Rationale

- Better economics than full single-tenant from day one.
- Better isolation and compliance posture than naive shared-schema only.
- Allows selective premium isolation later without redesigning the entire control plane.

## Enforcement Controls

1. Every tenant-owned table includes `tenant_id`.
2. Service-layer queries enforce tenant filters.
3. DB-level protections (RLS/policies where configured) backstop service checks.
4. Background jobs execute with tenant context and never global unscoped operations.
5. Audit events always include tenant identifier and actor metadata.

## Testable Assertions

1. Unauthorized cross-tenant reads return no data.
2. Unauthorized cross-tenant writes/deletes are denied.
3. Job processor executes scoped by tenant and cohort without cross-tenant mutation.
4. Data export and erasure endpoints only operate on caller tenant.

## Consequences

- Slightly higher implementation complexity than full shared tenancy.
- Lower long-term migration risk for enterprise isolation requirements.
- Enables tier-based isolation upgrades for high-compliance customers.
