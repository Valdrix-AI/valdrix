# All Changes Categorization Register (2026-03-08)

Generated from live working tree using `git status --porcelain -uall`.

## Summary

- Total changed paths: 209
- Modified paths: 152
- New/untracked paths: 53
- Deleted paths: 4

## Track Rollup

| Track | Scope | Path Count | Tracking Issue |
|---|---|---:|---|
| Track AM | Backend runtime, governance, and data model changes | 47 | #244 |
| Track AN | Frontend dashboard, marketing, and brand asset updates | 54 | #245 |
| Track AO | Test coverage, release automation, and CI controls | 79 | #246 |
| Track AP | Documentation, deployment, and operational governance artifacts | 29 | #247 |

## Full Inventory By Track

### Track AM - Backend runtime, governance, and data model changes (47)

| Status | Path |
|---|---|
| `M` | `app/main.py` |
| `M` | `app/models/pricing.py` |
| `M` | `app/modules/billing/api/v1/billing.py` |
| `M` | `app/modules/governance/api/v1/admin.py` |
| `M` | `app/modules/governance/api/v1/audit_access.py` |
| `M` | `app/modules/governance/api/v1/audit_compliance.py` |
| `M` | `app/modules/governance/api/v1/public.py` |
| `M` | `app/modules/governance/api/v1/settings/__init__.py` |
| `M` | `app/modules/governance/api/v1/settings/onboard.py` |
| `M` | `app/modules/governance/api/v1/settings/profile.py` |
| `M` | `app/modules/governance/domain/jobs/handlers/notifications.py` |
| `M` | `app/modules/governance/domain/security/compliance_pack_bundle.py` |
| `M` | `app/modules/governance/domain/security/compliance_pack_bundle_exports.py` |
| `M` | `app/modules/optimization/domain/actions/aws/base.py` |
| `M` | `app/modules/optimization/domain/actions/azure/base.py` |
| `M` | `app/modules/optimization/domain/actions/base.py` |
| `M` | `app/modules/optimization/domain/actions/gcp/base.py` |
| `M` | `app/modules/reporting/domain/persistence.py` |
| `M` | `app/modules/reporting/domain/pricing/service.py` |
| `M` | `app/shared/core/auth.py` |
| `M` | `app/shared/core/config.py` |
| `M` | `app/shared/core/config_validation.py` |
| `M` | `app/shared/core/logging.py` |
| `M` | `app/shared/core/maintenance.py` |
| `M` | `app/shared/core/middleware.py` |
| `M` | `app/shared/core/ops_metrics.py` |
| `M` | `app/shared/core/rate_limit.py` |
| `M` | `app/shared/core/runtime_dependencies.py` |
| `M` | `app/shared/core/tracing.py` |
| `M` | `app/shared/core/turnstile.py` |
| `M` | `app/tasks/scheduler_sweep_ops.py` |
| `M` | `migrations/versions/h2i3j4k5l6m7_add_partition_auto_archival.py` |
| `??` | `app/modules/governance/api/v1/public_marketing.py` |
| `??` | `app/modules/governance/api/v1/settings/account.py` |
| `??` | `app/modules/governance/domain/security/compliance_pack_contracts.py` |
| `??` | `app/modules/optimization/adapters/common/remediation_clients.py` |
| `??` | `app/modules/reporting/domain/persistence_retention_ops.py` |
| `??` | `app/shared/core/app_runtime.py` |
| `??` | `app/shared/core/cloud_pricing_data.py` |
| `??` | `app/shared/core/config_validation_observability.py` |
| `??` | `app/shared/core/config_validation_runtime.py` |
| `??` | `app/shared/core/log_exporter.py` |
| `??` | `app/shared/core/ops_metrics_runtime.py` |
| `??` | `app/shared/core/proxy_headers.py` |
| `??` | `app/shared/core/webhooks.py` |
| `??` | `app/tasks/scheduler_maintenance_ops.py` |
| `??` | `migrations/versions/n0p1q2r3s4t5_add_cloud_resource_pricing_catalog.py` |

### Track AN - Frontend dashboard, marketing, and brand asset updates (54)

