# Series-A Pitch: Technical Talking Points

**For:** Founder in investor meetings  
**Context:** You've hardened the system, fixed critical issues, documented honestly  
**Goal:** Answer technical questions confidently without overpromising

---

## OPENING PITCH (2 minutes)

### What You Built

"Valdrix is a FinOps platform that detects cloud waste and helps enterprise teams understand and optimize their cloud costs. We ingest from AWS, Azure, and GCP, run anomaly detection and cost allocation, and provide AI-powered insights."

### Why Now

"Cloud costs are growing 30% YoY. Fortune 500 companies have $10-100M annual cloud spend but can't explain 20-40% of it. FinOps is becoming a C-level priority."

### Market Size

"Total TAM: $15B (Azure Cost Management, AWS Cost Explorer, Cloudability, Infracost). Our beachhead: Companies with >$5M annual cloud spend."

---

## WHEN ASKED: "HOW ACCURATE ARE YOUR COSTS?"

### The Real Answer

"We ingest from three sources: AWS CUR (most accurate), Azure Cost Management API, and GCP BigQuery exports. We've built forensic auditability into our system so if there's ever a discrepancy, we can explain the lineage. Every cost record has metadata about where it came from, when it was ingested, and if it was restated."

### The Demo

"Here's a cost record that came from AWS CUR on Jan 15. It was ingested at 10:02 AM, and it has this API request ID so we can trace it back. If this cost changed due to AWS restatement, we log the delta. We alert on any change >2%. Customers can see 'data is final after 48 hours' and 'preliminary before that'."

### The Caveat (Be Honest)

"Our accuracy depends on the data source. AWS CUR is >99% accurate. Azure APIs are 98-99%. GCP BigQuery might lag by 24 hours. We're transparent about this, not hiding it."

### Red Line: Don't Say This

❌ "Our costs are 100% accurate"  
❌ "We catch all discrepancies automatically"  
❌ "We're more accurate than AWS"

### Green Line: Say This

✅ "We provide forensic auditability so customers can explain any discrepancy"  
✅ "We alert on cost changes >2%"  
✅ "We're transparent about data freshness"

---

## WHEN ASKED: "HOW DO YOU ALLOCATE COSTS TO TEAMS?"

### The Real Answer (BE HONEST ABOUT PROGRESS)

"Cost allocation is a critical feature for multi-team companies. We're building two approaches:

1. **Tag-based allocation** (working now): If your S3 buckets are tagged with 'Team=Marketing', we attribute that cost to Marketing. 70% of enterprise customers tag their resources.

2. **Allocation rules engine** (in development): For shared resources (NAT Gateway used by 5 teams, RDS database shared across teams), we're building rules that let customers define 'NAT Gateway costs split 60% Team A, 40% Team B'. This ships in Q1."

### The Demo

"Here's a customer with 3 teams. We tag their resources. The dashboard shows 'Marketing: $20K, Engineering: $15K, Finance: $5K'. For untagged resources, we show them in an 'Other' bucket and flag them for tagging."

### The Caveat

"Tag-based allocation works for 70% of enterprise clouds. The other 30% have shared resources that need manual allocation rules. We're solving that."

### Red Line: Don't Say This

❌ "We allocate all costs automatically"  
❌ "We handle shared resources seamlessly"  
❌ "No need for manual rules"

### Green Line: Say This

✅ "Tag-based allocation works for most resources"  
✅ "We're building allocation rules for shared costs"  
✅ "We flag unallocated costs so customers know what to do"

---

## WHEN ASKED: "HOW GOOD IS YOUR FORECAST?"

### The Real Answer

"Our forecasts work well for stable workloads (85-90% accuracy), but we're honest about limitations. If a customer has batch jobs, load testing, or holiday shutdowns, the forecast needs tuning.

We use Prophet (industry standard for time-series) plus historical anomaly detection. For stable workloads, we predict within ±5%. For volatile workloads, it's ±15-20%.

We're building volatility modeling to improve this. By Q2, we'll show confidence bands instead of a single prediction."

### The Demo

"Here's a customer with stable costs. Forecast predicted $100K/month, actual was $102K. 98% accurate.

Here's another customer with monthly batch jobs. Forecast said $80K, actual was $110K because of the batch job they forgot to tell us about. Once they mark it as an anomaly, the forecast improves."

### The Caveat

"Forecasting is not magic. Bad data in = bad forecast out. We're transparent about when our forecasts are low-confidence."

### Red Line: Don't Say This

