# Valdrix Roadmap Progress Snapshot

Date: **2026-02-14**

This is a progress archive (what shipped + evidence pointers). For the previous snapshot, see:
- `reports/roadmap/ROADMAP_PROGRESS_2026-02-13.md`

## Completed (Engineering) Since 2026-02-13

### 1) FOCUS v1.3 Core Export (Compliance)
- Domain export: `app/modules/reporting/domain/focus_export.py`
- API: `app/modules/reporting/api/v1/costs.py` (`GET /api/v1/costs/export/focus`)
- Docs: `docs/compliance/focus_export.md`
- Tests: `tests/unit/api/v1/test_focus_export.py`

### 2) Compliance Pack Procurement Add-ons (Evidence Bundle v2)
- API: `app/modules/governance/api/v1/audit.py` (`GET /api/v1/audit/compliance-pack`)
- Savings proof domain: `app/modules/reporting/domain/savings_proof.py`
- Savings proof API: `app/modules/reporting/api/v1/savings.py`
- Close package domain: `app/modules/reporting/domain/reconciliation.py` (`generate_close_package`)
- Tests: `tests/unit/api/v1/test_audit_compliance_pack.py`, `tests/unit/reporting/test_savings_proof_api.py`
- UI: `dashboard/src/routes/audit/+page.svelte`

### 3) Cloud+ Currency Normalization (SaaS Native Connectors)
- Currency utility: `app/shared/core/currency.py` (`convert_to_usd`)
- SaaS adapter: `app/shared/adapters/saas.py` (Stripe/Salesforce conversion)
- FOCUS export currency alignment: `app/modules/reporting/domain/focus_export.py`
- Tests: `tests/unit/services/adapters/test_cloud_plus_adapters.py`

### 4) Automated Daily Acceptance Suite Capture (Operator)
- Job type: `app/models/background_job.py` (`acceptance_suite_capture`)
- Handler: `app/modules/governance/domain/jobs/handlers/acceptance.py`
- Orchestrator schedule: `app/modules/governance/domain/scheduler/orchestrator.py`
- Scheduler task: `app/tasks/scheduler_tasks.py`
- Docs: `docs/ops/acceptance_evidence_capture.md`
- Tests: `tests/unit/services/jobs/test_acceptance_suite_capture_handler.py`, `tests/unit/tasks/test_scheduler_tasks.py`, `tests/unit/governance/scheduler/test_orchestrator.py`
- Month-end close evidence: `app/modules/governance/domain/jobs/handlers/acceptance.py` (`acceptance.close_package_captured`), scheduled monthly via `app/tasks/scheduler_tasks.py` (payload set on day 1 UTC)

### 5) Unified Normalized Ingestion Shape (Resource/Usage Metadata)
Adds explicit `resource_id`, `usage_amount`, and `usage_unit` fields to Cloud+ adapter outputs and ensures the ingestion pipeline preserves them in `ingestion_metadata`.

- SaaS adapter: `app/shared/adapters/saas.py` (resource_id + usage fields for Stripe/Salesforce + feed pass-through)
- License adapter: `app/shared/adapters/license.py` (resource_id + usage fields for Microsoft 365 + feed pass-through)
- Ingestion normalization: `app/modules/governance/domain/jobs/handlers/costs.py` (fills defaults and injects provider)
- Persistence lineage: `app/modules/reporting/domain/persistence.py` (stores tags/resource/usage fields in `ingestion_metadata`)
- Tests: `tests/unit/services/adapters/test_cloud_plus_adapters.py`, `tests/governance/test_cost_persistence.py`, `tests/unit/governance/domain/jobs/handlers/test_cost_handlers.py`

### 6) FOCUS-Native Cost Ledger Fields (v1)
Promotes Cloud+ resource/usage metadata from `ingestion_metadata` into first-class ledger columns for queryability and export stability.

- Model: `app/models/cloud.py` (`CostRecord.resource_id`, `usage_amount`, `usage_unit`, `tags`)
- Persistence: `app/modules/reporting/domain/persistence.py` (writes/updates the new columns)
- FOCUS export: `app/modules/reporting/domain/focus_export.py` (uses `CostRecord.tags` first, falls back to `ingestion_metadata.tags`)
- Migration: `migrations/versions/f4a1b2c3d4e5_add_focus_native_fields_to_cost_records.py`
- Tests: `tests/unit/api/v1/test_focus_export.py`

