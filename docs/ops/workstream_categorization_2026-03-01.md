# Workstream Categorization (2026-03-01)

This register splits the current mixed local delta into merge-safe tracks.

## Track A: Frontend landing decomposition and auth flow
- Issue: https://github.com/Valdrics/valdrics/issues/199
- Scope: landing component decomposition, public auth intent routing, onboarding/login/layout regressions, and landing e2e alignment.

## Track B: Billing dunning and Paystack resilience
- Issue: https://github.com/Valdrics/valdrics/issues/200
- Scope: billing operations, dunning behavior, Paystack webhook/retry hardening, and coverage for failure/idempotency branches.

## Track C: Governance cloud IAM auditing (Azure/GCP unified)
- Issue: https://github.com/Valdrics/valdrics/issues/201
- Scope: Azure RBAC + GCP IAM auditors, unified domain finding models, and audit payload stability.

## Track D: Ops safety guardrails and infra policy checks
- Issue: https://github.com/Valdrics/valdrics/issues/202
- Scope: destructive-script safeguards, verification scripts, deployment channel checks, and Terraform/IAM policy updates.

## Track E: Enforcement/scheduler/runtime resilience
- Issue: https://github.com/Valdrics/valdrics/issues/203
- Scope: enforcement service reliability branches, scheduler handling, hybrid scheduler behavior, circuit-breaker resilience, and safety bounds.

## Merge strategy
- Keep each track in a dedicated branch and PR.
- Require track-local tests plus relevant contract checks before merge.
- Avoid bundling multiple tracks into a single high-risk PR.
