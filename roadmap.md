**12-Month Roadmap (Starting February 11, 2026)**

**Assumptions**
1. Goal: move from strong cloud optimization product to enterprise Cloud+ FinOps platform.
2. Team: 2 squads minimum (Data Platform, FinOps Intelligence) + shared frontend.
3. Cadence: monthly releases, quarterly outcome targets.

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

**Dependencies (critical path)**
1. Q1 ledger/reconciliation must land before Q2 chargeback and unit economics.
2. Q2 ingestion/backfill must land before Q3 close workflow and Cloud+ unification.
3. Q3 enterprise-grade trust outputs must land before Q4 procurement proof motions.

If you want, I can convert this into a sprint-ready backlog with issue titles, story points, and owner mapping per epic.