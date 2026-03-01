# Enforcement Release Evidence Artifacts

This directory stores staged enforcement evidence artifacts used by release gates.

## Required Artifact Names

1. Stress artifact: `enforcement_stress_artifact_YYYY-MM-DD.json`
2. Failure-injection artifact: `enforcement_failure_injection_YYYY-MM-DD.json`
3. Finance guardrail artifact: `finance_guardrails_YYYY-MM-DD.json`
4. Pricing benchmark register: `pricing_benchmark_register_YYYY-MM-DD.json`
5. PKG/FIN policy decision artifact: `pkg_fin_policy_decisions_YYYY-MM-DD.json`
6. Finance telemetry snapshot artifact: `finance_telemetry_snapshot_YYYY-MM-DD.json`
7. Finance committee assumptions artifact: `finance_committee_packet_assumptions_YYYY-MM-DD.json`
8. Valdrics disposition register artifact: `valdrix_disposition_register_YYYY-MM-DD.json`
9. PKG/FIN operational readiness summary (optional but recommended): `pkg_fin_operational_readiness_YYYY-MM-DD.json`

## Template Seeds

1. `enforcement_stress_artifact_TEMPLATE.json`
2. `enforcement_failure_injection_TEMPLATE.json`
3. `finance_guardrails_TEMPLATE.json`
4. `pricing_benchmark_register_TEMPLATE.json`
5. `pkg_fin_policy_decisions_TEMPLATE.json`
6. `finance_telemetry_snapshot_TEMPLATE.json`
7. `finance_committee_packet_assumptions_TEMPLATE.json`
8. `valdrix_disposition_register_TEMPLATE.json`

## Staged Failure-Injection Capture

Generate the failure-injection artifact from the FI matrix selectors:

```bash
DEBUG=false uv run python3 scripts/generate_enforcement_failure_injection_evidence.py \
  --output docs/ops/evidence/enforcement_failure_injection_YYYY-MM-DD.json \
  --executed-by sre.executor@valdrix.local \
  --approved-by release.approver@valdrix.local
```

Use templates only as schema seeds. Do not submit templates as staged-run evidence.

## Capture Commands

Stress capture:

```bash
uv run python scripts/load_test_api.py \
  --profile enforcement \
  --rounds 3 \
  --enforce-thresholds \
  --out docs/ops/evidence/enforcement_stress_artifact_YYYY-MM-DD.json
```

Failure-injection staged evidence should be captured to:

```text
docs/ops/evidence/enforcement_failure_injection_YYYY-MM-DD.json
```

Finance guardrail staged evidence should be captured to:

```text
docs/ops/evidence/finance_guardrails_YYYY-MM-DD.json
```

Pricing benchmark register evidence should be captured to:

```text
docs/ops/evidence/pricing_benchmark_register_YYYY-MM-DD.json
```

PKG/FIN policy decision evidence should be captured to:

```text
docs/ops/evidence/pkg_fin_policy_decisions_YYYY-MM-DD.json
```

Finance telemetry snapshot evidence should be captured to:

```text
docs/ops/evidence/finance_telemetry_snapshot_YYYY-MM-DD.json
```

Finance committee assumptions should be captured to:

```text
docs/ops/evidence/finance_committee_packet_assumptions_YYYY-MM-DD.json
```

Valdrics disposition register should be captured to:

```text
docs/ops/evidence/valdrix_disposition_register_YYYY-MM-DD.json
```

## Verification Commands

Stress verifier:

```bash
uv run python3 scripts/verify_enforcement_stress_evidence.py \
  --evidence-path docs/ops/evidence/enforcement_stress_artifact_YYYY-MM-DD.json \
  --required-database-engine postgresql
```

Failure-injection verifier:

```bash
uv run python3 scripts/verify_enforcement_failure_injection_evidence.py \
  --evidence-path docs/ops/evidence/enforcement_failure_injection_YYYY-MM-DD.json
```

Finance guardrail verifier:

```bash
uv run python3 scripts/verify_finance_guardrails_evidence.py \
  --evidence-path docs/ops/evidence/finance_guardrails_YYYY-MM-DD.json \
  --max-artifact-age-hours 744
```

Pricing benchmark register verifier:

