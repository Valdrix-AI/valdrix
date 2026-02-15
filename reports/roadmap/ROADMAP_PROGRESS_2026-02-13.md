**12-Month Roadmap (Starting February 11, 2026)**

**Assumptions**
1. Goal: move from strong cloud optimization product to enterprise Cloud+ FinOps platform.
2. Team: 2 squads minimum (Data Platform, FinOps Intelligence) + shared frontend.
3. Cadence: monthly releases, quarterly outcome targets.

**Cross-Cutting Delivery Guardrails (All Quarters)**
1. Deterministic-first core: allocation, anomaly detection, reconciliation, and savings math remain rule/model based; LLM is used for summarization, explanation, and remediation guidance only.
2. Ingestion contracts: all connectors must be scheduled, idempotent, and schema-versioned with explicit replay/backfill behavior.
3. Unified normalized model: all providers (cloud + Cloud+) emit a single internal shape: provider, account/subscription/project, service, resource_id, usage_amount, usage_unit, cost, currency, timestamp, tags/labels.
4. Operational loop: every detection path must support ownership + action (ticket/workflow/policy/notification), not dashboard-only visibility.
5. Persona separation: Engineering, Finance, Platform, and Leadership each get role-appropriate views and APIs.
6. Acceptance evidence: each epic closes only when code/tests pass and live acceptance metrics/SLOs are captured.

**Immediate Foundation Sprint (Next 7 Days)**
1. Epic: Licensing clarity (BSL + SaaS boundaries).
Acceptance criteria:
- Publish a single licensing page with plain-English summary, exact BSL text, and FAQ.
- Explicitly define: allowed self-hosting/internal use, prohibited competitive hosted offering, production use, hosted service, change date, and change license.
- Add a customer-facing policy matrix: internal use, partner use, resale, and managed-service scenarios.

2. Epic: Tenancy architecture decision and enforcement baseline.
Acceptance criteria:
- Publish a tenancy ADR selecting one model (recommended: hybrid control plane + tenant-isolated data plane).
- Document enforcement controls: tenant scoping, key boundaries, and migration/isolation guarantees.
- Add testable tenant-isolation assertions for critical data paths.

3. Epic: Security and trust minimum bar.
Acceptance criteria:
- RBAC matrix is documented and enforced in API routes.
- Audit logs cover policy/rule/budget/configuration changes with actor + timestamp + before/after.
- Tenant data export and tenant delete workflows have executable runbooks.
- Baseline operational docs exist for retention, incident response, and service SLOs.

4. Epic: Packaging and pricing metric alignment.
Acceptance criteria:
- Default pricing metric is defined and implemented for early SaaS (connected account/subscription/project + tier limits).
- Billing events map to product actions without hidden coupling.
- Pricing guardrails avoid penalizing optimization behavior.

5. Epic: Open-core boundary definition.
Acceptance criteria:
- Clearly define which components are permissive (for example connectors/agents/SDKs) versus BSL (control plane/UI/policy engine).
- Contribution policy (CLA or DCO) is documented.
- License headers and repository docs match the chosen boundary model.

**Immediate Foundation Sprint Status (As of February 12, 2026)**
1. Licensing clarity (BSL + SaaS boundaries): `DONE`
- Evidence: `docs/licensing.md`, `README.md` license section updated.

2. Tenancy architecture decision and enforcement baseline: `DONE`
- Evidence: `docs/architecture/ADR-0001-tenancy-model.md`.

3. Security and trust minimum bar: `PARTIAL`
- Implemented: RBAC, audit logging/export, data retention policy, GDPR erasure endpoint.
- Evidence: `app/shared/core/auth.py`, `app/modules/governance/domain/security/audit_log.py`, `app/modules/governance/api/v1/audit.py`, `docs/policies/data_retention.md`, `docs/runbooks/tenant_data_lifecycle.md`.
- Remaining: production SLO evidence collection and periodic acceptance reporting.

4. Packaging and pricing metric alignment: `PARTIAL`
- Implemented: tier model + limits and free trial baseline in code.
- Evidence: `app/shared/core/pricing.py`, `docs/pricing_model.md`.
- Remaining: explicit usage-metering events in production billing pipeline and acceptance dashboards.

5. Open-core boundary definition: `DONE`
- Evidence: `docs/open_core_boundary.md`, `CONTRIBUTING.md`.

