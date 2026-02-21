# Valdrix Deployment Guide (Cloudflare Pages + Koyeb + Supabase)

Last verified: **2026-02-18**

This guide defines the current production path for Valdrix:
- Frontend: Cloudflare Pages (SvelteKit + Cloudflare adapter)
- API: Koyeb (FastAPI)
- Data/Auth: Supabase (PostgreSQL + Auth)
- Optional cache/rate-limit backend: Upstash Redis

## Architecture

```
Cloudflare Pages (dashboard.valdrix.ai)
            |
            | /api/edge/* (SvelteKit endpoint on Pages Functions) + direct API calls
            v
Koyeb (api.valdrix.ai, FastAPI)
            |
            | SQL + JWT verification
            v
Supabase (PostgreSQL + Auth)
```

Notes:
- The dashboard now includes an edge proxy endpoint: `dashboard/src/routes/api/edge/[...path]/+server.ts`.
- Core dashboard server loads and CSRF bootstrap use proxy URLs via `dashboard/src/lib/edgeProxy.ts`.
- Several feature routes still call `PUBLIC_API_URL` directly; edge coverage is selective, not global.

## Step 1: Supabase Setup

1. Create a Supabase project.
2. Copy the pooled Postgres URL (pooler endpoint).
3. Copy `SUPABASE_JWT_SECRET`.
4. Copy `PUBLIC_SUPABASE_URL` and `PUBLIC_SUPABASE_ANON_KEY` for dashboard runtime.

## Step 2: Required Secrets

Generate and store:

```bash
openssl rand -hex 32   # ENCRYPTION_KEY
openssl rand -hex 16   # ADMIN_API_KEY
openssl rand -hex 32   # CSRF_SECRET_KEY
openssl rand -base64 32 # KDF_SALT (must decode to exactly 32 bytes)
```

Also create:
- `GROQ_API_KEY` (if using managed Groq for low-cost/default LLM)

## Step 3: Deploy API to Koyeb

1. Create a Koyeb web service from this repository.
2. Use Docker build from project `Dockerfile`.
3. Set port `8000`.
4. Configure environment variables:

| Variable | Example | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql://...` | Supabase pooled URL |
| `SUPABASE_JWT_SECRET` | `...` | Supabase JWT secret |
| `CSRF_SECRET_KEY` | `...` | >=32 chars, non-default |
| `ENCRYPTION_KEY` | `...` | 64-char hex |
| `KDF_SALT` | `...` | Base64, decodes to 32 bytes |
| `ADMIN_API_KEY` | `...` | Admin secret |
| `LLM_PROVIDER` | `groq` | Default managed provider |
| `GROQ_API_KEY` | `gsk_...` | If not BYOK-only |
| `CORS_ORIGINS` | `["https://dashboard.valdrix.ai"]` | Must match dashboard origin |
| `SAAS_STRICT_INTEGRATIONS` | `true` | Recommended |
| `UPSTASH_REDIS_URL` | `https://...` | Optional |
| `UPSTASH_REDIS_TOKEN` | `...` | Optional |
| `PAYSTACK_DEFAULT_CHECKOUT_CURRENCY` | `NGN` | Checkout settlement currency default (`NGN` or `USD`) |
| `PAYSTACK_ENABLE_USD_CHECKOUT` | `false` | Set `true` to allow USD checkout requests |
| `ENCRYPTION_KEY_CACHE_TTL_SECONDS` | `3600` | Encryption key-cache TTL in seconds |
| `ENCRYPTION_KEY_CACHE_MAX_SIZE` | `1000` | Max cached derived-key entries |
| `LLM_FAIR_USE_GUARDS_ENABLED` | `false` | Keep disabled until rollout criteria are met |
| `LLM_FAIR_USE_PRO_DAILY_SOFT_CAP` | `1200` | Optional; only used when fair-use guards are enabled |
| `LLM_FAIR_USE_ENTERPRISE_DAILY_SOFT_CAP` | `4000` | Optional; only used when fair-use guards are enabled |
| `LLM_FAIR_USE_PER_MINUTE_CAP` | `30` | Optional; only used when fair-use guards are enabled |
| `LLM_FAIR_USE_PER_TENANT_CONCURRENCY_CAP` | `4` | Optional; only used when fair-use guards are enabled |
| `LLM_FAIR_USE_CONCURRENCY_LEASE_TTL_SECONDS` | `180` | Optional; lease self-heal window |

5. Deploy and record your service URL.
6. Run runtime preflight against the deployment env contract before traffic cutover:

```bash
uv run python scripts/validate_runtime_env.py --environment production
```

If `prophet` is intentionally not bundled in production/staging, set all of:
- `FORECASTER_ALLOW_HOLT_WINTERS_FALLBACK=true`
- `FORECASTER_BREAK_GLASS_REASON=<ticket/incident reference>`
- `FORECASTER_BREAK_GLASS_EXPIRES_AT=<ISO-8601 UTC, future timestamp>`

