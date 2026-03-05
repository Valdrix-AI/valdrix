# All Changes Categorization Register (2026-03-04)

Generated from live working tree using `git status --porcelain`.

## Summary

- Total changed paths: 372
- Modified paths: 302
- New/untracked paths: 65
- Deleted paths: 5

## Track Rollup

| Track | Scope | Path Count | Tracking Issue |
|---|---|---:|---|
| Track U - Backend (services/core) | Backend services and shared platform code | 174 | #224 |
| Track U - Backend tests | Backend/platform test coverage | 99 | #224 |
| Track V - Frontend/public routes | Dashboard UI/routes/tests | 46 | #225 |
| Track W - CI/tooling/automation | Automation, CI, and scripts | 45 | #226 |
| Track X - Docs/evidence | Ops and architecture docs | 8 | #227 |

## Superseded Earlier Tracks

- `#221` (Track R), `#222` (Track S), and `#223` (Track T) are superseded by this consolidated batch and will be closed by the consolidation PR.

## Full Inventory By Track

### Track U - Backend platform, enforcement, and shared core (174)

| Status | Path |
|---|---|
| `M` | `app/main.py` |
| `M` | `app/modules/billing/api/v1/billing.py` |
| `M` | `app/modules/billing/api/v1/billing_ops.py` |
| `M` | `app/modules/billing/domain/billing/dunning_service.py` |
| `M` | `app/modules/billing/domain/billing/paystack_service_impl.py` |
| `M` | `app/modules/billing/domain/billing/paystack_webhook_impl.py` |
| `M` | `app/modules/billing/domain/billing/webhook_retry.py` |
| `M` | `app/modules/enforcement/api/v1/common.py` |
| `M` | `app/modules/enforcement/api/v1/enforcement.py` |
| `M` | `app/modules/enforcement/domain/reconciliation_worker.py` |
| `M` | `app/modules/enforcement/domain/service.py` |
| `M` | `app/modules/governance/api/v1/audit_access.py` |
| `M` | `app/modules/governance/api/v1/audit_evidence.py` |
| `M` | `app/modules/governance/api/v1/audit_partitioning.py` |
| `M` | `app/modules/governance/api/v1/health_dashboard.py` |
| `M` | `app/modules/governance/api/v1/jobs.py` |
| `M` | `app/modules/governance/api/v1/public.py` |
| `M` | `app/modules/governance/api/v1/scim.py` |
| `M` | `app/modules/governance/api/v1/settings/identity.py` |
| `M` | `app/modules/governance/api/v1/settings/notifications.py` |
| `M` | `app/modules/governance/api/v1/settings/onboard.py` |
| `M` | `app/modules/governance/api/v1/settings/safety.py` |
| `M` | `app/modules/governance/domain/jobs/cur_ingestion.py` |
| `M` | `app/modules/governance/domain/jobs/handlers/acceptance.py` |
| `M` | `app/modules/governance/domain/jobs/handlers/base.py` |
| `M` | `app/modules/governance/domain/jobs/handlers/costs.py` |
| `M` | `app/modules/governance/domain/jobs/handlers/finops.py` |
| `M` | `app/modules/governance/domain/jobs/processor.py` |
| `M` | `app/modules/governance/domain/scheduler/orchestrator.py` |
| `M` | `app/modules/governance/domain/scheduler/processors.py` |
| `M` | `app/modules/governance/domain/security/compliance_pack_bundle.py` |
| `M` | `app/modules/governance/domain/security/iam_auditor.py` |
| `M` | `app/modules/governance/domain/security/remediation_policy.py` |
| `M` | `app/modules/notifications/domain/email_service.py` |
| `M` | `app/modules/notifications/domain/jira.py` |
| `M` | `app/modules/notifications/domain/slack.py` |
| `M` | `app/modules/notifications/domain/teams.py` |
| `M` | `app/modules/notifications/domain/workflows.py` |
| `M` | `app/modules/optimization/adapters/aws/plugins/compute.py` |
| `M` | `app/modules/optimization/adapters/aws/plugins/rightsizing.py` |
| `M` | `app/modules/optimization/adapters/aws/plugins/search.py` |
| `M` | `app/modules/optimization/adapters/aws/region_discovery.py` |
| `M` | `app/modules/optimization/adapters/azure/detector.py` |
| `M` | `app/modules/optimization/adapters/azure/plugins/ai.py` |
| `M` | `app/modules/optimization/adapters/azure/plugins/compute.py` |
| `M` | `app/modules/optimization/adapters/azure/plugins/containers.py` |
| `M` | `app/modules/optimization/adapters/azure/plugins/database.py` |
| `M` | `app/modules/optimization/adapters/azure/plugins/network.py` |
| `M` | `app/modules/optimization/adapters/azure/plugins/rightsizing.py` |
| `M` | `app/modules/optimization/adapters/azure/plugins/storage.py` |
| `M` | `app/modules/optimization/adapters/gcp/detector.py` |
| `M` | `app/modules/optimization/adapters/gcp/plugins/ai.py` |
| `M` | `app/modules/optimization/adapters/gcp/plugins/compute.py` |
| `M` | `app/modules/optimization/adapters/gcp/plugins/containers.py` |
| `M` | `app/modules/optimization/adapters/gcp/plugins/database.py` |
| `M` | `app/modules/optimization/adapters/gcp/plugins/network.py` |
| `M` | `app/modules/optimization/adapters/gcp/plugins/rightsizing.py` |
| `M` | `app/modules/optimization/adapters/gcp/plugins/search.py` |
| `M` | `app/modules/optimization/adapters/gcp/plugins/storage.py` |
| `M` | `app/modules/optimization/adapters/kubernetes/plugins/kubernetes_pvc.py` |
| `M` | `app/modules/optimization/adapters/saas/plugins/api.py` |
| `M` | `app/modules/optimization/api/v1/strategies.py` |
| `M` | `app/modules/optimization/api/v1/zombies.py` |
| `M` | `app/modules/optimization/domain/actions/base.py` |
| `M` | `app/modules/optimization/domain/actions/license/base.py` |
| `M` | `app/modules/optimization/domain/license_governance.py` |
| `M` | `app/modules/optimization/domain/ports.py` |
| `M` | `app/modules/optimization/domain/remediation_context.py` |
| `M` | `app/modules/optimization/domain/remediation_execute.py` |
| `M` | `app/modules/optimization/domain/remediation_hard_limit.py` |
| `M` | `app/modules/optimization/domain/remediation_workflow.py` |
| `M` | `app/modules/optimization/domain/service.py` |
| `M` | `app/modules/optimization/domain/strategies/baseline_commitment.py` |
| `M` | `app/modules/reporting/api/v1/costs.py` |
| `M` | `app/modules/reporting/api/v1/leaderboards.py` |
| `M` | `app/modules/reporting/api/v1/leadership.py` |
| `M` | `app/modules/reporting/api/v1/savings.py` |
| `M` | `app/modules/reporting/api/v1/usage.py` |
| `M` | `app/modules/reporting/domain/aggregator.py` |
| `M` | `app/modules/reporting/domain/anomaly_detection.py` |
| `M` | `app/modules/reporting/domain/arm_analyzer.py` |
| `M` | `app/modules/reporting/domain/attribution_engine.py` |
| `M` | `app/modules/reporting/domain/budget_alerts.py` |
| `M` | `app/modules/reporting/domain/carbon_scheduler.py` |
| `M` | `app/modules/reporting/domain/focus_export.py` |
| `M` | `app/modules/reporting/domain/leadership_kpis.py` |
| `M` | `app/modules/reporting/domain/persistence.py` |
| `M` | `app/modules/reporting/domain/pricing/service.py` |
| `M` | `app/modules/reporting/domain/realized_savings.py` |
| `M` | `app/modules/reporting/domain/reconciliation.py` |
| `M` | `app/modules/reporting/domain/service.py` |
| `M` | `app/schemas/connections.py` |
| `M` | `app/shared/adapters/aws_cur.py` |
| `M` | `app/shared/adapters/aws_multitenant.py` |
| `M` | `app/shared/adapters/aws_resource_explorer.py` |
| `M` | `app/shared/adapters/azure.py` |
| `M` | `app/shared/adapters/cost_cache.py` |
| `M` | `app/shared/adapters/gcp.py` |
| `M` | `app/shared/adapters/hybrid.py` |
| `M` | `app/shared/adapters/platform.py` |
| `M` | `app/shared/adapters/saas.py` |
| `M` | `app/shared/analysis/cur_usage_analyzer.py` |
| `M` | `app/shared/analysis/forecaster.py` |
| `M` | `app/shared/connections/aws.py` |
| `M` | `app/shared/connections/discovery.py` |
| `M` | `app/shared/connections/oidc.py` |
| `M` | `app/shared/connections/organizations.py` |
| `M` | `app/shared/core/approval_permissions.py` |
| `M` | `app/shared/core/auth.py` |
| `M` | `app/shared/core/cache.py` |
| `M` | `app/shared/core/circuit_breaker.py` |
| `M` | `app/shared/core/cloud_connection.py` |
| `M` | `app/shared/core/config.py` |
| `M` | `app/shared/core/currency.py` |
| `M` | `app/shared/core/health.py` |
| `M` | `app/shared/core/maintenance.py` |
| `M` | `app/shared/core/ops_metrics.py` |
| `M` | `app/shared/core/performance_testing.py` |
| `M` | `app/shared/core/pricing.py` |
| `M` | `app/shared/core/rate_limit.py` |
| `M` | `app/shared/core/retry.py` |
| `M` | `app/shared/core/security.py` |
| `M` | `app/shared/core/timeout.py` |
| `M` | `app/shared/db/session.py` |
| `M` | `app/shared/llm/analyzer.py` |
| `M` | `app/shared/llm/budget_execution.py` |
| `M` | `app/shared/llm/budget_fair_use.py` |
| `M` | `app/shared/llm/circuit_breaker.py` |
| `M` | `app/shared/llm/hybrid_scheduler.py` |
| `M` | `app/shared/llm/pricing_data.py` |
| `M` | `app/shared/llm/prompts.yaml` |
| `M` | `app/shared/llm/usage_tracker.py` |
| `M` | `app/shared/llm/zombie_analyzer.py` |
| `M` | `app/shared/remediation/autonomous.py` |
| `M` | `app/shared/remediation/circuit_breaker.py` |
| `M` | `app/shared/remediation/hard_cap_service.py` |
| `M` | `app/tasks/license_tasks.py` |
| `M` | `app/tasks/scheduler_tasks.py` |
| `??` | `app/modules/enforcement/domain/approval_flow_ops.py` |
| `??` | `app/modules/enforcement/domain/approval_routing_ops.py` |
| `??` | `app/modules/enforcement/domain/approval_token_ops.py` |
| `??` | `app/modules/enforcement/domain/budget_credit_ops.py` |
| `??` | `app/modules/enforcement/domain/computed_context_ops.py` |
| `??` | `app/modules/enforcement/domain/credit_ops.py` |
| `??` | `app/modules/enforcement/domain/export_bundle_ops.py` |
| `??` | `app/modules/enforcement/domain/gate_evaluation_ops.py` |
| `??` | `app/modules/enforcement/domain/policy_contract_ops.py` |
| `??` | `app/modules/enforcement/domain/reconciliation_flow_ops.py` |
| `??` | `app/modules/enforcement/domain/reconciliation_ops.py` |
| `??` | `app/modules/enforcement/domain/runtime_query_ops.py` |
| `??` | `app/modules/enforcement/domain/service_models.py` |
| `??` | `app/modules/enforcement/domain/service_private_ops.py` |
| `??` | `app/modules/enforcement/domain/service_runtime_ops.py` |
| `??` | `app/modules/enforcement/domain/service_utils.py` |
| `??` | `app/modules/enforcement/domain/waterfall_ops.py` |
| `??` | `app/modules/governance/api/v1/scim_group_route_ops.py` |
| `??` | `app/modules/governance/api/v1/scim_membership_ops.py` |
| `??` | `app/modules/governance/api/v1/scim_user_route_ops.py` |
| `??` | `app/modules/governance/api/v1/settings/identity_diagnostics_ops.py` |
| `??` | `app/modules/governance/api/v1/settings/identity_settings_ops.py` |
| `??` | `app/modules/governance/api/v1/settings/notification_diagnostics_ops.py` |
| `??` | `app/modules/governance/api/v1/settings/notification_settings_ops.py` |
| `??` | `app/modules/governance/api/v1/settings/notifications_models.py` |
| `??` | `app/modules/governance/domain/jobs/handlers/acceptance_runtime_ops.py` |
| `??` | `app/modules/optimization/domain/strategy_service.py` |
| `??` | `app/modules/reporting/api/v1/costs_acceptance_payload.py` |
| `??` | `app/modules/reporting/api/v1/costs_acceptance_routes.py` |
| `??` | `app/modules/reporting/api/v1/costs_core_routes.py` |
| `??` | `app/modules/reporting/api/v1/costs_reconciliation_routes.py` |
| `??` | `app/modules/reporting/api/v1/costs_unit_economics_routes.py` |
| `??` | `app/py.typed` |
| `??` | `app/shared/testing/` |
| `??` | `app/tasks/scheduler_runtime_ops.py` |
| `??` | `app/tasks/scheduler_sweep_ops.py` |

