# ADR-0003: Core Circuit Breaker State Scope

- Date: 2026-02-20
- Status: Accepted

## Context

`app/shared/core/circuit_breaker.py` maintains breaker state in-process.  
In multi-worker deployments, this can create divergent state per worker.

## Decision

For now, the core breaker remains process-local, and deployment safety is
enforced through configuration validation:

- `WEB_CONCURRENCY` must be `1` in `staging`/`production`.
- Multi-worker deployment is blocked until distributed breaker state is implemented.

This fail-closed guard is implemented in `app/shared/core/config.py`.

## Consequences

- Prevents silent multi-worker divergence in production.
- Makes deployment intent explicit.
- Future distributed breaker implementation can remove the single-worker
  production constraint.
