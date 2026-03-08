# Valdrics Capacity Plan (2026)

This plan outlines the infrastructure targets for scaling the platform.

It assumes the repository-managed `Helm + Terraform (AWS/EKS)` profile as the
primary scale path. The `Cloudflare Pages + Koyeb` profile remains a supported
managed-platform deployment surface, but it is not the primary basis for the
high-scale targets below.

## 1. Metric Targets

| Tier | Users | DB Size | Req/sec | AWS Adapters |
| --- | --- | --- | --- | --- |
| **Startup** | 100 - 1k | 10GB | 50 | 1k |
| **Growth** | 1k - 10k | 100GB | 500 | 10k |
| **Enterprise**| 10k - 100k| 1TB | 5k | 100k |

## 2. Scaling Strategies

### Database (PostgreSQL / AWS RDS profile)
- **Current**: Multi-AZ relational database with connection-pool budgeting enforced at the application layer.
- **10k Users**: Introduce read scaling for analytics/reporting and continue partition/index governance for high-volume tables.
- **100k Users**: Move large analytical workloads off the primary OLTP path or introduce a horizontally scalable analytical store.

### Compute Workloads (API + Workers)
- **Current**: FastAPI API replicas plus Celery workers with Redis-backed coordination.
- **Managed PaaS profile**: `koyeb.yaml` and `koyeb-worker.yaml` must be deployed together; the API manifest alone is not a supported runtime topology.
- **1k+ Users**: Scale API and worker pools independently and keep scheduler-driven sweeps bounded.
- **Auto-Scaling**: Horizontal Pod Autoscaling (HPA) based on CPU and queue depth when running the Helm profile.

### LLM Consumption
- **Strategy**: Leverage the **LLM Provider Waterfall** to prevent 429 errors.
- **Cache**: Increase Redis cache TTL for repeated analysis results.