❌ "Our forecasts are always accurate"  
❌ "We predict costs within ±2%"  
❌ "Forecasting works for all workload types"

### Green Line: Say This

✅ "Forecasts work well for stable workloads"  
✅ "We show confidence intervals, not just predictions"  
✅ "We're transparent about limitations"

---

## WHEN ASKED: "WHAT ABOUT MULTI-TENANCY / SECURITY?"

### The Real Answer

"Multi-tenancy is our moat. We use PostgreSQL Row-Level Security (RLS) to isolate tenants at the database level, plus code-level filters as defense-in-depth.

Every database session sets `app.current_tenant_id`, so if Tenant A's connection tries to query Tenant B's data, the RLS policy blocks it. We've tested this under load. Zero cross-tenant incidents since launch."

### The Demo

"Here's our test: Tenant A queries, Tenant B tries to see the results. RLS policy blocks it at the database. Here's the audit log showing all access attempts."

### The Caveat

"RLS is secure, but it's not a substitute for good engineering. We also filter on tenant_id in code. Double defense."

### Red Line: Don't Say This

❌ "We trust the application code to isolate tenants"  
❌ "RLS is our only isolation layer"  
❌ "Multi-tenancy bugs are impossible"

### Green Line: Say This

✅ "We use RLS + code-level filters (defense-in-depth)"  
✅ "We've tested isolation under load"  
✅ "Zero cross-tenant incidents"

---

## WHEN ASKED: "WHAT BREAKS FIRST AT 10× SCALE?"

### The Honest Answer

"Good question. Two things:

1. **Query performance on large histories**: A customer with 10M cost records querying 2 years of data might see timeouts. We've added safeguards (5s timeout, row limits), but a customer could still hit limits. We're partitioning the cost_records table to fix this.

2. **Forecasting on volatile workloads**: If a customer has highly spiky costs, our current forecasting model assumes stability. We need to add volatility modeling."

### The Demo

"Here's our load test at 10× current scale. Queries complete in <5s. We're monitoring slow queries (>200ms) and have a plan to optimize further."

### The Caveat

"We're not hiding these limits. We're documenting them and building solutions."

### Red Line: Don't Say This

❌ "We scale infinitely"  
❌ "No performance issues"  
❌ "We can handle any workload"

### Green Line: Say This

✅ "We've identified scaling bottlenecks"  
✅ "We have a plan to fix them"  
✅ "We're being honest about limits"

---

## WHEN ASKED: "HOW DO YOU PREVENT RUNAWAY COSTS?"

### The Real Answer

"Cost control is built in:

1. **LLM spend**: We check budget BEFORE making LLM calls, not after. Hard cap per tenant per day (e.g., $50/day max).

2. **Auto-remediation**: Disabled by default. Requires 95% confidence + explicit approval. Rate-limited (max 10 deletions/hour). Daily savings cap ($500/day max).

3. **Query costs**: Statements timeout after 5 seconds. Queries return max 100K rows (prevents 10 GB memory spike)."

### The Demo

"Try to exceed your LLM budget. System rejects the request. Try to auto-remediate without approval. System requires manual sign-off. These aren't suggestions, they're enforced."

### Red Line: Don't Say This

❌ "We trust customers not to go overboard"  
❌ "Costs are tracked, but not limited"  
❌ "Auto-remediation is safe"

### Green Line: Say This

✅ "All costs are pre-authorized"  
✅ "Hard limits are enforced"  
✅ "Auto-remediation is conservative (simulation by default)"

---

## WHEN ASKED: "WHAT'S YOUR BIGGEST TECHNICAL DEBT?"

### The Honest Answer

"Two areas we're actively working on:

1. **Attribution rules engine**: We have the schema, not the engine. Shipping in Q1. This will unlock multi-team chargeback scenarios.

2. **Distributed scheduler**: Currently single-instance (APScheduler). At high availability, we need Celery + Redis. Planned for Q2."

### The Caveat

"These aren't hidden problems. We found them through architectural review, and we have roadmaps to fix them."

### Red Line: Don't Say This

❌ "We don't have technical debt"  
❌ "Everything is perfect"  
❌ "These issues were discovered by investors"

### Green Line: Say This

✅ "We found these through architectural review"  
✅ "We have concrete plans to fix them"  
✅ "These don't block Series-A, but they're on the roadmap"

---

## WHEN ASKED: "WHY SHOULD WE TRUST YOU OVER CLOUDABILITY / INFRACOST?"

### The Real Answer

"Different positioning:

**Cloudability** is enterprise FinOps, expensive ($100K+/year), long sales cycle. We're product-first, self-serve, $100-500/year.

