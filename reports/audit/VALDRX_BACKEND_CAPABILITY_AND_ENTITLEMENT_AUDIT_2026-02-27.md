# Valdrx Backend Capability and Entitlement Audit (Fresh)

- Snapshot date: 2026-02-27
- Scope: Runtime-registered FastAPI routes excluding docs/openapi helper routes.
- Total endpoints audited: 241
- Source method: live route graph extraction (`app.main.valdrix_app`) + dependency closure decoding + in-handler gate signal scan.

## Endpoint Counts by Auth Surface

- `admin_api_key`: 2
- `jwt_db`: 208
- `jwt_only`: 1
- `public`: 18
- `scim_bearer_token`: 12

## Endpoint Counts by Minimum User Level

- `admin`: 89
- `authenticated_pre_onboarding`: 1
- `member`: 117
- `n/a`: 14
- `owner`: 2
- `public`: 18

## Capability Areas (Endpoint Count)

- `admin_utilities`: 2
- `attribution_chargeback`: 8
- `audit_compliance`: 24
- `billing`: 10
- `carbon_greenops`: 11
- `connections`: 44
- `cost_reporting`: 24
- `currency`: 2
- `enforcement_control_plane`: 30
- `health_dashboard`: 2
- `jobs_background`: 7
- `leadership`: 6
- `lifecycle_observability`: 4
- `oidc_discovery`: 2
- `optimization_commitments`: 4
- `optimization_zombies`: 8
- `other`: 1
- `public_endpoints`: 3
- `savings`: 4
- `scim`: 16
- `settings_governance`: 28
- `usage_metering`: 1

## Role Model (Backend Enforcement Basis)

- `owner`: full access; bypasses lower role checks.
- `admin`: configuration and operational control endpoints.
- `member`: default authenticated access for read and routine execution flows.
- `authenticated_pre_onboarding`: JWT-authenticated but not tenant-bound routes (onboard).
- Non-user auth surfaces: `admin_api_key`, `scim_bearer_token`, and public routes.

## Tier Feature Matrix (What Each Plan Gets)

| Feature | free | starter | growth | pro | enterprise |
|---|---|---|---|---|---|
| ai_analysis_detailed | - | - | - | Y | Y |
| ai_insights | - | Y | Y | Y | Y |
| alerts | Y | Y | Y | Y | Y |
| anomaly_detection | - | - | Y | Y | Y |
| api_access | - | - | - | Y | Y |
| audit_logs | - | - | - | Y | Y |
| auto_remediation | - | - | Y | Y | Y |
| carbon_assurance | - | - | - | Y | Y |
| carbon_tracking | Y | Y | Y | Y | Y |
| chargeback | - | - | Y | Y | Y |
| close_workflow | - | - | - | Y | Y |
| cloud_plus_connectors | - | - | - | Y | Y |
| commitment_optimization | - | - | Y | Y | Y |
| compliance_exports | - | - | - | Y | Y |
| cost_tracking | Y | Y | Y | Y | Y |
| dashboards | Y | Y | Y | Y | Y |
| dedicated_support | - | - | - | Y | Y |
| domain_discovery | Y | Y | Y | Y | Y |
| escalation_workflow | - | - | Y | Y | Y |
| forecasting | - | - | - | - | Y |
| gitops_remediation | - | - | - | Y | Y |
| greenops | Y | Y | Y | Y | Y |
| hourly_scans | - | - | - | Y | Y |
| idp_deep_scan | - | - | - | Y | Y |
| incident_integrations | - | - | - | Y | Y |
| ingestion_backfill | - | - | Y | Y | Y |
| ingestion_sla | - | Y | Y | Y | Y |
| llm_analysis | Y | Y | Y | Y | Y |
| multi_cloud | - | - | Y | Y | Y |
| multi_region | - | Y | Y | Y | Y |
| owner_attribution | - | - | Y | Y | Y |
| policy_configuration | - | - | - | Y | Y |
| policy_preview | - | - | Y | Y | Y |
| precision_discovery | - | - | Y | Y | Y |
| reconciliation | - | - | - | Y | Y |
| savings_proof | - | - | - | Y | Y |
| scim | - | - | - | - | Y |
| slack_integration | - | - | - | Y | Y |
| sso | - | - | - | Y | Y |
| unit_economics | Y | Y | Y | Y | Y |
| zombie_scan | Y | Y | Y | Y | Y |

## Tier Limits (Configured Limits in Code)

