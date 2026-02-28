# CI Green Run Evidence Template

Use this file as the baseline structure for release-packet CI capture.

## Capture Metadata

1. Date: `YYYY-MM-DD`
2. Commit SHA: `<sha>`
3. Workflow run URL: `<url>`
4. Trigger: `push|pull_request|manual`

## Enterprise Gate Command

```bash
DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py
```

## Required Gate Outputs

1. `coverage-enterprise-gate.xml` generated.
2. Enterprise gate test summary (`N passed`) captured.
3. Enforcement subset coverage result captured.
4. LLM guardrail subset coverage result captured.
5. Analytics visibility subset coverage result captured.

## Artifact References

1. Stress evidence: `docs/ops/evidence/enforcement_stress_artifact_YYYY-MM-DD.json`
2. Failure injection evidence: `docs/ops/evidence/enforcement_failure_injection_YYYY-MM-DD.json`
