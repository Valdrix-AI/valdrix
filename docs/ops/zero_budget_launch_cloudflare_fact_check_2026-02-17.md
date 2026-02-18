# Zero-Budget Launch with Cloudflare Pages - Fact Check and Required Actions

Validated on **February 18, 2026** against:
- Current codebase state in this repository.
- Official provider docs/pricing pages linked at the end.

## Executive Summary

Cloudflare Pages is a valid frontend hosting option for zero-budget launch, but the feedback includes multiple incorrect or unproven claims. The biggest gap is architectural: the current dashboard calls the API directly, so moving frontend hosting to Cloudflare Pages alone does **not** produce the claimed 75-80% backend load reduction.

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
- `Cloudflare Pages reduces Koyeb load by 75-80%` is not supported by current code behavior.
  - This repository does not currently route dashboard API calls through Cloudflare edge proxy/cache.
- `Yes, architecture can handle 100 concurrent users` remains unproven by stored benchmark evidence.
  - Existing captured performance evidence files are empty (`items: []`).

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
- API calls are direct to `PUBLIC_API_URL` from browser/server code (not Cloudflare edge proxy):
  - `dashboard/src/lib/api.ts:11`
  - `dashboard/src/lib/api.ts:62`
  - `dashboard/src/routes/+layout.server.ts:8`
- Stored load-test evidence is currently empty:
  - `reports/acceptance/20260215T084156Z/performance_load_test_evidence.json:1`

## Required Actions (Documented Work)

1. Deployment documentation correction: completed.
   - `docs/DEPLOYMENT.md` now uses Cloudflare Pages as the default frontend path and includes provider-source links.

2. Frontend hosting policy decision: completed.
   - Deployment policy now explicitly targets Cloudflare Pages for production frontend hosting.

3. Cloudflare adapter migration: completed and validated.
   - Added `@sveltejs/adapter-cloudflare` in `dashboard/package.json`.
   - Switched SvelteKit adapter to Cloudflare in `dashboard/svelte.config.js`.
   - Validation evidence: `pnpm --dir dashboard check` and `pnpm --dir dashboard build` both pass on 2026-02-18.

4. If backend-load reduction is a goal, add explicit edge proxy/cache design.
   - Introduce dashboard-side server endpoints or Worker proxy for selected cacheable GET routes.
   - Keep authenticated/no-store flows uncached by default.
   - Define route-by-route caching policy with TTL and auth constraints.

5. Produce real performance evidence before capacity claims.
   - Run k6/Locust against deployed stack.
   - Store non-empty evidence artifacts.
   - Report p50/p95/p99 latency, error rate, and throughput for declared concurrency levels.

## Recommendation (As of 2026-02-18)

Recommended launch path:

1. Use Cloudflare Pages for the dashboard.
   - This is a cost/distribution optimization (frontend delivery), not proof of higher API concurrency.

2. Keep backend topology unchanged for MVP.
   - API on Koyeb, DB/Auth on Supabase, Redis on Upstash.
   - Do not claim edge-caching-driven API scale gains until an actual edge proxy/cache layer exists.

3. Treat "100 concurrent users" as a test target, not a published capability claim.
   - Publish that claim only after collecting and storing real load-test evidence from deployed infrastructure.

4. Document limits with provider-official numbers only and date-stamp them.
   - Re-verify limits before investor/customer-facing communication.

5. Phase 2 (post-MVP): add selective edge proxy/cache for safe read endpoints.
   - Start with non-sensitive, cacheable GET endpoints.
   - Keep authenticated user HTML/API flows conservative (`no-store` by default).
   - Re-benchmark and then update capacity statements.

Decision rule for go-live:
- `Go` when adapter migration validation passes (`dashboard` install/check/build) and deployment docs are corrected.
- `No-Go` for any public scale claims until benchmark artifacts are non-empty and reproducible.

## Recommended Claim Language (Safe/Accurate)

Use this wording in external/internal launch docs:
- "Cloudflare Pages can reduce static asset delivery cost and improve global asset latency."
- "API capacity and concurrent user claims require measured load-test evidence on the target deployment."
- "Current implementation does not yet include an edge API proxy/cache layer."

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