### 7) Finance-Grade Realized Savings Evidence (v1)
Adds post-action ledger-delta realized savings computation and persistence for remediation actions.

- Model: `app/models/realized_savings.py` (`RealizedSavingsEvent`)
- Domain service: `app/modules/reporting/domain/realized_savings.py` (baseline vs measurement windows, finalized ledger only)
- API: `app/modules/reporting/api/v1/savings.py` (`POST /api/v1/savings/realized/compute`)
- Savings proof uses evidence when present: `app/modules/reporting/domain/savings_proof.py`
- Migration: `migrations/versions/a7b8c9d0e1f2_add_realized_savings_events.py`
- Tests: `tests/unit/reporting/test_realized_savings_v1.py`, `tests/unit/reporting/test_savings_proof_api.py`

### 8) Enterprise Close Workflow UAT Harness (Artifacts)
Extends the operator evidence bundle to include close artifacts and documents a repeatable month-end close run.

- Evidence script: `scripts/capture_acceptance_evidence.py` (captures close package JSON/CSV + restatements CSV)
- Docs: `docs/ops/acceptance_evidence_capture.md`, `docs/runbooks/month_end_close.md`

### 9) Realized Savings Automation + Exports (Procurement Evidence)
Adds finance-grade realized savings evidence exports and best-effort automation.

- API: `app/modules/reporting/api/v1/savings.py` (`GET /api/v1/savings/realized/events` JSON/CSV)
- Scheduler: `app/tasks/scheduler_tasks.py` (best-effort daily realized savings compute sweep)
- Compliance pack inclusion: `app/modules/governance/api/v1/audit.py` (`include_realized_savings=true`)
- Tests: `tests/unit/reporting/test_realized_savings_v1.py`, `tests/unit/api/v1/test_audit_compliance_pack.py`

### 10) Ledger Data-Quality KPIs in Acceptance Evidence
Adds ledger normalization + canonical mapping coverage metrics into the consolidated acceptance KPI payload.

- API: `app/modules/reporting/api/v1/costs.py` (`GET /api/v1/costs/acceptance/kpis`)
- UI: `dashboard/src/routes/ops/+page.svelte` (Acceptance KPI Evidence table reflects the new metrics)
- Tests: `tests/unit/api/v1/test_costs_endpoints.py`

### 11) Procurement Bundle Hardening (Docs + Evidence)
Hardens the procurement bundle by including key runbooks and licensing docs in the compliance pack and extending the operator evidence bundle with realized-savings exports.

- Compliance pack docs: `app/modules/governance/api/v1/audit.py` (adds runbooks + licensing docs into ZIP)
- Evidence script: `scripts/capture_acceptance_evidence.py` (adds realized savings JSON/CSV)
- Docs: `docs/ops/acceptance_evidence_capture.md`
- Tests: `tests/unit/api/v1/test_audit_compliance_pack.py`

### 12) Performance Evidence Capture + Compliance Pack Inclusion
Adds audit-grade load-test evidence capture and includes it in the compliance pack for procurement/performance sign-off.

- Audit event type: `app/modules/governance/domain/security/audit_log.py` (`performance.load_test_captured`)
- API: `app/modules/governance/api/v1/audit.py`
  - `POST /api/v1/audit/performance/load-test/evidence`
  - `GET /api/v1/audit/performance/load-test/evidence`
- Compliance pack: `app/modules/governance/api/v1/audit.py` (adds `performance_load_test_evidence.json`)
- Operator runner: `scripts/load_test_api.py` (`--publish` publishes evidence to the API)
- Evidence capture bundle: `scripts/capture_acceptance_evidence.py` (pulls performance evidence snapshots)
- Docs: `docs/ops/acceptance_evidence_capture.md`
- Tests: `tests/unit/api/v1/test_performance_evidence_endpoints.py`, `tests/unit/api/v1/test_audit_compliance_pack.py`

### 13) Deterministic Cost Anomaly Detection Hardening
Hardens anomaly detection execution and alert routing for production SaaS operation.

