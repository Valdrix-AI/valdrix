# Landing Release Package (2026-02-28)

## Release Scope
Public landing and docs packaging for the backend-aligned positioning update:
- Buyer-facing positioning cleanup (remove internal language from homepage copy).
- Full capability coverage messaging (Cost, GreenOps, SaaS, ITAM/license, remediation, guardrails, leadership proof, integrations, identity).
- Public technical validation surface linking capabilities to active API families.
- SEO and discoverability updates for technical-validation route.
- Mobile and accessibility hardening validation.

## User-Facing Outcomes
1. Landing communicates complete platform value, not only cloud visibility.
2. GreenOps is explicitly represented in both coverage and capability narratives.
3. Buyers can open a compact public "Technical Validation" page without homepage clutter.
4. Documentation now includes a direct technical-validation entry point.

## Implementation Summary
- Landing capability enhancements and technical-validation CTA:
  - `dashboard/src/lib/components/LandingHero.svelte`
- Public-safe validation route:
  - `dashboard/src/routes/docs/technical-validation/+page.svelte`
- Docs hub navigation update:
  - `dashboard/src/routes/docs/+page.svelte`
- SEO sitemap entry:
  - `dashboard/src/routes/sitemap.xml/+server.ts`
- Backend capability trace reference:
  - `docs/ops/landing_capability_backend_trace_2026-02-28.md`

## Validation Evidence
All checks below passed for this release package:

1. Targeted landing/docs unit tests
- `pnpm --dir dashboard exec vitest run src/lib/components/LandingHero.svelte.test.ts src/routes/docs/docs-page.svelte.test.ts src/routes/docs/technical-validation/technical-validation-page.svelte.test.ts src/routes/sitemap.xml/sitemap.server.test.ts`
- Result: `5 passed`

2. Type and Svelte checks
- `pnpm --dir dashboard run check`
- Result: `0 errors, 0 warnings`

3. Mobile layout regression audit
- `PLAYWRIGHT_PUBLIC_ONLY=1 pnpm --dir dashboard exec playwright test e2e/landing-layout-audit.spec.ts`
- Result: `2 passed`

4. Public accessibility gate
- `PLAYWRIGHT_PUBLIC_ONLY=1 pnpm --dir dashboard run test:a11y:public`
- Result: `7 passed` (includes `/docs/technical-validation`)

5. Public visual regression
- `PLAYWRIGHT_PUBLIC_ONLY=1 pnpm --dir dashboard run test:visual:update`
- `PLAYWRIGHT_PUBLIC_ONLY=1 pnpm --dir dashboard run test:visual`
- Result: `2 passed`

## Risk and Rollback
- Risk profile: low to moderate (copy/layout/doc route + snapshot baseline adjustment).
- Rollback plan:
  1. Revert landing capability CTA block and `/docs/technical-validation` route.
  2. Revert sitemap addition for `/docs/technical-validation`.
  3. Restore prior visual snapshots if rolling back visual state.

## Suggested Commit Message
`feat(landing): add backend-aligned capability narrative and public technical validation route`

## Suggested PR Title
`Landing: backend-aligned capability messaging + public technical validation page`
