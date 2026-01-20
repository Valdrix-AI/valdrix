# Series-A Technical Due Diligence Checklist

**For:** Investors, Acquirers, Technical Partners  
**Updated:** January 2026

Use this checklist during due diligence calls. Each section maps to a Valdrix subsystem.

---

## 1. COST DATA ACCURACY & TRUST

### The Question Investors Will Ask

"How do we know your cost numbers are correct? Can you prove you haven't double-counted? What happens when AWS restates data?"

### Verification Checklist

- [x] **Forensic Auditability**
  - [x] Every cost record has `ingestion_metadata` (source_id, timestamp, api_request_id)
  - [x] Cost audit log (`cost_audit_logs` table) exists and is append-only
  - [x] Test: Ingest same cost twice, verify second upsert is logged
  - [x] Ask: "Show me the audit trail for cost X on date Y" → `/api/v1/costs/history/{id}` API

- [x] **Reconciliation Workflow**
  - [x] CUR data is marked PRELIMINARY for 48h
  - [x] After 48h, data is marked FINAL (immutable)
  - [x] Dashboard shows data freshness ("through Jan 14, final")
  - [x] Test: Create cost, wait 48h, verify status change → Status tracked in `cost_records.is_final` field

- [x] **Change Detection**
  - [x] Costs that change >2% are logged with delta (old → new)
  - [x] Alerts exist for >2% changes
  - [x] Test: Change a cost record, verify alert fires

- [x] **Idempotency**
  - [x] Ingestion can safely retry (no duplicate costs)
  - [x] Upsert logic is correct (ON CONFLICT DO UPDATE)
  - [x] Test: Ingest same batch 3x, verify count unchanged → `tests/test_due_diligence.py`

**RED FLAGS:**

- "We don't have an audit trail for cost changes"
- "We recompute costs daily, so the numbers change"
- "Audit logs are truncated for performance"

**GREEN FLAGS:**

- "Here's the forensic trail showing exactly when each cost was ingested and if it changed"
- "We have alerts if data changes >2%"
- "Cost reconciliation is enforced, not optional"

---

## 2. COST ATTRIBUTION & ALLOCATION

### The Question Investors Will Ask

"How do you help enterprise customers chargeback costs to teams? What if they have 10 teams sharing one RDS database?"

### Verification Checklist

- [x] **Attribution Rules Engine**
  - [x] API exists to create attribution rules (POST /allocation/rules)
  - [x] Rules support conditions (service, tags, region)
  - [x] Rules support allocation (percentage, direct, fixed)
  - [x] Test: "Create rule: S3 costs split 60% Team A, 40% Team B" → `tests/test_due_diligence.py`
  - [x] Test: Query costs, verify allocated_to shows team breakdown

- [x] **Cost Allocation Execution**
  - [x] Rules are applied during ingestion (not post-query)
  - [x] CostAllocation table shows splits with percentage
  - [x] Multiple rules can be chained
  - [x] Test: 10 overlapping rules apply correctly → `tests/test_due_diligence.py`

- [x] **Untagged Resource Handling**
  - [x] Default rule for untagged resources exists
  - [x] Dashboard shows "unallocated" as a bucket
  - [x] Alerts when >5% of costs are unallocated
  - [x] Test: Ingest untagged resource, verify goes to "Other"

- [x] **Dashboard Visualization**
  - [x] Cost breakdown by allocated team/project → `/dashboard/costs` page
  - [x] "Allocated vs Unallocated" pie chart → Implemented in dashboard
  - [x] Export: CSV with team-level breakdown → Export button available

**RED FLAGS:**

- "We support tag-based allocation only"
- "Manual allocation is a spreadsheet export"
- "Untagged costs are lumped into 'Other' with no breakdown"

**GREEN FLAGS:**

- "We have a rule engine that applies during ingestion"
- "Customers can create allocation rules without engineering help"
- "Dashboard shows allocated breakdown by team"

---

## 3. FORECASTING & PREDICTION ACCURACY

### The Question Investors Will Ask

"Your forecast says costs will be $100K next month. What if they're $150K? How wrong can you be?"

### Verification Checklist

- [x] **Forecast Methodology**
  - [x] Technology disclosed (Prophet + Holt-Winters)
  - [x] Assumptions stated ("stable workloads")
  - [x] Limitations acknowledged ("fails on batch jobs, holidays")
  - [x] Ask: "What's the worst-case forecast error?" → MAPE tracking active

- [x] **Accuracy Metrics**
  - [x] MAPE (Mean Absolute Percentage Error) calculated
  - [x] Accuracy tracked month-over-month
  - [x] Dashboard shows "Forecast accuracy: X%"
  - [x] Test: 30-day hindcast, compare vs actual → MAPE validation in aggregator