| Status | Path |
|---|---|
| `D` | `assets/valdrics_icon.png` |
| `M` | `dashboard/e2e/public-marketing.spec.ts` |
| `M` | `dashboard/package.json` |
| `M` | `dashboard/src/app.components-layout.css` |
| `M` | `dashboard/src/app.design.css` |
| `M` | `dashboard/src/app.html` |
| `M` | `dashboard/src/hooks.server.test.ts` |
| `M` | `dashboard/src/hooks.server.ts` |
| `M` | `dashboard/src/lib/components/CloudLogo.svelte` |
| `M` | `dashboard/src/lib/components/CommandPalette.svelte` |
| `M` | `dashboard/src/lib/components/LandingHero.footer.css` |
| `M` | `dashboard/src/lib/components/LandingHero.hero-copy.primary.css` |
| `M` | `dashboard/src/lib/components/LandingHero.hero-copy.proof.css` |
| `M` | `dashboard/src/lib/components/LandingHero.metrics-demo.css` |
| `M` | `dashboard/src/lib/components/LandingHero.motion.surface.css` |
| `M` | `dashboard/src/lib/components/LandingHero.roi-plans.css` |
| `M` | `dashboard/src/lib/components/LandingHero.signal-map.css` |
| `M` | `dashboard/src/lib/components/LandingHero.signal-preview.css` |
| `M` | `dashboard/src/lib/components/LandingHero.svelte` |
| `M` | `dashboard/src/lib/components/LandingHero.svelte.test.ts` |
| `M` | `dashboard/src/lib/components/LandingHero.trust.css` |
| `M` | `dashboard/src/lib/components/ProviderSelector.svelte` |
| `M` | `dashboard/src/lib/components/Toast.svelte` |
| `M` | `dashboard/src/lib/components/landing/LandingCapabilitiesSection.svelte` |
| `M` | `dashboard/src/lib/components/landing/LandingCloudHookSection.svelte` |
| `M` | `dashboard/src/lib/components/landing/LandingHeroCopy.svelte` |
| `M` | `dashboard/src/lib/components/landing/LandingHeroView.svelte` |
| `M` | `dashboard/src/lib/components/landing/LandingPlansSection.svelte` |
| `M` | `dashboard/src/lib/components/landing/LandingRoiSimulator.svelte` |
| `M` | `dashboard/src/lib/components/landing/LandingSignalMapCard.svelte` |
| `M` | `dashboard/src/lib/components/landing/LandingTrustSection.svelte` |
| `M` | `dashboard/src/lib/components/landing/landing_components.svelte.test.ts` |
| `M` | `dashboard/src/lib/components/landing/landing_decomposition.svelte.test.ts` |
| `M` | `dashboard/src/lib/components/landing/signal_map_demo.svelte.test.ts` |
| `M` | `dashboard/src/lib/landing/heroContent.core.ts` |
| `M` | `dashboard/src/lib/landing/heroContent.extended.ts` |
| `M` | `dashboard/src/lib/landing/publicNav.test.ts` |
| `M` | `dashboard/src/lib/landing/publicNav.ts` |
| `M` | `dashboard/src/lib/landing/realtimeSignalMap.ts` |
| `M` | `dashboard/src/lib/logging/server.ts` |
| `M` | `dashboard/src/routes/api/edge/[...path]/+server.ts` |
| `M` | `dashboard/src/routes/api/marketing/subscribe/+server.ts` |
| `M` | `dashboard/src/routes/api/marketing/subscribe/subscribe.server.test.ts` |
| `M` | `dashboard/src/routes/layout-public-menu.svelte.test.ts` |
| `M` | `dashboard/src/routes/layout/AppAuthenticatedShell.svelte` |
| `M` | `dashboard/src/routes/layout/PublicSiteShell.svelte` |
| `M` | `dashboard/src/routes/layout/layoutPublicNav.css` |
| `M` | `dashboard/static/favicon.png` |
| `M` | `dashboard/static/valdrics_icon.png` |
| `M` | `dashboard/svelte.config.js` |
| `??` | `assets/valdrics_icon1.png` |
| `??` | `dashboard/src/lib/server/backend-origin.ts` |
| `??` | `dashboard/static/valdrics_icon1.png` |
| `??` | `dashboard/static/valdrics_wordmark.svg` |