**Q1 2026 (Feb-Mar): Data Trust Foundation**
1. Epic: Canonical billing ledger + FOCUS-ready normalization.
Acceptance criteria:
- Add canonical fields and mappings in ingestion model (`app/models/cloud.py`) and adapters (`app/shared/adapters/*`).
- 99%+ of ingested rows map to canonical charge categories; unmapped rows are explicitly flagged.
- Cost APIs expose data quality metadata (`app/modules/reporting/api/v1/costs.py`).

2. Epic: Reconciliation v1 (real discrepancy detection, not placeholder summary).
Acceptance criteria:
- Replace placeholder logic in `app/modules/reporting/domain/reconciliation.py` with source-vs-source delta checks.
- Daily/monthly reconciliation report includes discrepancy %, impacted services, and confidence.
- Alerting fires when variance exceeds defined threshold (for example 1%).

3. Epic: Commitment optimization v1.
Acceptance criteria:
- Remove heuristic baseline logic from `app/modules/optimization/domain/service.py` and `app/modules/optimization/domain/strategies/compute_savings.py`.
- Recommendations include break-even, confidence, and expected savings range.
- Backtest harness shows prediction error within agreed tolerance on historical data.

4. Epic: Ingestion source parity baseline.
Acceptance criteria:
- Source coverage includes AWS CUR, Azure Cost Management exports, GCP Billing export (BigQuery), and SaaS invoice/CSV ingestion.
- All ingestion jobs are idempotent, schema-versioned, and support bounded replay/backfill windows.
- Daily completeness/recency SLI is reported per source and alerts on missed ingestion windows.

**Q2 2026 (Apr-Jun): Financial Productization**
1. Epic: Chargeback/showback product APIs + workflows.
Acceptance criteria:
- Rule CRUD + simulation endpoints for allocation published (extending `app/modules/reporting/domain/attribution_engine.py`).
- Monthly allocation outputs by team/product/environment.
- Pilot tenants reach >=90% allocation coverage of spend.

2. Epic: Unit economics layer.
Acceptance criteria:
- Support configurable unit-cost KPIs (cost per request, cost per workload, cost per customer).
- New reporting endpoints and dashboard views for unit cost trends.
- Unit-cost anomalies detected and routed through existing alerting path.

3. Epic: Ingestion completeness and backfill.
Acceptance criteria:
- Date-range backfill and replay for CUR/azure/gcp adapters.
- Idempotent rerun behavior verified for overlapping ingestion windows.
- Ingestion SLAs defined and monitored.

4. Epic: Deterministic anomaly detection v1.
Acceptance criteria:
- Detect daily cost deltas per service/account with rolling baseline + seasonality.
- Output includes service, account, probable cause classification, and confidence score.
- Alert routing supports severity thresholds and suppression windows.

5. Epic: Waste and rightsizing detection v1.
Acceptance criteria:
- Detect idle compute, over-provisioned resources, orphaned assets, and unattached storage.
- Recommendation payload includes estimated savings range, confidence, and required action.
- Results are reproducible from deterministic inputs (no LLM dependency for detection).

6. Epic: Architectural inefficiency detection v1.
Acceptance criteria:
- Detect overbuilt availability patterns, unjustified multi-zone deployment, and duplicated non-production environments from deterministic infrastructure and billing signals.
- Findings include probable cause, confidence, expected savings range, and risk label for remediation.
- Findings can be routed into policy/approval workflows and owner-assigned action queues.

**Q2 2026 Status (As of February 13, 2026)**
1. Chargeback/showback product APIs + workflows: `DONE`
- Evidence: allocation rule engine + CRUD/simulation/apply APIs + coverage KPIs in `app/modules/reporting/domain/attribution_engine.py`, `app/modules/reporting/api/v1/attribution.py`, and `app/modules/reporting/api/v1/costs.py`.

2. Unit economics layer: `DONE`
- Evidence: unit economics settings + KPI endpoints and Ops dashboard monitoring in `app/modules/reporting/api/v1/costs.py` and `dashboard/src/routes/ops/+page.svelte`.

3. Ingestion completeness and backfill: `DONE`
- Evidence: bounded backfill/replay job windows, ingestion SLA endpoint, provider recency evidence, and Ops KPI dashboard wiring in `app/modules/governance/domain/jobs/handlers/costs.py`, `app/modules/reporting/api/v1/costs.py`, and `dashboard/src/routes/ops/+page.svelte`.