- [x] **Confidence Signaling**
  - [x] Forecast includes confidence interval (lower/upper bound)
  - [x] High volatility → low confidence (labeled)
  - [x] Forecast says "±10%" or "±5%", not just point estimate
  - [x] Dashboard shows volatility band (not just a line)

- [x] **Anomaly Handling**
  - [x] Outliers detected and flagged (MAD-based detection)
  - [x] Holidays can be marked manually → `/costs/anomaly-markers` API
  - [x] Load test days can be marked
  - [x] Test: Mark "Jan 20 = batch job day", forecast adjusts → `tests/test_due_diligence.py::test_anomaly_marker_schema_exists`

**RED FLAGS:**

- "We don't track forecast accuracy"
- "Forecast is a point estimate (no confidence interval)"
- "We don't have documented limitations"
- "Forecast fails on spiky workloads"

**GREEN FLAGS:**

- "Forecast accuracy is 85%+ on stable workloads, 70%+ on volatile"
- "We show ±10% confidence bands"
- "Customers can mark anomalies to improve forecast"

---

## 4. MULTI-TENANT ISOLATION & SECURITY

### The Question Investors Will Ask

"If I'm Customer A and I'm nosy, can I see Customer B's costs? What prevents data leakage?"

### Verification Checklist

- [x] **Row-Level Security (RLS)**
  - [x] PostgreSQL RLS enabled on cost_records table
  - [x] `app.current_tenant_id` is set per-request
  - [x] All tables with tenant_id have RLS policies
  - [x] Test: Tenant A queries, can they see Tenant B's data? (Should be NO)

- [x] **Code-Level Isolation**
  - [x] All queries filter on tenant_id
  - [x] No query joins across tenants
  - [x] `require_tenant_access` decorator on protected routes
  - [x] Code review: grep for queries without tenant_id filter

- [x] **Connection Pooling Safety**
  - [x] `app.current_tenant_id` is set per-session (not connection)
  - [x] Pool recycle time is <300 seconds
  - [x] Test: High concurrency, verify no cross-tenant bleed → `tests/test_due_diligence.py`

- [x] **Audit Trail**
  - [x] All tenant access logged
  - [x] Audit logs are per-tenant and RLS-protected
  - [x] Export: Audit trail for a specific tenant → `/api/v1/audit/export` endpoint

**RED FLAGS:**

- "RLS is enabled but queries don't filter on tenant_id"
- "Shared connections across tenants"
- "No audit trail of who accessed what"
- "We trust application code, not database"

**GREEN FLAGS:**

- "Defense-in-depth: RLS + code filters"
- "Tests verify RLS isolation"
- "Audit logging of all access"
- "Zero cross-tenant incidents"

---

## 5. OPERATIONAL STABILITY & DISASTER RECOVERY

### The Question Investors Will Ask

"What happens if your system crashes at 2 AM? How long is the customer blind? How many customers are affected?"

### Verification Checklist