### Track AO - Test coverage, release automation, and CI controls (79)

| Status | Path |
|---|---|
| `M` | `.github/workflows/ci.yml` |
| `M` | `.github/workflows/performance-gate.yml` |
| `M` | `.github/workflows/security-scan.yml` |
| `M` | `scripts/archive_partitions.sql` |
| `M` | `scripts/check_frontend_hygiene.py` |
| `M` | `scripts/run_archival_setup.py` |
| `M` | `scripts/security/check_local_env_for_live_secrets.py` |
| `M` | `scripts/verify_enforcement_post_closure_sanity.py` |
| `M` | `scripts/verify_pending_approval_flow.py` |
| `M` | `tests/api/test_endpoints_security_auth.py` |
| `M` | `tests/integration/billing/test_paystack_flows.py` |
| `M` | `tests/security/test_security_regression.py` |
| `D` | `tests/unit/api/v1/test_costs_acceptance_payload_branches.py` |
| `M` | `tests/unit/core/test_auth_audit.py` |
| `M` | `tests/unit/core/test_auth_branch_paths.py` |
| `M` | `tests/unit/core/test_auth_core.py` |
| `M` | `tests/unit/core/test_config_audit.py` |
| `M` | `tests/unit/core/test_config_branch_paths.py` |
| `M` | `tests/unit/core/test_config_validation.py` |
| `M` | `tests/unit/core/test_env_contract_templates.py` |
| `M` | `tests/unit/core/test_logging_audit.py` |
| `M` | `tests/unit/core/test_main.py` |
| `M` | `tests/unit/core/test_maintenance_service.py` |
| `M` | `tests/unit/core/test_middleware.py` |
| `M` | `tests/unit/core/test_middleware_audit.py` |
| `M` | `tests/unit/core/test_ops_metrics.py` |
| `M` | `tests/unit/core/test_rate_limit.py` |
| `M` | `tests/unit/core/test_rate_limit_audit.py` |
| `M` | `tests/unit/core/test_rate_limit_branch_paths_2.py` |
| `M` | `tests/unit/core/test_rate_limit_expanded.py` |
| `M` | `tests/unit/core/test_runtime_dependencies.py` |
| `M` | `tests/unit/core/test_tracing_deep.py` |
| `M` | `tests/unit/governance/api/test_public.py` |
| `D` | `tests/unit/governance/settings/test_notifications.py` |
| `M` | `tests/unit/governance/test_compliance_pack_bundle_exports.py` |
| `M` | `tests/unit/modules/optimization/domain/test_cloud_action_modules.py` |
| `M` | `tests/unit/modules/reporting/test_pricing_service.py` |
| `D` | `tests/unit/modules/reporting/test_reporting_service.py` |
| `M` | `tests/unit/ops/test_production_deployment_contracts.py` |
| `M` | `tests/unit/ops/test_secret_rotation_contracts.py` |
| `M` | `tests/unit/ops/test_terraform_ha_contracts.py` |
| `M` | `tests/unit/ops/test_verify_enforcement_post_closure_sanity.py` |
| `M` | `tests/unit/ops/test_verify_exception_governance.py` |
| `M` | `tests/unit/optimization/test_saas_action_wiring.py` |
| `M` | `tests/unit/reporting/test_reporting_persistence_deep.py` |
| `M` | `tests/unit/shared/adapters/test_saas_adapter_branch_paths.py` |
| `M` | `tests/unit/supply_chain/test_supply_chain_provenance_workflow.py` |
| `M` | `tests/unit/tasks/test_scheduler_tasks_sweeps.py` |
| `M` | `tests/unit/test_main_coverage.py` |
| `??` | `.github/workflows/disaster-recovery-drill.yml` |
| `??` | `scripts/bootstrap_performance_tenant.py` |
| `??` | `scripts/run_disaster_recovery_drill.py` |
| `??` | `scripts/verify_documentation_runtime_contracts.py` |
| `??` | `scripts/verify_python_module_preferred_budget_baseline.py` |
| `??` | `tests/unit/api/v1/costs_acceptance_test_helpers.py` |
| `??` | `tests/unit/api/v1/test_costs_acceptance_payload_alerts.py` |
| `??` | `tests/unit/api/v1/test_costs_acceptance_payload_core.py` |
| `??` | `tests/unit/api/v1/test_costs_acceptance_payload_endpoints.py` |
| `??` | `tests/unit/core/test_cloud_pricing_data.py` |
| `??` | `tests/unit/governance/settings/conftest.py` |
| `??` | `tests/unit/governance/settings/test_account_settings.py` |
| `??` | `tests/unit/governance/settings/test_notifications_acceptance_evidence.py` |
| `??` | `tests/unit/governance/settings/test_notifications_core_slack.py` |
| `??` | `tests/unit/governance/settings/test_notifications_diagnostics_workflow.py` |
| `??` | `tests/unit/governance/settings/test_notifications_teams_jira.py` |
| `??` | `tests/unit/modules/optimization/domain/test_remediation_clients.py` |
| `??` | `tests/unit/modules/reporting/conftest.py` |
| `??` | `tests/unit/modules/reporting/test_reporting_service_connections.py` |
| `??` | `tests/unit/modules/reporting/test_reporting_service_ingestion.py` |
| `??` | `tests/unit/modules/reporting/test_reporting_service_post_ingest.py` |
| `??` | `tests/unit/ops/test_bootstrap_performance_tenant.py` |
| `??` | `tests/unit/ops/test_check_frontend_hygiene.py` |
| `??` | `tests/unit/ops/test_check_local_env_for_live_secrets.py` |
| `??` | `tests/unit/ops/test_documentation_runtime_contracts.py` |
| `??` | `tests/unit/ops/test_observability_metric_contracts.py` |
| `??` | `tests/unit/ops/test_run_disaster_recovery_drill.py` |
| `??` | `tests/unit/ops/test_verify_documentation_runtime_contracts.py` |
| `??` | `tests/unit/ops/test_verify_pending_approval_flow.py` |
| `??` | `tests/unit/ops/test_verify_python_module_preferred_budget_baseline.py` |

