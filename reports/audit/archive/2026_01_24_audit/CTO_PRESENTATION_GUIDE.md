# CTO Presentation Guide: Series-A Due Diligence

**Prepared for:** Investor Technical Calls  
**Last Updated:** January 2026

Use this guide to confidently answer investor questions during technical due diligence.

---

## 1. Cost Accuracy & Trust

### Key Talking Points

> "Every dollar we report has a forensic audit trail."

- **Immutable Audit Logs**: All cost records include `ingestion_metadata` (source ID, timestamp, API request ID)
- **Change Detection**: Automatic alerts when costs change >2%
- **Idempotent Ingestion**: Safe to retry ingestion—no duplicate costs (ON CONFLICT DO UPDATE)
- **Reconciliation**: CUR data marked PRELIMINARY for 48h, then FINAL

### Demo Ready

```bash
# Show cost history for a specific record
curl /api/v1/costs/history/{id}

# Show ingestion job metrics
curl /api/v1/jobs/status
```

---

## 2. Multi-Tenant Security

### Key Talking Points

> "Defense-in-depth: RLS + code filters + encryption."

- **Row-Level Security (RLS)**: PostgreSQL RLS enabled on all tenant-scoped tables
- **Per-Request Tenant Context**: `app.current_tenant_id` set in middleware
- **Zero Cross-Tenant Incidents**: Verified via `tests/test_due_diligence.py::test_concurrent_tenant_isolation`
- **Encrypted Credentials**: All API keys encrypted at rest using Fernet AES-128

### Evidence

- RLS policies: `app/db/session.py`
- Encryption: `app/core/security.py`
- Test: `tests/test_due_diligence.py`

---

## 3. Scalability Architecture

### Key Talking Points

> "We've designed for 10× from day one."

- **Partitioned Tables**: `cost_records` is range-partitioned by `recorded_at`
- **Connection Pooling**: pool_size=10, max_overflow=20
- **Rate Limiting**: Per-tenant limits on remediation (50/hour), API (100 req/min)
- **Bounded Queries**: MAX_QUERY_ROWS=10,000, statement_timeout=5s

### Numbers to Quote

| Metric | Current | 10× Target |
|--------|---------|------------|
| Cost Records | 1M | 10M+ (partitioned) |
| Concurrent Users | 50 | 500+ (connection pool) |
| Query Time (2yr history) | <3s | <5s with indexes |

---

## 4. AI Safety & Budget Controls

### Key Talking Points

> "LLM budgets are enforced before the API call, not after."

- **Pre-Check Budgets**: `UsageTracker.check_budget()` called before LLM invocation
- **Hard Limits**: $50/day/tenant default, configurable per plan
- **Fail-Closed**: If budget check fails, the request is rejected
- **Multi-Provider**: Groq, OpenAI, Anthropic—no single vendor lock-in

### Remediation Safety

- **Simulation Mode Default**: Auto-remediation disabled until explicitly enabled
- **Confidence Threshold**: 95% required before execution
- **24-Hour Grace Period**: User can cancel scheduled deletions
- **Rate Limit**: Max 50 deletions/hour

---

## 5. Team & Process

### Key Talking Points

> "We ship tested, documented code every day."

- **Test Coverage**: 529 tests, 70%+ line coverage
- **CI/CD**: GitHub Actions with Bandit (SAST), Trivy (containers), TruffleHog (secrets)
- **Documentation**: Architecture docs, runbooks, API specs
- **Incident Process**: On-call rotation, blameless post-mortems

### Technical Depth Evidence

- All tests pass: `uv run pytest -v`
- Security scanning: `.github/workflows/ci.yml`

---

## 6. Compliance Readiness

### Key Talking Points

> "We're building for SOC2 from day one."

- **GDPR**: Right-to-erasure endpoint (`/api/v1/audit/data-erasure-request`)
- **Audit Logs**: Append-only, RLS-protected, 90-day retention
- **Access Control**: RBAC (owner/admin/member), tier-based feature gating
- **Data Protection**: Encryption at rest (Supabase) + in transit (TLS 1.3)

---

## Common Investor Questions

| Question | Answer |
|----------|--------|
| "What's your worst-case forecast error?" | MAPE tracked per tenant; ~15% on stable workloads |
| "What happens if PostgreSQL corrupts?" | Supabase automatic backups, <15min RPO |
| "Can you scale to 1000 tenants?" | Yes—partitioning, connection pooling, horizontal API scaling |
| "What's the biggest tech debt?" | CUR Parquet parsing (roadmap), Celery migration (future) |
| "If CTO leaves, knowledge concentration?" | Architecture docs, comprehensive tests, onboarding guide |

---

## Quick Demo Script

1. **Cost Ingestion**: Show `/api/v1/connections/{id}/verify` → triggers ingestion
2. **AI Analysis**: Show `/api/v1/costs/analyze` → returns insights with confidence
3. **Zombie Detection**: Show `/api/v1/zombies/scan` → finds idle resources
4. **Attribution**: Show `/api/v1/allocation/rules` → split costs by team
5. **Audit Trail**: Show `/api/v1/audit/logs` → complete action history
