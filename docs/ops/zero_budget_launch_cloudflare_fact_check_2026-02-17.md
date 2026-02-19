# Zero-Budget Launch with Cloudflare Pages - Fact Check and Required Actions

Validated on **February 18, 2026** against:
- Current codebase state in this repository.
- Official provider docs/pricing pages linked at the end.

## Executive Summary

Cloudflare Pages is a valid frontend hosting option for zero-budget launch, but the feedback includes multiple incorrect or unproven claims. The biggest remaining gap is **evidence scope**: the repository now includes an edge proxy path for selected routes, but broad "75-80% backend load reduction" and "100 concurrent users across real workloads" claims are still not proven by full-path production benchmarks.

## What Is Factually Correct

- The dashboard is SvelteKit and can be deployed to Cloudflare Pages with `@sveltejs/adapter-cloudflare`.
- Cloudflare Pages Free includes 500 builds/month and static assets are not billed by bandwidth/request count.
- Cloudflare Functions usage on free tier is governed by Workers free limits.
- Supabase + Koyeb + Upstash + Cloudflare Pages can be combined for a $0 infra starting point.

## What Is Incorrect or Not Proven

- `Upstash Redis Free = 10K commands/day` is outdated.
  - Current public pricing is **500,000 commands/month**.
- `Cloudflare custom domains = unlimited` is incorrect.
  - Current limit is **100 custom domains per project**.
- `Vercel custom domains = 1 per project` is incorrect.
  - Current limits page shows **50 domains per project**.
- `Vercel free = 100GB/month` is incomplete/outdated framing.
  - Current limits/fair-use framing for Hobby includes **100 GB Fast Data Transfer/month** with separate included compute quotas (for example active CPU/provisioned memory/invocations/build execution), not a single "100 GB-hours function execution" line item.
- For commercial production usage, Vercel Hobby is not suitable.
  - Current fair-use guidance states commercial usage requires Pro or Enterprise.
- `$0 on Koyeb` is possible but needs onboarding caveat.
  - Current Koyeb pricing FAQ states Starter is free but requires a credit card.
- `Cloudflare Pages reduces Koyeb load by 75-80%` is still not proven.
  - The repository now has an edge proxy/cache path for selected routes, but not full dashboard/API coverage and no measured cache hit-rate evidence for that claim.
- `Yes, architecture can handle 100 concurrent users` remains unproven for production workloads.
  - Local liveness evidence at 100 concurrency now passes, but that does not prove full authenticated dashboard/API workload capacity.

## Repository Evidence (Current State)

- Dashboard is now configured for Cloudflare adapter:
  - `dashboard/svelte.config.js:1`
  - `dashboard/svelte.config.js:12`
  - `dashboard/package.json:25`
- Most app routes are authenticated/non-public:
  - `dashboard/src/hooks.server.ts:63`
  - `dashboard/src/lib/routeProtection.ts:3`
- Authenticated HTML is explicitly marked `Cache-Control: no-store`:
  - `dashboard/src/hooks.server.ts:82`
  - `dashboard/src/hooks.server.ts:85`
- Edge proxy/cache path now exists and is used in selected flows:
  - `dashboard/src/lib/edgeProxy.ts:1`
  - `dashboard/src/routes/api/edge/[...path]/+server.ts:1`
  - `dashboard/src/routes/+layout.server.ts:26`
  - `dashboard/src/routes/+page.ts:49`
  - `dashboard/src/lib/api.ts:60`
- Many feature routes still call `PUBLIC_API_URL` directly, so backend-load reduction claims must remain conservative:
  - `dashboard/src/routes/settings/+page.svelte:97`
  - `dashboard/src/routes/ops/+page.svelte:633`
  - `dashboard/src/routes/connections/+page.svelte:436`
- Historical evidence artifacts from 2026-02-15 are empty placeholders:
  - `reports/acceptance/20260215T084156Z/performance_load_test_evidence.json:1`
- Non-empty benchmark evidence now exists from 2026-02-18:
  - `reports/acceptance/20260218T185609Z/performance_load_test_evidence.json:1`
  - Result summary (100 concurrent users, 30s, `/health` + `/api/v1/public/csrf`): p95 `12.4233s`, p99 `18.9147s`, throughput `13.3468 rps`, error rate `24.5509%`, `meets_targets=false`.
  - Interpretation caveat: this mixes deep dependency health (`/health`) into user-capacity evidence. Updated load-test profiles now default to `/health/live` and include preflight validation.