### Track U - Backend/platform test coverage (99)

| Status | Path |
|---|---|
| `M` | `tests/conftest.py` |
| `M` | `tests/core/test_cache_service.py` |
| `M` | `tests/governance/test_job_processor.py` |
| `M` | `tests/unit/adapters/test_azure_adapter.py` |
| `M` | `tests/unit/adapters/test_gcp_adapter.py` |
| `M` | `tests/unit/analysis/test_forecaster.py` |
| `M` | `tests/unit/api/test_audit.py` |
| `M` | `tests/unit/api/v1/test_audit_high_impact_branches.py` |
| `M` | `tests/unit/api/v1/test_billing.py` |
| `M` | `tests/unit/api/v1/test_leaderboards_endpoints.py` |
| `M` | `tests/unit/api/v1/test_leadership_kpis_branch_paths_2.py` |
| `M` | `tests/unit/api/v1/test_savings_branch_paths.py` |
| `M` | `tests/unit/api/v1/test_usage_branch_paths.py` |
| `M` | `tests/unit/core/test_auth_audit.py` |
| `M` | `tests/unit/core/test_auth_branch_paths.py` |
| `M` | `tests/unit/core/test_auth_core.py` |
| `M` | `tests/unit/core/test_cache_deep.py` |
| `M` | `tests/unit/core/test_cache_resilience.py` |
| `M` | `tests/unit/core/test_cloud_connection_audit.py` |
| `M` | `tests/unit/core/test_finding_2_cloud_leakage.py` |
| `M` | `tests/unit/core/test_health_deep.py` |
| `M` | `tests/unit/core/test_health_missing_coverage.py` |
| `M` | `tests/unit/core/test_performance_testing.py` |
| `M` | `tests/unit/core/test_pricing_deep.py` |
| `M` | `tests/unit/core/test_rate_limit_expanded.py` |
| `M` | `tests/unit/core/test_retry_utils.py` |
| `M` | `tests/unit/core/test_retry_utils_branch_paths.py` |
| `M` | `tests/unit/core/test_session_audit.py` |
| `M` | `tests/unit/db/test_session_missing_coverage.py` |
| `M` | `tests/unit/enforcement/test_enforcement_service.py` |
| `M` | `tests/unit/governance/api/test_public.py` |
| `M` | `tests/unit/governance/domain/jobs/handlers/test_base_handler.py` |
| `M` | `tests/unit/governance/domain/jobs/handlers/test_cost_handlers.py` |
| `M` | `tests/unit/governance/jobs/test_cur_ingestion_branch_paths.py` |
| `M` | `tests/unit/governance/jobs/test_job_processor.py` |
| `M` | `tests/unit/governance/scheduler/test_orchestrator.py` |
| `M` | `tests/unit/governance/settings/test_notifications.py` |
| `M` | `tests/unit/governance/settings/test_onboard_deep.py` |
| `M` | `tests/unit/governance/settings/test_safety.py` |
| `M` | `tests/unit/llm/test_analyzer_branch_edges.py` |
| `M` | `tests/unit/llm/test_circuit_breaker.py` |
| `M` | `tests/unit/llm/test_hybrid_scheduler.py` |
| `M` | `tests/unit/llm/test_usage_tracker.py` |
| `M` | `tests/unit/llm/test_usage_tracker_audit.py` |
| `M` | `tests/unit/llm/test_zombie_analyzer_exhaustive.py` |
| `M` | `tests/unit/modules/notifications/test_notifications_comprehensive.py` |
| `M` | `tests/unit/modules/optimization/adapters/azure/test_azure_next_gen.py` |
| `M` | `tests/unit/modules/optimization/adapters/azure/test_azure_plugins_fallbacks.py` |
| `M` | `tests/unit/modules/optimization/adapters/azure/test_azure_rightsizing.py` |
| `M` | `tests/unit/modules/optimization/adapters/gcp/test_gcp_new_zombies.py` |
| `M` | `tests/unit/modules/reporting/test_anomaly_detection.py` |
| `M` | `tests/unit/modules/reporting/test_budget_alerts_deep.py` |
| `M` | `tests/unit/modules/reporting/test_carbon_scheduler_comprehensive.py` |
| `M` | `tests/unit/modules/reporting/test_leadership_kpis_domain.py` |
| `M` | `tests/unit/modules/reporting/test_pricing_service.py` |
| `M` | `tests/unit/modules/reporting/test_reporting_service.py` |
| `M` | `tests/unit/modules/reporting/test_webhook_retry.py` |
| `M` | `tests/unit/notifications/domain/test_email_service.py` |
| `M` | `tests/unit/notifications/domain/test_slack_service.py` |
| `M` | `tests/unit/notifications/test_jira_service.py` |
| `M` | `tests/unit/notifications/test_workflow_dispatchers.py` |
| `M` | `tests/unit/optimization/test_detector_error_paths.py` |
| `M` | `tests/unit/optimization/test_optimization_service.py` |
| `M` | `tests/unit/optimization/test_region_discovery_error_paths.py` |
| `M` | `tests/unit/optimization/test_remediation_branch_coverage.py` |
| `M` | `tests/unit/optimization/test_remediation_context_branch_paths.py` |
| `M` | `tests/unit/optimization/test_strategies_api_branch_paths_2.py` |
| `M` | `tests/unit/reporting/test_aggregator.py` |
| `M` | `tests/unit/reporting/test_billing_api.py` |
| `M` | `tests/unit/reporting/test_realized_savings_service_branches.py` |
| `M` | `tests/unit/reporting/test_reconciliation_branch_paths.py` |
| `M` | `tests/unit/reporting/test_reporting_persistence_deep.py` |
| `M` | `tests/unit/services/adapters/test_azure_adapter.py` |
| `M` | `tests/unit/services/adapters/test_cost_cache.py` |
| `M` | `tests/unit/services/billing/test_dunning_service.py` |
| `M` | `tests/unit/services/billing/test_paystack_billing_branches.py` |
| `M` | `tests/unit/services/jobs/test_job_handlers.py` |
| `M` | `tests/unit/services/scheduler/test_processors_expanded.py` |
| `M` | `tests/unit/services/zombies/test_base.py` |
| `M` | `tests/unit/services/zombies/test_remediation_service.py` |
| `M` | `tests/unit/services/zombies/test_zombie_service.py` |
| `M` | `tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py` |
| `M` | `tests/unit/tasks/test_scheduler_tasks.py` |
| `M` | `tests/unit/tasks/test_scheduler_tasks_branch_paths_2.py` |
| `M` | `tests/unit/tasks/test_scheduler_tasks_comprehensive.py` |
| `M` | `tests/unit/zombies/gcp/test_idle_instances.py` |
| `M` | `tests/unit/zombies/test_zombies_api_branches.py` |
| `??` | `tests/unit/api/v1/test_costs_reconciliation_routes.py` |
| `??` | `tests/unit/llm/test_pricing_data.py` |
| `??` | `tests/unit/modules/reporting/test_arm_analyzer.py` |
| `??` | `tests/unit/ops/test_db_diagnostics.py` |
| `??` | `tests/unit/ops/test_verify_adapter_test_coverage.py` |
| `??` | `tests/unit/ops/test_verify_audit_report_resolved.py` |
| `??` | `tests/unit/ops/test_verify_env_hygiene.py` |
| `??` | `tests/unit/ops/test_verify_exception_governance.py` |
| `??` | `tests/unit/ops/test_verify_python_module_size_budget.py` |
| `??` | `tests/unit/ops/test_verify_repo_root_hygiene.py` |
| `??` | `tests/unit/shared/adapters/test_license_vendor_types.py` |
| `??` | `tests/unit/shared/testing/` |