4. Deterministic anomaly detection v1: `DONE`
- Evidence: `app/modules/reporting/domain/anomaly_detection.py`, `/api/v1/costs/anomalies`, scheduler/job wiring, and tests.

5. Waste and rightsizing detection v1: `DONE`
- Evidence: deterministic recommendation shaping in `app/modules/optimization/domain/waste_rightsizing.py`, integrated in zombie scan payload via `waste_rightsizing`, with targeted tests.

6. Architectural inefficiency detection v1: `DONE`
- Evidence: deterministic findings in `app/modules/optimization/domain/architectural_inefficiency.py`, integrated in zombie scan payload via `architectural_inefficiency`, with targeted tests.

**Q3 2026 (Jul-Sep): Enterprise Close + Cloud+ Expansion**
1. Epic: Reconciliation v2 with close workflow.
Acceptance criteria:
- Month-end close package generation (JSON/CSV + audit trail) is reproducible.
- Preliminary vs final lifecycle is operationally enforced.
- Restatement history is queryable and exportable.

2. Epic: Cloud+ scope expansion.
Acceptance criteria:
- Add at least 2 non-IaaS spend connectors (SaaS/license or similar) through adapter architecture (`app/shared/adapters/factory.py`).
- Unified reporting combines cloud + non-cloud costs.
- Same attribution/reconciliation flow works on Cloud+ sources.

3. Epic: Carbon assurance v2.
Acceptance criteria:
- Carbon outputs in `app/modules/reporting/domain/calculator.py` include factor source/version/timestamp metadata.
- Methodology versioning and reproducibility checks are implemented.
- Carbon reports are auditable for enterprise compliance reviews.

4. Epic: Governance and policy workflows.
Acceptance criteria:
- Support policy rules for budget/usage guardrails (including approval-required classes such as GPU).
- Policy evaluation emits actionable outcomes (allow, warn, block, escalate).
- Violations are logged with audit evidence and owner attribution.

5. Epic: Integrations and action automation.
Acceptance criteria:
- Integrate with Slack/Teams for alerts and approvals.
- Integrate with Jira for automatic issue creation from findings.
- Integrate with GitHub/GitLab/CI for workflow-triggered remediation and evidence links.

**Q3 2026 Status (As of February 13, 2026)**
1. Reconciliation v2 with close workflow: `DONE (ENGINEERING)` / `PENDING PRODUCTION ACCEPTANCE EVIDENCE`
- Evidence: deterministic close package + integrity hash + JSON/CSV export + restatement export APIs in `app/modules/reporting/domain/reconciliation.py` and `app/modules/reporting/api/v1/costs.py`, plus Ops workflow controls in `dashboard/src/routes/ops/+page.svelte`.
- Remaining: execute and capture live month-end close acceptance runs in production.

2. Cloud+ scope expansion: `DONE (ENGINEERING)` / `PENDING PRODUCTION ACCEPTANCE EVIDENCE`
- Evidence: SaaS/license connection models with `connector_config` (`app/models/saas_connection.py`, `app/models/license_connection.py`), native connector support for Stripe/Salesforce/Microsoft 365 (`app/shared/adapters/saas.py`, `app/shared/adapters/license.py`), and connection setup/verification APIs (`app/modules/governance/api/v1/settings/connections.py`) with targeted coverage.
- Remaining: run live tenant ingestion acceptance across native connector paths and capture recency/completeness evidence.

3. Carbon assurance v2: `DONE (ENGINEERING)` / `PENDING PRODUCTION ACCEPTANCE EVIDENCE`
- Evidence: multi-cloud methodology/factor metadata with deterministic reproducibility checks in `app/modules/reporting/domain/calculator.py`, surfaced through carbon APIs and covered by calculator/carbon test suites.
- Remaining: collect periodic production assurance snapshots and attach to compliance evidence pack.

4. Governance and policy workflows: `DONE (ENGINEERING)` / `PENDING PRODUCTION ACCEPTANCE EVIDENCE`
- Evidence: deterministic policy engine decisions (`allow/warn/block/escalate`) in `app/modules/governance/domain/security/remediation_policy.py`, policy preview and execution gating in `app/modules/optimization/api/v1/zombies.py`, escalation workflow state including `pending_approval`, and audit logging in `app/modules/governance/domain/security/audit_log.py`.
- Remaining: complete live approval/escalation UAT for each tier and capture operator run evidence.

