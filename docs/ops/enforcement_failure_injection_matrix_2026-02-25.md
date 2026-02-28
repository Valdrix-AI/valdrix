# Enforcement Failure Injection Matrix (2026-02-25)

This matrix defines required failure-injection scenarios that must be covered by automated tests and release evidence.

Template seed (for schema orientation only): `docs/ops/evidence/enforcement_failure_injection_TEMPLATE.json`

## Scenario Matrix

| ID | Failure class | Required evidence |
|---|---|---|
| `FI-001` | Gate timeout fallback semantics | `tests/unit/enforcement/test_enforcement_api.py::test_gate_failsafe_timeout_and_error_modes` and `tests/unit/enforcement/test_enforcement_service.py::test_resolve_fail_safe_gate_timeout_mode_behavior` |
| `FI-002` | Gate lock contention and lock-timeout routing | `tests/unit/enforcement/test_enforcement_api.py::test_gate_lock_failures_route_to_failsafe_with_lock_reason_codes` and `tests/unit/enforcement/test_enforcement_service_helpers.py::test_acquire_gate_evaluation_lock_rowcount_zero_raises_contended_reason` |
| `FI-003` | Approval token replay/tamper rejection under fault paths | `tests/unit/enforcement/test_enforcement_api.py::test_consume_approval_token_endpoint_rejects_replay_and_tamper` and `tests/unit/enforcement/test_enforcement_service.py::test_consume_approval_token_rejects_replay` |
| `FI-004` | Reservation reconciliation race behavior | `tests/unit/enforcement/test_enforcement_property_and_concurrency.py::test_concurrency_reconcile_same_idempotency_key_settles_credit_once` and `tests/unit/enforcement/test_enforcement_property_and_concurrency.py::test_concurrency_reconcile_overdue_claims_each_reservation_once` |
| `FI-005` | Cross-tenant limiter saturation and global gate throttle | `tests/unit/core/test_rate_limit.py::test_global_rate_limit_throttles_cross_tenant_requests` and `tests/unit/enforcement/test_enforcement_api.py::test_enforcement_global_gate_limit_uses_configured_cap` |

## Closure Rule

1. All `FI-001` through `FI-005` scenarios must remain present in this matrix.
2. Any scenario regression in referenced tests blocks release.

## Staged Evidence Contract

1. For release-grade staged operations proof, capture JSON artifact with:
   - `profile=enforcement_failure_injection`
   - `runner=staged_failure_injection`
   - `execution_class=staged`
   - timezone-aware `captured_at`
   - separation of duties (`executed_by != approved_by`)
   - `scenarios[]` entries covering exactly `FI-001..FI-005` with `status`, `duration_seconds`, `checks`, `evidence_refs`
   - `summary` integrity fields (`total_scenarios`, `passed_scenarios`, `failed_scenarios`, `overall_passed=true`)
2. Generate artifact from real FI scenario test execution:

```bash
DEBUG=false uv run python3 scripts/generate_enforcement_failure_injection_evidence.py \
  --output docs/ops/evidence/enforcement_failure_injection_2026-02-27.json \
  --executed-by sre.executor@valdrix.local \
  --approved-by release.approver@valdrix.local
```

3. Validate artifact with:

```bash
uv run python3 scripts/verify_enforcement_failure_injection_evidence.py \
  --evidence-path docs/ops/evidence/enforcement_failure_injection_2026-02-27.json \
  --max-artifact-age-hours 48
```

4. Release gate integration:
   - `ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_PATH` enables validation in enterprise gate.
   - `ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_MAX_AGE_HOURS` enforces freshness.
   - `ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_REQUIRED=true` fails fast when path is absent.

## Single-Sprint One-Pass Gate Command

When staged stress + failure-injection artifacts are ready, use:

```bash
uv run python3 scripts/run_enforcement_release_evidence_gate.py \
  --stress-evidence-path docs/ops/evidence/enforcement_stress_artifact_2026-02-25.json \
  --failure-evidence-path docs/ops/evidence/enforcement_failure_injection_2026-02-27.json \
  --stress-max-age-hours 24 \
  --failure-max-age-hours 48 \
  --stress-min-duration-seconds 30 \
  --stress-min-concurrent-users 10 \
  --stress-required-database-engine postgresql
```