### free
- `ai_insights_per_month`: `0`
- `byok_enabled`: `True`
- `llm_analyses_per_day`: `1`
- `llm_analyses_per_user_per_day`: `1`
- `llm_analysis_max_records`: `128`
- `llm_analysis_max_window_days`: `31`
- `llm_output_max_tokens`: `512`
- `llm_prompt_max_input_tokens`: `2048`
- `llm_system_analyses_per_day`: `1`
- `max_aws_accounts`: `1`
- `max_azure_tenants`: `0`
- `max_backfill_days`: `0`
- `max_gcp_projects`: `0`
- `max_hybrid_connections`: `0`
- `max_license_connections`: `0`
- `max_platform_connections`: `0`
- `max_saas_connections`: `0`
- `retention_days`: `30`
- `scan_frequency_hours`: `168`
- `zombie_scans_per_day`: `1`

### starter
- `ai_insights_per_month`: `10`
- `byok_enabled`: `True`
- `llm_analyses_per_day`: `5`
- `llm_analyses_per_user_per_day`: `2`
- `llm_analysis_max_records`: `256`
- `llm_analysis_max_window_days`: `90`
- `llm_output_max_tokens`: `1024`
- `llm_prompt_max_input_tokens`: `4096`
- `llm_system_analyses_per_day`: `2`
- `max_aws_accounts`: `5`
- `max_azure_tenants`: `0`
- `max_backfill_days`: `0`
- `max_gcp_projects`: `0`
- `max_hybrid_connections`: `0`
- `max_license_connections`: `0`
- `max_platform_connections`: `0`
- `max_saas_connections`: `0`
- `retention_days`: `90`
- `scan_frequency_hours`: `24`

### growth
- `byok_enabled`: `True`
- `llm_analyses_per_day`: `20`
- `llm_analyses_per_user_per_day`: `8`
- `llm_analysis_max_records`: `1024`
- `llm_analysis_max_window_days`: `365`
- `llm_output_max_tokens`: `2048`
- `llm_prompt_max_input_tokens`: `12288`
- `llm_system_analyses_per_day`: `5`
- `max_aws_accounts`: `20`
- `max_azure_tenants`: `10`
- `max_backfill_days`: `180`
- `max_gcp_projects`: `15`
- `max_hybrid_connections`: `0`
- `max_license_connections`: `0`
- `max_platform_connections`: `0`
- `max_saas_connections`: `0`
- `retention_days`: `365`

### pro
- `ai_insights_per_month`: `100`
- `byok_enabled`: `True`
- `llm_analyses_per_day`: `100`
- `llm_analyses_per_user_per_day`: `25`
- `llm_analysis_max_records`: `5000`
- `llm_analysis_max_window_days`: `730`
- `llm_output_max_tokens`: `4096`
- `llm_prompt_max_input_tokens`: `32768`
- `llm_system_analyses_per_day`: `30`
- `max_aws_accounts`: `25`
- `max_azure_tenants`: `25`
- `max_backfill_days`: `730`
- `max_gcp_projects`: `25`
- `max_hybrid_connections`: `10`
- `max_license_connections`: `10`
- `max_platform_connections`: `10`
- `max_saas_connections`: `10`
- `retention_days`: `730`
- `scan_frequency_hours`: `1`

### enterprise
- `ai_insights_per_month`: `999`
- `byok_enabled`: `True`
- `llm_analyses_per_day`: `2000`
- `llm_analyses_per_user_per_day`: `500`
- `llm_analysis_max_records`: `20000`
- `llm_analysis_max_window_days`: `3650`
- `llm_output_max_tokens`: `8192`
- `llm_prompt_max_input_tokens`: `65536`
- `llm_system_analyses_per_day`: `400`
- `max_aws_accounts`: `999`
- `max_azure_tenants`: `999`
- `max_gcp_projects`: `999`
- `max_hybrid_connections`: `999`
- `max_license_connections`: `999`
- `max_platform_connections`: `999`
- `max_saas_connections`: `999`
- `retention_days`: `None`
- `scan_frequency_hours`: `1`

## Most-Enforced Strict Features (by Endpoint Count)

- `compliance_exports`: 26
- `scim`: 12
- `chargeback`: 10
- `cloud_plus_connectors`: 8
- `carbon_assurance`: 6
- `greenops`: 5
- `close_workflow`: 5
- `sso`: 5
- `audit_logs`: 4
- `savings_proof`: 4
- `multi_cloud`: 4
- `commitment_optimization`: 4
- `unit_economics`: 3
- `reconciliation`: 2
- `auto_remediation`: 2
- `policy_preview`: 2
- `llm_analysis`: 1
- `anomaly_detection`: 1
- `ingestion_sla`: 1
- `cost_tracking`: 1

## Full Endpoint Matrix

See CSV for the exhaustive route-by-route matrix with method/path/auth/min-role/strict-features/eligible-tiers/manual-signal columns:

- `reports/audit/VALDRX_BACKEND_ENDPOINT_ACCESS_MATRIX_2026-02-27.csv`