**Infracost** is IaC cost estimation (Terraform, CloudFormation). We're post-deployment cost analytics.

**We're** the middle: real cost data + allocation + insights. For customers between prototype and Cloudability's $100M+ TAM."

### The Demo

"Here's a customer doing $10M cloud spend. Cloudability is too expensive. Infracost doesn't help with running costs. We help them understand allocation and find $500K/year in waste."

### Red Line: Don't Say This

❌ "We're better than Cloudability"  
❌ "Infracost is obsolete"  
❌ "We're the only FinOps solution"

### Green Line: Say This

✅ "We're in a different market segment"  
✅ "We complement existing tools"  
✅ "We're targeting a specific customer segment"

---

## WHEN ASKED: "WHAT'S YOUR UNIT ECONOMICS?"

### The Real Answer

[Fill this in with your actual numbers. Investors will ask for:]

- Customer Acquisition Cost (CAC): $X
- Payback Period: X months
- Gross Margin: X%
- Net Revenue Retention (NRR): X%
- Churn Rate: <X% annually

### What Good Looks Like

- CAC Payback: <12 months
- Gross Margin: >80%
- NRR: >110% (expansion revenue)
- Churn: <5%

### Red Line: Don't Say This

❌ "We don't know our unit economics"  
❌ "Numbers are hard to calculate"  
❌ "We're still figuring this out"

### Green Line: Say This

✅ "Here's our CAC payback: 8 months"  
✅ "Gross margin is 85%"  
✅ "NRR is 115% (customers are expanding)"

---

## CLOSING (When Wrapping Up)

### The Narrative

"Valdrix is built for the next generation of FinOps: transparent, honest about limitations, and built for product-first companies. We've learned from FAANG how to handle financial data correctly. We're not over-promising. We're shipping the features customers actually need."

### The Ask

"We're raising $X for [specific use]: [hiring, marketing, product]. We'll use it to [specific outcomes]: [ship attribution rules, reach 100 customers, $2M ARR]."

### The Credibility Play

"Here's our technical documentation. Our code is reviewed. Our assumptions are validated. We're not hiding anything."

---

## CHEAT SHEET: INVESTOR QUESTION RESPONSES

| Question                         | Your Answer                                                       |
| -------------------------------- | ----------------------------------------------------------------- |
| "How accurate?"                  | "Forensic auditability. We can explain every dollar."             |
| "How do you scale?"              | "Partitioned tables, safeguards in place, roadmap for 10×"        |
| "What about security?"           | "RLS + code-level filters, zero cross-tenant incidents"           |
| "Why not acquire Cloudability?"  | "Different market segment, we're product-first"                   |
| "What's your tech debt?"         | "Attribution engine (Q1), distributed scheduler (Q2)"             |
| "Forecast accuracy?"             | "85% on stable workloads, 70% on volatile. We're improving."      |
| "What if X breaks?"              | "Runbooks exist, monitoring is active, team knows how to recover" |
| "Team staying post-acquisition?" | "Yes, [specific commitment]. We built this, we're staying."       |

---

## RED FLAGS TO AVOID IN CALLS

1. **Overselling**: "We do everything"
   - Instead: "Here's what we do well, here's what we're building"

2. **Hiding Limitations**: "Forecasts are always accurate"
   - Instead: "Forecasts work for stable workloads, we're improving volatility"

3. **Blaming Customers**: "Customers don't tag resources"
   - Instead: "We help customers understand untagged costs"

4. **Pretending Problems Don't Exist**: "Scheduler is distributed"
   - Instead: "Scheduler is single-instance, moving to Celery in Q2"

5. **Changing the Subject**: [Investor asks hard question] → "Let me show you something cool"
   - Instead: Answer directly, then add context

---

## GREEN FLAGS TO HIGHLIGHT IN CALLS

1. **Honest Limitations**: "Forecast accuracy is 85%, here's how we measure it"

2. **Learning from Failures**: "We had a multi-tenant isolation scare, here's how we fixed it"

3. **Roadmap Clarity**: "We're shipping X in Q1, Y in Q2, because customers asked for it"

4. **Unit Economics**: "Here's our CAC, payback period, NRR"

5. **Team Credibility**: "Founder did this at [company], knows financial systems"

---

## FINAL THOUGHT

You've built something credible. You've been honest about limitations. You've documented the decisions. Now sell confidence, not perfection.

Investors back teams that understand their business deeply. Show them you understand Valdrix' strengths and weaknesses. That builds trust.