- Tier gating:
  - Job handler skips anomaly detection when `FeatureFlag.ANOMALY_DETECTION` is not enabled for the tenant tier: `app/modules/governance/domain/jobs/handlers/costs.py`
  - Scheduler only enqueues anomaly detection jobs when the tenant tier includes anomaly detection: `app/tasks/scheduler_tasks.py`
- Alert suppression:
  - Suppression fingerprint includes `day` to avoid cross-day suppression: `app/modules/reporting/domain/anomaly_detection.py`
- Action routing:
  - Emits a tenant-scoped workflow event `cost.anomaly_detected` when workflow dispatchers are configured: `app/modules/reporting/domain/anomaly_detection.py`
- Tests:
  - `tests/unit/modules/reporting/test_anomaly_detection.py`

### 14) Waste/Rightsizing Expansion Beyond Classic Zombies
Extends the deterministic rightsizing payload and scan aggregation to cover more practical FinOps waste classes (containers, serverless, and network hygiene) without dropping provider-specific categories.

- Aggregation:
  - Adds canonical buckets and mapping for Azure/GCP container + serverless + network categories: `app/modules/optimization/domain/service.py`
- Deterministic shaping:
  - Adds shaping rules for the new canonical buckets: `app/modules/optimization/domain/waste_rightsizing.py`
- Tests:
  - `tests/unit/modules/optimization/test_waste_rightsizing.py`
  - `tests/unit/optimization/test_zombie_service_audit.py`

### 15) Tenancy Isolation Verification Evidence (Enterprise)
Adds operator-capturable tenancy isolation evidence (audit-grade) and bundles it into the procurement compliance pack.

- Audit event type:
  - `tenancy.isolation_verification_captured`: `app/modules/governance/domain/security/audit_log.py`
- API:
  - `POST /api/v1/audit/tenancy/isolation/evidence`
  - `GET /api/v1/audit/tenancy/isolation/evidence`
  - `app/modules/governance/api/v1/audit.py`
- Compliance pack:
  - Includes `tenant_isolation_evidence.json`: `app/modules/governance/api/v1/audit.py`
- Operator tooling:
  - Runner: `scripts/verify_tenant_isolation.py` (`--publish` stores evidence)
  - Bundle capture: `scripts/capture_acceptance_evidence.py` (pulls evidence snapshots)
- Docs:
  - `docs/ops/acceptance_evidence_capture.md`
- Tests:
  - `tests/unit/api/v1/test_tenant_isolation_evidence_endpoints.py`
  - `tests/unit/api/v1/test_audit_compliance_pack.py`

### 16) Jira Incident Automation v1 (Cost Anomaly Issues)
Adds Jira incident creation for high-severity cost anomalies (tier-gated) to keep anomaly detection actionable in enterprise workflows.

- Jira templates:
  - `JiraService.create_cost_anomaly_issue`: `app/modules/notifications/domain/jira.py`
- Anomaly dispatch:
  - Creates Jira issues for `high|critical` anomalies when the tenant tier includes `FeatureFlag.INCIDENT_INTEGRATIONS`: `app/modules/reporting/domain/anomaly_detection.py`
- Tests:
  - `tests/unit/modules/reporting/test_anomaly_detection.py`

### 17) Carbon Assurance Evidence Capture (Audit-Grade)
Adds audit-grade carbon methodology/factor snapshots for reproducibility and procurement assurance.

- Snapshot generator:
  - `carbon_assurance_snapshot`: `app/modules/reporting/domain/calculator.py`
- Audit event type:
  - `carbon.assurance_snapshot_captured`: `app/modules/governance/domain/security/audit_log.py`
- API:
  - `POST /api/v1/audit/carbon/assurance/evidence`
  - `GET /api/v1/audit/carbon/assurance/evidence`
  - `app/modules/governance/api/v1/audit.py`
- Compliance pack:
  - Includes `carbon_assurance_evidence.json`: `app/modules/governance/api/v1/audit.py`
- Operator tooling:
  - `scripts/capture_carbon_assurance_evidence.py`
  - `scripts/capture_acceptance_evidence.py` (pulls evidence snapshots)
- Docs:
  - `docs/ops/acceptance_evidence_capture.md`
