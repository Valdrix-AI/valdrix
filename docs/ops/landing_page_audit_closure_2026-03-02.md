# Valdrics Landing Audit Closure Register (2026-03-02)

Source report:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/landing_page_audit_report.md.resolved`

## Cross-Persona Findings Closure

1. Privacy Policy / Terms placeholder-grade (`Critical`)
- Status: `CLOSED`
- Evidence:
  - `dashboard/src/routes/privacy/+page.svelte`
  - `dashboard/src/routes/terms/+page.svelte`
  - tests:
    - `dashboard/src/routes/privacy/privacy-page.svelte.test.ts`
    - `dashboard/src/routes/terms/terms-page.svelte.test.ts`

2. Missing cookie consent with localStorage telemetry (`Critical`)
- Status: `CLOSED`
- Evidence:
  - `dashboard/src/lib/components/landing/LandingCookieConsent.svelte`
  - `dashboard/src/lib/components/LandingHero.svelte`
  - `dashboard/src/lib/components/LandingHero.css`
  - test:
    - `dashboard/src/lib/components/LandingHero.svelte.test.ts`

3. Supabase `ERR_NAME_NOT_RESOLVED` console errors (`High`)
- Status: `CLOSED` for anonymous landing flow
- Evidence:
  - `dashboard/e2e/landing-layout-audit.spec.ts`
  - validation: Playwright landing layout audit pass (`3 passed`)

4. No Talk-to-Sales / Book-a-Demo CTA (`High`)
- Status: `CLOSED`
- Evidence:
  - `dashboard/src/routes/talk-to-sales/+page.svelte`
  - `dashboard/src/lib/landing/publicNav.ts`
  - `dashboard/src/routes/+layout.svelte`
  - test:
    - `dashboard/src/routes/talk-to-sales/talk-to-sales-page.svelte.test.ts`

5. No visible keyboard focus indicators (`Medium`)
- Status: `CLOSED`
- Evidence:
  - `dashboard/src/lib/components/LandingHero.css` (`:focus-visible` coverage across links/buttons/controls)
  - regression coverage via landing/unit tests and e2e navigation checks

6. Missing SOC2/GDPR trust language (`Medium`)
- Status: `CLOSED`
- Evidence:
  - above-fold trust badges:
    - `dashboard/src/lib/landing/heroContent.ts`
    - `dashboard/src/lib/components/landing/LandingHeroCopy.svelte`
  - trust/compliance section:
    - `dashboard/src/lib/components/landing/LandingTrustSection.svelte`

7. Missing canonical + robots meta (`Medium`)
- Status: `CLOSED`
- Evidence:
  - `dashboard/src/routes/+layout.svelte` (`<link rel="canonical">`, `<meta name="robots">`)

8. No email capture / newsletter / blog (`Medium`)
- Status: `CLOSED`
- Evidence:
  - newsletter lead capture:
    - `dashboard/src/lib/components/landing/LandingLeadCaptureSection.svelte`
    - `dashboard/src/routes/api/marketing/subscribe/+server.ts`
  - content hub:
    - `dashboard/src/routes/insights/+page.svelte`
    - nav/footer links: `dashboard/src/lib/landing/publicNav.ts`

9. Anonymized case studies (`Medium`)
- Status: `MITIGATED`
- Evidence:
  - strengthened case-study specificity:
    - `dashboard/src/lib/landing/heroContent.ts` (`CUSTOMER_PROOF_STORIES`)
  - named references path for diligence:
    - `dashboard/src/lib/components/landing/LandingTrustSection.svelte`

10. Missing downloadable sales collateral (`Medium`)
- Status: `CLOSED`
- Evidence:
  - `dashboard/src/routes/resources/valdrics-enterprise-one-pager.md/+server.ts`
  - `dashboard/src/routes/resources/valdrics-roi-assumptions.csv/+server.ts`
  - surfaced in resources hub:
    - `dashboard/src/routes/resources/+page.svelte`
  - surfaced directly on landing trust section:
    - `dashboard/src/lib/components/landing/LandingTrustSection.svelte`
    - `dashboard/src/lib/components/LandingHero.svelte`

11. “20-second demo” text implies missing video (`Medium`)
- Status: `CLOSED`
- Evidence:
  - wording updated:
    - `dashboard/src/lib/components/landing/LandingSignalMapCard.svelte`

12. Missing TCO / implementation-cost mention (`Medium`)
- Status: `CLOSED`
- Evidence:
  - pricing + enterprise path:
    - `dashboard/src/lib/components/landing/LandingPlansSection.svelte`
    - `dashboard/src/routes/talk-to-sales/+page.svelte`
  - ROI decision framing now uses a visible ungated model preview:
    - `dashboard/src/lib/components/landing/LandingRoiPlannerCta.svelte`
  - downloadable planning collateral remains available in resources:
    - `dashboard/src/routes/resources/+page.svelte`
    - `dashboard/src/routes/resources/valdrics-roi-assumptions.csv/+server.ts`

13. LCP/CLS risk from animated Signal Map (`Low-Med`)
- Status: `MITIGATED`
- Evidence:
  - bounded animation controls, in-view rotation gating, reduced-motion handling:
    - `dashboard/src/lib/components/LandingHero.svelte`
    - `dashboard/src/lib/components/LandingHero.css`
  - layout stability checks:
    - `dashboard/e2e/landing-layout-audit.spec.ts`

14. High jargon for non-technical audiences (`Low-Med`)
- Status: `CLOSED`
- Evidence:
  - plain-English mode toggle:
    - `dashboard/src/lib/components/landing/LandingHeroCopy.svelte`
    - `dashboard/src/lib/components/LandingHero.svelte`
  - copy simplification pass across sections completed on 2026-03-02

15. Very long page without progress indicator (`Low`)
- Status: `CLOSED`
- Evidence:
  - progress/back-to-top:
    - `dashboard/src/lib/components/LandingHero.svelte`
  - reduced vertical spacing and copy density:
    - `dashboard/src/lib/components/LandingHero.css`
    - landing component section padding normalization (`pb-16`)

## Validation Evidence

1. `cd dashboard && npm run check` -> passed (`0 errors`, `0 warnings`).
2. `cd dashboard && npm run test:unit -- --run src/lib/components/LandingHero.svelte.test.ts src/lib/components/landing/landing_decomposition.svelte.test.ts src/routes/resources/resources-page.svelte.test.ts src/routes/insights/insights-page.svelte.test.ts src/routes/talk-to-sales/talk-to-sales-page.svelte.test.ts src/routes/privacy/privacy-page.svelte.test.ts src/routes/terms/terms-page.svelte.test.ts` -> passed (`7 files`, `15 tests`).
3. `cd dashboard && npx playwright test e2e/landing-layout-audit.spec.ts` -> passed (`3 passed`).
4. `uv run python3 scripts/verify_landing_component_budget.py` -> passed (`hero_lines=774 max=800 components=14`).

## Post-Closure Sanity Check (Release-Critical)

1. Concurrency:
- No shared mutable state added in landing paths; existing observer/interval lifecycle remains deterministic and teardown-tested.

2. Observability:
- Landing telemetry still captures funnel and CTA interactions with consent-aware gating.

3. Deterministic replay:
- Public pages remain static-content deterministic with explicit test coverage for navigation and route outputs.

4. Snapshot stability:
- Realtime signal snapshots unchanged structurally; UI layout regressions guarded by Playwright mobile checks.

5. Export integrity:
- New collateral downloads are static, deterministic, and content-type tested.

6. Failure modes:
- Marketing subscribe endpoint keeps rate-limit + honeypot + webhook-failure handling under test.

7. Operational misconfiguration:
- New public routes (`/insights`, `/talk-to-sales`) are covered in route protection and sitemap tests to prevent accidental auth-gating or discoverability drift.
