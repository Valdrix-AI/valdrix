# Series-A Technical Due Diligence Checklist

**For:** Investors, Acquirers, Technical Partners  
**Updated:** January 2026

Use this checklist during due diligence calls. Each section maps to a Valdrix subsystem.

---

## 1. COST DATA ACCURACY & TRUST

### The Question Investors Will Ask

"How do we know your cost numbers are correct? Can you prove you haven't double-counted? What happens when AWS restates data?"

### Verification Checklist

- [ ] **Forensic Auditability**
  - [ ] Every cost record has `ingestion_metadata` (source_id, timestamp, api_request_id)
  - [ ] Cost audit log (`cost_audit_logs` table) exists and is append-only
  - [ ] Test: Ingest same cost twice, verify second upsert is logged
  - [ ] Ask: "Show me the audit trail for cost X on date Y"

- [ ] **Reconciliation Workflow**
  - [ ] CUR data is marked PRELIMINARY for 48h
  - [ ] After 48h, data is marked FINAL (immutable)
  - [ ] Dashboard shows data freshness ("through Jan 14, final")
  - [ ] Test: Create cost, wait 48h, verify status change

- [ ] **Change Detection**
  - [ ] Costs that change >2% are logged with delta (old → new)
  - [ ] Alerts exist for >2% changes
  - [ ] Test: Change a cost record, verify alert fires

- [ ] **Idempotency**
  - [ ] Ingestion can safely retry (no duplicate costs)
  - [ ] Upsert logic is correct (ON CONFLICT DO UPDATE)
  - [ ] Test: Ingest same batch 3x, verify count unchanged

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

- [ ] **Attribution Rules Engine**
  - [ ] API exists to create attribution rules (POST /allocation/rules)
  - [ ] Rules support conditions (service, tags, region)
  - [ ] Rules support allocation (percentage, direct, fixed)
  - [ ] Test: "Create rule: S3 costs split 60% Team A, 40% Team B"
  - [ ] Test: Query costs, verify allocated_to shows team breakdown

- [ ] **Cost Allocation Execution**
  - [ ] Rules are applied during ingestion (not post-query)
  - [ ] CostAllocation table shows splits with percentage
  - [ ] Multiple rules can be chained
  - [ ] Test: 10 overlapping rules apply correctly

- [ ] **Untagged Resource Handling**
  - [ ] Default rule for untagged resources exists
  - [ ] Dashboard shows "unallocated" as a bucket
  - [ ] Alerts when >5% of costs are unallocated
  - [ ] Test: Ingest untagged resource, verify goes to "Other"

- [ ] **Dashboard Visualization**
  - [ ] Cost breakdown by allocated team/project
  - [ ] "Allocated vs Unallocated" pie chart
  - [ ] Export: CSV with team-level breakdown

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

- [ ] **Forecast Methodology**
  - [ ] Technology disclosed (Prophet + Holt-Winters)
  - [ ] Assumptions stated ("stable workloads")
  - [ ] Limitations acknowledged ("fails on batch jobs, holidays")
  - [ ] Ask: "What's the worst-case forecast error?"

- [ ] **Accuracy Metrics**
  - [ ] MAPE (Mean Absolute Percentage Error) calculated
  - [ ] Accuracy tracked month-over-month
  - [ ] Dashboard shows "Forecast accuracy: X%"
  - [ ] Test: 30-day hindcast, compare vs actual

- [ ] **Confidence Signaling**
  - [ ] Forecast includes confidence interval (lower/upper bound)
  - [ ] High volatility → low confidence (labeled)
  - [ ] Forecast says "±10%" or "±5%", not just point estimate
  - [ ] Dashboard shows volatility band (not just a line)

- [ ] **Anomaly Handling**
  - [ ] Outliers detected and flagged
  - [ ] Holidays can be marked manually
  - [ ] Load test days can be marked
  - [ ] Test: Mark "Jan 20 = batch job day", forecast adjusts

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

- [ ] **Row-Level Security (RLS)**
  - [ ] PostgreSQL RLS enabled on cost_records table
  - [ ] `app.current_tenant_id` is set per-request
  - [ ] All tables with tenant_id have RLS policies
  - [ ] Test: Tenant A queries, can they see Tenant B's data? (Should be NO)

- [ ] **Code-Level Isolation**
  - [ ] All queries filter on tenant_id
  - [ ] No query joins across tenants
  - [ ] `require_tenant_access` decorator on protected routes
  - [ ] Code review: grep for queries without tenant_id filter

- [ ] **Connection Pooling Safety**
  - [ ] `app.current_tenant_id` is set per-session (not connection)
  - [ ] Pool recycle time is <300 seconds
  - [ ] Test: High concurrency, verify no cross-tenant bleed

- [ ] **Audit Trail**
  - [ ] All tenant access logged
  - [ ] Audit logs are per-tenant and RLS-protected
  - [ ] Export: Audit trail for a specific tenant

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

