# Enforcement Release Evidence Artifacts

This directory stores staged enforcement evidence artifacts used by release gates.

## Required Artifact Names

1. Stress artifact: `enforcement_stress_artifact_YYYY-MM-DD.json`
2. Failure-injection artifact: `enforcement_failure_injection_YYYY-MM-DD.json`
3. Finance guardrail artifact: `finance_guardrails_YYYY-MM-DD.json`
4. Pricing benchmark register: `pricing_benchmark_register_YYYY-MM-DD.json`

## Template Seeds

1. `enforcement_stress_artifact_TEMPLATE.json`
2. `enforcement_failure_injection_TEMPLATE.json`
3. `finance_guardrails_TEMPLATE.json`
4. `pricing_benchmark_register_TEMPLATE.json`

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