### Track V - Frontend landing, content, and public routes (46)

| Status | Path |
|---|---|
| `M` | `dashboard/e2e/landing-layout-audit.spec.ts` |
| `M` | `dashboard/src/hooks.server.test.ts` |
| `M` | `dashboard/src/lib/components/LandingHero.css` |
| `M` | `dashboard/src/lib/components/LandingHero.svelte` |
| `M` | `dashboard/src/lib/components/LandingHero.svelte.test.ts` |
| `M` | `dashboard/src/lib/components/landing/LandingRoiCalculator.svelte` |
| `M` | `dashboard/src/lib/components/landing/LandingRoiSimulator.svelte` |
| `M` | `dashboard/src/lib/components/landing/LandingSignalMapCard.svelte` |
| `M` | `dashboard/src/lib/components/landing/LandingTrustSection.svelte` |
| `M` | `dashboard/src/lib/components/landing/landing_decomposition.svelte.test.ts` |
| `M` | `dashboard/src/lib/landing/heroContent.ts` |
| `M` | `dashboard/src/lib/landing/publicNav.test.ts` |
| `M` | `dashboard/src/lib/landing/publicNav.ts` |
| `M` | `dashboard/src/lib/landing/realtimeSignalMap.ts` |
| `M` | `dashboard/src/lib/landing/roiCalculator.test.ts` |
| `M` | `dashboard/src/lib/landing/roiCalculator.ts` |
| `M` | `dashboard/src/lib/routeProtection.test.ts` |
| `M` | `dashboard/src/lib/routeProtection.ts` |
| `M` | `dashboard/src/lib/security/turnstile.test.ts` |
| `M` | `dashboard/src/lib/security/turnstile.ts` |
| `M` | `dashboard/src/lib/server/customerCommentsStore.ts` |
| `M` | `dashboard/src/routes/+layout.svelte` |
| `M` | `dashboard/src/routes/admin/customer-comments/+page.svelte` |
| `M` | `dashboard/src/routes/api/marketing/customer-comments/+server.ts` |
| `M` | `dashboard/src/routes/api/marketing/subscribe/+server.ts` |
| `M` | `dashboard/src/routes/billing/+page.svelte` |
| `M` | `dashboard/src/routes/insights/insights-page.svelte.test.ts` |
| `M` | `dashboard/src/routes/layout-public-menu.svelte.test.ts` |
| `M` | `dashboard/src/routes/onboarding/+page.svelte` |
| `M` | `dashboard/src/routes/pricing/+page.svelte` |
| `M` | `dashboard/src/routes/privacy/+page.svelte` |
| `M` | `dashboard/src/routes/privacy/privacy-page.svelte.test.ts` |
| `M` | `dashboard/src/routes/resources/+page.svelte` |
| `M` | `dashboard/src/routes/resources/resources-page.svelte.test.ts` |
| `M` | `dashboard/src/routes/roi-planner/+page.svelte` |
| `M` | `dashboard/src/routes/roi-planner/roi-planner-page.svelte.test.ts` |
| `M` | `dashboard/src/routes/sitemap.xml/+server.ts` |
| `M` | `dashboard/src/routes/talk-to-sales/+page.svelte` |
| `M` | `dashboard/src/routes/talk-to-sales/talk-to-sales-page.svelte.test.ts` |
| `M` | `dashboard/src/routes/terms/+page.svelte` |
| `M` | `dashboard/src/routes/terms/terms-page.svelte.test.ts` |
| `??` | `dashboard/src/lib/components/landing/signal_map_demo.svelte.test.ts` |
| `??` | `dashboard/src/routes/.well-known/` |
| `??` | `dashboard/src/routes/api/geo/` |
| `??` | `dashboard/src/routes/pricing/pricing-page.svelte.test.ts` |
| `??` | `dashboard/src/routes/resources/global-finops-compliance-workbook.md/` |

