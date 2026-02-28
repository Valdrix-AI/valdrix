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

Validated during this pass (`2026-02-27`), with current published anchors:
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