- Tests:
  - `tests/unit/api/v1/test_carbon_assurance_evidence_endpoints.py`
  - `tests/unit/api/v1/test_audit_compliance_pack.py`

### 18) Carbon Factors v2 Refresh Process (DB + Guardrails)
Adds DB-backed carbon factor sets so factor updates can be staged, validated, and auto-activated with audit-grade evidence.

- Models:
  - `app/models/carbon_factors.py` (`CarbonFactorSet`, `CarbonFactorUpdateLog`)
- Domain lifecycle manager:
  - `app/modules/reporting/domain/carbon_factors.py` (seed, stage, validate, auto-activate)
- API:
  - `app/modules/reporting/api/v1/carbon.py` (factor set list/stage/activate + audit-log snapshots)
- Migration:
  - `migrations/versions/b3c4d5e6f7a8_add_carbon_factor_sets.py`
- Tests:
  - `tests/unit/api/v1/test_carbon_factor_endpoints.py`

### 19) Enterprise Identity Hardening (SSO/SCIM Reliability)
Adds tenant identity onboarding diagnostics and safe SCIM token validation/rotation flows with audit logging.

- Model:
  - `app/models/tenant_identity_settings.py` (`TenantIdentitySettings`)
- API:
  - `app/modules/governance/api/v1/settings/identity.py`
    - `GET /api/v1/settings/identity/diagnostics`
    - `POST /api/v1/settings/identity/scim/test-token`
    - `POST /api/v1/settings/identity/rotate-scim-token`
- SCIM provisioning API:
  - `app/modules/governance/api/v1/scim.py`
- Audit events:
  - `app/modules/governance/domain/security/audit_log.py` (`identity.settings_updated`, `scim.token_rotated`)
- Tests:
  - `tests/unit/governance/settings/test_identity_settings.py`

### 20) Ingestion Persistence Performance Evidence (10x Readiness Signal)
Adds a repeatable ingestion-write benchmark evidence capture endpoint to support “10x ingestion” readiness sign-off.

- API:
  - `app/modules/governance/api/v1/audit.py`
    - `POST /api/v1/audit/performance/ingestion/persistence/evidence`
    - `GET /api/v1/audit/performance/ingestion/persistence/evidence`
- Operator runner:
  - `scripts/benchmark_ingestion_persistence.py` (`--publish` stores evidence)
- Tests:
  - `tests/unit/api/v1/test_ingestion_persistence_evidence_endpoints.py`

### 21) Leadership KPI Export Automation (Commercial Proof)
Adds procurement/leadership-friendly KPI exports (JSON/CSV) with audit-grade evidence capture.

- Domain:
  - `app/modules/reporting/domain/leadership_kpis.py`
- API:
  - `app/modules/reporting/api/v1/leadership.py`
    - `GET /api/v1/leadership/kpis` (json|csv)
    - `POST /api/v1/leadership/kpis/capture` (audit-grade evidence)
    - `GET /api/v1/leadership/kpis/evidence`
- Audit events:
  - `app/modules/governance/domain/security/audit_log.py` (`leadership.kpis_captured`)
- Tests:
  - `tests/unit/api/v1/test_leadership_kpis_endpoints.py`

### 22) Enterprise Identity UX Sprint (Dashboard Diagnostics + SCIM Token Test)
Surfaces identity onboarding diagnostics in the dashboard and adds a safe SCIM token test UI to reduce SSO/SCIM onboarding failures.

- UI:
  - `dashboard/src/lib/components/IdentitySettingsCard.svelte` (auto-load diagnostics + token test input)
- Tests:
  - `dashboard/src/lib/components/IdentitySettingsCard.svelte.test.ts`
- Docs:
  - `docs/integrations/sso.md`
  - `docs/integrations/scim.md`
- Ops:
  - `docs/ops/acceptance_evidence_capture.md` (updated evidence capture artifacts list)

### 23) Performance Scale Sprint v2 Enhancements (Backfill Stress + Benchmark Runs)
Extends performance evidence tooling for 10x scale validation and reduces ingestion hot-path overhead.

- Persistence performance:
  - `app/modules/reporting/domain/persistence.py` (skip adjustment checks for preliminary writes; run on FINAL only)