### Track AP - Documentation, deployment, and operational governance artifacts (29)

| Status | Path |
|---|---|
| `M` | `README.md` |
| `M` | `docs/CAPACITY_PLAN.md` |
| `M` | `docs/DEPLOYMENT.md` |
| `M` | `docs/ROLLBACK_PLAN.md` |
| `M` | `docs/SOC2_CONTROLS.md` |
| `M` | `docs/architecture/database_schema_overview.md` |
| `M` | `docs/architecture/failover.md` |
| `M` | `docs/architecture/overview.md` |
| `M` | `docs/integrations/workflow_automation.md` |
| `M` | `docs/ops/evidence/exception_governance_baseline.json` |
| `M` | `docs/ops/parallel_backend_hardening_2026-03-05.md` |
| `M` | `docs/policies/data_retention.md` |
| `M` | `docs/runbooks/disaster_recovery.md` |
| `M` | `docs/runbooks/incident_response.md` |
| `M` | `docs/runbooks/production_env_checklist.md` |
| `M` | `grafana/dashboards/finops-overview.json` |
| `M` | `helm/valdrics/templates/_helpers.tpl` |
| `M` | `helm/valdrics/templates/deployment.yaml` |
| `M` | `helm/valdrics/templates/external-secrets.yaml` |
| `M` | `helm/valdrics/templates/worker-deployment.yaml` |
| `M` | `helm/valdrics/values.yaml` |
| `M` | `koyeb.yaml` |
| `M` | `prometheus/alerts.yml` |
| `M` | `terraform/modules/db/main.tf` |
| `M` | `terraform/modules/secrets_rotation/main.tf` |
| `??` | `CODEOWNERS` |
| `??` | `deep-research-report.md` |
| `??` | `docs/ops/evidence/python_module_size_preferred_baseline.json` |
| `??` | `koyeb-worker.yaml` |
