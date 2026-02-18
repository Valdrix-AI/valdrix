# Pricing Metric Model

Last updated: February 12, 2026

## Default Value Metric

Primary pricing metric for early SaaS packaging:

- Connected cloud scope (accounts/subscriptions/projects) by tier
- Feature tier access (for example: Cloud+, reconciliation, compliance exports)
- Plan-level operational limits (retention, backfill, scan frequency)

Reference implementation: `app/shared/core/pricing.py`.

## Plan Baseline

- `free`: permanent entry tier with strict limits and no credit card requirement.
- `starter`, `growth`, `pro`, `enterprise`: progressively higher scale and capability.

## Billing Event Mapping (Product to Billing)

| Product action | Billing impact |
| --- | --- |
| Plan selected/changed | Plan price + feature/limit envelope updates |
| Connection count growth beyond plan limits | Upgrade prompt / policy gate before overage |
| Cloud+ connector enablement | Feature gate by tier (for example Pro+) |
| Backfill window increase | Tier-gated limit check |
| Compliance export / advanced workflows | Tier-gated access |

## Guardrails

1. Pricing must not penalize customers for reducing waste.
2. Core allocation/reconciliation signals remain available at practical tiers.
3. Hard limits should fail with clear guidance, not silent degradation.
4. Tier checks must be deterministic and test-covered.