### 24) Commitment Optimization v2 (RI/SP/CUD Depth + Backtest Harness)
Expands commitment optimization beyond a single Savings Plan recommendation and adds a deterministic backtest endpoint.

- Feature flag: `FeatureFlag.COMMITMENT_OPTIMIZATION` (Growth+)
- Strategy expansion:
  - Provider-aware baseline commitment strategy: `app/modules/optimization/domain/strategies/baseline_commitment.py`
  - Strategy type expansion: `app/models/optimization.py` (`CUD`, `AZURE_RESERVATION`)
  - Default strategy seeds: `app/modules/optimization/domain/service.py` (`_seed_default_strategies`)
- Backtest endpoint:
  - `GET /api/v1/strategies/backtest`: `app/modules/optimization/api/v1/strategies.py`
- Tests:
  - `tests/unit/optimization/test_strategies_api.py`
  - `tests/unit/optimization/test_optimization_service.py`

### 25) Allocation Engine v2 (Audit Trail + Coverage/Unallocated Endpoints)
Hardens chargeback workflow by adding immutable audit events and filling the remaining API surface.

- Audit events: `app/modules/governance/domain/security/audit_log.py`
  - `attribution.rule_*`, `attribution.rules_applied`
- API:
  - Audit logging added to create/update/delete/simulate/apply: `app/modules/reporting/api/v1/attribution.py`
  - New endpoints:
    - `GET /api/v1/attribution/coverage`
    - `GET /api/v1/attribution/unallocated-analysis`
- Tests:
  - `tests/unit/api/v1/test_attribution_endpoints.py`

### 26) Enterprise Close Workflow v3 (Invoice-Linked Reconciliation)
Adds DB-backed provider invoices so month-end close can reconcile finalized ledger totals against the provider invoice.

- Model: `app/models/invoice.py` (`ProviderInvoice`)
- Domain:
  - Invoice CRUD + reconciliation summary in close package: `app/modules/reporting/domain/reconciliation.py`
- API:
  - `GET/POST/PATCH/DELETE /api/v1/costs/reconciliation/invoices`: `app/modules/reporting/api/v1/costs.py`
  - Close package now includes `invoice_reconciliation` when provider is scoped.
- Migration:
  - `migrations/versions/c6d7e8f9a0b1_add_provider_invoices_for_close_workflow.py`
- Dashboard:
  - Ops close workflow card renders invoice reconciliation summary and supports invoice upsert/delete: `dashboard/src/routes/ops/+page.svelte`
  - Close workflow provider selector includes Platform/Hybrid (Cloud+ parity): `dashboard/src/routes/ops/+page.svelte`
  - Close package CSV now includes invoice reconciliation section (when provider-scoped): `app/modules/reporting/domain/reconciliation.py`
- Tests:
  - `tests/unit/api/v1/test_invoice_reconciliation_endpoints.py`
- Evidence payload shape:
  - `app/modules/governance/api/v1/audit.py` (`IngestionPersistenceEvidencePayload` supports per-run metrics/backfill)
- Operator tooling:
  - `scripts/benchmark_ingestion_persistence.py` (`--backfill-runs`, run metrics, provider parameterization)
  - `scripts/load_test_api.py` (new `scale` profile for executive/performance endpoints)
- Tests:
  - `tests/unit/tasks/test_scheduler_tasks.py`
  - `tests/unit/services/jobs/test_acceptance_suite_capture_handler.py`

### 27) Quarterly Commercial Proof Report Templates (Commercial Proof v2)
Adds deterministic quarterly procurement templates (JSON/CSV) combining leadership KPIs and savings proof, with audit-grade evidence capture and compliance pack inclusion.

- Domain:
  - `app/modules/reporting/domain/commercial_reports.py`
- API:
  - `app/modules/reporting/api/v1/leadership.py`
    - `GET /api/v1/leadership/reports/quarterly` (json|csv)
    - `POST /api/v1/leadership/reports/quarterly/capture` (audit-grade evidence)
    - `GET /api/v1/leadership/reports/quarterly/evidence`
- Scheduler/automation:
  - `app/tasks/scheduler_tasks.py` (quarter-boundary `capture_quarterly_report` payload)
  - `app/modules/governance/domain/jobs/handlers/acceptance.py` (captures previous quarter evidence)
