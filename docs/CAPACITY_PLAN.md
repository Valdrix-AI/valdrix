# Valdrics Capacity Plan (2026)

This plan outlines the infrastructure targets for scaling the platform.

## 1. Metric Targets

| Tier | Users | DB Size | Req/sec | AWS Adapters |
| --- | --- | --- | --- | --- |
| **Startup** | 100 - 1k | 10GB | 50 | 1k |
| **Growth** | 1k - 10k | 100GB | 500 | 10k |
| **Enterprise**| 10k - 100k| 1TB | 5k | 100k |

## 2. Scaling Strategies

### Database (Neon/Supabase)
- **Current**: Single instance, Supavisor pooling.
- **10k Users**: Enable read replicas for reporting/analytics query load and implement partition pruning on `audit_logs` by `created_at`.
- **100k Users**: Shard by `tenant_id` or migrate to Citus for horizontal scale.

### Compute Workloads (Analyzers)
- **Current**: APScheduler on single backend instance.
- **1k+ Users**: Migrate background jobs to a distributed queue (Celery/Temporal).
- **Auto-Scaling**: Horizontal Pod Autoscaling (HPA) based on CPU and job queue depth.

### LLM Consumption
- **Strategy**: Leverage the **LLM Provider Waterfall** to prevent 429 errors.
- **Cache**: Increase Redis cache TTL for repeated analysis results.