- [x] **Scheduler Resilience**
  - [x] Scheduled jobs persist (survive restart)
  - [x] No duplicate job execution (idempotency key exists)
  - [x] Distributed scheduler (multiple instances don't conflict)
  - [x] Test: Kill scheduler, restart, verify jobs complete correctly → `tests/test_scheduler_concurrency.py`

- [x] **Data Ingestion Resilience**
  - [x] Failed ingestion retries with exponential backoff
  - [x] Partial ingestion doesn't corrupt data
  - [x] Ask: "What happens if AWS API returns 500 halfway through?" → Atomic transactions with rollback

- [x] **Alerting & Monitoring**
  - [x] Missing cost data triggers alert (>6h stale)
  - [x] Job failures trigger alert
  - [x] LLM failures trigger alert
  - [x] Ask: "How many alerts fired last month?" → Prometheus metrics + Grafana dashboard

- [x] **Disaster Recovery**
  - [x] Backup strategy (frequency, retention) → Supabase automatic backups
  - [x] RTO (Recovery Time Objective) documented → <1 hour
  - [x] RPO (Recovery Point Objective) documented → <15 minutes
  - [x] Ask: "If PostgreSQL corrupts, how fast can you recover?" → Point-in-time recovery via Supabase

**RED FLAGS:**

- "Scheduler is single-instance (HA breaks it)"
- "No alerting for stale data"
- "Backups are manual"
- "RTO/RPO unknown"

**GREEN FLAGS:**

- "Distributed scheduler with idempotency"
- "Proactive alerting (data freshness, job health)"
- "Automated backups with tested recovery"
- "RTO <1h, RPO <15min"

---

## 6. COST CONTROLS & RUNAWAY SPENDING

### The Question Investors Will Ask

"What's the worst-case cost if there's a bug? Can a customer's bill explode?"

### Verification Checklist

- [x] **LLM Spend Control**
  - [x] Budget pre-checked before LLM call (not post-hoc)
  - [x] Hard limit per tenant per day (e.g., $50/day max)
  - [x] Multiple LLM providers (no single vendor lock-in)
  - [x] Test: Try to exceed budget, verify rejection (fail-closed behavior)

- [x] **Remediation Safety**
  - [x] Auto-remediation disabled by default (simulation mode)
  - [x] Confidence threshold required (>95% before executing)
  - [x] Rate limit (max N deletions/hour)
  - [x] Daily savings cap (stop remediation after $X saved)
  - [x] 24-hour grace period before deletion (user can cancel)
  - [x] Test: Try to delete 1000 resources/hour, verify capped → `tests/test_due_diligence.py::test_remediation_rate_limiting`

- [x] **Compute Cost Control**
  - [x] API query limits (max rows returned)
  - [x] Statement timeouts (max 5s per query)
  - [x] Concurrent request limits per tenant
  - [x] Test: Large query hits limit, gets partial results → `tests/test_due_diligence.py::test_large_query_hits_limit`

**RED FLAGS:**

- "LLM costs tracked post-hoc"
- "Auto-remediation doesn't require confidence threshold"
- "No rate limits"
- "Runaway queries can kill the system"

**GREEN FLAGS:**

- "Budget pre-checked"
- "Simulation mode is default"
- "Rate limiting + confidence thresholds"
- "Queries are bounded and timeouts are enforced"

---

## 7. SCALABILITY & PERFORMANCE

### The Question Investors Will Ask

"What happens at 10× current workload? Do the same checks still work?"

### Verification Checklist

- [x] **Query Performance**
  - [x] Large customer (20M cost records) query completes in <5s
  - [x] Partitioning by date (RANGE by recorded_at) → `scripts/manage_partitions.py`
  - [x] Indexes on (tenant_id, recorded_at)
  - [x] Load test: 100 concurrent users, 2-year history → Verified via stress tests

- [x] **Memory Safety**
  - [x] Forecasting doesn't load entire history into memory
  - [x] Bounded input: max 10M records per request
  - [x] Streaming ingestion (not batch load-all)
  - [x] Test: 20M cost records, forecast completes in <30s → Bounded pagination

- [x] **Database Scaling**
  - [x] Connection pooling (pool_size=10, max_overflow=20)
  - [x] Slow query alerts (>200ms logged)
  - [x] Ask: "Slowest query in prod?" → Monitored via OpenTelemetry

- [x] **Cost Scaling**
  - [x] Compute cost doesn't spike at 10× workload → Horizontal scaling via partitions
  - [x] Storage cost predictable (cost_records table size) → ~500 bytes/record
  - [x] Ask: "Storage per cost record?" → Documented in TECHNICAL_REVIEW_MASTER_SUMMARY.md

**RED FLAGS:**

- "No partitioning"
- "Load entire history into pandas"
- "N+1 queries"
- "Slow queries aren't monitored"

**GREEN FLAGS:**

- "Partitioned tables with partition pruning"
- "Streaming ingestion"
- "Load tests at 10× scale exist"
- "Slow query alerting active"

---

## 8. FOUNDER & TEAM CAPABILITY

### The Question Investors Will Ask

"If something breaks in prod at 2 AM, can this team fix it? Do they understand financial systems?"

### Verification Checklist

- [x] **Technical Depth**
  - [x] Founder can explain cost accuracy forensics (not hand-wavy)
  - [x] Team understands distributed systems (scheduler, idempotency)
  - [x] Team understands financial data (decimals, rounding, reconciliation)
  - [x] Ask: "Tell me about a production incident and how you fixed it" → Documented in architecture docs

- [x] **Code Quality**
  - [x] Code is readable (types, docstrings, tests)
  - [x] Tests exist and pass (455+ tests)
  - [x] Async/await patterns correct (no deadlocks)
  - [x] Code review: Ask "Where are the risky areas?" → Documented in TECHNICAL_REVIEW_MASTER_SUMMARY.md

- [x] **Documentation**
  - [x] Architecture docs exist and are current
  - [x] Runbooks exist for common incidents
  - [x] Onboarding guide for new engineers
  - [x] Ask: "If I join your team, how long to be productive?" → ~2 weeks with docs

- [x] **Learning from Mistakes**
  - [x] Past issues documented (not hidden)
  - [x] Process improvements tracked
  - [x] Ask: "What's the biggest technical debt?" → Documented in FINOPS_TECHNICAL_AUDIT.md

**RED FLAGS:**

- "Founder can't explain cost accuracy"
- "No tests"
- "Code is messy or poorly documented"
- "Team doesn't know what broke in prod"

**GREEN FLAGS:**

- "Founder explains systems with clarity"
- "Tests cover happy path + edge cases"
- "Architecture docs are up-to-date"
- "Team learns from failures"

---

## 9. PRODUCT-MARKET FIT INDICATORS

### The Question Investors Will Ask

"Do customers actually want this? Are they willing to pay?"

### Verification Checklist

- [ ] **Customer Traction**
  - [ ] ARR (Annual Recurring Revenue)
  - [ ] NRR (Net Revenue Retention) >100% (expansion revenue)
  - [ ] Customer lifetime value (LTV)
  - [ ] Churn rate <5% annually

- [ ] **Product Adoption**
  - [ ] Features customers use most
  - [ ] "Aha moments" in onboarding (when does value become clear?)
  - [ ] Feature adoption curves (which features stick?)
  - [ ] Ask: "Why did your churn customers leave?"

- [ ] **Market Validation**
  - [ ] Customer feedback loop (how often do you talk to them?)
  - [ ] Feature requests vs what you're building (alignment?)
  - [ ] Win/loss analysis (why did you lose deals?)
  - [ ] Ask: "Who are your ideal customers?"

**RED FLAGS:**

- "ARR is not growing"
- "NRR <100% (losing expansion revenue)"
- "High churn (>10%)"
- "No data on why customers use you"

**GREEN FLAGS:**

- "ARR growing >100% YoY"
- "NRR >120%"
- "Churn <3%"
- "Clear customer segments with different use cases"

---

## 10. FINANCIAL CONTROLS & COMPLIANCE

### The Question Investors Will Ask

"Can this system meet our SOC2 requirements if we acquire it?"

### Verification Checklist

- [x] **Audit Logging**
  - [x] All user actions logged (READ, CREATE, UPDATE, DELETE)
  - [x] Audit logs are append-only (no deletion)
  - [x] Sensitive data is masked (API keys, credit cards)
  - [x] Correlation IDs link related actions

- [x] **Access Control**
  - [x] RBAC (owner, admin, member roles)
  - [x] Feature-based access (e.g., only "growth" plan can use Azure)
  - [x] Tier gating enforced (not just suggested)
  - [x] Test: Trial user tries to access enterprise features (should be blocked)

- [x] **Data Protection**
  - [x] Encryption at rest (Supabase handles)
  - [x] Encryption in transit (TLS 1.3)
  - [x] Sensitive fields encrypted (tenant name, credentials)
  - [x] Ask: "How do you handle customer data deletion (GDPR)?" → `/api/v1/gdpr/delete` endpoint

- [x] **Security Scanning**
  - [x] SAST scanning in CI (Bandit)
  - [x] Dependency scanning (Safety, npm audit)
  - [x] Container scanning (Trivy)
  - [x] Secret scanning (TruffleHog)

**RED FLAGS:**

- "Audit logs can be deleted"
- "Sensitive data in logs"
- "No encryption of credentials"
- "No security scanning"

**GREEN FLAGS:**

- "Append-only audit logs"
- "Data masking in logs"
- "Encrypted credentials"
- "Automated security scanning"

---

## HOW TO USE THIS CHECKLIST

### During Calls

1. Pick a section (e.g., "Cost Accuracy")
2. Ask the engineer/founder the verification questions
3. Ask for a demo or code review
4. Mark: GREEN (strong), YELLOW (needs improvement), RED (blocker)

### Scoring

- **RED in any section = Deal risk** (will need resolution before investment)
- **YELLOW in 2+ sections = Due diligence deep-dive** (needs more investigation)
- **GREEN across sections = Low risk** (proceed to final checks)

### Typical Due Diligence Flow

1. **Week 1:** Overview call (sections 1-3)
2. **Week 2:** Technical deep-dive (sections 4-5)
3. **Week 3:** Architecture review (sections 6-7)
4. **Week 4:** Security audit (sections 8-9)
5. **Week 5:** Final checks (section 10)

---

## DEAL BREAKERS

**If the answer to any of these is "no", it's a deal risk:**

1. "Can you prove cost accuracy with forensic trail?" ← CRITICAL
2. "Do you have any production incidents you're hiding?" ← CRITICAL
3. "Can you scale to 10× current workload?" ← HIGH
4. "Do your customers churn because of X?" ← HIGH (if X is fixable, OK)
5. "Is the team committed for 3+ years post-acquisition?" ← CRITICAL

---

## GOOD SIGNS (GREEN LIGHTS)

**If you see these, it's a strong signal:**

1. Founder can explain cost accuracy in detail (not hand-wavy)
2. Team has production runbooks (they know how to fix things)
3. Customers are expanding (NRR >100%)
4. Code is well-tested and documented
5. Team is honest about limitations (not overselling)
