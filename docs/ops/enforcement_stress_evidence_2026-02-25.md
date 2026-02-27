# Enforcement Stress Evidence Protocol (2026-02-25)

This document defines the mandatory stress evidence capture and validation protocol for enforcement release readiness.

## Capture Command

Run staged stress with enforcement profile:

```bash
uv run python scripts/load_test_api.py \
  --profile enforcement \
  --rounds 3 \
  --output artifact.json
```

## Validation Command

Validate captured evidence before promotion:

```bash
uv run python scripts/verify_enforcement_stress_evidence.py \
  --artifact artifact.json \
  --max-p95-seconds 2.0 \
  --max-error-rate-percent 1.0 \
  --min-throughput-rps 0.5
```

## Release Rule

Failing stress evidence blocks release promotion.
