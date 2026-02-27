# Enforcement Post-Closure Sanity Policy (2026-02-26)

## Policy Statement

Whenever a control, feature, or gap is marked DONE, the team must execute and record a post-closure sanity check before release promotion.
These validations are release-critical and block promotion when evidence is missing.

## Required Sanity Dimensions

1. `concurrency`
   - Validate contention handling, idempotency behavior, and serialized settlement paths.
2. `observability`
   - Validate alert wiring, lock-contention metrics, and actionable operator reason codes.
3. `deterministic replay`
   - Validate replay protection for approval tokens and idempotent reconciliation.
4. `snapshot stability`
   - Validate computed-context snapshot boundaries and deterministic replay with stable metadata.
5. `export integrity`
   - Validate parity, lineage hashing, and deterministic export bundle reconciliation.
6. `failure modes`
   - Validate timeout, dependency failure, and fail-safe behavior under injected faults.
7. `operational misconfiguration risks`
   - Validate deployment safety contracts (for example fail-closed webhook prerequisites).

## Release Gate Contract

1. `scripts/verify_enforcement_post_closure_sanity.py` must pass.
2. Evidence tokens for all required dimensions must exist in repo-backed tests/docs.
3. The gap register must contain the post-closure sanity check gate evidence update.
