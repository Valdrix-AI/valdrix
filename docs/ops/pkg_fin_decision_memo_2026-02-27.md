# PKG/FIN Decision Memo (2026-02-27)

## Purpose

This memo captures:
1. What can be enforced in code immediately.
2. What still requires product/finance policy decisions.
3. Recommended default decisions from current external guidance.

## Why "internal telemetry + policy choices" is the blocker

`PKG-*` and `FIN-*` are not only implementation tasks. Several open items are decision-bound:
1. Packaging boundary (`PKG-016/026/027`): which control-plane capabilities are contractually Pro vs Enterprise.
2. Pricing policy (`PKG-009`): flat floor vs spend-based vs hybrid.
3. Transition rules (`PKG-018`): how existing customers are migrated/grandfathered.
4. Finance gates (`FIN-GATE-*`): exact thresholds and corrective actions when breached.

These cannot be made "correct by code only" without:
1. Real usage telemetry (margin, COGS, conversion trends, expansion behavior).
2. Explicit commercial policy approvals (what to sell, to whom, at what floor).

## How to resolve the blocker

1. Stand up a monthly finance packet with fixed inputs:
   - tier-level MRR/effective MRR/COGS split,
   - p50/p95/p99 LLM usage by tier,
   - conversion and expansion deltas by tier cohort.
2. Lock a pricing-policy rubric in writing:
   - enterprise floor model type (flat/spend/hybrid),
   - maximum annual discount band by segment,
   - grandfathering and migration guardrails.
3. Enforce policy via release evidence gates:
   - finance guardrail artifact (`FIN-GATE-*`),
   - pricing benchmark register freshness (`PKG-020`),
   - no pricing-motion approval without both artifacts passing validation.
4. Re-run thresholds quarterly (or earlier on breach) and update contracts only through approved evidence packet.

## Blocker Clarification (Plain Language)

"Internal telemetry + policy choices are the primary blocker" means:
1. We can enforce gates and run tests for correctness, but pricing/packaging moves are still unsafe without real operating data from recent closes.
2. Tooling cannot infer business decisions that must be explicitly approved (pricing model type, migration approach, discount caps, tier boundary commitments).
3. Therefore, code alone is not enough: we need both machine-verifiable telemetry evidence and signed policy choices in the same release decision packet.

### How to resolve the blocker (operationally)

1. Close telemetry gap:
   - Capture two complete monthly closes with tier-level usage/cost/revenue rollups.
   - Regenerate `finance_guardrails` and `pkg_fin_policy_decisions` artifacts from those closes.
2. Close policy gap:
   - Finalize policy choices in the decision artifact (`enterprise_model`, migration strategy, growth/pro boundaries).
   - Obtain required sign-offs (`finance_owner`, `product_owner`, `go_to_market_owner`) with timestamp.
3. Enforce both at release time:
   - Require `--finance-evidence-required`, `--pricing-benchmark-register-required`, and `--pkg-fin-policy-decisions-required`.
4. Define breach behavior in advance:
   - If any `FIN-GATE-*` or `PKG/FIN` decision gate fails, freeze packaging/pricing rollout and run corrective plan.
5. Revalidate continuously:
   - Re-run evidence checks monthly and during any pricing/packaging motion.

## Implementation update (2026-02-28G): decision-bound backlog made machine-checkable

The remaining decision-bound backlog now has an explicit verification contract, not just narrative tracking:

1. Canonical backlog coverage is required in `pkg_fin_policy_decisions` evidence:
   - every required PKG/FIN decision ID must be present,
   - every item must carry owner, owner-function, approval reference, and approval timestamp.
2. Launch-blocking decisions must resolve prelaunch:
   - release gate fails if any launch-blocking item is only `scheduled_postlaunch`.
3. Postlaunch commitments must be concrete:
   - `scheduled_postlaunch` entries require target dates and success criteria.
4. Release now checks dedicated governance gates:
   - `pkg_fin_gate_backlog_coverage_complete`
   - `pkg_fin_gate_launch_blockers_resolved`
   - `pkg_fin_gate_postlaunch_commitments_scheduled`

This keeps implementation and governance aligned: engineering cannot mark policy backlog complete without explicit, machine-verifiable product/finance/GTM sign-off records.

## Focused research check (2026-02-28)