- [ ] **Scheduler Resilience**
  - [ ] Scheduled jobs persist (survive restart)
  - [ ] No duplicate job execution (idempotency key exists)
  - [ ] Distributed scheduler (multiple instances don't conflict)
  - [ ] Test: Kill scheduler, restart, verify jobs complete correctly

- [ ] **Data Ingestion Resilience**
  - [ ] Failed ingestion retries with exponential backoff
  - [ ] Partial ingestion doesn't corrupt data
  - [ ] Ask: "What happens if AWS API returns 500 halfway through?"

- [ ] **Alerting & Monitoring**
  - [ ] Missing cost data triggers alert (>6h stale)
  - [ ] Job failures trigger alert
  - [ ] LLM failures trigger alert
  - [ ] Ask: "How many alerts fired last month?"

- [ ] **Disaster Recovery**
  - [ ] Backup strategy (frequency, retention)
  - [ ] RTO (Recovery Time Objective) documented
  - [ ] RPO (Recovery Point Objective) documented
  - [ ] Ask: "If PostgreSQL corrupts, how fast can you recover?"

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

- [ ] **LLM Spend Control**
  - [ ] Budget pre-checked before LLM call (not post-hoc)
  - [ ] Hard limit per tenant per day (e.g., $50/day max)
  - [ ] Multiple LLM providers (no single vendor lock-in)
  - [ ] Test: Try to exceed budget, verify rejection

- [ ] **Remediation Safety**
  - [ ] Auto-remediation disabled by default (simulation mode)
  - [ ] Confidence threshold required (>95% before executing)
  - [ ] Rate limit (max N deletions/hour)
  - [ ] Daily savings cap (stop remediation after $X saved)
  - [ ] Test: Try to delete 1000 resources/hour, verify capped

- [ ] **Compute Cost Control**
  - [ ] API query limits (max rows returned)
  - [ ] Statement timeouts (max 5s per query)
  - [ ] Concurrent request limits per tenant
  - [ ] Test: Large query hits limit, gets partial results (not crash)

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

- [ ] **Query Performance**
  - [ ] Large customer (20M cost records) query completes in <5s
  - [ ] Partitioning by date (RANGE by recorded_at)
  - [ ] Indexes on (tenant_id, recorded_at)
  - [ ] Load test: 100 concurrent users, 2-year history

- [ ] **Memory Safety**
  - [ ] Forecasting doesn't load entire history into memory
  - [ ] Bounded input: max 10M records per request
  - [ ] Streaming ingestion (not batch load-all)
  - [ ] Test: 20M cost records, forecast completes in <30s

- [ ] **Database Scaling**
  - [ ] Connection pooling (pool_size=10, max_overflow=20)
  - [ ] Slow query alerts (>200ms logged)
  - [ ] Ask: "Slowest query in prod?"

- [ ] **Cost Scaling**
  - [ ] Compute cost doesn't spike at 10× workload
  - [ ] Storage cost predictable (cost_records table size)
  - [ ] Ask: "Storage per cost record?"

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

- [ ] **Technical Depth**
  - [ ] Founder can explain cost accuracy forensics (not hand-wavy)
  - [ ] Team understands distributed systems (scheduler, idempotency)
  - [ ] Team understands financial data (decimals, rounding, reconciliation)
  - [ ] Ask: "Tell me about a production incident and how you fixed it"

- [ ] **Code Quality**
  - [ ] Code is readable (types, docstrings, tests)
  - [ ] Tests exist and pass
  - [ ] Async/await patterns correct (no deadlocks)
  - [ ] Code review: Ask "Where are the risky areas?"

- [ ] **Documentation**
  - [ ] Architecture docs exist and are current
  - [ ] Runbooks exist for common incidents
  - [ ] Onboarding guide for new engineers
  - [ ] Ask: "If I join your team, how long to be productive?"

- [ ] **Learning from Mistakes**
  - [ ] Past issues documented (not hidden)
  - [ ] Process improvements tracked
  - [ ] Ask: "What's the biggest technical debt?"

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

- [ ] **Audit Logging**
  - [ ] All user actions logged (READ, CREATE, UPDATE, DELETE)
  - [ ] Audit logs are append-only (no deletion)
  - [ ] Sensitive data is masked (API keys, credit cards)
  - [ ] Correlation IDs link related actions

- [ ] **Access Control**
  - [ ] RBAC (owner, admin, member roles)
  - [ ] Feature-based access (e.g., only "growth" plan can use Azure)
  - [ ] Tier gating enforced (not just suggested)
  - [ ] Test: Trial user tries to access enterprise features (should be blocked)

- [ ] **Data Protection**
  - [ ] Encryption at rest (Supabase handles)
  - [ ] Encryption in transit (TLS 1.3)
  - [ ] Sensitive fields encrypted (tenant name, credentials)
  - [ ] Ask: "How do you handle customer data deletion (GDPR)?"

- [ ] **Security Scanning**
  - [ ] SAST scanning in CI (Bandit)
  - [ ] Dependency scanning (Safety, npm audit)
  - [ ] Container scanning (Trivy)
  - [ ] Secret scanning (TruffleHop)

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
