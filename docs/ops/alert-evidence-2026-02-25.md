# Enforcement Ops Evidence Pack (2026-02-25)

## Scope

This artifact pack captures the minimum viable operational evidence for enforcement control-plane monitoring:

1. Alert rules are versioned and reference production metrics.
2. Dashboard panels cover gate reliability, abuse, approvals, and export integrity.
3. Trigger methods for each alert are documented.

## Versioned Artifacts

1. Alert rules: `ops/alerts/enforcement_control_plane_rules.yml`
2. Dashboard: `ops/dashboards/enforcement_control_plane_overview.json`

## Alert IDs and Trigger Methods

1. `ValdrixEnforcementErrorBudgetBurnFast`
   - Trigger method: force fail-safe gate path (`timeout` or `lock_contended`) under sustained load for at least 1 hour so both 1h and 5m burn windows cross 14.4x on the 99.9% error-budget baseline.
2. `ValdrixEnforcementErrorBudgetBurnSlow`
   - Trigger method: keep elevated fail-safe rate over a 6-hour period so both 6h and 30m windows cross 6x on the 99.9% error-budget baseline.
3. `ValdrixEnforcementGateTimeoutSpike`
   - Trigger method: induce repeated gate timeouts by temporarily lowering `ENFORCEMENT_GATE_TIMEOUT_SECONDS` and running slow gate requests.
4. `ValdrixEnforcementGateLockContentionSpike`
   - Trigger method: run concurrent gate requests for same tenant with reduced lock timeout to generate `contended`/`timeout` events.
5. `ValdrixEnforcementGateLatencyP95High`
   - Trigger method: execute sustained gate load and inject DB latency.
6. `ValdrixEnforcementGlobalThrottleHits`
   - Trigger method: burst gate traffic across multiple tenants above global cap.
7. `ValdrixEnforcementApprovalQueueBacklogHigh`
   - Trigger method: seed pending approvals without processing approvals queue.
8. `ValdrixEnforcementExportParityMismatch`
   - Trigger method: force mismatch path in export parity test harness.
9. `ValdrixLLMFairUseDenialsSpike`
   - Trigger method: exceed fair-use guardrails in controlled staging workload.

## Evidence Validation

Unit validation verifies:

1. Required alert rules exist and reference expected metrics.
2. Dashboard JSON is valid and references required metric families.
3. Burn-rate recording rules and burn-rate alert IDs are present in the packed artifacts.

## Release Hold Criteria (BSAFE-016)

Hold release promotion when either burn-rate alert is firing:

1. `ValdrixEnforcementErrorBudgetBurnFast` (critical)
2. `ValdrixEnforcementErrorBudgetBurnSlow` (warning)

Clear hold only after:

1. alert state returns to inactive for two consecutive evaluation windows,
2. root cause and mitigation are recorded in `docs/runbooks/enforcement_incident_response.md`,
3. rollback/forward plan is approved by on-call owner.

Validation tests:

1. `tests/unit/ops/test_enforcement_observability_pack.py`