Current primary-source signals remain aligned with this implementation:
1. FinOps Framework still anchors governance/policy and unit-economics as first-class capabilities.
2. FOCUS changelog confirms current normalization direction (latest ratified set remains usable for evidence contracts).
3. Stripe and Chargebee both document controlled price-change and grandfathering migration mechanics, supporting explicit migration policy artifacts.
4. AWS Cost Optimization guidance continues to require measurable governance controls and periodic cost-review loops.

## Recommended defaults (implementable now)

1. Keep hard runtime gating for enforcement APIs tied to explicit feature checks (`PKG-003/014` baseline).
2. Enforce finance guardrail evidence in release workflows when a finance artifact is provided.
3. Use a hybrid enterprise pricing policy draft (platform floor + governed usage envelope) pending final pricing committee sign-off.
4. Keep conservative finance thresholds until 2 monthly closes prove stability:
   - blended gross margin floor: `>= 80%`
   - stress margin floor: `>= 75%`
   - p95 tenant LLM COGS envelope: bounded by percent-of-MRR threshold
   - annual discount impact ceiling: bounded
   - conversion momentum gates: non-negative month-over-month deltas

## External references used

Validated during this pass (`2026-02-28`), with current published anchors:
1. FOCUS latest specification page indicates `FOCUS 1.3` ratified in December 2025.
2. AWS Cost Optimization pillar whitepaper revision date is June 27, 2024.

1. FinOps Framework capabilities (governance + unit economics):  
   https://www.finops.org/framework/capabilities/
2. FinOps maturity model (`crawl/walk/run` staged rollout):  
   https://www.finops.org/framework/maturity-assessment/
3. FOCUS changelog (latest normalization signals for cost datasets):  
   https://focus.finops.org/changelog/
4. AWS Well-Architected Cost Optimization pillar (cost governance controls):  
   https://docs.aws.amazon.com/wellarchitected/latest/cost-optimization-pillar/welcome.html
5. OpenAI production guidance (cost controls + budgeting):  
   https://platform.openai.com/docs/guides/production-best-practices
6. Stripe subscription price-change operations (migration mechanics):  
   https://docs.stripe.com/billing/subscriptions/change-price
7. Chargebee billing migration with grandfathering concepts:  
   https://www.chargebee.com/docs/billing/2.0/subscriptions/migrate-subscriptions
8. ChartMogul benchmark direction on retention/expansion signals (operating context):  
   https://chartmogul.com/saas-growth-report/
   https://chartmogul.com/reports/saas-benchmarks/

## Execution status from this pass

1. Finance evidence artifact schema and verifier were added and wired for release-gate usage.
2. Finance evidence templates and staged example artifact were added.
3. Release gate scripts were extended so finance evidence can be required in the same pass as stress/failure evidence.
4. Unit tests were added for verifier integrity and gate wiring behavior.
5. Pricing benchmark register schema and verifier were added to close `PKG-020` automation baseline.
6. PKG/FIN policy-decision evidence schema and verifier were added to close decision-governance automation baseline:
   - `scripts/verify_pkg_fin_policy_decisions.py`
   - `docs/ops/evidence/pkg_fin_policy_decisions_TEMPLATE.json`
   - `docs/ops/evidence/pkg_fin_policy_decisions_2026-02-28.json`

## Implementation update (2026-02-28)

This pass applies the packaging semantics directly in production code and test gates:

1. Tier pricing updated in source-of-truth config (`app/shared/core/pricing.py`):
   - Starter: `49 / 490` (monthly/annual USD)
   - Growth: `149 / 1490`
   - Pro: `299 / 2990`
2. Fallback frontend pricing updated to match backend source of truth:
   - `dashboard/src/routes/pricing/plans.ts`
   - `dashboard/src/routes/billing/+page.svelte`
3. Growth auto-remediation boundary hardened:
   - Growth tier is now blocked from approving/executing production remediation targets.
   - Implemented in `app/modules/optimization/api/v1/zombies.py`.
   - Production target classifier exported in `app/modules/governance/domain/security/remediation_policy.py`.
4. Regression tests expanded and executed for pricing + boundary behavior:
   - `tests/unit/zombies/test_zombies_api_branches.py`
   - `tests/unit/optimization/test_remediation_policy.py`
   - `tests/unit/api/v1/test_billing.py`
   - `tests/unit/services/billing/test_paystack_billing_branches.py`
   - `tests/api/test_endpoints.py`
   - `dashboard/src/routes/pricing/pricing.load.test.ts`

