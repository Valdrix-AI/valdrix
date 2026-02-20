# Valdrix Roadmap (Internal)

Last updated: **February 20, 2026**

Progress archive (shipped work + evidence):
- `reports/roadmap/ROADMAP_PROGRESS_2026-02-20.md`
- `reports/roadmap/ROADMAP_PROGRESS_2026-02-15.md`
- `reports/roadmap/ROADMAP_PROGRESS_2026-02-14.md`
- `reports/roadmap/ROADMAP_PROGRESS_2026-02-13.md`

## Delivery Guardrails (Always)
1. Deterministic-first core: allocation, anomaly detection, reconciliation, and savings math remain rule/model based; LLM is used for summarization/explanation/remediation guidance only.
2. Ingestion contracts: all connectors must be scheduled, idempotent, and schema-versioned with explicit replay/backfill behavior.
3. Unified normalized model: all sources (cloud + Cloud+) emit one internal shape: provider, account/subscription/project, service, resource_id, usage_amount, usage_unit, cost, currency, timestamp, tags/labels.
4. Operational loop: every detection path supports ownership + action (ticket/workflow/policy/notification), not dashboards-only.
5. Persona separation: Engineering, Finance, Platform, and Leadership get role-appropriate views and APIs.
6. Acceptance evidence: each epic closes only when code/tests pass and repeatable acceptance evidence is captured.

## Sprint Standard (How We Ship)
1. Pick one sprint goal with crisp acceptance criteria.
2. Review existing implementation patterns first (avoid duplication).
3. Implement end-to-end (API + domain + persistence) with security, performance, and tenancy isolation in mind.
4. Add targeted tests for happy paths and failure paths.
5. Run the focused tests for the changed modules.
6. Capture acceptance evidence (Ops automation where possible) and record pointers in the progress archive.

## 12-Month Roadmap (High-Level)

### Q1 2026: Data Trust Foundation
1. Canonical billing ledger + FOCUS-ready normalization.
2. Reconciliation v1 (real discrepancy detection, not placeholder summaries).
3. Commitment optimization v1 (break-even, confidence, expected savings range).
4. Ingestion source parity baseline (AWS CUR, Azure exports, GCP BigQuery billing export, SaaS/license feeds) with replay/backfill and SLIs.

### Q2 2026: Financial Productization
1. Chargeback/showback product APIs + workflows (rules + simulation + coverage KPIs).
2. Unit economics layer (configurable unit-cost KPIs + anomaly routing).
3. Ingestion completeness and backfill (idempotent overlap windows, SLAs, monitoring).
4. Deterministic anomaly detection v1.
5. Waste/rightsizing detection v1.
6. Architectural inefficiency detection v1.

### Q3 2026: Enterprise Close + Cloud+ Expansion
1. Reconciliation v2 close workflow (JSON/CSV + audit trail, preliminary vs final lifecycle).
2. Cloud+ scope expansion (SaaS/license/platform/hybrid connectors through the same pipeline).
3. Carbon assurance v2 (factor versioning, auditability, reproducibility).
4. Governance/policy workflows (allow|warn|block|escalate + approval flow).
5. Integrations/action automation (Slack/Teams, Jira, GitHub/GitLab/CI webhooks).

### Q4 2026: Scale, Procurement, and Proof
1. Enterprise packaging hardening (SSO/SCIM, compliance exports, isolation verification).
2. Performance and reliability scale-up (10x ingestion volume, p95 dashboard targets, job SLOs).
3. Commercial proof system (savings realized vs opportunity + close package + procurement bundle).
4. Cloud+ domain expansion beyond IaaS/SaaS basics (platform + hybrid).
5. Persona-specific product experience hardening.

## Latest Sprint Shipped
Full detail and evidence pointers live in `reports/roadmap/ROADMAP_PROGRESS_2026-02-20.md`.

Highlights:
- Acceptance evidence capture closure refreshed with full pass (`26/26`) using enterprise-tier sign-off run (`reports/acceptance/20260220T160636Z/manifest.json`).
- SSO federation operator smoke + publish path validated end-to-end (tenant-scoped discovery, admin validation, audit evidence publish).
- Enterprise close workflow v3 (invoice-linked reconciliation) + Ops dashboard workflow UX.
- Enterprise identity hardening (SSO enforcement diagnostics, SCIM token flows, SCIM group mappings).
- Performance scale evidence capture (load-test p95/error-rate + ingestion persistence benchmarks) + compliance pack inclusion.
- Reliability evidence capture (job SLO + backlog snapshot) + compliance pack inclusion.
- Commercial proof automation (leadership KPI exports + quarterly templates + realized savings evidence).
- Commercial proof drilldowns (savings proof by strategy type + remediation action) + compliance pack export.
- Workflow integrations v2 (Microsoft Teams tenant-scoped notifications + evidence capture + settings UI).
- Real SSO federation v1 (tenant-scoped Supabase SSO bootstrap via domain/provider_id + callback flow + identity settings UI/API).

## Next Sprint Candidates (Pick 1)
1. Pick a new sprint goal (SSO federation v2 hardening shipped).

## Sprint Status (Current)
- Enterprise close workflow v3: implemented (invoice-linked reconciliation).
- Enterprise identity hardening v2: implemented (SCIM group mappings + Schemas endpoint + dashboard editor).
- Enterprise identity interop v3: implemented (SCIM Groups resources + membership-driven entitlement recompute).
- Enterprise identity interop v4: implemented (SCIM compatibility matrix + conformance tests).
- Enterprise identity interop v5: implemented (IdP reference configs + operator SCIM smoke test runner + audit-grade evidence capture + compliance pack inclusion).
- Performance and reliability scale-up v3: implemented (load-test evidence + ingestion persistence benchmarks + job SLO evidence).
- Performance and reliability scale-up v4: implemented (end-to-end ingestion soak evidence + partitioning validation + partition maintenance runbook + evidence bundle capture).
- Commercial proof system v3: implemented (savings proof drilldowns + quarterly templates + compliance pack exports).
- Cloud+ expansion (platform + hybrid native pulls) v1: implemented (ledger HTTP connectors + scheduled ingestion parity + tests).
- Cloud+ vendor-native connectors v2: implemented (Datadog + New Relic priced-usage platform pulls; OpenStack CloudKitty + VMware vCenter hybrid pulls; connector secrets + UI + tests).
- Persona-specific UX hardening v1: implemented (persona-first nav + persistent “show all” + tier gating polish).
- Performance CI gate v1: implemented (manual GitHub Action workflow dispatch using the load-test runner with thresholds).
- Workflow integrations v2: implemented (Teams channel support + policy notification actions + test endpoint + acceptance evidence + compliance export metadata).
- Real SSO federation v1: implemented (tenant-scoped discovery API + federated login start/callback + identity settings federation controls).
- Real SSO federation v2 hardening: implemented (operator validation endpoint + audit-grade evidence capture endpoints + smoke test runner + docs/tests).
- Acceptance sign-off bundle refresh (2026-02-20): implemented (full acceptance capture pass, SSO smoke publish pass, evidence archived in `reports/acceptance/20260220T160636Z`).
