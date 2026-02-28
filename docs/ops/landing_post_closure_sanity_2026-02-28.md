# Landing Post-Closure Sanity Check (2026-02-28)

Scope: public landing hardening release for messaging, mobile navigation, telemetry funnel visibility, performance budgets, and visual stability.

## Release-Critical Validation

1. Concurrency
- Rotating UI timers are lifecycle-safe (`LandingHero` interval setup + teardown).
- Mobile menu focus/scroll lock handlers cleanly attach/detach on open/close and route transitions.
- Validation:
  - `pnpm --dir dashboard exec vitest run src/lib/components/LandingHero.svelte.test.ts src/routes/layout-public-menu.svelte.test.ts`

2. Observability
- Landing telemetry emits stage transitions (`view`, `engaged`, `cta`, `signup_intent`) with attribution context.
- Weekly funnel trend checks are exposed on `/ops/landing-intelligence`.
- Validation:
  - `pnpm --dir dashboard exec vitest run src/lib/landing/landingTelemetry.test.ts src/lib/landing/landingFunnel.test.ts src/routes/ops/landing-intelligence/landing-intelligence-page.svelte.test.ts`

3. Deterministic Replay
- Landing experiment resolution is deterministic by default and only override-driven by explicit URL params.
- CTA experiment parameters are no longer appended by default; this prevents unintended replay drift.
- Validation:
  - `pnpm --dir dashboard exec vitest run src/lib/landing/landingExperiment.test.ts src/lib/components/LandingHero.svelte.test.ts`

4. Snapshot Stability
- Visual baseline snapshots created for desktop/mobile key sections (`.landing-hero`, `#cloud-hook`, `#trust`).
- Validation:
  - `PLAYWRIGHT_PUBLIC_ONLY=1 pnpm --dir dashboard run test:visual`

5. Export Integrity
- Weekly conversion report generation normalizes stored counts and preserves deterministic week windows.
- UI dashboard renders from persisted storage without schema drift.
- Validation:
  - `pnpm --dir dashboard exec vitest run src/lib/landing/landingFunnel.test.ts src/routes/ops/landing-intelligence/landing-intelligence-page.svelte.test.ts`

6. Failure Modes
- `matchMedia` fallback added in root layout for non-browser-like test/runtime contexts.
- Visual/perf tests run against production build preview path.
- Validation:
  - `pnpm --dir dashboard run check`
  - `PLAYWRIGHT_PUBLIC_ONLY=1 pnpm --dir dashboard run test:perf:ci`

7. Operational Misconfiguration Risk
- Public-only Playwright mode (`PLAYWRIGHT_PUBLIC_ONLY=1`) prevents backend dependency for landing gates.
- CI wiring includes perf and visual gates in dashboard quality checks.
- Validation:
  - `.github/workflows/ci.yml` includes `test:perf:ci` and `test:visual`.

## Recorded Result

- Unit/integration landing packs: passing.
- Svelte check: passing.
- Playwright performance budgets (desktop + mobile): passing.
- Playwright visual regression (desktop + mobile): passing with committed baselines.