```bash
uv run python3 scripts/verify_pricing_benchmark_register.py \
  --register-path docs/ops/evidence/pricing_benchmark_register_YYYY-MM-DD.json \
  --max-source-age-days 120
```

PKG/FIN policy decision verifier:

```bash
uv run python3 scripts/verify_pkg_fin_policy_decisions.py \
  --evidence-path docs/ops/evidence/pkg_fin_policy_decisions_YYYY-MM-DD.json \
  --max-artifact-age-hours 744
```

PKG/FIN policy decision artifact minimum required policy fields:
1. `telemetry.source_type` (`synthetic_prelaunch` or `production_observed`)
2. `policy_decisions.pricing_motion_allowed`
3. `approvals.governance_mode` (`founder_acting_roles_prelaunch` or `segregated_owners`)
4. `approvals.approval_record_ref`
5. `decision_backlog.required_decision_ids` (canonical PKG/FIN decision set)
6. `decision_backlog.decision_items[*].resolution` (`locked_prelaunch` or `scheduled_postlaunch`)
7. `decision_backlog.decision_items[*].launch_blocking`

PKG/FIN policy decision release gates:
1. `pkg_fin_gate_policy_decisions_complete`
2. `pkg_fin_gate_telemetry_window_sufficient`
3. `pkg_fin_gate_approvals_complete`
4. `pkg_fin_gate_pricing_motion_guarded`
5. `pkg_fin_gate_backlog_coverage_complete`
6. `pkg_fin_gate_launch_blockers_resolved`
7. `pkg_fin_gate_postlaunch_commitments_scheduled`

Finance telemetry snapshot verifier:

```bash
uv run python3 scripts/verify_finance_telemetry_snapshot.py \
  --snapshot-path docs/ops/evidence/finance_telemetry_snapshot_YYYY-MM-DD.json \
  --max-artifact-age-hours 744
```

Finance telemetry snapshot minimum guardrail fields for PKG-010:
1. `free_tier_compute_guardrails` (free-vs-starter bounded LLM limits)
2. `free_tier_margin_watch` (free-tier LLM cost telemetry against starter MRR reference)
3. `gate_results.telemetry_gate_free_tier_guardrails_bounded`
4. `gate_results.telemetry_gate_free_tier_margin_guarded`

Monthly finance committee packet generator:

```bash
uv run python3 scripts/generate_finance_committee_packet.py \
  --telemetry-path docs/ops/evidence/finance_telemetry_snapshot_YYYY-MM-DD.json \
  --assumptions-path docs/ops/evidence/finance_committee_packet_assumptions_YYYY-MM-DD.json \
  --output-dir docs/ops/evidence \
  --require-all-gates-pass
```

Monthly finance refresh verifier (release reminder gate):

```bash
uv run python3 scripts/verify_monthly_finance_evidence_refresh.py \
  --finance-guardrails-path docs/ops/evidence/finance_guardrails_YYYY-MM-DD.json \
  --finance-telemetry-snapshot-path docs/ops/evidence/finance_telemetry_snapshot_YYYY-MM-DD.json \
  --pkg-fin-policy-decisions-path docs/ops/evidence/pkg_fin_policy_decisions_YYYY-MM-DD.json \
  --max-age-days 35 \
  --max-capture-spread-days 14
```

Valdrics disposition freshness verifier (risk-review reminder gate):

```bash
uv run python3 scripts/verify_valdrix_disposition_freshness.py \
  --register-path docs/ops/evidence/valdrix_disposition_register_YYYY-MM-DD.json \
  --max-artifact-age-days 45 \
  --max-review-window-days 120
```

PKG/FIN operational readiness summary verifier/generator:

```bash
uv run python3 scripts/verify_pkg_fin_operational_readiness.py \
  --policy-decisions-path docs/ops/evidence/pkg_fin_policy_decisions_YYYY-MM-DD.json \
  --finance-guardrails-path docs/ops/evidence/finance_guardrails_YYYY-MM-DD.json \
  --telemetry-snapshot-path docs/ops/evidence/finance_telemetry_snapshot_YYYY-MM-DD.json \
  --output-path docs/ops/evidence/pkg_fin_operational_readiness_YYYY-MM-DD.json
```
