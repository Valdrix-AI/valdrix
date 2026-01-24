# Valdrix: AI Coding Instructions

## Project Summary

**Valdrix** is a multi-cloud FinOps & GreenOps intelligence platform that detects cloud waste, optimizes costs, and provides AI-powered recommendations. It's a FastAPI backend + SvelteKit frontend deployed across Supabase (database), Koyeb (API), and Vercel (dashboard).

**Tech Stack:**

- Backend: FastAPI 0.115+, Python 3.12+, SQLAlchemy 2.0 (async), Pydantic
- Frontend: SvelteKit 5, Svelte, TypeScript, Vite
- Database: PostgreSQL (Supabase) with RLS & Alembic migrations
- Multi-Cloud: AWS, Azure, GCP (STS-based temporary credentials)
- LLM: OpenAI, Claude, Groq, Gemini (pluggable via LangChain)

---

## Critical Architecture Patterns

### 1. **Plugin-Based Zombie Detection System**

The system detects 11 types of AWS waste using an abstract plugin pattern:

```
ZombiePlugin (ABC base class)
├── Compute: IdleInstancesPlugin, OrphanLoadBalancersPlugin
├── Storage: UnattachedVolumesPlugin, OldSnapshotsPlugin, IdleS3BucketsPlugin
├── Database: IdleRdsPlugin, ColdRedshiftPlugin
├── Network: UnusedElasticIpsPlugin, UnderusedNatGatewaysPlugin
├── Containers: LegacyEcrImagesPlugin
└── Analytics: IdleSageMakerPlugin
```

**Key Pattern:** Each plugin:

