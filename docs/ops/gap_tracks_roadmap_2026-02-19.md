# Gap Tracks Roadmap (Execution Only, Not Marketing)

Date created: 2026-02-19  
Program window: 2026-03-02 to 2026-09-30

This roadmap converts the current competitive-parity gaps into delivery tracks with engineering gates.  
These tracks are internal execution plans and must not be used as external claims until each exit gate is passed.

## Feedback reconciliation (2026-02-19)

The latest strategic feedback includes several recommendations that are already implemented in this repo.
Use the table below as the source of truth before opening new work items.

| Recommendation from feedback | Current repo status | Decision |
|---|---|---|
| Add Cloudflare adapter for dashboard | Implemented (`dashboard/svelte.config.js`, `dashboard/package.json`) | No new work |
| Add CSP `frame-ancestors 'none'` | Implemented backend + dashboard CSP (`app/shared/core/middleware.py`, `dashboard/svelte.config.js`) | No new work |
| Rename free trial to permanent free tier | Implemented (`PricingTier.FREE`) | No new work |
| BYOK on all paid tiers with no discount | Implemented in tier config and pricing copy guardrails | Keep policy; monitor fair-use |
| Keep Cost Explorer removed/blocked | Implemented + CI guardrails (`tests/unit/core/test_competitive_guardrails.py`) | Continue enforcement |
| Add Paystack USD support | Implemented with `NGN` default + feature-gated `USD` checkout (`app/modules/billing/domain/billing/paystack_billing.py`, `app/modules/billing/api/v1/billing.py`) | No new work |
| Market “zero API cost” as absolute | Not evidence-backed as an absolute claim | Keep as cost-minimized architecture claim |

## 90-day execution overlay (updated)

This is the practical delivery path from current state, aligned with existing implementation.

### Weeks 1-2: Launch hardening
- Close high-priority security hygiene items:
  - Standardize production-safe error responses (prevent internal detail leakage).
  - Finalize encryption key lifecycle/TTL policy and document runbook.
- Add API response compression middleware and measure p95 impact before/after.
- Lock marketing copy to evidence-backed/qualified claims only.

Execution update (2026-02-19):
- Implemented API GZip compression middleware (`app/main.py`).
- Implemented 5xx HTTP error-message sanitization for production/staging (`app/main.py`).
- Implemented configurable encryption key-cache policy:
  - `ENCRYPTION_KEY_CACHE_TTL_SECONDS`
  - `ENCRYPTION_KEY_CACHE_MAX_SIZE`
  (`app/shared/core/config.py`, `app/shared/core/security.py`).
- Implemented app entrypoint modularization slice:
  - moved lifecycle/health route registration and API router registry into
    `app/shared/core/app_routes.py`
  - reduced `app/main.py` from 558 to 477 lines.
- Implemented DB session backend-detection hardening (fail-closed on unresolved backend):
  - added layered backend resolution in `app/shared/db/session.py`
  - unknown backend now keeps `rls_context_set=False` and emits explicit security logs.

### Weeks 3-4: Billing currency expansion
- Design and implement Paystack currency mode:
  - Add explicit checkout currency strategy (`NGN` default, `USD` feature-gated).
  - Add tier subunit config for supported currencies.
  - Add webhook reconciliation tests for multi-currency events.
- Exit criteria:
  - End-to-end checkout + renewal pass in sandbox for both enabled currencies.

Execution update (2026-02-19):
- Implemented checkout currency request handling (`/api/v1/billing/checkout`).
- Implemented Paystack `NGN` default + feature-gated `USD` support:
  - `PAYSTACK_DEFAULT_CHECKOUT_CURRENCY`
  - `PAYSTACK_ENABLE_USD_CHECKOUT`
  (`app/modules/billing/api/v1/billing.py`, `app/modules/billing/domain/billing/paystack_billing.py`, `app/shared/core/config.py`).

### Weeks 5-8: Core differentiation depth
- Execute AUTO-1 and K8S-1 milestones from this roadmap:
  - Auto-scaling policy schema + simulation (dry-run only).
  - Kubernetes allocation foundation (namespace/workload cost model).
- Maintain guardrail tests for CE ban, discovery tier split, and GPU coverage.

Execution update (2026-02-19):
- Modularized settings connections API into focused modules (no compatibility façade):
  - `connections_helpers.py` (tier/tenant/limit policy helpers)
  - `connections_setup_aws_discovery.py`
  - `connections_azure_gcp.py`
  - `connections_cloud_plus.py`
  - slim router aggregator: `connections.py`

