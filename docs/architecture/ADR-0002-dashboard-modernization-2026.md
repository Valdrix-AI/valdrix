# ADR-0002: Dashboard Modernization (2026 Frontend Standards)

- Status: Accepted
- Date: February 14, 2026
- Owners: Frontend, Platform, Security

## Context

The Valdrix dashboard is a core product surface and must meet modern expectations for:

- performance (fast navigations, predictable budgets, good Core Web Vitals)
- security (strong headers/CSP, safe auth/session handling, dependency auditing)
- reliability (timeouts, resilient fetch, stable tests)
- maintainability (strict typing, component separation, consistent tooling)

The codebase must remain production-ready and work in both local development and CI.

## Decision

Modernize the `dashboard/` frontend around an actively maintained, ESM-first toolchain:

- Framework/tooling:
  - SvelteKit + Svelte 5 (runes) with Vite as the bundler
  - Node adapter for production deployments
  - Strict TypeScript (`strict: true`) and Svelte typechecking (`svelte-check`)
- Performance:
  - lazy-load heavy client-only libraries (for example Chart.js) via dynamic imports
  - enforce bundle-size performance budgets as a CI gate
  - avoid blocking navigations on slow API calls by moving non-critical hydration client-side
- Security:
  - baseline security headers in `dashboard/src/hooks.server.ts`
  - CSP directives in `dashboard/svelte.config.js`
  - dependency auditing in CI (`pnpm audit --audit-level=high`)
- Quality gates:
  - CI job to run dashboard lint, typecheck, unit tests, build, and bundle budgets
  - Playwright E2E uses a reproducible backend webServer command (uv/uvicorn)

## Rationale

- SvelteKit/Vite provide maintained, fast builds with modern ESM output and good tree-shaking.
- Strict TS + linting + unit tests reduce regressions and epistemic debt.
- Lazy loading + performance budgets prevent gradual bundle bloat that harms Core Web Vitals.
- Security headers/CSP + dependency auditing provide practical protections against common web threats.

## Enforcement Controls

1. `pnpm -C dashboard lint` must pass (format + ESLint).
2. `pnpm -C dashboard check` must pass (SvelteKit sync + svelte-check).
3. `pnpm -C dashboard test:unit -- --run` must pass (Vitest).
4. `pnpm -C dashboard build` must succeed (Vite/SvelteKit).
5. `pnpm -C dashboard check:bundle` must pass (bundle budgets).
6. CI runs `pnpm audit --audit-level=high` for dashboard dependencies.

## Testable Assertions

1. Sidebar navigation is instantaneous (routes do not block on long API calls).
2. Heavy charting code does not inflate initial JS bundles (lazy-loaded).
3. Requests that exceed timeouts fail fast with user-friendly errors.
4. Security headers are present on server-rendered responses.

## Consequences

- Dependency upgrades require lockfile regeneration (and registry access) to keep CI `--frozen-lockfile` reliable.
- CSP may need iterative tuning if new integrations require additional `connect-src`/`img-src` domains.
- Performance budgets will force intentional decisions when introducing new large dependencies.