### Track W - CI, tooling, and operational automation (45)

| Status | Path |
|---|---|
| `M` | `.github/workflows/ci.yml` |
| `M` | `.gitignore` |
| `D` | `scripts/analyze_tables.py` |
| `M` | `scripts/capture_acceptance_evidence.py` |
| `D` | `scripts/check_db.py` |
| `D` | `scripts/check_db_tables.py` |
| `M` | `scripts/check_partitions.py` |
| `M` | `scripts/cleanup_partitions.py` |
| `M` | `scripts/create_partitions.py` |
| `M` | `scripts/database_wipe.py` |
| `D` | `scripts/db_check.py` |
| `D` | `scripts/db_deep_dive.py` |
| `M` | `scripts/deactivate_aws.py` |
| `M` | `scripts/delete_cloudfront.py` |
| `M` | `scripts/disable_cloudfront.py` |
| `M` | `scripts/emergency_disconnect.py` |
| `M` | `scripts/emergency_token.py` |
| `M` | `scripts/force_wipe_app.py` |
| `M` | `scripts/generate_finance_committee_packet.py` |
| `M` | `scripts/list_tables.py` |
| `M` | `scripts/list_zombies.py` |
| `M` | `scripts/load_test_api.py` |
| `M` | `scripts/purge_simulation_data.py` |
| `M` | `scripts/run_enterprise_tdd_gate.py` |
| `M` | `scripts/run_rls_optimization.py` |
| `M` | `scripts/simple_token.py` |
| `M` | `scripts/smoke_test_scim_idp.py` |
| `M` | `scripts/smoke_test_sso_federation.py` |
| `M` | `scripts/soak_ingestion_jobs.py` |
| `M` | `scripts/supabase_cleanup.py` |
| `M` | `scripts/test_tenant_import.py` |
| `M` | `scripts/truncate_cost_records.py` |
| `M` | `scripts/update_exchange_rates.py` |
| `M` | `scripts/validate_runtime_env.py` |
| `M` | `scripts/verify_enforcement_post_closure_sanity.py` |
| `M` | `scripts/verify_greenops.py` |
| `M` | `scripts/verify_pending_approval_flow.py` |
| `M` | `scripts/verify_remediation.py` |
| `??` | `scripts/db_diagnostics.py` |
| `??` | `scripts/verify_adapter_test_coverage.py` |
| `??` | `scripts/verify_audit_report_resolved.py` |
| `??` | `scripts/verify_env_hygiene.py` |
| `??` | `scripts/verify_exception_governance.py` |
| `??` | `scripts/verify_python_module_size_budget.py` |
| `??` | `scripts/verify_repo_root_hygiene.py` |

