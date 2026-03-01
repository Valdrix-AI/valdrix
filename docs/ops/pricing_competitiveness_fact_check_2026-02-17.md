# Pricing Competitiveness and Sustainability - Fact Check (2026-02-18)

Validated on **February 18, 2026** against current repository code.

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

8. Alembic head state consolidated after free-tier rollout.
- Merge migration unifies branches to one head for clean deploy pipelines.
- `migrations/versions/c9d0e1f2a3b4_merge_heads_free_tier_cleanup.py:1`

9. Billing FX path is now fail-closed for checkout safety.
- Billing conversion no longer falls back to hardcoded/stale rates for charge creation.
- Checkout returns service-unavailable semantics when live FX cannot be trusted.
- `app/shared/core/currency.py:28`
- `app/modules/billing/api/v1/billing.py:369`

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

## Currency Charging Accuracy (2026-02-19)

Status: **remediated in code with a single FX service path**.

Implemented:
- Unified billing/reporting FX logic into `app/shared/core/currency.py` (single service).
- Removed hardcoded NGN fallback from settings (`FALLBACK_NGN_RATE` removed).
- Removed ExchangeRate-API integration path and related config dependency.
- NGN live source now prioritizes CBN NFEM endpoint (`/api/GetAllNFEM_RatesGRAPH`).
- Billing strict mode now fails closed if CBN official NGN rate is unavailable.
- Billing strict mode now rejects cached NGN rates unless provider is `cbn_nfem`.
- Non-CBN NGN fallback rates no longer overwrite DB authoritative FX rows.
- If non-official provider would be used for strict NGN billing, checkout is blocked.
- Paystack checkout remains explicitly NGN for now (`PAYSTACK_CHECKOUT_CURRENCY = "NGN"` in `app/modules/billing/domain/billing/paystack_billing.py`).
- Billing now stores immutable charge audit details per subscription:
  - `billing_currency`
  - `last_charge_amount_subunits`
  - `last_charge_fx_rate`
  - `last_charge_fx_provider`
  - `last_charge_reference`
  - `last_charge_at`
  - Model: `app/models/pricing.py`
  - Migration: `migrations/versions/e6f7a8b9c0d1_add_charge_audit_fields_to_tenant_subscriptions.py`
- Admin FX endpoint now exposes billing guardrail health flags:
  - `age_hours`, `is_stale`, `is_official_provider`, `billing_safe`, `warning`
  - Endpoint: `GET /api/v1/billing/admin/rates` in `app/modules/billing/api/v1/billing.py`

Operational impact:
- Reduces risk of inflated NGN checkout amounts caused by spread-heavy non-official sources.
- Keeps display/reporting resilient with non-strict fallback behavior.
- Maintains billing safety: no charge creation when trustworthy official NGN rate cannot be obtained.

Business clarification for current Paystack NGN checkout mode:
- If checkout currency is NGN, Paystack charges the card in NGN.
- International cardholders are billed by their issuer using the issuer/network FX conversion.
- Therefore, NGN amount selection directly affects effective USD-equivalent paid by the customer.

Next step when your USD settlement is activated on Paystack:
- Switch checkout currency to USD for exact `$29/$79/$199` charging consistency.

References:
- CBN exchange rates page: https://www.cbn.gov.ng/rates/ExchRateByCurrency.html
- CBN NFEM JSON endpoint: https://www.cbn.gov.ng/api/GetAllNFEM_RatesGRAPH
- Paystack Initialize Transaction API: https://paystack.com/docs/api/transaction/#initialize
- Paystack supported currencies guidance: https://support.paystack.com/en/articles/2129794

## BYOK Policy (2026-02-19)

Implemented:
- BYOK is enabled for all tiers (`free`, `starter`, `growth`, `pro`, `enterprise`) through explicit `byok_enabled` tier limits in `app/shared/core/pricing.py`.
- BYOK requests no longer incur a per-request surcharge (`BYOK_PLATFORM_FEE_USD = 0.00`) in `app/shared/llm/budget_manager.py`.
- Tier daily analysis quotas remain enforced regardless of BYOK (`llm_analyses_per_day` still applies).
- LLM settings API now contains explicit BYOK entitlement enforcement based on tier limits in `app/modules/governance/api/v1/settings/llm.py`.
- Usage tracking now correctly propagates `is_byok` from `UsageTracker.record(...)` to budget/usage persistence in `app/shared/llm/usage_tracker.py`.

Operational interpretation:
- BYOK is a flexibility/privacy control feature, not a pricing discount path.
- Subscription pricing remains tier-based; BYOK does not change plan price.

## Near-Unlimited Framework (Disabled by Default) (2026-02-19)