## Step 4: Run Database Migrations

Run after backend env vars are configured:

```bash
uv run alembic upgrade head
```

If `uv alembic` fails in your shell, use:

```bash
.venv/bin/alembic upgrade head
```

Confirm migration state:

```bash
uv run alembic heads
uv run alembic current
```

## Step 5: Deploy Dashboard to Cloudflare Pages

The dashboard is now configured for Cloudflare runtime via `@sveltejs/adapter-cloudflare`.

1. In Cloudflare Pages, connect this repository.
2. Set **Root directory** to `dashboard`.
3. Set build config:
   - **Build command**: `pnpm run build`
   - **Build output directory**: `.svelte-kit/cloudflare`
4. Set runtime environment variables:

| Variable | Example |
|---|---|
| `PUBLIC_API_URL` | `https://api.valdrix.ai` |
| `PRIVATE_API_ORIGIN` | `https://api.valdrix.ai` |
| `PUBLIC_SUPABASE_URL` | `https://<project-ref>.supabase.co` |
| `PUBLIC_SUPABASE_ANON_KEY` | `<anon-key>` |

`PRIVATE_API_ORIGIN` is used server-side by the edge proxy endpoint so upstream origin resolution is explicit and not dependent on public URL parsing.

5. Deploy and record your Pages URL.
6. Add custom domain `dashboard.valdrix.ai` (or your preferred domain).
7. Update Koyeb `CORS_ORIGINS` to the final dashboard URL.

## Step 6: Verify Deployment

1. API health check:

```bash
curl -fsS https://api.valdrix.ai/health
```

2. Dashboard auth flow:
- Open dashboard URL
- Sign in
- Confirm dashboard routes load

3. API connectivity from dashboard:
- Confirm subscription/profile requests succeed

4. Fair-use guardrails (if explicitly enabled):
- Confirm 429 responses include `llm_fair_use_exceeded` when limits are hit.
- Confirm metrics emit:
  - `valdrix_ops_llm_fair_use_denials_total`
  - `valdrix_ops_llm_fair_use_evaluations_total`
  - `valdrix_ops_llm_fair_use_observed`
- Confirm tenant-scoped runtime visibility endpoint responds:
  - `GET /api/v1/admin/health-dashboard/fair-use` (admin-authenticated)
- Confirm no CORS errors in browser console

5. Edge proxy connectivity:

```bash
curl -i https://dashboard.valdrix.ai/api/edge/health/live
```

Expect `x-valdrix-edge-proxy: 1` on the response.

## Troubleshooting

### `Multiple head revisions are present`
Use:

```bash
uv run alembic heads
```

If more than one head appears, merge revisions first, then rerun upgrade.

### Cloudflare build fails with missing adapter
Install dashboard dependencies and ensure the adapter exists:

```bash
pnpm --dir dashboard install
pnpm --dir dashboard build
```

### CORS failures
- Ensure exact scheme + host in `CORS_ORIGINS`
- Avoid wildcard origins in production

### Edge proxy upstream resolution failure
- Ensure `PRIVATE_API_ORIGIN` is set on Cloudflare Pages runtime.
- Confirm upstream API origin is reachable from Pages Functions.

## Provider Limits Snapshot (for planning)

Verified against official docs on **2026-02-18**:

| Provider | Free-tier point relevant to this stack |
|---|---|
| Cloudflare Pages | 500 builds/month; custom domains are capped per project |
| Cloudflare Pages/Workers | Static asset delivery and Functions are governed by Pages + Workers limits |
| Upstash Redis | Free plan uses monthly request/command quota (not 10K/day legacy claim) |
| Vercel Hobby | Not suitable for commercial production usage per fair-use policy |
| Koyeb Starter | Free starter exists; onboarding requires credit card |

Always re-check limits before external/customer claims.

## Sources

- Cloudflare Pages limits: https://developers.cloudflare.com/pages/platform/limits/
- Cloudflare Pages Functions pricing: https://developers.cloudflare.com/pages/functions/pricing/
- Cloudflare Workers pricing: https://developers.cloudflare.com/workers/platform/pricing/
- Cloudflare SvelteKit guide: https://developers.cloudflare.com/pages/framework-guides/deploy-a-svelte-kit-site/
- SvelteKit Cloudflare adapter: https://kit.svelte.dev/docs/adapter-cloudflare
- Upstash Redis pricing: https://upstash.com/pricing/redis
- Supabase pricing: https://supabase.com/pricing
- Koyeb pricing: https://www.koyeb.com/pricing/
- Vercel limits: https://vercel.com/docs/limits
- Vercel fair-use: https://vercel.com/docs/limits/fair-use-guidelines
