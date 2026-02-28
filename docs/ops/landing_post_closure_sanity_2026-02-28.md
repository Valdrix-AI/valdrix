# Landing Post-Closure Sanity Check (2026-02-28)

Scope: public landing + auth conversion hardening release covering messaging clarity, mobile navigation, telemetry ingestion, accessibility gates, performance budgets, and visual stability.

## Release-Critical Validation

1. Concurrency
- Landing interval-driven UI remains lifecycle-safe (snapshot and demo rotations are torn down on unmount).
- Public mobile menu focus trap and scroll lock handlers attach/detach cleanly and close on route/scroll transitions.
- Auth page mode/context sync is URL-driven and avoids effect-loop state churn.
- Validation:
  - `pnpm --dir dashboard exec vitest run src/lib/components/LandingHero.svelte.test.ts src/routes/layout-public-menu.svelte.test.ts src/routes/auth/login/login-page.svelte.test.ts`

2. Observability
- Public landing/auth telemetry events are emitted client-side and ingested server-side through `POST /api/v1/public/landing/events`.
- Ingest path increments bounded Prometheus counters and logs normalized labels with hashed client identity.
- Validation:
  - `DEBUG=false uv run pytest -q --no-cov tests/unit/governance/api/test_public.py`
  - `pnpm --dir dashboard exec vitest run src/lib/landing/landingTelemetry.test.ts`

3. Deterministic Replay
- Landing/auth context parsing (`intent`, `persona`, `utm`, `next`) is normalized and deterministic.
- Callback redirect safety now rejects protocol-relative next targets (`//...`) to prevent open-redirect behavior.
- Validation:
  - `pnpm --dir dashboard exec vitest run src/lib/auth/publicAuthIntent.test.ts src/routes/auth/callback/callback-route.server.test.ts`

4. Snapshot Stability
- Visual baselines updated for intentional trust-section redesign.
- Desktop/mobile snapshots for hero/hook/trust sections are green after baseline refresh.
- Validation:
  - `pnpm --dir dashboard run test:visual:update`
  - `pnpm --dir dashboard run test:visual`

5. Export Integrity
- Landing funnel attribution and context-preserving auth handoff continue to serialize stable parameters into redirect paths.
- ROI pathways and signup-intent context remain deterministic across CTA -> auth transitions.
- Validation:
  - `pnpm --dir dashboard exec vitest run src/lib/auth/publicAuthIntent.test.ts src/routes/auth/login/login-page.svelte.test.ts src/lib/landing/roiCalculator.test.ts`

6. Failure Modes
- Out-of-window telemetry timestamps are explicitly ignored (non-fatal) with ingest reason codes.
- Auth conversion flow supports password, magic-link, and SSO paths with non-blocking error handling.
- Validation:
  - `DEBUG=false uv run pytest -q --no-cov tests/unit/governance/api/test_public.py`
  - `pnpm --dir dashboard exec vitest run src/routes/auth/login/login-page.svelte.test.ts`

7. Operational Misconfiguration Risk
- Added dedicated public accessibility gate to avoid coupling landing checks with authenticated app routes.
- Public-only Playwright mode remains enforced for perf/visual/a11y gates.
- Validation:
  - `pnpm --dir dashboard run test:a11y:public`
  - `pnpm --dir dashboard run test:perf:ci`
  - `pnpm --dir dashboard run check`

## Recorded Result (February 28, 2026 UTC)

- Frontend landing/auth targeted unit suites: passing (`30 passed`).
- Backend public API suite for landing ingest + discovery paths: passing (`18 passed`).
- Svelte type/accessibility check: passing (`0 errors, 0 warnings`).
- Public accessibility Playwright gate: passing (`6 passed`).
- Public performance budgets: passing (`2 passed`).
- Public visual regression gate: passing after intentional trust-section baseline refresh (`2 passed`).
