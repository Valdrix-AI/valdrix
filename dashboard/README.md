# Valdrix Dashboard Frontend

SvelteKit frontend for Valdrix.

## Commands

```sh
pnpm run dev
pnpm run build
pnpm run lint
pnpm run check
pnpm run test:unit -- --run
pnpm run test:e2e
pnpm run test:perf
pnpm run check:bundle
pnpm audit --audit-level=high
```

## E2E Auth in Test Mode

Playwright authenticated-route tests use a test-only auth bypass in `hooks.server.ts`.

- It is active only when `TESTING=true`.
- It requires header `x-valdrix-e2e-auth` matching `E2E_AUTH_SECRET`.
- `playwright.config.ts` sets these values for the local E2E web server.

This avoids hardcoded test credentials and removes auth-related E2E skips while keeping production behavior unchanged.

## Performance Gate

`pnpm run test:perf` runs `e2e/performance.spec.ts` and enforces baseline budgets for:

- TTFB
- FCP
- LCP
- CLS
- DOM Complete

These checks are intended as a repeatable release gate for frontend performance regressions.
