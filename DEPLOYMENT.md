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
git clone https://github.com/Valdrics/valdrics.git
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
# Add the helm chart (if using a repo) or use the local one
helm upgrade --install valdrix ./helm/valdrix --namespace valdrix --create-namespace

# Verify deployment
kubectl get pods -n valdrix -l app.kubernetes.io/name=valdrix
```

### Helm Chart Structure

| Component | Description |
|---|---|
| `templates/deployment.yaml` | API + Worker pods |
| `templates/service.yaml` | Internal services |
| `templates/configmap.yaml` | Configuration |
| `templates/hpa.yaml` | Autoscaling (3→20 replicas) |
| `templates/ingress.yaml` | External access with TLS |

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