### Track X - Documentation and evidence updates (8)

| Status | Path |
|---|---|
| `M` | `docs/ops/audit_remediation_2026-02-20.md` |
| `M` | `docs/ops/cloudflare_go_live_checklist_2026-03-02.md` |
| `M` | `docs/ops/landing_page_audit_closure_2026-03-02.md` |
| `??` | `docs/architecture/database_schema_overview.md` |
| `??` | `docs/notes/` |
| `??` | `docs/ops/all_changes_categorization_2026-03-04.md` |
| `??` | `docs/ops/email_auth_dns_baseline_2026-03-04.md` |
| `??` | `docs/ops/evidence/exception_governance_baseline.json` |

## Release Candidate Execution Snapshot (2026-03-05)

### Scope
- Executed after report-driven closure and gate wiring updates.
- Primary objective: run release gate end-to-end and capture closure state.

### What was remediated during RC run
- Fixed stale feature enforceability evidence mapping drift after reporting route decomposition by regenerating:
  - `docs/ops/feature_enforceability_matrix_2026-02-27.json`

### Verification results
- `uv run python3 scripts/verify_audit_report_resolved.py --report-path /home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`
  - result: `passed=27/27`
- `uv run python3 scripts/verify_feature_enforceability_matrix.py --matrix-path docs/ops/feature_enforceability_matrix_2026-02-27.json`
  - result: `passed`
