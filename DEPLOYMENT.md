# Deployment Guide: Valdrix AI

> [!IMPORTANT]
> This guide covers the production deployment process for the Valdrix AI platform. Ensure all [Security Requirements](#security-best-practices) are met before proceeding.

## 1. Prerequisites
- Docker & Docker Compose
- PostgreSQL 16+ (or RDS/Cloud SQL)
- Redis 7+ (or Upstash/ElastiCache)
- AWS/Azure/GCP credentials with read-only access for scanning and specific remediation permissions.

## 2. Environment Configuration
Create a `.env` file based on [.env.example](file:///.env.example). Critical variables:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/valdrix

# Security
SECRET_KEY=generate_a_secure_random_string_here
CSRF_SECRET_KEY=generate_another_random_string

# Cloud Providers (Optional in env, preferred via encrypted DB storage)
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

## 3. Docker Deployment
We use a hardened, multi-stage Docker image for production.

### Building the Image
```bash
docker build -t valdrix:latest .
```

### Running with Docker Compose
Use [docker-compose.prod.yml](file:///docker-compose.prod.yml) for a production-like local setup:
```bash
docker-compose -f docker-compose.prod.yml up -d
```

## 4. Database Migrations
Always run migrations before starting the application:
```bash
docker exec -it valdrix_api alembic upgrade head
```

## 5. Security Best Practices
- **Non-Root User:** The Docker image runs as `appuser` by default. Do not override this.
- **Secret Management:** Use AWS Secrets Manager, HashiCorp Vault, or GitHub Secrets. Avoid plain-text `.env` in production.
- **Network Isolation:** Ensure the database and Redis are not publicly accessible.
- **Audit Logs:** Standardize on the `AuditLogger` for all sensitive operations (SOC2 compliance).

## 6. Monitoring & Health
- **Prometheus:** Metrics are exposed at `/metrics`.
- **Health Check:** Labeled health checks are at `/health`.
- **Logging:** Structured JSON logs are sent to `stdout`.

## 7. Troubleshooting
Check logs via:
```bash
docker logs -f valdrix_api
```
Common issues:
- `ConnectionRefusedError`: Verify DB/Redis connectivity.
- `403 Forbidden`: Check `SECRET_KEY` and CORS settings.