Implemented guardrail framework (OFF by default):
- Feature flag: `LLM_FAIR_USE_GUARDS_ENABLED` (default `false`) in `app/shared/core/config.py`.
- Scope: fair-use gates apply only to `pro` and `enterprise` when enabled.
- Gates:
  - Soft daily cap (`LLM_FAIR_USE_PRO_DAILY_SOFT_CAP`, `LLM_FAIR_USE_ENTERPRISE_DAILY_SOFT_CAP`)
  - Per-minute cap (`LLM_FAIR_USE_PER_MINUTE_CAP`)
  - Per-tenant in-flight concurrency cap (`LLM_FAIR_USE_PER_TENANT_CONCURRENCY_CAP`)
- Concurrency guard uses Redis lease if available, with local fallback, and lease TTL (`LLM_FAIR_USE_CONCURRENCY_LEASE_TTL_SECONDS`).
- Denials return explicit HTTP 429 via `LLMFairUseExceededError` (`llm_fair_use_exceeded`) with upgrade/contact guidance.
- Existing tier daily limits (`llm_analyses_per_day`) remain in place.

Implementation references:
- `app/shared/llm/budget_manager.py`
- `app/shared/core/exceptions.py`
- `app/shared/core/error_governance.py`

## Fair-Use Observability Gates (2026-02-19)

Added metrics for rollout monitoring:
- `valdrix_ops_llm_fair_use_denials_total` (counter; labels: `gate`, `tenant_tier`)
- `valdrix_ops_llm_fair_use_evaluations_total` (counter; labels: `gate`, `outcome`, `tenant_tier`)
- `valdrix_ops_llm_fair_use_observed` (gauge; labels: `gate`, `tenant_tier`)
- Existing `valdrix_ops_llm_pre_auth_denials_total` now also tags fair-use denial reasons.
- Admin runtime visibility endpoint is available at:
  - `GET /api/v1/admin/health-dashboard/fair-use`
  - Includes `guards_enabled`, `tenant_tier`, `active_for_tenant`, and threshold values.

Audit evidence:
- Fair-use denials emit `llm_fair_use_denied` audit events with gate/limit/observed fields.

## Activation Criteria Before Enabling Fair-Use Guards

Do not enable `LLM_FAIR_USE_GUARDS_ENABLED=true` until all criteria are met:
1. At least 14 consecutive days of stable production traffic.
2. API error rate remains <= 1% over that window.
3. LLM request latency p95 remains within your SLO target for that window.
4. No unresolved incident involving tenant starvation or queue collapse.
5. Denial-rate simulation is reviewed with support/commercial messaging prepared.

Operational rollout sequence:
1. Keep guardrails OFF in production.
2. Enable in staging with realistic replay/load.
3. Review fair-use metrics + audit events for at least 7 days.
4. Enable in production at low-traffic window with active monitoring.
5. Reassess thresholds weekly for the first month.

## Cloud API Cost Claims Validation (2026-02-19)

Status: **partially valid; current code supports low incremental cost posture, but absolute fixed-dollar claims are not yet defensible.**

Validated in repository:
- AWS Cost Explorer is intentionally excluded from customer role policy (`cloudformation/valdrix-role.yaml`).
- CUR-first AWS ingestion path is implemented and CE access is blocked in adapter flow (`app/shared/adapters/factory.py`, `app/shared/adapters/aws_multitenant.py`).
- Many AWS zombie plugins can still call CloudWatch metrics when CUR-based signal is missing (`app/modules/optimization/adapters/aws/plugins/compute.py`, `app/modules/optimization/adapters/aws/plugins/database.py`, `app/modules/optimization/adapters/aws/plugins/network.py`, `app/modules/optimization/adapters/aws/plugins/storage.py`).
- GCP cost path uses BigQuery query jobs (`app/shared/adapters/gcp.py`), so query bytes scanned can create variable cost.
- Azure path uses Cost Management query APIs (`app/shared/adapters/azure.py`); cost posture should be described as provider-plan dependent, not universally zero.

Not validated for external claims:
- A universal statement like "`~$0.01/month` per account" across AWS/GCP/Azure.
- Broad competitor dollar comparisons without dated external benchmark methodology.
- A blanket "zero API cost across all platforms" statement.

Safe external wording:
- "Valdrics is CUR-first on AWS and avoids Cost Explorer by default."
- "The platform is engineered for low incremental API costs; actual customer-side cost varies with scan profile, CloudWatch fallback usage, and BigQuery bytes scanned."
- "Published dollar figures are based on measured tenant workloads and date-stamped provider pricing."

Provider references used for fact-check:
- AWS Cost Explorer pricing: https://aws.amazon.com/aws-cost-management/aws-cost-explorer/pricing/
- Amazon CloudWatch billing concepts: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch_billing.html
- Google BigQuery pricing: https://cloud.google.com/bigquery/pricing
- Azure Cost Management exports/queries guidance: https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports
