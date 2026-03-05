# All Changes Categorization Register (2026-03-05)

Generated from live working tree using `git status --porcelain -uall`.

## Summary

- Total changed paths: 72
- Modified paths: 50
- New/untracked paths: 7
- Deleted paths: 15

## Track Rollup

| Track | Scope | Path Count | Tracking Issue |
|---|---|---:|---|
| Track Y | Backend domain refactor and governance/security implementation | 32 | #229 |
| Track Z | Frontend landing, enterprise page, and public route updates | 27 | #230 |
| Track AA | Release gate and verification automation | 10 | #231 |
| Track AB | Documentation and evidence matrix updates | 3 | #232 |

## Full Inventory By Track

### Track Y - Backend domain refactor and governance/security implementation (32)

| Status | Path |
|---|---|
| `M` | `app/modules/governance/domain/security/compliance_pack_bundle.py` |
| `M` | `app/modules/optimization/domain/__init__.py` |
| `D` | `app/modules/optimization/domain/aws_provider/__init__.py` |
| `D` | `app/modules/optimization/domain/aws_provider/detector.py` |
| `D` | `app/modules/optimization/domain/aws_provider/plugins.py` |
| `D` | `app/modules/optimization/domain/aws_provider/plugins/__init__.py` |
| `D` | `app/modules/optimization/domain/aws_provider/plugins/compute.py` |
| `D` | `app/modules/optimization/domain/azure_provider/__init__.py` |
| `D` | `app/modules/optimization/domain/azure_provider/detector.py` |
| `D` | `app/modules/optimization/domain/azure_provider/plugins.py` |
| `D` | `app/modules/optimization/domain/base.py` |
| `D` | `app/modules/optimization/domain/detector.py` |
| `D` | `app/modules/optimization/domain/gcp_provider/__init__.py` |
| `D` | `app/modules/optimization/domain/gcp_provider/detector.py` |
| `D` | `app/modules/optimization/domain/gcp_provider/plugins.py` |
| `D` | `app/modules/optimization/domain/remediation_service.py` |
| `D` | `app/modules/optimization/domain/zombie_plugin.py` |
| `M` | `tests/conftest.py` |
| `M` | `tests/governance/test_audit_phase_2.py` |
| `M` | `tests/governance/test_detector_core.py` |
| `M` | `tests/governance/test_hard_limit_enforcement.py` |
| `M` | `tests/governance/test_remediation_atomicity.py` |
| `M` | `tests/unit/api/v1/test_reconciliation_endpoints.py` |
| `M` | `tests/unit/enforcement/test_enforcement_actions_api.py` |
| `M` | `tests/unit/llm/test_analyzer_exhaustive.py` |
| `M` | `tests/unit/services/zombies/aws_provider/test_aws_detector.py` |
| `M` | `tests/unit/services/zombies/test_base.py` |
| `M` | `tests/unit/services/zombies/test_remediation_service.py` |
| `M` | `tests/unit/zombies/aws/test_compute_refactored.py` |
| `M` | `tests/unit/zombies/test_tier_gating_phase8.py` |
| `??` | `app/modules/governance/domain/security/compliance_pack_bundle_exports.py` |
| `??` | `tests/unit/governance/test_compliance_pack_bundle_exports.py` |

### Track Z - Frontend landing, enterprise page, and public route updates (27)

| Status | Path |
|---|---|
| `M` | `dashboard/src/lib/components/LandingHero.css` |
| `M` | `dashboard/src/lib/components/LandingHero.svelte` |
| `M` | `dashboard/src/lib/components/LandingHero.svelte.test.ts` |
| `M` | `dashboard/src/lib/components/landing/LandingHeroCopy.svelte` |
| `M` | `dashboard/src/lib/components/landing/LandingTrustSection.svelte` |
| `M` | `dashboard/src/lib/components/landing/landing_components.svelte.test.ts` |
| `M` | `dashboard/src/lib/components/landing/landing_decomposition.svelte.test.ts` |
| `M` | `dashboard/src/lib/landing/landingFunnel.test.ts` |
| `M` | `dashboard/src/lib/landing/landingFunnel.ts` |
| `M` | `dashboard/src/lib/landing/publicNav.test.ts` |
| `M` | `dashboard/src/lib/landing/publicNav.ts` |
| `M` | `dashboard/src/lib/routeProtection.test.ts` |
| `M` | `dashboard/src/lib/routeProtection.ts` |
| `M` | `dashboard/src/routes/layout-public-menu.svelte.test.ts` |
| `M` | `dashboard/src/routes/ops/landing-intelligence/+page.svelte` |
| `M` | `dashboard/src/routes/ops/landing-intelligence/landing-intelligence-page.svelte.test.ts` |
| `M` | `dashboard/src/routes/pricing/+page.svelte` |
| `M` | `dashboard/src/routes/pricing/pricing-page.svelte.test.ts` |
| `M` | `dashboard/src/routes/resources/+page.svelte` |
| `M` | `dashboard/src/routes/resources/global-finops-compliance-workbook.md/workbook.server.test.ts` |
| `M` | `dashboard/src/routes/resources/resources-page.svelte.test.ts` |
| `M` | `dashboard/src/routes/sitemap.xml/+server.ts` |
| `M` | `dashboard/src/routes/sitemap.xml/sitemap.server.test.ts` |
| `M` | `dashboard/src/routes/talk-to-sales/+page.svelte` |
| `M` | `dashboard/src/routes/talk-to-sales/talk-to-sales-page.svelte.test.ts` |
| `??` | `dashboard/src/routes/enterprise/+page.svelte` |
| `??` | `dashboard/src/routes/enterprise/enterprise-page.svelte.test.ts` |

### Track AA - Release gate and verification automation (10)

| Status | Path |
|---|---|
| `M` | `scripts/run_enterprise_tdd_gate.py` |
| `M` | `scripts/verify_audit_report_resolved.py` |
| `M` | `scripts/verify_python_module_size_budget.py` |
| `M` | `tests/api/test_pagination.py` |
| `M` | `tests/core/test_rate_limit_stress.py` |
| `M` | `tests/security/test_due_diligence.py` |
| `M` | `tests/unit/ops/test_verify_audit_report_resolved.py` |
| `M` | `tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py` |
| `??` | `scripts/verify_test_to_production_ratio.py` |
| `??` | `tests/unit/ops/test_verify_test_to_production_ratio.py` |

### Track AB - Documentation and evidence matrix updates (3)

| Status | Path |
|---|---|
| `M` | `docs/ops/all_changes_categorization_2026-03-04.md` |
| `M` | `docs/ops/feature_enforceability_matrix_2026-02-27.json` |
| `??` | `docs/ops/all_changes_categorization_2026-03-05.md` |
