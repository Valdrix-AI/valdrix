# Pricing Competitiveness and Sustainability - Fact Check (2026-02-17)

Validated on **February 17, 2026** against current repository code.

## Executive Summary

- The product now uses a **permanent `free` tier** (hard cut), not `free_trial`.
- This removes trial lifecycle complexity and aligns onboarding, tier enum, scheduler behavior, and billing downgrade paths.
- The free tier is viable for activation and product-led growth, but retention will depend on whether users reach repeated value moments, not just signup conversion.

## Implemented Product Decision

Decision: **Permanent free tier with strict limits; no backward-compatible `free_trial` path.**

### Code-backed implementation status

1. Tier model and limits updated to `free` baseline.
- `app/shared/core/pricing.py:34`
- `app/shared/core/pricing.py:87`

2. Onboarding now assigns permanent free tier.
- `app/modules/governance/api/v1/settings/onboard.py:56`

3. Scheduler no longer places free users in recurring dormant cohorts.
- DORMANT enqueue scope is starter-only: `app/tasks/scheduler_tasks.py:161`
- Job mix is feature-driven (no unconditional ingestion/analysis): `app/tasks/scheduler_tasks.py:193`

4. LLM controls added for cost safety on lower tiers.
- Daily per-tier analysis quota enforcement: `app/shared/llm/budget_manager.py:102`
- Budget auto-bootstrap on first use: `app/shared/llm/budget_manager.py:188`
- Analysis endpoint rate limit hook: `app/modules/reporting/api/v1/costs.py:812`

5. Billing failure downgrade now lands on free tier semantics.
- `app/modules/billing/domain/billing/dunning_service.py:223`

6. DB migration constraints/defaults normalized to `free`.
- `migrations/versions/5f3a9c2d1e8b_enforce_free_trial_tier_constraints.py:21`

7. Follow-up schema cleanup for existing migrated environments.
- Drops legacy `tenants.trial_started_at` column.
- Normalizes any persisted `trial`/`free_trial` tier values to `free`.
- Reasserts default + allowed-tier constraints for `tenants.plan` and `tenant_subscriptions.tier`.
- `migrations/versions/b0c1d2e3f4a5_drop_trial_started_at_and_enforce_free_tier_defaults.py:1`

## Why this is better than trial-only complexity

1. Simpler lifecycle model.
- No trial expiry timers, no entitlement cliff logic, fewer edge-case transitions.

2. Lower support and product ambiguity.
- Users understand a stable free plan with clear caps.

3. Better top-of-funnel consistency.
- Marketing, onboarding, pricing UI, and backend contract are aligned on the same entry plan.

## Is free tier enough to keep users?

Short answer: **enough to keep users exploring, not enough to keep all users long-term without upgrade triggers.**

What free currently provides (value moments):
- Core dashboards + cost visibility.
- 1 AWS account support.
- Weekly zombie scans.
- Limited AI assistance (strict daily cap).

What drives upgrades (and therefore healthy retention economics):
- More connected accounts/projects.
- Higher scan frequency and ingestion/backfill capabilities.
- Higher LLM analysis allowance and advanced automation.

Interpretation:
- Free tier should maximize **activation and trust**.
- Paid tiers should maximize **operational depth and automation**.
- If free already solves 100% of recurring customer jobs, upgrade pressure collapses.

## Cost-Safety Guardrails for Permanent Free

1. Keep free out of recurring heavy scheduler cohorts (already implemented).
2. Keep free LLM usage tightly capped and budget-enforced (already implemented).
3. Keep strict account and retention limits (already implemented in pricing config).
4. Keep expensive workflows tier-gated via feature flags (already used in API/service guards).

## Metrics to validate the free-tier strategy (next 30 days)

1. Activation rate: signup -> first connected account -> first insight generated.
2. Weekly retained free users (W2/W4).
3. Free-to-paid conversion by trigger (account limit hit, feature gate hit, frequency need).
4. Cost per active free tenant (compute + DB + LLM).
5. Median time-to-upgrade for converted tenants.

## Recommendation

- Keep permanent free tier as the default entry model.
- Do not reintroduce trial lifecycle unless conversion data proves free-tier-only underperforms.
- If conversion is weak, add an **optional paid-feature trial overlay** (time-boxed boost), not a replacement of the permanent free plan.
