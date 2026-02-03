# Deployment Guide

## Prerequisites

- Python 3.12+
- Docker & Docker Compose
- PostgreSQL (or Supabase)
- Redis (for caching/Celery)

---

## Local Development

```bash
# Clone and setup
git clone https://github.com/Valdrix-AI/valdrix.git
cd valdrix

# Install dependencies (using uv)
uv sync

# Copy environment file
cp .env.example .env

# Start services
docker-compose up -d

# Run migrations
uv run alembic upgrade head

# Start API
uv run uvicorn app.main:app --reload
```

---

## Docker Deployment

```bash
# Build
docker build -t valdrix/api:latest .

# Run
docker run -d \
  --name valdrix-api \
  -p 8000:8000 \
  --env-file .env \
  valdrix/api:latest
```

---

## Kubernetes Production

### Quick Start

```bash
# Apply all manifests
kubectl apply -f k8s/

# Verify deployment
kubectl get pods -l app=valdrix
kubectl get hpa
```

### Manifests

| File | Description |
|---|---|
| `k8s/deployment.yaml` | API + Worker pods |
| `k8s/service.yaml` | Internal services |
| `k8s/configmap.yaml` | Configuration |
| `k8s/hpa.yaml` | Autoscaling (3→20 replicas) |
| `k8s/ingress.yaml` | External access with TLS |

### Required Secrets

Create before deployment:
```bash
kubectl create secret generic valdrix-secrets \
  --from-literal=database-url='postgresql://...' \
  --from-literal=encryption-key='your-key' \
  --from-literal=openai-api-key='sk-...'
```

---

## Load Testing

Before production, validate performance:

```bash
# Install k6
brew install k6  # or apt/yum

# Run load test
k6 run loadtest/k6-test.js

# Expected results:
# - p95 latency < 500ms
# - Error rate < 1%
```

---

## Monitoring

### Prometheus Metrics
- Endpoint: `/metrics`
- Includes: request latency, error rates, active connections

### Health Check
- Endpoint: `/health`
- Returns: `{"status": "healthy"}`

---

## Production Checklist

- [ ] Secrets configured in Kubernetes
- [ ] TLS certificates deployed
- [ ] Database migrations run
- [ ] HPA tested under load
- [ ] Monitoring/alerting configured
- [ ] SBOM generated and reviewed