- Implements `async def scan(...)` returning `List[Dict[str, Any]]`
- Has a `category_key` property (e.g., `"idle_instances"`)
- Receives STS temporary credentials (no long-lived keys)
- Uses pricing from [ESTIMATED_COSTS dict](app/services/zombies/zombie_plugin.py#L7) for impact calculation

**When extending:** Copy an existing plugin, override `category_key` and `scan()`, register in [detector.py](app/services/zombies/detector.py).

### 2. **Async Database with RLS (Row Level Security)**

Every database operation is async and tenant-isolated:

```python
# Database session automatically sets tenant context for RLS
async def get_db(request: Request):
    # Sets: app.current_tenant_id in PostgreSQL session
    # Enables: WHERE tenant_id = current_setting('app.current_tenant_id')
```

**Critical Details:**

- Sessions use `expire_on_commit=False` (async lazy-load prevention)
- Slow query warnings log queries >200ms to structlog
- Connection pooling: `pool_size=10, max_overflow=20, pool_recycle=300s` (Supavisor compatible)
- Encryption: StringEncryptedType(AES-256) for sensitive fields like `Tenant.name`
- Migrations: Use Alembic (`alembic/versions/`), run with `alembic upgrade head`

See: [app/db/session.py](app/db/session.py), [app/models/tenant.py](app/models/tenant.py)

### 3. **Multi-Tenant STS-Based Cloud Access**

No long-lived AWS credentials stored; instead:

```python
# Each request assumes an IAM role with temporary creds
credentials = {
    "AccessKeyId": "ASIA...",
    "SecretAccessKey": "...",
    "SessionToken": "..."  # 15-min expiry
}
detector = ZombieDetector(credentials=credentials)
```

**Security implications:**

- Principle of least privilege: IAM role is read-only
- Each tenant has separate AWS account or role
- Azure/GCP adapters follow same pattern

### 4. **LLM Analysis as a Service**

Multi-model LLM support via [LangChain](app/services/llm/):

```python
# Pluggable: OpenAI, Claude, Groq, Gemini
# Selection: LLM_PROVIDER env var (openai|anthropic|groq|gemini)
# Budget control: LLMBudget model tracks spend per tenant
```

The analyzer receives raw zombie data and generates human-readable insights with cost implications.

---

## Critical Workflows

### Running Tests

```bash
# All tests with coverage report (HTML in htmlcov/)
pytest --cov=app --cov-report=html

# Single file
pytest tests/test_zombie_detector.py -v

# Async tests: configured auto-mode in pyproject.toml
# No manual @pytest.mark.asyncio needed
```

**Test patterns:**

- Mock AWS clients with `AsyncMock`
- Test both plugin interface compliance and individual scan logic
- See [tests/test_zombie_detector.py](tests/test_zombie_detector.py) for examples

**CRITICAL:** Before committing, check for these anti-patterns:

- Scheduler logic that holds DB transactions longer than needed (→ deadlock at scale)
- LLM calls without pre-request token budgeting (→ runaway spend)
- Scan endpoints without explicit timeouts (→ customer thread starvation)
- Multi-tenant queries without RLS context verification (→ data leakage risk)

### Local Development

```bash
# 1. Activate venv (already done in this shell)
source .venv/bin/activate

# 2. Start services: FastAPI + PostgreSQL + Prometheus + Grafana
docker-compose up

# 3. Run API server (auto-reloads)
uvicorn app.main:app --reload

# 4. Access dashboard on localhost:3000
# API on localhost:8000/docs (OpenAPI/Swagger)
```

### Database Migrations

```bash
# Create migration (after model changes)
alembic revision --autogenerate -m "description"

# Apply to local DB
alembic upgrade head

# Downgrade (careful in prod)
alembic downgrade -1
```

### Building & Deployment

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for production deployment (Supabase + Koyeb + Vercel).

---

## Project-Specific Conventions

### 1. **Error Handling & Logging**

- Use `structlog` for all logging (not `print()` or `logging`)
- Custom exceptions inherit from `ValdrixException` (see [app/core/exceptions.py](app/core))
- HTTP 422: validation errors, 400: business logic, 401/403: auth/permission

Example:

```python
from app.core.exceptions import ValdrixException
import structlog

logger = structlog.get_logger()

async def some_operation():
    try:
        ...
    except SomeError as e:
        logger.warning("operation_failed", error=str(e), tenant_id=tenant_id)
        raise ValdrixException("User-friendly message") from e
```

### 2. **Security Validation (see app/core/config.py)**

- **Production checks:** CSRF key, encryption key (32+ chars), ADMIN_API_KEY all required
- **CORS:** No `localhost` in production
- **Database:** SSL mode required (`require`, `verify-ca`, `verify-full`); no plaintext passwords
- **Secrets:** Use environment variables, never hardcode; encrypt sensitive DB fields

### 3. **API Response Format**

All endpoints return Pydantic models. Structure:

```python
from pydantic import BaseModel

class ZombieResponse(BaseModel):
    category: str
    resource_id: str
    estimated_monthly_savings: float
    remediation_steps: list[str]
```

Use `response_model` in route definitions for OpenAPI docs.

### 4. **Async Patterns**

Everything is async:

- `async def` for all DB, AWS, LLM operations
- Use `aioboto3` (not `boto3`) for AWS
- No blocking I/O inside async functions
- Connection context managers: `async with session.begin():` for transactions

### 5. **Configuration Management**

All settings in [app/core/config.py](app/core/config.py) using Pydantic `BaseSettings`:

- Environment-aware: `local`, `development`, `staging`, `production`
- Validation at startup (fail-fast if DATABASE_URL missing, ENCRYPTION_KEY too short, etc.)
- Used via: `settings = get_settings()` (cached with `@lru_cache`)

### 6. **Code Organization**

```
app/
├── api/v1/          # Route handlers (organized by feature: zombies/, costs/, etc.)
├── models/          # SQLAlchemy ORM models
├── schemas/         # Pydantic request/response models
├── services/        # Business logic
│   ├── zombies/     # Plugin detector + individual plugins
│   ├── llm/         # LLM analysis
│   ├── aws/         # AWS service adapters
│   └── ...
├── core/            # Config, security, logging, middleware
└── db/              # Database session & migrations (alembic/)
```

Routes import dependencies via FastAPI `Depends()` (see get_db pattern).

---

## Integration Points & External Dependencies

| System                           | Purpose         | Auth Method                          |
| -------------------------------- | --------------- | ------------------------------------ |
| **AWS**                          | Cloud scanning  | STS AssumeRole (temp creds)          |
| **Azure**                        | Cloud scanning  | Managed Identity / Service Principal |
| **GCP**                          | Cloud scanning  | Service Account JSON                 |
| **Supabase**                     | Database + Auth | PostgreSQL + JWT                     |
| **OpenAI/Anthropic/Groq/Gemini** | LLM analysis    | API keys from LLM_PROVIDER           |
| **Slack**                        | Notifications   | Webhook URL                          |
| **Prometheus**                   | Metrics         | Scrapes FastAPI `/metrics`           |

**Key Files:**

- [app/services/adapters/](app/services/adapters/) — cloud provider adapters
- [app/services/llm/](app/services/llm/) — LLM integration
- [app/core/config.py](app/core/config.py) — all env var requirements

---

## File Navigation Quick Reference

| Task                  | File                                                        |
| --------------------- | ----------------------------------------------------------- |
| Add new zombie plugin | `app/services/zombies/aws_provider/plugins/`                |
| Add API endpoint      | `app/api/v1/{feature}/`                                     |
| Add database model    | `app/models/{entity}.py` + alembic migration                |
| Adjust security rules | `app/core/config.py` (validation), `app/services/security/` |
| Update LLM behavior   | `app/services/llm/analyzer.py`                              |
| Configure monitoring  | `prometheus/prometheus.yml`, `docker-compose.yml`           |
| Frontend (dashboard)  | `dashboard/src/` (SvelteKit)                                |

---

## Common Pitfalls & How to Avoid

1. **Long-lived DB transactions in scheduler** — The scheduler's `cohort_analysis_job` must NOT hold transactions while iterating tenants. Move job insertion outside the transaction to prevent deadlocks at >100 tenants.

2. **LLM calls without pre-authorization** — Every LLM request must check available budget BEFORE calling the API. Current code tracks spend post-hoc, causing runaway costs.

3. **Scan endpoints without timeouts** — `scan_zombies` endpoint can block forever if AWS API stalls. Add 5-minute hard timeout and stream partial results.

4. **Missing RLS verification** — Not all endpoints enforce tenant isolation via `require_tenant_access`. Services that create new sessions bypass RLS. Audit this regularly.

5. **Slow queries** — Queries >200ms log warnings; add database indexes for new WHERE clauses. Watch for N+1 on large result sets (zombie scans with 1000+ resources).

6. **Test isolation** — Use `NullPool` in testing mode; mock AWS clients with `AsyncMock`. Integration tests against real AWS will fail silently or cost money.

7. **Silent scheduler failures** — Background jobs can silently fail. No alerting for stuck jobs (>1 hour in PENDING state). Add Prometheus metrics.

See [.github/CTO_TECHNICAL_REVIEW.md](.github/CTO_TECHNICAL_REVIEW.md) for deeper analysis of scale-blocking issues.

---

## When Stuck

1. **Architecture questions** → Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
2. **Deployment/ops issues** → See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) & [docs/RUNBOOKS.md](docs/RUNBOOKS.md)
3. **Plugin implementation** → Copy from existing plugin in `app/services/zombies/aws_provider/plugins/`
4. **API endpoint structure** → Check similar route in `app/api/v1/`
5. **Database model questions** → Review `app/models/tenant.py` (encryption example) or `app/models/aws_connection.py` (relationships)