Validation evidence (single pass):
1. `DEBUG=false TESTING=true ENVIRONMENT=development uv run pytest --no-cov -q tests/unit/zombies/test_zombies_api_branches.py tests/unit/optimization/test_remediation_policy.py tests/unit/api/v1/test_billing.py tests/unit/services/billing/test_paystack_billing_branches.py` -> `72 passed`
2. `DEBUG=false TESTING=true ENVIRONMENT=development uv run pytest --no-cov -q tests/api/test_endpoints.py` -> `36 passed`
3. `uv run ruff check app/shared/core/pricing.py app/modules/governance/domain/security/remediation_policy.py app/modules/optimization/api/v1/zombies.py tests/unit/zombies/test_zombies_api_branches.py tests/unit/optimization/test_remediation_policy.py tests/unit/api/v1/test_billing.py tests/unit/services/billing/test_paystack_billing_branches.py` -> passed
4. `uv run mypy app/shared/core/pricing.py app/modules/governance/domain/security/remediation_policy.py app/modules/optimization/api/v1/zombies.py --hide-error-context --no-error-summary` -> passed
5. `pnpm --dir dashboard exec vitest --run src/routes/pricing/pricing.load.test.ts` -> `4 passed`

Operational note:
1. If `pricing_plans` rows already exist in production, update those records during rollout to avoid stale DB price overrides on billing-plan reads and renewal lookups.

## Implementation update (2026-02-28B): policy-decision gate closure

1. Added PKG/FIN decision evidence verification into release gates:
   - `scripts/run_enterprise_tdd_gate.py`
   - `scripts/run_enforcement_release_evidence_gate.py`
2. New release-gate env/CLI contracts:
   - `ENFORCEMENT_PKG_FIN_POLICY_DECISIONS_PATH`
   - `ENFORCEMENT_PKG_FIN_POLICY_DECISIONS_REQUIRED`
   - `ENFORCEMENT_PKG_FIN_POLICY_DECISIONS_MAX_AGE_HOURS`
   - `--pkg-fin-policy-decisions-path`
   - `--pkg-fin-policy-decisions-required`
   - `--pkg-fin-policy-decisions-max-age-hours`
3. New machine-verifiable decision gates:
   - `pkg_fin_gate_policy_decisions_complete`
   - `pkg_fin_gate_telemetry_window_sufficient`
   - `pkg_fin_gate_approvals_complete`

## Validation rerun (2026-02-28C): full closure pass

1. Targeted regression run:
   - `DEBUG=false uv run pytest --no-cov -q tests/unit/ops/test_verify_pkg_fin_policy_decisions.py tests/unit/ops/test_pkg_fin_policy_decisions_pack.py tests/unit/ops/test_release_artifact_templates_pack.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py tests/unit/supply_chain/test_run_enforcement_release_evidence_gate.py tests/unit/ops/test_verify_finance_guardrails_evidence.py tests/unit/ops/test_verify_pricing_benchmark_register.py tests/unit/zombies/test_zombies_api_branches.py tests/unit/optimization/test_remediation_policy.py tests/unit/api/v1/test_billing.py tests/unit/services/billing/test_paystack_billing_branches.py tests/api/test_endpoints.py`
   - Result: `160 passed`.
2. Static checks:
   - `uv run ruff check $(git diff --name-only -- '*.py')` -> passed
   - `uv run mypy app/shared/core/pricing.py app/modules/governance/domain/security/remediation_policy.py app/modules/optimization/api/v1/zombies.py scripts/run_enterprise_tdd_gate.py scripts/run_enforcement_release_evidence_gate.py scripts/verify_pkg_fin_policy_decisions.py --hide-error-context --no-error-summary` -> passed
3. Post-closure sanity check:
   - `uv run python3 scripts/verify_enforcement_post_closure_sanity.py`
   - Result: all 7 dimensions `OK` (`concurrency`, `observability`, `deterministic_replay`, `snapshot_stability`, `export_integrity`, `failure_modes`, `operational_misconfiguration`).
