# Workstream Categorization (2026-03-02)

This register categorizes all current local changes into merge tracks.

## Track G: Landing component redesign and conversion surfaces
- Issue: https://github.com/Valdrics/valdrics/issues/207
- Scope:
  - Landing hero and visual system refresh
  - Decomposed landing sections and conversion components
  - Landing composition/regression tests
- Files:
  - `dashboard/src/lib/components/LandingHero.svelte`
  - `dashboard/src/lib/components/LandingHero.css`
  - `dashboard/src/lib/components/LandingHero.svelte.test.ts`
  - `dashboard/src/lib/components/landing/LandingHeroCopy.svelte`
  - `dashboard/src/lib/components/landing/LandingBenefitsSection.svelte`
  - `dashboard/src/lib/components/landing/LandingCapabilitiesSection.svelte`
  - `dashboard/src/lib/components/landing/LandingCloudHookSection.svelte`
  - `dashboard/src/lib/components/landing/LandingPersonaSection.svelte`
  - `dashboard/src/lib/components/landing/LandingPlansSection.svelte`
  - `dashboard/src/lib/components/landing/LandingRoiCalculator.svelte`
  - `dashboard/src/lib/components/landing/LandingRoiPlannerCta.svelte`
  - `dashboard/src/lib/components/landing/LandingRoiSimulator.svelte`
  - `dashboard/src/lib/components/landing/LandingSignalMapCard.svelte`
  - `dashboard/src/lib/components/landing/LandingTrustSection.svelte`
  - `dashboard/src/lib/components/landing/LandingWorkflowSection.svelte`
  - `dashboard/src/lib/components/landing/LandingCookieConsent.svelte`
  - `dashboard/src/lib/components/landing/LandingExitIntentPrompt.svelte`
  - `dashboard/src/lib/components/landing/LandingLeadCaptureSection.svelte`
  - `dashboard/src/lib/components/landing/landing_components.svelte.test.ts`
  - `dashboard/src/lib/components/landing/landing_decomposition.svelte.test.ts`
  - `dashboard/src/lib/landing/heroContent.ts`

## Track H: Public routes, navigation IA, and route protection updates
- Issue: https://github.com/Valdrics/valdrics/issues/208
- Scope:
  - Public navigation and menu expansion
  - Route-protection and route-visibility updates
  - Public docs/legal/marketing route content and tests
- Files:
  - `dashboard/src/routes/+layout.svelte`
  - `dashboard/src/lib/landing/publicNav.ts`
  - `dashboard/src/lib/landing/publicNav.test.ts`
  - `dashboard/src/lib/routeProtection.ts`
  - `dashboard/src/lib/routeProtection.test.ts`
  - `dashboard/src/routes/docs/+page.svelte`
  - `dashboard/src/routes/docs/docs-page.svelte.test.ts`
  - `dashboard/src/routes/privacy/+page.svelte`
  - `dashboard/src/routes/privacy/privacy-page.svelte.test.ts`
  - `dashboard/src/routes/terms/+page.svelte`
  - `dashboard/src/routes/terms/terms-page.svelte.test.ts`
  - `dashboard/src/routes/insights/+page.svelte`
  - `dashboard/src/routes/insights/insights-page.svelte.test.ts`
  - `dashboard/src/routes/resources/+page.svelte`
  - `dashboard/src/routes/resources/resources-page.svelte.test.ts`
  - `dashboard/src/routes/talk-to-sales/+page.svelte`
  - `dashboard/src/routes/talk-to-sales/talk-to-sales-page.svelte.test.ts`
  - `dashboard/src/routes/layout-public-menu.svelte.test.ts`

## Track I: Marketing APIs/assets and sitemap expansion
- Issue: https://github.com/Valdrics/valdrics/issues/209
- Scope:
  - Marketing subscribe endpoint
  - Public downloadable asset endpoints
  - Sitemap expansion for new public routes
  - Cloudflare worker route config
- Files:
  - `dashboard/src/routes/api/marketing/subscribe/+server.ts`
  - `dashboard/src/routes/api/marketing/subscribe/subscribe.server.test.ts`
  - `dashboard/src/routes/resources/valdrics-enterprise-one-pager.md/+server.ts`
  - `dashboard/src/routes/resources/valdrics-enterprise-one-pager.md/one-pager.server.test.ts`
  - `dashboard/src/routes/resources/valdrics-roi-assumptions.csv/+server.ts`
  - `dashboard/src/routes/resources/valdrics-roi-assumptions.csv/roi-assumptions.server.test.ts`
  - `dashboard/src/routes/sitemap.xml/+server.ts`
  - `dashboard/src/routes/sitemap.xml/sitemap.server.test.ts`
  - `dashboard/wrangler.toml`

## Track J: Ops evidence updates and landing budget guardrails
- Issue: https://github.com/Valdrics/valdrics/issues/210
- Scope:
  - Ops evidence log updates for rollout progress
  - Landing component budget guardrail sync
- Files:
  - `docs/ops/audit_remediation_2026-02-20.md`
  - `docs/ops/enforcement_control_plane_gap_register_2026-02-23.md`
  - `scripts/verify_landing_component_budget.py`
  - `tests/unit/ops/test_verify_landing_component_budget.py`

## Execution plan
- Keep one PR for this current local batch, linked to all four track issues.
- Run changed frontend test modules + landing budget guardrail unit test before merge.
