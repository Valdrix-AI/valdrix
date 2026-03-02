# Enforcement Incident Response Runbook

## Purpose

Operational response guide for enforcement control-plane incidents affecting gate decisions, approvals, reservation integrity, and LLM abuse protections.

This runbook covers the required critical scenarios:

- abuse spike
- false-positive enforcement block
- signing key compromise
- reconciliation drift anomaly

## Scope

Applies to:

- `POST /api/v1/enforcement/gate/*`
- `POST /api/v1/enforcement/approvals/*`
- `GET /api/v1/enforcement/ledger`
- reservation reconciliation endpoints and worker sweep
- LLM pre-authorization abuse protections

## Severity Model

- `SEV-1`: active production outage or broad customer impact.
- `SEV-2`: degraded enforcement behavior, isolated or time-bounded impact.
- `SEV-3`: low-risk anomaly requiring follow-up but no immediate outage.

## SLO Burn-Rate Policy (BSAFE-016)

Target SLO for enforcement gate reliability: `99.9%` (error budget `0.1%`).

Burn-rate alerts and thresholds:

1. `ValdricsEnforcementErrorBudgetBurnFast` (`critical`)
   - windows: `1h` + `5m`
   - threshold: `14.4x` burn (`error_ratio > 14.4 * 0.001`)
2. `ValdricsEnforcementErrorBudgetBurnSlow` (`warning`)
   - windows: `6h` + `30m`
   - threshold: `6x` burn (`error_ratio > 6 * 0.001`)

Low-traffic guardrails are required in rule expressions to avoid false positives:

1. minimum decision volume in window for alert eligibility.

Release-gate rule:

1. Any firing burn-rate alert blocks release promotion.
2. Promotion resumes only after alerts are clear for two consecutive windows and incident owner signs off mitigation.

## Scenario 1: Abuse Spike (Cross-Tenant Burst)

### Detection Signals

- `valdrics_ops_llm_fair_use_denials_total`
- `valdrics_ops_enforcement_gate_failures_total`
- `valdrics_ops_enforcement_gate_decisions_total` rapid surge with deny/failsafe skew

### Immediate Response

1. Declare incident severity and open incident channel.
2. Enable or tighten global abuse thresholds:
   - `LLM_GLOBAL_ABUSE_GUARDS_ENABLED=true`
   - lower `LLM_GLOBAL_ABUSE_PER_MINUTE_CAP`
   - lower `LLM_GLOBAL_ABUSE_UNIQUE_TENANTS_THRESHOLD`
   - if required, set `LLM_GLOBAL_ABUSE_KILL_SWITCH=true`
3. Increase audit sampling on gateway traffic and approval-token failures.
4. Track whether denial rates stabilize within 15 minutes.

### Exit Criteria

- burst traffic returns below threshold.
- false-positive rate remains within acceptable threshold.
- kill switch (if enabled) reverted with written incident note.

## Scenario 2: False-Positive Enforcement Block

### Detection Signals

- sudden rise in `DENY` or `REQUIRE_APPROVAL` for known-good paths.
- spike in `valdrics_ops_enforcement_gate_decision_reasons_total` for a single reason.
- escalation from customer support or on-call pipeline failures.

### Immediate Response

1. Confirm impacted policy mode and policy version.
2. Switch affected source mode to `soft` or `shadow` to reduce blast radius.
3. Manually approve critical queued requests if policy intent is clear.
4. Capture impacted request fingerprints and reason-code distribution.
5. Prepare policy patch and rollout validation plan.

### Exit Criteria

- policy fix deployed.
- deny distribution returns to baseline.
- affected customers notified with corrective summary.

## Scenario 3: Approval Signing Key Compromise

### Detection Signals

- unexpected token validation mismatches or replay attempts.
- suspected exposure of signing secret (`SUPABASE_JWT_SECRET`).
- untrusted token generation observed in logs.

### Immediate Response

1. Trigger emergency secret rotation:
   - follow `docs/runbooks/secret_rotation_emergency.md`.
2. Freeze approval-token issuance path temporarily if active abuse is confirmed.
3. Rotate signing key, redeploy, and invalidate old tokens.
4. Re-test token issue/consume paths and ensure replay protections remain active.
5. Record impacted window and blast radius in incident timeline.

### Exit Criteria

- old key rejected everywhere.
- token consume validation passes in smoke checks.
- incident timeline and RCA published.

## Scenario 4: Reservation Reconciliation Drift Surge

### Detection Signals

- spike in `valdrics_ops_enforcement_reservation_drift_usd_total`
- elevated `overage`/`savings` exceptions from reconciliation endpoints.
- alert hooks for `drift_exception` and `sla_release`.

### Immediate Response

1. Trigger overdue reconciliation sweep.
2. Review top drift exceptions and classify by root cause.
3. Reconcile impacted decisions manually when needed.
4. If systemic, reduce blast radius by moving affected source to `soft`.
5. Open follow-up issue for decisioning or estimation bias.

### Exit Criteria

- drift volume below alert threshold for two consecutive windows.
- exception queue aging normalized.
- remediation and prevention actions documented.

## Communications Checklist

1. Incident opened with severity and owner.
2. Impacted tenant/project scope identified.
3. Mitigation steps posted every 15-30 minutes for SEV-1/SEV-2.
4. Final status includes root cause, fix, and follow-up tasks.

## Evidence Checklist

- Alert timeline and metric snapshots.
- API/test execution traces for mitigation validation.
- Policy or config changes applied during incident.
- Post-incident summary linked from `docs/ops/incident_response_runbook.md`.