4. Full release-evidence gate (non-dry-run):
   - `DEBUG=false uv run python3 scripts/run_enforcement_release_evidence_gate.py --stress-evidence-path docs/ops/evidence/enforcement_stress_artifact_2026-02-27.json --failure-evidence-path docs/ops/evidence/enforcement_failure_injection_2026-02-27.json --finance-evidence-path docs/ops/evidence/finance_guardrails_2026-02-27.json --pricing-benchmark-register-path docs/ops/evidence/pricing_benchmark_register_2026-02-27.json --pkg-fin-policy-decisions-path docs/ops/evidence/pkg_fin_policy_decisions_2026-02-28.json --finance-evidence-required --pricing-benchmark-register-required --pkg-fin-policy-decisions-required`
   - Result: passed (`845 passed`) and coverage gates satisfied:
     - enforcement subset: `99%` (`>=95%`)
     - LLM guardrail subset: `100%` (`>=90%`)
     - analytics visibility subset: `100%` (`>=99%`)

## Implementation update (2026-02-28D): live telemetry automation baseline

Engineering-only automation added to reduce manual FIN packet work:

1. New telemetry collector and verifier:
   - `scripts/collect_finance_telemetry_snapshot.py`
   - `scripts/verify_finance_telemetry_snapshot.py`
2. New monthly packet generator with gate-aware alert hook:
   - `scripts/generate_finance_committee_packet.py`
   - Generates:
     - `finance_guardrails_<label>.json`
     - `finance_committee_packet_<label>.json`
     - tier/scenario CSV exports for committee review.
3. New evidence contracts and templates:
   - `docs/ops/evidence/finance_telemetry_snapshot_TEMPLATE.json`
   - `docs/ops/evidence/finance_telemetry_snapshot_2026-02-28.json`
   - `docs/ops/evidence/finance_committee_packet_assumptions_TEMPLATE.json`
   - `docs/ops/evidence/finance_committee_packet_assumptions_2026-02-28.json`
4. Gate wiring expanded:
   - `scripts/run_enterprise_tdd_gate.py`
     - `ENFORCEMENT_FINANCE_TELEMETRY_SNAPSHOT_PATH`
     - `ENFORCEMENT_FINANCE_TELEMETRY_SNAPSHOT_REQUIRED`
     - `ENFORCEMENT_FINANCE_TELEMETRY_SNAPSHOT_MAX_AGE_HOURS`
   - `scripts/run_enforcement_release_evidence_gate.py`
     - `--finance-telemetry-snapshot-path`
     - `--finance-telemetry-snapshot-required`
     - `--finance-telemetry-max-age-hours`
5. Verification and tests added:
   - `tests/unit/ops/test_verify_finance_telemetry_snapshot.py`
   - `tests/unit/ops/test_collect_finance_telemetry_snapshot.py`
   - `tests/unit/ops/test_generate_finance_committee_packet.py`
   - `tests/unit/ops/test_finance_telemetry_snapshot_pack.py`
   - gate-wiring updates in supply-chain tests.

Execution evidence:
1. `DEBUG=false uv run pytest --no-cov -q tests/unit/ops/test_verify_finance_telemetry_snapshot.py tests/unit/ops/test_collect_finance_telemetry_snapshot.py tests/unit/ops/test_generate_finance_committee_packet.py tests/unit/ops/test_finance_telemetry_snapshot_pack.py tests/unit/ops/test_release_artifact_templates_pack.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py tests/unit/supply_chain/test_run_enforcement_release_evidence_gate.py` -> `48 passed`
2. `uv run ruff check ...` on all new/changed telemetry scripts/tests -> passed
3. `uv run mypy scripts/verify_finance_guardrails_evidence.py scripts/verify_finance_telemetry_snapshot.py scripts/collect_finance_telemetry_snapshot.py scripts/generate_finance_committee_packet.py scripts/run_enterprise_tdd_gate.py scripts/run_enforcement_release_evidence_gate.py --hide-error-context --no-error-summary` -> passed
4. `DEBUG=false uv run python3 scripts/run_enforcement_release_evidence_gate.py --stress-evidence-path docs/ops/evidence/enforcement_stress_artifact_2026-02-27.json --failure-evidence-path docs/ops/evidence/enforcement_failure_injection_2026-02-27.json --finance-evidence-path docs/ops/evidence/finance_guardrails_2026-02-27.json --finance-telemetry-snapshot-path docs/ops/evidence/finance_telemetry_snapshot_2026-02-28.json --pricing-benchmark-register-path docs/ops/evidence/pricing_benchmark_register_2026-02-27.json --pkg-fin-policy-decisions-path docs/ops/evidence/pkg_fin_policy_decisions_2026-02-28.json --finance-evidence-required --finance-telemetry-snapshot-required --pricing-benchmark-register-required --pkg-fin-policy-decisions-required` -> passed (`860 passed`)