- Compliance pack:
  - `app/modules/governance/api/v1/audit.py` (`quarterly_commercial_proof_evidence.json`)
- Operator tooling:
  - `scripts/capture_acceptance_evidence.py` (captures quarterly JSON/CSV best-effort)
- Tests:
  - `tests/unit/api/v1/test_quarterly_commercial_report_endpoints.py`
  - `tests/unit/api/v1/test_audit_compliance_pack.py`

### 28) Commitment Optimization Engine Productionization (DB-Backed Strategies)
Removes prototype “dummy config” strategy execution and makes commitment optimization scans DB-backed and idempotent.

- Service hardening:
  - `app/modules/optimization/domain/service.py`
    - strategies loaded from DB (seeds a default compute savings plan strategy when empty)
    - per-scan idempotency: replaces existing OPEN recommendations per (tenant_id, strategy_id)
    - compute-only baseline aggregation (uses `canonical_charge_category=compute`)
    - daily-ledger support: converts daily buckets into hourly baseline for consistent commitment math
- Strategy cleanup:
  - `app/modules/optimization/domain/strategies/compute_savings.py` (removes legacy `min_hourly_spend` fallback)
- Tests:
  - `tests/unit/optimization/test_optimization_service.py`

### 29) SCIM Group Mappings (Enterprise RBAC/Persona)
Adds tenant-configurable SCIM group mappings so IdP groups can deterministically assign Valdrix `role` and optional default `persona` during provisioning (Enterprise identity hardening).

- Model:
  - `app/models/tenant_identity_settings.py` (`TenantIdentitySettings.scim_group_mappings`)
- Migration:
  - `migrations/versions/d8e9f0a1b2c3_add_scim_group_mappings.py`
- Identity settings API:
  - `app/modules/governance/api/v1/settings/identity.py` (GET/PUT includes `scim_group_mappings`, Enterprise-gated)
- SCIM provisioning:
  - `app/modules/governance/api/v1/scim.py` (applies mappings on `POST/PUT /scim/v2/Users`, supports `groups` payload)
  - `app/modules/governance/api/v1/scim.py` (adds `GET /scim/v2/Schemas` for IdP discovery)
- Dashboard:
  - `dashboard/src/lib/components/IdentitySettingsCard.svelte` (SCIM mapping editor)
- Docs:
  - `docs/integrations/scim.md` (group mapping guidance)
- Tests:
  - `tests/unit/governance/test_scim_api.py`
  - `tests/unit/governance/settings/test_identity_settings.py`
  - `dashboard/src/lib/components/IdentitySettingsCard.svelte.test.ts`

### 30) Job SLO Evidence Capture + Compliance Pack Inclusion (Reliability)
Adds audit-grade job reliability evidence capture (server-computed) so procurement/performance packs can include job success-rate and backlog (backpressure) signals.

- Domain:
  - `app/modules/governance/domain/jobs/metrics.py` (terminal-job SLO compute + backlog snapshot)
- Jobs API:
  - `app/modules/governance/api/v1/jobs.py` (`GET /api/v1/jobs/slo` uses shared compute)
- Audit evidence API:
  - `app/modules/governance/api/v1/audit.py`
    - `POST /api/v1/audit/jobs/slo/evidence`
    - `GET /api/v1/audit/jobs/slo/evidence`
- Compliance pack:
  - `app/modules/governance/api/v1/audit.py` now bundles `job_slo_evidence.json`
- Operator runbook + tooling:
  - `docs/ops/acceptance_evidence_capture.md`
  - `scripts/capture_acceptance_evidence.py` captures job SLO evidence into audit logs and downloads evidence snapshots
- Tests:
  - `tests/unit/api/v1/test_job_slo_evidence_endpoints.py`
  - `tests/unit/api/v1/test_audit_compliance_pack.py`

### 31) Savings Proof Drilldowns (Commercial Proof v3)
Adds drilldown views for “savings realized vs opportunity” so finance/procurement teams can trace savings proof by strategy category and remediation action.

- Domain:
  - `app/modules/reporting/domain/savings_proof.py` (`drilldown`, `render_drilldown_csv`)
  - Savings Proof provider parity expanded to include `platform|hybrid`.
