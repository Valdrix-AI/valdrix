# Landing Capability to Backend Trace Matrix (2026-02-28)

## Purpose
Map each public landing capability claim to active backend API families and implementation modules so marketing copy stays aligned with shippable product surface.

## Source of Truth
- Landing capability cards: `dashboard/src/lib/components/LandingHero.svelte` (`BACKEND_CAPABILITY_PILLARS`)
- API prefix registry: `app/shared/core/app_routes.py` (`register_api_routers`)
- Router implementations: `app/modules/**/api/v1/*.py`

## Capability Trace
| Landing capability | Primary API families (prefix + route family) | Core backend modules |
| --- | --- | --- |
| Cost Intelligence and Forecasting | `/api/v1/costs` (`/`, `/breakdown`, `/forecast`, `/anomalies`, `/unit-economics`, `/reconciliation/*`), `/api/v1/attribution` (`/rules`, `/simulate`, `/apply`, `/coverage`), `/api/v1/usage`, `/api/v1/currency` | `app/modules/reporting/api/v1/costs.py`, `app/modules/reporting/domain/anomaly_detection.py`, `app/shared/analysis/forecaster.py`, `app/modules/reporting/api/v1/attribution.py`, `app/modules/reporting/api/v1/usage.py`, `app/modules/reporting/api/v1/currency.py` |
| GreenOps Execution | `/api/v1/carbon` (`/`, `/budget`, `/intensity`, `/schedule`, `/factors*`), `/api/v1/settings/carbon` | `app/modules/reporting/api/v1/carbon.py`, `app/modules/reporting/domain/budget_alerts.py`, `app/modules/reporting/domain/carbon_factors.py`, `app/modules/governance/api/v1/settings/carbon.py`, `app/shared/analysis/carbon_data.py` |
| Cloud Hygiene and Remediation | `/api/v1/zombies` (scan/request/approve/execute/plan), `/api/v1/strategies` (RI/SP recommendations/backtest/apply), `/api/v1/enforcement/actions/*`, `/api/v1/settings/safety` | `app/modules/optimization/api/v1/zombies.py`, `app/modules/optimization/domain/remediation.py`, `app/modules/optimization/api/v1/strategies.py`, `app/modules/enforcement/api/v1/actions.py`, `app/modules/governance/api/v1/settings/safety.py` |
| SaaS and ITAM License Control | `/api/v1/settings/connections/saas*`, `/api/v1/settings/connections/license*`, `/api/v1/settings/connections/platform*`, `/api/v1/settings/connections/hybrid*` | `app/modules/governance/api/v1/settings/connections_cloud_plus.py`, `app/shared/connections/saas.py`, `app/shared/connections/license.py`, `app/shared/adapters/license.py`, `app/shared/adapters/license_vendor_ops.py`, `app/modules/optimization/domain/license_governance.py` |
| Financial Guardrails | `/api/v1/enforcement/gate/*`, `/api/v1/enforcement/policies`, `/api/v1/enforcement/budgets`, `/api/v1/enforcement/credits`, `/api/v1/enforcement/approvals/*`, `/api/v1/enforcement/reservations/*`, `/api/v1/enforcement/ledger`, `/api/v1/enforcement/exports/*` | `app/modules/enforcement/api/v1/enforcement.py`, `app/modules/enforcement/api/v1/policy_budget_credit.py`, `app/modules/enforcement/api/v1/approvals.py`, `app/modules/enforcement/api/v1/reservations.py`, `app/modules/enforcement/api/v1/ledger.py`, `app/modules/enforcement/api/v1/exports.py`, `app/modules/enforcement/domain/service.py` |
| Savings Proof for Leadership | `/api/v1/savings/*`, `/api/v1/leaderboards`, `/api/v1/leadership/*`, `/api/v1/costs/acceptance/kpis` | `app/modules/reporting/api/v1/savings.py`, `app/modules/reporting/domain/savings_proof.py`, `app/modules/reporting/domain/realized_savings.py`, `app/modules/reporting/api/v1/leaderboards.py`, `app/modules/reporting/api/v1/leadership.py`, `app/modules/reporting/domain/commercial_reports.py` |
| Operational Integrations | `/api/v1/settings/notifications*`, `/api/v1/jobs/*` | `app/modules/governance/api/v1/settings/notifications.py`, `app/modules/governance/api/v1/jobs.py`, `app/modules/notifications/domain/slack.py`, `app/modules/notifications/domain/teams.py`, `app/modules/notifications/domain/jira.py`, `app/modules/notifications/domain/email_service.py` |
| Security and Identity | `/scim/v2/*`, `/api/v1/settings/identity*`, `/api/v1/public/sso/discovery`, `/api/v1/audit/*` | `app/modules/governance/api/v1/scim.py`, `app/modules/governance/api/v1/settings/identity.py`, `app/modules/governance/api/v1/public.py`, `app/modules/governance/api/v1/audit_access.py`, `app/modules/governance/api/v1/audit_evidence.py`, `app/modules/governance/api/v1/audit_compliance.py` |

## Alignment Rules
1. A landing capability claim must map to at least one registered API family in `register_api_routers`.
2. If an API family is deprecated or renamed, landing copy for that capability must be reviewed in the same change.
3. If a new cross-functional capability ships (for example procurement or contract governance), add it to both `BACKEND_CAPABILITY_PILLARS` and this matrix in the same PR.
4. Any KPI/claim shown on landing must remain directional unless backed by tenant-validated production baselines.