5. Integrations and action automation: `DONE (ENGINEERING)` / `PENDING PRODUCTION ACCEPTANCE EVIDENCE`
- Implemented: Slack + Jira policy/remediation notification flows and configuration/test endpoints in `app/modules/governance/api/v1/settings/notifications.py`, `app/modules/notifications/domain/slack.py`, and `app/modules/notifications/domain/jira.py`.
- Implemented: GitHub Actions, GitLab CI, and generic CI webhook workflow dispatch for policy/remediation events with deterministic evidence links in `app/modules/notifications/domain/workflows.py` and `app/shared/core/notifications.py`, wired into remediation execution flow in `app/modules/optimization/domain/remediation.py`.
- Implemented: tenant-scoped workflow integration settings (encrypted tokens + API + settings UI + test endpoint), with environment-based fallback for self-hosted operator mode.
- Implemented: strict SaaS integration mode (`SAAS_STRICT_INTEGRATIONS`) to disable env-based Slack/Jira/workflow dispatchers while preserving tenant-scoped execution paths.
- Implemented: acceptance-evidence capture/list APIs that persist integration test traces to immutable audit logs (`POST/GET /api/v1/settings/notifications/acceptance-evidence*`).
- Implemented: Ops Center now surfaces latest integration acceptance runs (run-level status + channel outcomes) and can trigger new acceptance captures with per-channel + fail-fast controls from tenant-scoped UI in `dashboard/src/routes/ops/+page.svelte`.
- Remaining: execute and archive live production runs for each enabled target per tenant.

**Q4 2026 (Oct-Dec): Scale, Procurement, and Proof**
1. Epic: Enterprise packaging hardening.
Acceptance criteria:
- Full SSO/SCIM onboarding flow production-ready.
- Compliance export pack (controls, evidence, audit logs) generated on demand.
- Security/tenant isolation verification passes at enterprise test depth.

2. Epic: Performance and reliability scale-up.
Acceptance criteria:
- 10x ingestion volume load tests pass.
- Dashboard/reporting p95 latency meets target under load.
- Scheduled job reliability meets quarterly SLO.

3. Epic: Commercial proof system.
Acceptance criteria:
- Standardized “savings realized vs opportunity” report per tenant.
- Design partner cohort validates measurable realized savings over 90 days.
- Close/reconciliation + realized savings evidence supports procurement cycles.

4. Epic: Cloud+ domain expansion beyond IaaS and SaaS basics.
Acceptance criteria:
- Add internal platform and private/hybrid infrastructure spend domains through the same normalized pipeline.
- Apply the same allocation/reconciliation/forecast flow to expanded Cloud+ sources.
- Coverage and quality metrics are reported consistently across all domains.

5. Epic: Persona-specific product experience hardening.
Acceptance criteria:
- Engineering, Finance, Platform, and Leadership workflows have distinct default views and API payloads.
- Role-specific KPIs and actions are validated in UAT with representative users.
- Cross-persona handoff workflows (detect -> assign -> act -> verify) are documented and measurable.

**Public V1 Scope (Minimum Serious FinOps Platform)**
1. Multi-cloud ingestion (AWS CUR, Azure exports, GCP BigQuery billing export) + Cloud+ connectors (SaaS/license/manual feeds).
2. Canonical normalization model and data quality gates.
3. Allocation engine with rules, simulation, and coverage KPIs.
4. Deterministic anomaly + waste/rightsizing + architectural inefficiency detection.
5. Action integrations (Slack/Teams + Jira + GitHub/GitLab/CI).
6. Policy engine for budget/guardrail enforcement.
7. Clear licensing page (BSL terms + FAQ) and tenancy/security baseline docs.

**Dependencies (critical path)**
1. Q1 ledger/reconciliation must land before Q2 chargeback and unit economics.
2. Q2 ingestion/backfill must land before Q3 close workflow and Cloud+ unification.
3. Q3 enterprise-grade trust outputs must land before Q4 procurement proof motions.

If you want, I can convert this into a sprint-ready backlog with issue titles, story points, and owner mapping per epic.