- API:
  - `app/modules/reporting/api/v1/savings.py` (`GET /api/v1/savings/proof/drilldown`)
- Compliance pack:
  - `app/modules/governance/api/v1/audit.py` now bundles drilldowns:
    - `exports/savings-proof-drilldown-strategy-type.{json,csv}`
    - `exports/savings-proof-drilldown-remediation-action.{json,csv}`
- Dashboard:
  - `dashboard/src/routes/savings/+page.svelte` (drilldown selector + table)
- Tests:
  - `tests/unit/reporting/test_savings_proof_api.py`
  - `tests/unit/api/v1/test_audit_compliance_pack.py`

### 32) SCIM Groups v1 (Enterprise Identity Interop v3)
Adds optional SCIM Group resources so IdPs that manage membership via `/Groups` can provision group objects and memberships, with membership-driven entitlement recomputation using tenant-configured SCIM group mappings.

- Models:
  - `app/models/scim_group.py` (`ScimGroup`, `ScimGroupMember`)
- Migration:
  - `migrations/versions/e1f2a3b4c5d6_add_scim_groups_and_memberships.py`
- SCIM API:
  - `app/modules/governance/api/v1/scim.py`
    - `GET/POST/GET/PUT/PATCH/DELETE /scim/v2/Groups`
    - `GET /scim/v2/Schemas` now exposes both User and Group schemas
    - User resources include `groups` references based on stored memberships
    - Group membership updates recompute user entitlements deterministically
- Audit events:
  - `app/modules/governance/domain/security/audit_log.py` (`scim.group_created`, `scim.group_updated`, `scim.group_deleted`)
- Docs:
  - `docs/integrations/scim.md` (Groups support + supported operations)
- Tests:
  - `tests/unit/governance/test_scim_api.py` (Groups lifecycle + membership-driven entitlement recompute)

### 33) SCIM IdP Interop v4 (Compatibility Matrix + Conformance Tests)
Adds an explicit SCIM interoperability checklist and expands conformance tests to cover common IdP payload variants.

- Docs:
  - `docs/integrations/scim_compatibility.md` (supported endpoints + patch variants)
  - `docs/integrations/scim.md` (links to compatibility matrix)
- Tests:
  - `tests/unit/governance/test_scim_api.py` (ResourceTypes includes Groups; PATCH variants for Users/Groups)

### 34) Performance Scale Sprint v4 (Load Test Soak Evidence)
Extends load-test evidence to support “soak” runs (multiple rounds) and preserves per-round results in captured evidence payloads.

- Operator runner:
  - `scripts/load_test_api.py` (`--rounds`, `--pause`, new `soak` profile alias)
- Evidence schema:
  - `app/modules/governance/api/v1/audit.py` (`LoadTestEvidencePayload.rounds`, `runs`, `min_throughput_rps`)
- Tests:
  - `tests/unit/api/v1/test_performance_evidence_endpoints.py`

### 35) Performance Scale Sprint v4 (Partitioning Validation Evidence)
Adds an audit-grade partitioning readiness snapshot so operators can capture whether high-volume tables are partitioned (Postgres) and which partitions exist.

- API:
  - `POST /api/v1/audit/performance/partitioning/evidence`
  - `GET /api/v1/audit/performance/partitioning/evidence`
  - `app/modules/governance/api/v1/audit.py`
- Audit event type:
  - `performance.partitioning_captured`: `app/modules/governance/domain/security/audit_log.py`
- Tests:
  - `tests/unit/api/v1/test_partitioning_evidence_endpoints.py`

### 36) Performance Scale Sprint v4 (End-to-End Ingestion Soak Evidence)
Adds an audit-grade, end-to-end ingestion soak runner so operators can validate real ingestion job throughput, p95 latency, and error-rate under sustained load (not just DB write benchmarks).

- Audit event type:
  - `performance.ingestion_soak_captured`: `app/modules/governance/domain/security/audit_log.py`
- API:
  - `POST /api/v1/audit/performance/ingestion/soak/evidence`
  - `GET /api/v1/audit/performance/ingestion/soak/evidence`
  - `app/modules/governance/api/v1/audit.py`