## What is truly left after this pass

Engineering baseline is now in place for collection, generation, verification, and gating.
Remaining blockers are decision/governance or post-launch data availability:

1. Policy decisions:
   - final price floors/ceilings and discount policy,
   - final enforcement commercial boundary strategy.
2. Live telemetry requirement:
   - two consecutive monthly closes from real cohorts for production pricing motions.
3. Approval governance:
   - required executive sign-offs on generated committee packet outputs.

## Final Team Decisions (2026-02-28F, pre-launch locked)

Decision scope: close the 3 remaining policy items for pre-launch readiness with machine-verifiable contracts.

1. Commercial policy lock:
   - Launch public list prices stay at:
     - Starter: `49 / 490`
     - Growth: `149 / 1490`
     - Pro: `299 / 2990`
   - Enterprise remains contract-led with floor policy:
     - `enterprise_pricing_model=hybrid`
     - `enterprise_floor_usd_monthly=799`
   - Max annual discount cap remains:
     - `max_annual_discount_percent=20`
   - Control-plane boundary remains locked:
     - `growth_auto_remediation_scope=nonprod_only`
     - `pro_enforcement_boundary=required_for_prod_enforcement`

2. Telemetry governance lock (pre-launch vs pricing-motion):
   - Pre-launch evidence may be synthetic:
     - `telemetry.source_type=synthetic_prelaunch`
   - Pricing motion is explicitly blocked until production telemetry is available:
     - `policy_decisions.pricing_motion_allowed=false`
   - New gate enforces this:
     - `pkg_fin_gate_pricing_motion_guarded=true`
   - Operational meaning:
     - platform launch is allowed,
     - packaging/pricing changes are locked until `source_type=production_observed` with sufficient observed window.

3. Approval governance lock for a small pre-launch team:
   - Governance mode:
     - `approvals.governance_mode=founder_acting_roles_prelaunch`
   - Formal record required:
     - `approvals.approval_record_ref` non-empty
   - Future state remains supported without schema changes:
     - `segregated_owners` mode enforces distinct finance/product/go-to-market owners.

## Validation rerun (2026-02-28E): workspace closure audit

This rerun was executed to confirm there are no hidden engineering gaps left in current in-flight changes.

Execution evidence:
1. Full non-dry-run release-evidence gate:
   - `DEBUG=false uv run python3 scripts/run_enforcement_release_evidence_gate.py --stress-evidence-path docs/ops/evidence/enforcement_stress_artifact_2026-02-27.json --failure-evidence-path docs/ops/evidence/enforcement_failure_injection_2026-02-27.json --finance-evidence-path docs/ops/evidence/finance_guardrails_2026-02-27.json --finance-telemetry-snapshot-path docs/ops/evidence/finance_telemetry_snapshot_2026-02-28.json --pricing-benchmark-register-path docs/ops/evidence/pricing_benchmark_register_2026-02-27.json --pkg-fin-policy-decisions-path docs/ops/evidence/pkg_fin_policy_decisions_2026-02-28.json --finance-evidence-required --finance-telemetry-snapshot-required --pricing-benchmark-register-required --pkg-fin-policy-decisions-required`
   - Result: passed (`860 passed`) with coverage gates satisfied.
2. Additional backend regressions on non-gate modified modules:
   - `DEBUG=false uv run pytest --no-cov -q tests/unit/api/v1/test_billing.py tests/unit/services/billing/test_paystack_billing_branches.py tests/unit/optimization/test_remediation_policy.py tests/unit/zombies/test_zombies_api_branches.py`
   - Result: `72 passed`.
3. Frontend verification on modified pricing paths:
   - `npm run test:unit -- --run src/routes/pricing/pricing.load.test.ts` (under `dashboard/`) -> `4 passed`.
   - `npm run check` (under `dashboard/`) -> `0 errors`, `0 warnings`.
4. Static quality on changed/new Python files:
   - `uv run ruff check ...` -> passed.
   - `uv run mypy ... --hide-error-context --no-error-summary` -> passed.

Conclusion:
1. Engineering/test automation changes currently in scope are green.
2. Remaining blockers are still policy/telemetry-governance decisions listed above, not unverified code quality debt.
