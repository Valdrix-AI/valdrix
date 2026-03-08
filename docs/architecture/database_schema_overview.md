# Database Schema Overview

## Scope

This document defines the operational database surface for Valdrics backend services and the migration safety contract enforced in CI.

## Engine and migration authority

- Primary runtime engine: PostgreSQL (`postgresql+asyncpg`).
- Migration authority: Alembic (`migrations/versions`).
- Single-head policy is enforced by `scripts/verify_alembic_head_integrity.py`.
- One-step forward/rollback smoke is enforced in CI by:
  1. `alembic upgrade head`
  2. `alembic downgrade -1`
  3. `alembic upgrade head`
- This smoke test does not imply arbitrary historical downgrades are safe.
- For irreversible or destructive migrations, backup/restore is the primary rollback path.

## Domain schema map

### Tenancy and identity

- `tenants`
- `users`
- `tenant_identity_settings`
- `sso_domain_mappings`
- `scim_groups`
- `scim_group_members`

### Billing and pricing

- `pricing_plans`
- `exchange_rates`
- `tenant_subscriptions`
- `provider_invoices`
- `realized_savings_events`
- `llm_provider_pricing`

### Cloud and optimization

- `aws_connections`
- `azure_connections`
- `gcp_connections`
- `saas_connections`
- `license_connections`
- `cost_records` (+ managed partition strategy)
- `attribution_rules`
- `cost_allocations`
- `optimization_strategies`
- `strategy_recommendations`

### Governance and security

- `audit_logs`
- `notification_settings`
- `tenant_teams_notification_settings`
- `remediation_settings`
- `remediation_requests`

### Enforcement control plane

- `enforcement_policies`
- `enforcement_decisions`
- `enforcement_credit_grants`
- `enforcement_budget_allocations`
- `enforcement_approval_requests`
- `enforcement_action_executions`

### LLM operations

- `llm_usage`
- `llm_budgets`

## Operational invariants

- Tenant isolation is mandatory on multi-tenant records (`tenant_id` boundaries).
- Schema changes must be migration-driven (no ad-hoc DDL in runtime code paths).
- Backward-incompatible schema transitions require staged migrations.
- Partition child tables and materialized views are excluded from Alembic autogenerate management in `migrations/env.py`.

## Local verification commands

```bash
uv run python scripts/verify_alembic_head_integrity.py
DB_SSL_MODE=disable DATABASE_URL='postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/valdrics_ci' uv run alembic upgrade head
DB_SSL_MODE=disable DATABASE_URL='postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/valdrics_ci' uv run alembic downgrade -1
DB_SSL_MODE=disable DATABASE_URL='postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/valdrics_ci' uv run alembic upgrade head
```

Treat the downgrade command above as a targeted reversibility smoke test for the
latest step only, not as a universal rollback promise for every migration in the
history.