- Operator runner:
  - `scripts/soak_ingestion_jobs.py` (`--jobs`, `--workers`, `--publish`)
- Evidence bundle capture:
  - `scripts/capture_acceptance_evidence.py` now downloads `ingestion_soak_evidence.json` snapshots.
- Tests:
  - `tests/unit/api/v1/test_ingestion_soak_evidence_endpoints.py`
  - `tests/unit/governance/jobs/test_job_processor.py`, `tests/governance/test_job_processor.py`

### 37) Postgres Partition Maintenance Automation (Runbook + Validation)
Finishes the partitioning story with operator automation (create/validate future partitions) and a runbook suitable for compliance packs.

- Operator tooling:
  - `scripts/manage_partitions.py` (`create` + `validate`, supports `--table all`)
- Runbook:
  - `docs/runbooks/partition_maintenance.md`
- Evidence:
  - Partitioning evidence now reports `expected_partitions` and `missing_partitions` for the current month plus future months.
- Compliance pack:
  - Includes the partition maintenance runbook (via `app/modules/governance/api/v1/audit.py`).

### 38) Cloud+ Expansion Beyond IaaS/SaaS Basics (Platform + Hybrid Native Pull v1)
Introduces true API-native pulls for platform/hybrid connectors via a ledger HTTP connector mode (usable for internal CMDB/ledger systems), with verification and scheduled ingestion parity.

- Adapters:
  - `app/shared/adapters/platform.py` (`ledger_http` native pulls + verify)
  - `app/shared/adapters/hybrid.py` (`ledger_http` native pulls + verify)
- Connection schema:
  - `app/schemas/connections.py` (supports `auth_method=api_key` and validates `connector_config.base_url` for ledger mode)
- Dashboard:
  - `dashboard/src/routes/connections/+page.svelte` (Platform/Hybrid API key mode + connector config UI)
- Tests:
  - `tests/unit/services/adapters/test_cloud_plus_adapters.py`

### 39) Persona UX Hardening + Tier Gating Polish (Dashboard)
Improves persona-first UX so navigation doesn’t feel “missing”, and clarifies tier-locked surfaces with consistent upgrade prompts.

- Persona allowlist hardening:
  - `dashboard/src/lib/persona.ts` (onboarding always visible; admin billing visible)
- Persona-first nav with persistence:
  - `dashboard/src/routes/+layout.svelte` (persistent “show all” toggle + active-secondary visibility)
- Tier gating clarity:
  - `dashboard/src/lib/components/UpgradeNotice.svelte`
  - `dashboard/src/routes/+page.svelte` (allocation locked state shows upgrade CTA)
- Frontend validation:
  - `pnpm -C dashboard test:unit`
  - `pnpm -C dashboard check`

### 40) Enterprise Identity Interop v5 (IdP Reference Configs + Operator Smoke Evidence)
Adds operator-grade IdP onboarding support for SCIM by shipping a stable reference config doc, a SCIM smoke runner, and audit-grade evidence capture included in the compliance pack.

- Docs:
  - `docs/integrations/idp_reference_configs.md` (Okta/Entra reference values + mapping guidance)
  - `docs/integrations/scim.md` (links to reference configs)
- Operator runner:
  - `scripts/smoke_test_scim_idp.py` (read-only mode by default; `--write` creates user+group then cleans up; `--publish` stores evidence)
- Audit evidence API:
  - `POST /api/v1/audit/identity/idp-smoke/evidence`
  - `GET /api/v1/audit/identity/idp-smoke/evidence`
  - `app/modules/governance/api/v1/audit.py`
- Audit event type:
  - `identity.idp_smoke_captured`: `app/modules/governance/domain/security/audit_log.py`
- Evidence bundle capture:
  - `scripts/capture_acceptance_evidence.py` downloads `identity_smoke_evidence.json`
  - `docs/ops/acceptance_evidence_capture.md` updated with the identity smoke workflow
- Compliance pack:
  - Includes `identity_smoke_evidence.json` and `docs/integrations/idp_reference_configs.md`: `app/modules/governance/api/v1/audit.py`
- Tests:
  - `tests/unit/api/v1/test_identity_smoke_evidence_endpoints.py`
  - `tests/unit/api/v1/test_audit_compliance_pack.py`