### Weeks 9-12: Enterprise readiness ramp
- Execute SOC2-1 and begin SOC2-2 preparation:
  - Control owner RACI, mock-audit, and gap closure artifacts.
  - Evidence cadence via compliance-pack + acceptance evidence capture.
- Keep these as roadmap-only until exit gates pass.

## Program rules
- Treat all items as `roadmap` until evidence is captured and reviewed.
- Require acceptance evidence in repo before moving status to `delivered`.
- Keep scope disciplined: finish one thin vertical slice per track before broadening.

## Track 1: SOC2 Audit Program

Objective:
- Move from “controls-ready” to auditable SOC2 program with repeatable evidence production.

Current baseline:
- Controls and audit logging exist (`docs/SOC2_CONTROLS.md`, `app/modules/governance/domain/security/audit_log.py`).
- Compliance export bundle exists (`GET /api/v1/audit/compliance-pack`).

Milestones:
1. SOC2-1: Audit readiness closure (2026-03-02 to 2026-03-31)
   - Finalize control owner RACI.
   - Close documented gaps (access removal process, centralized security monitoring, formal incident process artifacts).
   - Run internal mock audit and capture findings.
2. SOC2-2: Type I audit execution (2026-04-01 to 2026-05-15)
   - Freeze scope and control set.
   - Provide evidence package for auditor sampling.
   - Resolve findings and publish remediation log.
3. SOC2-3: Type II operating period readiness (2026-05-16 to 2026-09-30)
   - Automate monthly evidence capture cadence.
   - Track exceptions and control drift via quarterly review.

Exit gate:
- Type I attestation complete and Type II evidence cadence running for at least 1 full month.

## Track 2: Auto-Scaling Capability

Objective:
- Deliver safe, policy-governed auto-scaling actions that reduce waste without introducing reliability risk.

Guardrails:
- Start with `recommendation + dry-run` mode.
- Require per-tenant opt-in and explicit safety policy.
- Keep rollback and auditability mandatory.

Milestones:
1. AUTO-1: Policy and simulation layer (2026-03-02 to 2026-04-10)
   - Add scaling policy schema (min/max bounds, cooldown, blackout windows, approval mode).
   - Add simulation endpoint producing “would-scale” decisions with projected savings and risk.
2. AUTO-2: Canary automation (2026-04-11 to 2026-06-15)
   - Execute limited auto-actions for opted-in canary tenants.
   - Add rollback hooks and per-action audit events.
   - Add SLO protections (error budget and guard conditions).
3. AUTO-3: Production rollout (2026-06-16 to 2026-09-30)
   - Expand provider/resource coverage from initial scope.
   - Publish operational runbook and escalation path.

Exit gate:
- 30-day canary window with no critical incidents, positive net savings, and auditable rollback coverage.

## Track 3: Deeper Kubernetes Cost Depth

Objective:
- Move from basic Kubernetes visibility to workload-level cost allocation and optimization depth.

Scope strategy:
- Deliver by depth layers: allocation fidelity first, optimization second, automated actions last.

Milestones:
1. K8S-1: Allocation foundation (2026-03-02 to 2026-04-20)
   - Normalize cluster/workload identity model.
   - Add namespace/workload cost allocation with shared-cost split policy.
   - Validate against cloud billing sources and cluster telemetry.
2. K8S-2: Optimization depth (2026-04-21 to 2026-07-15)
   - Add request-vs-usage inefficiency detection per workload.
   - Add idle workload and overprovision signals (CPU/memory, node pool utilization).
   - Add recommendation scoring with confidence and risk class.
3. K8S-3: Governance and remediation path (2026-07-16 to 2026-09-30)
   - Add approval-based remediation suggestions (HPA/VPA-safe recommendations first).
   - Add exportable evidence for savings and risk outcomes.

Exit gate:
- Workload-level (namespace + deployment/statefulset) allocation and recommendation quality validated on production-like tenants.

## Cross-track operating cadence
- Weekly execution review: Monday 09:00 UTC.
- Monthly evidence checkpoint: first business day of each month.
- Status labels: `planned`, `in_progress`, `blocked`, `delivered`.

## Reporting template (use in weekly update)
- Track / milestone
- Status
- Delivered this week
- Risks / blockers
- Next 7 days
- Evidence link(s)

## Claim policy
- Do not publish “parity achieved” or “enterprise-ready” statements for these tracks until exit gates are met.
- External messaging must reference only evidence-backed claims from `docs/ops/competitive_parity_evidence_2026-02-19.md`.
