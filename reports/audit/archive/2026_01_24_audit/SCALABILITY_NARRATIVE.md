# How We Handle 10× Customer Load

**Prepared for:** Technical Due Diligence  
**Last Updated:** January 2026

This document explains how Valdrix is architected to scale from current load to 10× without redesign.

---

## Executive Summary

Valdrix is designed for horizontal scalability across all critical paths:

| Component | Current | 10× Strategy |
|-----------|---------|--------------|
| Cost Records | 1M records | Range partitioning by date |
| Concurrent Users | 50 | Connection pooling (10+20 overflow) |
| API Requests | 1K/min | Rate limiting + horizontal pod scaling |
| Forecasting | 100K records/request | Bounded input (10M max) |
| LLM Calls | 100/day/tenant | Pre-budgeted, multi-provider failover |

---

## 1. Database Scaling

### Partitioning Strategy

The `cost_records` table is range-partitioned by `recorded_at`:

```sql
-- Automatic partition creation for each month
CREATE TABLE cost_records_2026_01 PARTITION OF cost_records
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
```

**Benefits:**
- Partition pruning: queries for "last 30 days" only scan 1-2 partitions
- Archival: old partitions can be moved to cold storage
- Maintenance: VACUUM/ANALYZE run per-partition

**Proof:** See `scripts/manage_partitions.py`

### Connection Pooling

```python
# app/db/session.py
engine = create_async_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=300
)
```

**10× Math:**
- 10 base connections × 3 workers = 30 connections
- 20 overflow per worker = 60 burst connections
- PostgreSQL supports 100+ connections easily

### Query Boundaries

| Limit | Value | Purpose |
|-------|-------|---------|
| MAX_QUERY_ROWS | 10,000 | Prevent memory exhaustion |
| statement_timeout | 5s | Kill runaway queries |
| Pagination | Required | No unbounded result sets |

---

## 2. API Scaling

### Rate Limiting

Per-tenant limits enforced at middleware level:

```python
# app/core/rate_limit.py
LIMITS = {
    "remediation": 50,  # per hour
    "api": 100,         # per minute
    "llm": 100          # per day
}
```

**10× Strategy:** 
- Limits scale with plan tier (Enterprise gets 10× Starter)
- Redis-backed for distributed enforcement

### Horizontal Scaling

The API is stateless—no session affinity required:

```yaml
# kubernetes deployment
replicas: 3  # current
replicas: 30 # 10× (just add pods)
```

**Bottleneck:** Database connections (solved by pooling).

---

## 3. Compute Scaling

### Background Jobs

The distributed scheduler uses PostgreSQL SKIP LOCKED for safe concurrency:

```python
# No job duplication even with multiple workers
FOR UPDATE SKIP LOCKED
```

**10× Strategy:**
- Add more worker pods
- Each worker claims its own jobs
- Idempotency keys prevent duplicate execution

### Forecasting Limits

```python
# app/services/forecasting/prophet_forecaster.py
MAX_FORECAST_INPUT = 10_000_000  # 10M records max
```

**10× Strategy:**
- Bounded input prevents memory explosion
- Service-level decomposition (forecast EC2, RDS, S3 separately)
- Pre-aggregation reduces data volume

---

## 4. LLM Scaling

### Budget Enforcement

```python
# Pre-check BEFORE API call
budget_status = await usage_tracker.check_budget(tenant_id)
if budget_status == "exceeded":
    raise HTTPException(402, "LLM budget exceeded")
```

### Multi-Provider Failover

```python
PROVIDERS = [
    ("groq", "llama3-70b"),      # Primary (fast)
    ("openai", "gpt-4"),         # Fallback
    ("anthropic", "claude-3"),   # Fallback
]
```

**10× Strategy:**
- Circuit breaker per provider
- Automatic fallback on rate limit or error
- Cached insights (avoid redundant calls)

---

## 5. Storage Scaling

### Cost Per Record

| Field | Size |
|-------|------|
| UUID (id, tenant_id, account_id) | 48 bytes |
| Decimal (cost_usd, amount_raw) | 16 bytes |
| String (service, region) | ~50 bytes |
| Timestamp | 8 bytes |
| JSONB (tags, metadata) | ~100 bytes |
| **Total** | ~250 bytes |

**10× Math:**
- 10M records × 250 bytes = 2.5 GB
- 100M records × 250 bytes = 25 GB
- PostgreSQL handles 25 GB tables easily with partitioning

### Archival Strategy

```
cost_records_2025_* → Cold storage (S3)
cost_records_2026_* → Hot storage (PostgreSQL)
```

---

## 6. Monitoring at Scale

### Key Metrics

| Metric | Alert Threshold |
|--------|-----------------|
| Query latency (p95) | >200ms |
| Connection pool usage | >80% |
| Job queue depth | >1000 |
| Error rate | >1% |

### Observability Stack

- **Metrics:** Prometheus + Grafana
- **Tracing:** OpenTelemetry → Jaeger
- **Logs:** Structured JSON → Centralized logging

---

## 7. Cost of 10× Scale

### Infrastructure Estimate

| Component | Current | 10× |
|-----------|---------|-----|
| Database (Supabase Pro) | $25/mo | $50/mo |
| API Workers (3 pods) | $50/mo | $150/mo |
| Redis (Rate Limiting) | $20/mo | $40/mo |
| **Total** | ~$95/mo | ~$240/mo |

**Unit Economics:** Cost grows 2.5× for 10× load.

---

## Conclusion

Valdrix is already architected for scale:

1. **Partitioned database** for query performance
2. **Connection pooling** for concurrent users
3. **Rate limiting** for abuse prevention
4. **Bounded inputs** for memory safety
5. **Distributed jobs** for background processing
6. **Multi-provider LLM** for reliability

No major redesign required for 10× growth.