- Targeted TDD pack:
  - `tests/unit/ops/test_verify_audit_report_resolved.py`
  - `tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
  - `tests/unit/ops/test_verify_python_module_size_budget.py`
  - `tests/unit/ops/test_db_diagnostics.py`
  - `tests/unit/supply_chain/test_feature_enforceability_matrix.py`
  - result: `41 passed`
- `uv run python3 scripts/run_enterprise_tdd_gate.py --dry-run`
  - result: command chain validated successfully.

### Full gate status
- A full non-dry run of `scripts/run_enterprise_tdd_gate.py` progressed through all pre-pytest controls and evidence checks (including post-closure sanity and enforceability checks), then entered the large pytest tranche.
- In this environment, the pytest tranche did not complete within watchdog windows and was terminated.
- RC evidence therefore includes:
  - full control-plane/evidence checks passed,
  - full command chain validated (`--dry-run`),
  - targeted regression packs passed,
  - plus a documented long-running pytest tranche behavior requiring dedicated stabilization pass.

## M01-M03 Closure Snapshot (2026-03-05)

### Scope
- Closed the remaining Medium findings explicitly identified as deferred in the resolved audit report:
  - `M-01` optimization module structural bloat.
  - `M-03` oversized compliance pack bundle module.
  - Re-validated `M-02` adapter coverage with direct gate evidence.

### Implemented remediation
- `M-01` (optimization structural debt):
  - Removed legacy compatibility-wrapper modules in `app/modules/optimization/domain/` and provider wrapper subpackages.
  - Updated imports/callsites/tests to direct production modules (`adapters.*`, `domain.remediation`, `domain.plugin`, `domain.ports`).
  - Result: optimization Python module file count reduced from `117` to `102`.
- `M-03` (oversized compliance pack bundle):
  - Refactored `compliance_pack_bundle.py` by extracting zip export and manifest responsibilities into:
    - `app/modules/governance/domain/security/compliance_pack_bundle_exports.py`
  - Added focused unit tests for helper behaviors:
    - `tests/unit/governance/test_compliance_pack_bundle_exports.py`
  - Result: `compliance_pack_bundle.py` reduced to `593` lines (within default `600` budget).
- Governance tightening:
  - Removed special-size override for `compliance_pack_bundle.py` in `scripts/verify_python_module_size_budget.py`.
  - Strengthened `M-01` audit verifier control in `scripts/verify_audit_report_resolved.py`:
    - enforce optimization file-count budget (`<=105`),
    - enforce removal of legacy optimization wrapper files.
  - Tightened `M-03` audit verifier control to default `600`-line budget.

### Verification evidence
- `DEBUG=false UV_CACHE_DIR=/tmp/uv-cache uv run python3 scripts/verify_python_module_size_budget.py` -> passed.
- `DEBUG=false UV_CACHE_DIR=/tmp/uv-cache uv run python3 scripts/verify_adapter_test_coverage.py` -> passed.
- `DEBUG=false UV_CACHE_DIR=/tmp/uv-cache uv run python3 scripts/verify_audit_report_resolved.py --report-path /home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved` -> `passed=27/27`.
- `DEBUG=false UV_CACHE_DIR=/tmp/uv-cache uv run python3 scripts/run_enterprise_tdd_gate.py --dry-run` -> command chain + post-closure sanity checks validated.
- Targeted regression pack:
  - `64 passed` across modified optimization/audit guard/test surfaces.
  - Additional due-diligence unit subset: `10 passed, 2 deselected`.

### Operational notes
- In this environment, some broader API/integration-heavy suites remain long-running when executed as large combined invocations; decomposition-level controls, unit regressions, and report closure gates are all green for `M01-M03`.