- Updated baseline evidence (liveness profile) is now passing at 100 concurrent users:
  - `reports/acceptance/20260218T204814Z/performance_load_test_evidence.json:1`
  - Result summary (3 rounds, 20s each, `/health/live`): worst p95 `0.3144s`, error rate `0.0%`, throughput floor `363.0399 rps`, `meets_targets=true`.
  - Scope caveat: this validates liveness-path concurrency, not full authenticated dashboard/API workload capacity.

## Required Actions (Documented Work)

1. Deployment documentation correction: completed.
   - `docs/DEPLOYMENT.md` now uses Cloudflare Pages as the default frontend path and includes provider-source links.

2. Frontend hosting policy decision: completed.
   - Deployment policy now explicitly targets Cloudflare Pages for production frontend hosting.

3. Cloudflare adapter migration: completed and validated.
   - Added `@sveltejs/adapter-cloudflare` in `dashboard/package.json`.
   - Switched SvelteKit adapter to Cloudflare in `dashboard/svelte.config.js`.
   - Validation evidence: `pnpm --dir dashboard check` and `pnpm --dir dashboard build` both pass on 2026-02-18.

4. Edge proxy/cache design and initial implementation: partially completed.
   - Completed: dashboard-side edge proxy endpoint implemented at `/api/edge/[...path]`.
   - Completed: selected dashboard routes now use proxy path and conservative caching policy.
   - Remaining: expand coverage route-by-route and publish cache hit-rate/load evidence before any backend reduction claim.

5. Produce real performance evidence before capacity claims: partially completed.
   - Completed: non-empty artifact generated with p50/p95/p99, throughput, and error rate.
   - Completed: load-test tool now forwards configured headers (`app/shared/core/performance_testing.py`) and has regression tests (`tests/unit/core/test_performance_testing.py`).
   - Remaining: collect deployed-stack benchmark evidence that meets declared SLO thresholds before publishing any concurrency claim.

## Recommendation (As of 2026-02-18)

Recommended launch path:

1. Use Cloudflare Pages for the dashboard.
   - This is a cost/distribution optimization (frontend delivery), not proof of higher API concurrency.

2. Keep backend topology unchanged for MVP.
   - API on Koyeb, DB/Auth on Supabase, Redis on Upstash.
   - Edge proxy exists for selected routes, but do not claim broad edge-caching-driven scale gains until route coverage and cache hit-rate evidence are published.

3. Treat "100 concurrent users" as a test target, not a published capability claim.
   - Publish that claim only after collecting and storing real load-test evidence from deployed infrastructure.

4. Document limits with provider-official numbers only and date-stamp them.
   - Re-verify limits before investor/customer-facing communication.

5. Phase 2 (post-MVP): expand selective edge proxy/cache for safe read endpoints.
   - Extend proxy adoption across additional read-heavy dashboard routes.
   - Keep authenticated user HTML/API flows conservative (`no-store` by default).
   - Re-benchmark and then update capacity statements.

Decision rule for go-live:
- `Go` when adapter migration validation passes (`dashboard` install/check/build) and deployment docs are corrected.
- `No-Go` for any public scale claims until benchmark artifacts are non-empty, reproducible, and meet agreed latency/error thresholds.

## Recommended Claim Language (Safe/Accurate)

Use this wording in external/internal launch docs:
- "Cloudflare Pages can reduce static asset delivery cost and improve global asset latency."
- "API capacity and concurrent user claims require measured load-test evidence on the target deployment."
- "Current implementation includes a selective edge API proxy/cache layer; broad scale-impact claims require measured cache hit-rate and workload benchmarks."

## Sources

- Cloudflare Pages limits: https://developers.cloudflare.com/pages/platform/limits/
- Cloudflare Pages Functions pricing (static asset requests): https://developers.cloudflare.com/pages/functions/pricing/
- Cloudflare Workers pricing (free limits): https://developers.cloudflare.com/workers/platform/pricing/
- Cloudflare + SvelteKit guide: https://developers.cloudflare.com/pages/framework-guides/deploy-a-svelte-kit-site/
- Upstash Redis pricing: https://upstash.com/pricing/redis
- Supabase pricing: https://supabase.com/pricing
- Koyeb pricing: https://www.koyeb.com/pricing/
- Vercel limits: https://vercel.com/docs/limits
- Vercel fair-use guidelines: https://vercel.com/docs/limits/fair-use-guidelines
- Grafana Cloud plans: https://grafana.com/support/plans/
- Sentry pricing: https://sentry.io/pricing/
- Groq pricing: https://console.groq.com/docs/pricing
