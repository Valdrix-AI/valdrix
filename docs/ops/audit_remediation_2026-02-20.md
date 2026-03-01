# Audit Remediation Log (2026-02-20)

Source audit: `/home/daretechie/.gemini/antigravity/brain/c6c55133-7d83-4352-ab23-f80736e51075/audit_report.md.resolved`

## Remediation Status

## Additional remediation batch (2026-03-01, source: `.../dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`)

## Additional remediation batch (2026-03-01B, source: `.../dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`)

1. Horizontal scaling breaker-state blocker (remediation plane)
- Closed process-local only factory behavior in:
  - `app/shared/remediation/circuit_breaker.py`
- `get_circuit_breaker()` now resolves and injects a distributed Redis client when `CIRCUIT_BREAKER_DISTRIBUTED_STATE=true` and `REDIS_URL` is present, with safe in-memory fallback when unavailable.
- Added regression coverage:
  - `tests/unit/remediation/test_circuit_breaker_deep.py`
    - distributed client injection path
    - graceful fallback path
    - distributed resolver behavior

2. Enforcement fail-open risk on spend-context outage
- Closed fail-open posture when computed spend context is unavailable in:
  - `app/modules/enforcement/domain/service.py`
- Behavior now fails by enforcement mode when `computed_context.data_source_mode == "unavailable"` and request delta is positive:
  - `SHADOW` -> allow with explicit override reason,
  - `SOFT` -> require approval escalation,
  - `HARD` -> deny fail-closed.
- Added regression coverage:
  - `tests/unit/enforcement/test_enforcement_service.py`
    - soft-mode escalation on unavailable cost context
    - hard-mode denial on unavailable cost context

3. Validation evidence (this batch)
- `DEBUG=false uv run pytest -q --no-cov tests/unit/remediation/test_circuit_breaker_deep.py tests/core/test_circuit_breaker.py tests/unit/enforcement/test_enforcement_service.py -k "computed_context_unavailable or circuit_breaker"` -> `30 passed`.
- `uv run ruff check app/shared/remediation/circuit_breaker.py app/modules/enforcement/domain/service.py tests/unit/remediation/test_circuit_breaker_deep.py tests/unit/enforcement/test_enforcement_service.py` -> passed.
- `uv run mypy app/shared/remediation/circuit_breaker.py app/modules/enforcement/domain/service.py --hide-error-context --no-error-summary` -> passed.
- `cd dashboard && npm run test:e2e -- e2e/landing-layout-audit.spec.ts` -> passed (`2 passed`).
- `cd dashboard && npm run test:unit -- --run src/routes/layout.server.load.test.ts` -> passed (`4 passed`).
- `cd dashboard && npm run check` -> passed (`0 errors`, `0 warnings`).

## Additional remediation batch (2026-03-01C, source: `.../dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`)

1. Public-edge bot protection hardening (Turnstile propagation)
- Added shared frontend Turnstile helper:
  - `dashboard/src/lib/security/turnstile.ts`
- Wired Turnstile token forwarding for protected public/auth surfaces:
  - SSO discovery request: `dashboard/src/routes/auth/login/+page.svelte`
  - onboarding bootstrap request: `dashboard/src/routes/onboarding/+page.svelte`
- Added deterministic helper coverage:
  - `dashboard/src/lib/security/turnstile.test.ts`
  - updated route tests:
    - `dashboard/src/routes/auth/login/login-page.svelte.test.ts`
    - `dashboard/src/routes/onboarding/onboarding-page.svelte.test.ts`

2. Public auth-provider failure-mode hardening
- Hardened `safeGetSession()` against provider/network resolution failures in:
  - `dashboard/src/hooks.server.ts`
- Behavior now degrades to anonymous session state instead of crashing request flow.

3. Active-enforcement IAM policy baseline (Terraform)
- Implemented tag-scoped optional active remediation policy in:
  - `terraform/modules/iam/main.tf`
  - `terraform/modules/iam/variables.tf`
  - root wiring:
    - `terraform/main.tf`
    - `terraform/variables.tf`
    - `terraform/outputs.tf`
- Control is explicit and disabled by default:
  - `enable_active_enforcement = false` baseline.

4. Migration graph integrity hardening
- Added Alembic head-integrity verifier:
  - `scripts/verify_alembic_head_integrity.py`
- Added regression coverage:
  - `tests/unit/ops/test_verify_alembic_head_integrity.py`
- Wired verifier into enterprise gate command construction:
  - `scripts/run_enterprise_tdd_gate.py`
  - updated gate-runner tests:
    - `tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`

5. Validation evidence (this batch)
- `uv run python3 scripts/verify_alembic_head_integrity.py --migrations-path migrations/versions` -> passed.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/ops/test_verify_alembic_head_integrity.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py tests/unit/remediation/test_circuit_breaker_deep.py tests/unit/enforcement/test_enforcement_service.py -k "alembic or enterprise_tdd_gate_runner or computed_context_unavailable or circuit_breaker"` -> `48 passed`.
- `uv run ruff check app/shared/remediation/circuit_breaker.py app/modules/enforcement/domain/service.py scripts/verify_alembic_head_integrity.py scripts/run_enterprise_tdd_gate.py tests/unit/remediation/test_circuit_breaker_deep.py tests/unit/enforcement/test_enforcement_service.py tests/unit/ops/test_verify_alembic_head_integrity.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py` -> passed.
- `uv run mypy app/shared/remediation/circuit_breaker.py app/modules/enforcement/domain/service.py scripts/verify_alembic_head_integrity.py scripts/run_enterprise_tdd_gate.py --hide-error-context --no-error-summary` -> passed.
- `cd dashboard && npm run test:unit -- --run src/routes/auth/login/login-page.svelte.test.ts src/routes/onboarding/onboarding-page.svelte.test.ts src/lib/security/turnstile.test.ts src/routes/layout.server.load.test.ts` -> passed (`12 passed`).
- `cd dashboard && npm run check` -> passed (`0 errors`, `0 warnings`).
- `cd dashboard && npm run test:e2e -- e2e/landing-layout-audit.spec.ts` -> passed (`2 passed`).

1. Multi-cloud identity parity and unified domain auditing
- Added deterministic auditors:
  - `app/modules/governance/domain/security/azure_rbac_auditor.py`
  - `app/modules/governance/domain/security/gcp_iam_auditor.py`
  - `app/modules/governance/domain/security/unified_domain_auditor.py`
  - `app/modules/governance/domain/security/finding_models.py`
- Added regression tests:
  - `tests/governance/test_azure_rbac_auditor.py`
  - `tests/governance/test_gcp_iam_auditor.py`
  - `tests/governance/test_unified_domain_auditor.py`

2. Scheduler observability hardening
- Added explicit OTel spans and error-status propagation in:
  - `app/tasks/scheduler_tasks.py`
- Added branch-path coverage:
  - `tests/unit/tasks/test_scheduler_tasks_branch_paths_2.py`

3. Alerting hardening (silent-channel closure)
- Activated severity receivers in:
  - `prometheus/alertmanager.yml`
- Added verifier and enterprise-gate integration:
  - `scripts/verify_alertmanager_channels.py`
  - `scripts/run_enterprise_tdd_gate.py`
- Added tests:
  - `tests/unit/ops/test_verify_alertmanager_channels.py`

4. Landing maintainability and public-edge failure-mode hardening
- Extracted large landing marketing content constants to:
  - `dashboard/src/lib/landing/heroContent.ts`
- Updated public layout load to degrade gracefully on public-path auth resolution failures while preserving protected-path fail-closed behavior:
  - `dashboard/src/routes/+layout.server.ts`
  - `dashboard/src/routes/layout.server.load.test.ts`

5. Validation evidence (this batch)
- `DEBUG=false uv run pytest -q --no-cov tests/governance/test_azure_rbac_auditor.py tests/governance/test_gcp_iam_auditor.py tests/governance/test_unified_domain_auditor.py tests/unit/ops/test_verify_alertmanager_channels.py tests/unit/tasks/test_scheduler_tasks_branch_paths_2.py tests/unit/tasks/test_scheduler_tasks.py` -> `65 passed`.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py` -> `28 passed`.
- `uv run ruff check ...` (changed scheduler/security/audit-gate files + tests) -> passed.
- `uv run mypy app/tasks/scheduler_tasks.py app/modules/governance/domain/security/finding_models.py app/modules/governance/domain/security/azure_rbac_auditor.py app/modules/governance/domain/security/gcp_iam_auditor.py app/modules/governance/domain/security/unified_domain_auditor.py scripts/verify_alertmanager_channels.py scripts/run_enterprise_tdd_gate.py --hide-error-context --no-error-summary` -> passed.
- `uv run python3 scripts/verify_alertmanager_channels.py --config-path prometheus/alertmanager.yml` -> passed.
- `cd dashboard && npm run test:unit -- --run src/routes/layout.server.load.test.ts` -> passed (`4 tests`).
- `cd dashboard && npm run check` -> passed (`0 errors`, `0 warnings`).

0. Helm `WORKERS: "4"` + multi-replica defaults vs process-local breaker
- Fixed in `helm/valdrix/values.yaml`:
  - `WORKERS` removed
  - `WEB_CONCURRENCY: "1"` added
  - API default `replicaCount` set to `1`
  - HPA defaults set to single-replica safe baseline (`enabled: false`, `min/max: 1`)

1. Dockerfile HEALTHCHECK missing `curl`
- Fixed in `Dockerfile` by switching to Python/urllib health probe.

2. Local `.env` contains live secrets
- Code/config cannot rotate third-party credentials automatically.
- Added emergency runbook: `docs/runbooks/secret_rotation_emergency.md`.
- Added local detector: `scripts/security/check_local_env_for_live_secrets.py`.
- Action required: operator-led credential rotation and revocation.

3. NullPool in production
- Fixed via explicit pool strategy controls:
  - `DB_USE_NULL_POOL` (default `false`)
  - `DB_EXTERNAL_POOLER` guard for production
- Runtime defaults now use queue pooling in `app/shared/db/session.py`.

4. Core circuit breaker state is process-local
- Added production/staging fail-closed guard:
  - `WEB_CONCURRENCY` must be `1` while core breaker state remains process-local.
- Documented in ADR: `docs/architecture/ADR-0003-core-circuit-breaker-state-scope.md`.

5. JWT HS256 symmetric signing
- Accepted risk documented in ADR:
  `docs/architecture/ADR-0004-supabase-jwt-hs256.md`.

6. In-memory remediation rate limit fallback
- Already mitigated (unchanged).

7. `docker-compose.prod.yml` using `:test` images
- Fixed to registry/version-based image references.

8. CSRF secret fallback to empty string
- Fixed fail-closed behavior in `app/main.py`:
  - requires configured secret
  - testing-only non-empty deterministic fallback

9. Celery `autoretry_for=(Exception,)` too broad
- Fixed in `app/tasks/license_tasks.py`:
  narrowed retries to transient transport/DB/API exceptions.

10. Scattered `test_*.sqlite` root artifacts
- Local cleanup applied for generated files.
- Existing `.gitignore` patterns already prevent tracking.

11. Large root log/debug files
- Local cleanup applied for generated files.
- Existing `.gitignore` `*.log` already prevents tracking.

12. Budget hard-cap destructive behavior without approval/undo path
- Fixed in `app/shared/remediation/hard_cap_service.py`:
  - explicit approval gate (`approved=True`) required
  - pre-enforcement state snapshot captured
  - durable immutable audit events recorded for blocked/enforced/reversed actions
  - reversible flow implemented via `reverse_hard_cap()`
- Added admin reactivation endpoint:
  - `POST /api/v1/settings/activeops/hard-cap/reactivate`
  - implementation: `app/modules/governance/api/v1/settings/activeops.py`
  - tests: `tests/unit/governance/settings/test_activeops.py`

13. Cloud plugin TODOs (pricing/SKU completeness)
- Fixed:
  - `app/modules/optimization/adapters/aws/plugins/search.py` now uses `PricingService` for OpenSearch estimates
  - `app/modules/optimization/adapters/azure/plugins/ai.py` now performs SKU/PTU-aware cost estimation for Azure OpenAI
  - pricing catalog defaults updated in `app/shared/core/pricing_defaults.py`
  - pricing fallback logic hardened in `app/modules/reporting/domain/pricing/service.py`

14. Coverage gate mismatch (report finding F5)
- Still open as a platform-wide testing posture item; not closed by a localized code patch.
- Targeted regression suites for remediated paths are passing.

15. N+1 redundancy in bulk IaC plan generation (report finding F22)
- Fixed in `app/modules/optimization/domain/remediation.py`:
  - `generate_iac_plan()` now accepts optional pre-resolved `tenant_tier`
  - `bulk_generate_iac_plan()` resolves tenant tier once and reuses it for all items
- Regression test added:
  - `tests/unit/optimization/test_remediation_branch_coverage.py::test_bulk_generate_iac_plan_resolves_tier_once`

16. Paystack renewal date drift (report finding F24)
- Fixed in `app/modules/billing/domain/billing/paystack_billing.py`:
  - Added provider-authoritative next-payment-date fetch via `fetch_subscription()`
  - Added deterministic fallback calculation with interval inference (`monthly`/`annual`) and anchor protection
  - Replaced hardcoded `+30 days` renewal update path
- Regression tests added:
  - `tests/unit/services/billing/test_paystack_billing_branches.py::test_charge_renewal_uses_provider_next_payment_date_when_available`
  - `tests/unit/services/billing/test_paystack_billing_branches.py::test_charge_renewal_fallback_uses_annual_cycle_when_metadata_declares_annual`

17. Billing webhook race condition (report finding F25)
- Fixed at queueing boundary in `app/modules/governance/domain/jobs/processor.py`:
  - `enqueue_job()` now supports `deduplication_key`
  - handles unique-key collisions atomically and returns existing job instead of failing
- Fixed webhook ingestion flow in `app/modules/billing/domain/billing/webhook_retry.py`:
  - webhooks are enqueued with deterministic dedup keys
  - already-queued/already-processed duplicates return `None` (no re-processing in request path)
- API behavior clarified in `app/modules/billing/api/v1/billing.py` duplicate response messaging.
- Regression tests added:
  - `tests/governance/test_job_processor.py::test_returns_existing_job_when_dedup_key_conflicts`
  - updated `tests/unit/modules/reporting/test_webhook_retry.py` duplicate/queued semantics and dedup key assertions

18. Adapter retry-loop duplication and configuration parsing complexity
- Fixed by introducing shared adapter retry primitive:
  - `app/shared/adapters/http_retry.py::execute_with_http_retry()`
  - centralizes retryable status handling, transport retry behavior, and external API error normalization.
- Refactored adapters to use shared retry helper:
  - `app/shared/adapters/license.py`
  - `app/shared/adapters/saas.py`
  - `app/shared/adapters/platform.py`
  - `app/shared/adapters/hybrid.py`
- Extracted typed Google Workspace license connector config parsing:
  - `app/shared/adapters/license_config.py`
  - `app/shared/adapters/license.py` now consumes parsed config instead of ad-hoc dict plumbing.
- Added/updated regression coverage:
  - `tests/unit/shared/adapters/test_http_retry.py`
  - `tests/unit/shared/adapters/test_license_config.py`
  - updated retry-branch tests in:
    - `tests/unit/services/adapters/test_platform_additional_branches.py`
    - `tests/unit/services/adapters/test_hybrid_additional_branches.py`
    - `tests/unit/services/adapters/test_license_verification_stream_branches.py`
    - `tests/unit/shared/adapters/test_saas_adapter_branch_paths.py`

## Additional remediation batch (source: `.../4125ec18-fcb0-408c-a482-b7f431e9e6f6/walkthrough.md.resolved`)

- Fixed `SecretReloader` mutable-singleton pattern by replacing it with
  `reload_settings_from_environment()` in `app/shared/core/config.py`.
  - Uses `get_settings.cache_clear()` and rebuilds settings atomically under a lock.
  - Refreshes encryption key caches after reload.
  - Wired into app startup (`app/main.py` lifespan) to avoid dead-code drift.
- Added `JWT_SIGNING_KID` support for locally-issued tokens.
  - `create_access_token()` now includes JWT header `kid` when configured.
  - Test coverage: `tests/unit/core/test_auth_audit.py::test_create_access_token_sets_kid_header_when_configured`.
- Health endpoint now uses `get_system_db()` instead of tenant-scoped `get_db()`.
  - File: `app/shared/core/app_routes.py`.
- Docker reliability updates:
  - Liveness healthcheck switched to `/health/live`.
  - Runtime command now supports `WEB_CONCURRENCY` workers via shell expansion.
- Removed tautological CORS guard branch (`and True`) in `app/main.py`.
- Added stale in-memory remediation rate-limit state eviction in
  `app/shared/core/rate_limit.py` to prevent unbounded key growth.
- Filled observability gap in cohort scheduler:
  - `BACKGROUND_JOBS_ENQUEUED` is now incremented in `_cohort_analysis_logic`.
- Updated zombie API tests for current request schema (`provider` required):
  - `tests/api/test_endpoints.py`.
- Added local pre-commit hook to detect live secrets in `.env`:
  - `.pre-commit-config.yaml`
  - `scripts/security/check_local_env_for_live_secrets.py`
- Refactored DB runtime initialization to be lazy (remediates import-time engine/session construction):
  - `app/shared/db/session.py` no longer creates engine/session maker at module import.
  - Added lazy runtime builder and compatibility proxies for `engine` / `async_session_maker`.
  - Slow-query listeners are now attached when runtime initializes.
  - Added `reset_db_runtime()` helper and updated exhaustive tests for lazy-init semantics.

### Validation evidence

- `uv run ruff check app/shared/core/config.py app/shared/core/app_routes.py app/main.py app/shared/core/rate_limit.py app/tasks/scheduler_tasks.py app/shared/core/auth.py tests/api/test_endpoints.py tests/unit/core/test_auth_audit.py`
- `uv run mypy app/shared/core/config.py app/shared/core/app_routes.py app/main.py app/shared/core/rate_limit.py app/tasks/scheduler_tasks.py app/shared/core/auth.py --hide-error-context --no-error-summary`
- `uv run pytest tests/api/test_endpoints.py -q --no-cov -k "create_remediation_request_success or create_remediation_request_invalid_action or feature_flag_gates_endpoints or invalid_enum_values"`
- `uv run pytest tests/unit/core/test_auth_audit.py tests/unit/core/test_rate_limit_expanded.py tests/unit/tasks/test_scheduler_tasks.py tests/unit/test_main_coverage.py tests/contract/test_openapi_contract.py -q --no-cov`
- `uv run ruff check app/shared/db/session.py tests/unit/db/test_session_exhaustive.py`
- `uv run mypy app/shared/db/session.py --hide-error-context --no-error-summary`
- `uv run pytest tests/unit/db/test_session.py tests/unit/db/test_session_exhaustive.py tests/unit/db/test_session_deep.py tests/unit/shared/db/test_session_coverage.py tests/unit/core/test_session_audit.py tests/unit/core/test_db_session_deep.py -q --no-cov`
- `uv run ruff check app/shared/adapters/http_retry.py app/shared/adapters/license_config.py app/shared/adapters/license.py app/shared/adapters/saas.py app/shared/adapters/platform.py app/shared/adapters/hybrid.py tests/unit/shared/adapters/test_http_retry.py tests/unit/shared/adapters/test_license_config.py tests/unit/services/adapters/test_platform_additional_branches.py tests/unit/services/adapters/test_hybrid_additional_branches.py tests/unit/services/adapters/test_license_verification_stream_branches.py tests/unit/shared/adapters/test_saas_adapter_branch_paths.py`
- `uv run mypy app/shared/adapters/http_retry.py app/shared/adapters/license_config.py app/shared/adapters/license.py app/shared/adapters/saas.py app/shared/adapters/platform.py app/shared/adapters/hybrid.py --hide-error-context --no-error-summary`
- `DEBUG=false uv run pytest -q --no-cov tests/unit/shared/adapters/test_http_retry.py tests/unit/shared/adapters/test_license_config.py tests/unit/services/adapters/test_cloud_plus_adapters.py tests/unit/services/adapters/test_platform_hybrid_adapters.py tests/unit/services/adapters/test_platform_additional_branches.py tests/unit/services/adapters/test_hybrid_additional_branches.py tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/services/adapters/test_license_verification_stream_branches.py tests/unit/shared/adapters/test_saas_adapter_branch_paths.py`

### Residual non-code actions

- Local `.env` still contains live-pattern secrets on the developer workstation.
  - Verified by `python3 scripts/security/check_local_env_for_live_secrets.py`.
  - This requires external rotation/revocation in provider dashboards; no code patch can rotate third-party credentials.

### Finding reassessment notes

- `H-3` is now remediated via lazy DB runtime initialization in `app/shared/db/session.py`.

## Additional remediation batch (source: `.../dc5ab0ea-74a8-4714-a511-0dade0451f8a/VALDRX_CODEBASE_AUDIT_2026-02-28.md.resolved`)

- `VAL-CORE-001` remediated in `app/shared/core/pricing.py`:
  - Added explicit `Preview` feature roster (`_PREVIEW_MATURITY_FEATURES`).
  - Added startup invariants that enforce complete and exact maturity coverage for every `FeatureFlag`.
  - Runtime now fails closed with a `RuntimeError` if maturity classification drifts.
- `VAL-BILL-001` remediated in `app/modules/billing/domain/billing/paystack_service_impl.py`:
  - Removed eager plan-code capture at service initialization.
  - Added lazy `plan_codes` and `annual_plan_codes` properties that resolve from live settings at access time.
- `VAL-ADAPT-002` decomposition advanced in `app/shared/adapters/license.py`:
  - Extracted vendor-specific verify/revoke/activity operations into `app/shared/adapters/license_vendor_ops.py`.
  - Extracted vendor-specific stream-cost implementations for Google Workspace and Microsoft 365 into `app/shared/adapters/license_vendor_ops.py`.
  - `LicenseAdapter` now delegates these operations through thin wrappers, reducing vendor-strategy density in the core adapter file.

### Validation evidence (this batch)

- `uv run ruff check app/shared/core/pricing.py app/modules/billing/domain/billing/paystack_service_impl.py app/shared/adapters/license.py app/shared/adapters/license_vendor_ops.py tests/unit/services/adapters/test_license_verification_stream_branches.py`
- `uv run mypy app/shared/core/pricing.py app/modules/billing/domain/billing/paystack_service_impl.py app/shared/adapters/license.py app/shared/adapters/license_vendor_ops.py --hide-error-context --no-error-summary`
- `DEBUG=false uv run pytest -q --no-cov tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/services/adapters/test_license_verification_stream_branches.py tests/unit/services/billing/test_paystack_billing_branches.py tests/unit/core/test_pricing_packaging_contract.py` (`76 passed`)

### Residual architecture backlog

- `VAL-ADAPT-002+` remains open as maintainability refactor scope (full class-size/vendor-strategy split), not an immediate correctness or security hotfix blocker.

## Consolidated remediation status (Valdrics follow-up, 2026-02-28)

This section consolidates what is now remediated from the Valdrics audit stream so reviewers do not need to reconstruct status across multiple execution updates.

### Fully remediated (code + regression evidence captured)

- `VAL-DB-001`: RLS fail-closed session context hardening in `app/shared/db/session.py`.
- `VAL-BILL-005`: dunning enqueue rollback-safety hardening in `app/modules/billing/domain/billing/dunning_service.py`.
- `VAL-SEC-001`: CSRF test fallback hardening in `app/main.py`.
- `VAL-SEC-003`: proxy-header trust hardening for webhook source-IP handling in billing API/config.
- `VAL-CORE-003/004`: tenant-tier lookup/caching hardening in `app/shared/core/pricing.py`.
- `VAL-CORE-004`: removed awaitable-model branch in tenant-tier lookup; normalized async scalar handling in `app/shared/core/pricing.py`.
- `VAL-CORE-001`: explicit feature-maturity coverage invariants and fail-closed startup checks in `app/shared/core/pricing.py`.
- `VAL-BILL-001`: lazy/live Paystack plan-code resolution in `app/modules/billing/domain/billing/paystack_service_impl.py`.
- `VAL-BILL-006`: centralized entitlement sync policy in `app/modules/billing/domain/billing/entitlement_policy.py` (adopted by dunning + webhook flows).
- `VAL-SEC-002`: machine-checkable auth coverage audit with gate wiring (`scripts/verify_api_auth_coverage.py`).
- `VAL-ADAPT-005` (engineering scope): shared AWS paginator abstraction + rollout (`app/shared/adapters/aws_pagination.py`).
- `VAL-ADAPT-003`: shared HTTP retry abstraction implemented and consumed across Cloud+ adapters.
- `VAL-ADAPT-004`: typed Google Workspace connector config parser implemented and integrated.

### Partially remediated (architecture decomposition advanced)

- `VAL-ADAPT-002`:
  - Vendor verify/revoke/activity logic extracted into `app/shared/adapters/license_vendor_ops.py`.
  - `LicenseAdapter` delegates through thin wrappers to preserve test seams and behavior.
  - Remaining scope is deeper class-size decomposition (stream/discovery strategy split), tracked as maintainability backlog.

### Reassessed as non-hotfix architecture backlog in this pass

- Remaining `VAL-ADAPT-002+` class-size/vendor-strategy decomposition scope.
- No unresolved release-critical correctness/security defect was confirmed in this subset after remediation and regression reruns.

## Additional remediation batch (Valdrics continuation, 2026-02-28N)

- `VAL-SEC-002` remediated with machine-checkable API auth coverage:
  - Added `scripts/verify_api_auth_coverage.py` to recursively inspect route dependency trees.
  - Enforced explicit auth dependencies for private routes with allowlist-only public exceptions.
  - Wired verifier into `scripts/run_enterprise_tdd_gate.py`.
  - Hardened endpoints that were not explicitly covered:
    - `app/modules/governance/api/v1/jobs.py` (`/internal/process` now requires `require_internal_job_secret` dependency).
    - `app/modules/governance/api/v1/settings/llm.py` (`/llm/models` now requires authenticated user context).
- `VAL-ADAPT-005` advanced with shared paginator utility rollout:
  - Added `app/shared/adapters/aws_pagination.py::iter_aws_paginator_pages()`.
  - Applied to:
    - `app/shared/adapters/aws_resource_explorer.py`
    - `app/shared/adapters/aws_cur.py` (`s3.list_objects_v2` scan cap + warning on capped traversal).
- `VAL-BILL-006` remediated by replacing scattered manual tenant-plan sync updates with a centralized entitlement policy path:
  - Added `app/modules/billing/domain/billing/entitlement_policy.py`.
  - Adopted by:
    - `app/modules/billing/domain/billing/dunning_service.py`
    - `app/modules/billing/domain/billing/paystack_webhook_impl.py`
  - Added strict normalization + rowcount guardrails for deterministic plan-sync behavior.

### Validation evidence (this batch)

- `uv run ruff check app/modules/governance/api/v1/jobs.py app/modules/governance/api/v1/settings/llm.py scripts/verify_api_auth_coverage.py app/shared/adapters/aws_pagination.py app/shared/adapters/aws_resource_explorer.py app/shared/adapters/aws_cur.py scripts/run_enterprise_tdd_gate.py tests/unit/ops/test_verify_api_auth_coverage.py tests/unit/shared/adapters/test_aws_pagination.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py app/modules/billing/domain/billing/entitlement_policy.py app/modules/billing/domain/billing/dunning_service.py app/modules/billing/domain/billing/paystack_webhook_impl.py tests/unit/services/billing/test_entitlement_policy.py tests/unit/services/billing/test_dunning_service.py tests/unit/services/billing/test_paystack_billing_branches.py tests/unit/governance/settings/test_llm_settings.py`
- `uv run mypy app/modules/governance/api/v1/jobs.py app/modules/governance/api/v1/settings/llm.py app/shared/adapters/aws_pagination.py app/shared/adapters/aws_resource_explorer.py app/shared/adapters/aws_cur.py scripts/verify_api_auth_coverage.py scripts/run_enterprise_tdd_gate.py app/modules/billing/domain/billing/entitlement_policy.py app/modules/billing/domain/billing/dunning_service.py app/modules/billing/domain/billing/paystack_webhook_impl.py --hide-error-context --no-error-summary`
- `TESTING=true DEBUG=false uv run python3 scripts/verify_api_auth_coverage.py` -> `Auth coverage check passed.`
- `DEBUG=false uv run pytest -q --no-cov tests/unit/services/billing/test_entitlement_policy.py tests/unit/services/billing/test_dunning_service.py tests/unit/services/billing/test_paystack_billing_branches.py tests/unit/ops/test_verify_api_auth_coverage.py tests/unit/shared/adapters/test_aws_pagination.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py tests/unit/governance/test_jobs_api.py tests/unit/governance/settings/test_llm_settings.py` -> `98 passed`.

## Additional remediation batch (Valdrics continuation, 2026-02-28O)

- `VAL-ADAPT-002+` decomposition advanced further in `app/shared/adapters/license.py`:
  - moved manual-feed transformation/validation/activity logic to `app/shared/adapters/license_feed_ops.py`,
  - moved vendor alias resolution to `app/shared/adapters/license_vendor_registry.py`,
  - replaced conditional-heavy vendor dispatch with table-driven maps for verify/revoke/activity/native-stream paths while preserving existing wrapper seams.
- Added dedicated helper coverage:
  - `tests/unit/shared/adapters/test_license_feed_ops.py`
  - `tests/unit/shared/adapters/test_license_vendor_registry.py`

### Validation evidence (this batch)

- `uv run ruff check app/shared/adapters/license.py app/shared/adapters/license_feed_ops.py app/shared/adapters/license_vendor_registry.py tests/unit/shared/adapters/test_license_feed_ops.py tests/unit/shared/adapters/test_license_vendor_registry.py tests/unit/services/adapters/test_license_verification_stream_branches.py tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/services/adapters/test_adapter_helper_branches.py tests/unit/services/adapters/test_cloud_plus_adapters.py tests/unit/shared/adapters/test_google_workspace.py` -> passed.
- `uv run mypy app/shared/adapters/license.py app/shared/adapters/license_feed_ops.py app/shared/adapters/license_vendor_registry.py --hide-error-context --no-error-summary` -> passed.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/shared/adapters/test_license_feed_ops.py tests/unit/shared/adapters/test_license_vendor_registry.py tests/unit/services/adapters/test_adapter_helper_branches.py tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/services/adapters/test_license_verification_stream_branches.py tests/unit/services/adapters/test_cloud_plus_adapters.py tests/unit/shared/adapters/test_google_workspace.py` -> `123 passed`.

## Additional remediation batch (Valdrics continuation, 2026-02-28P)

- `VAL-ADAPT-002+` decomposition advanced from helper extraction to vendor-module split:
  - `app/shared/adapters/license_vendor_verify.py`
  - `app/shared/adapters/license_vendor_google.py`
  - `app/shared/adapters/license_vendor_microsoft.py`
  - `app/shared/adapters/license_vendor_github.py`
  - `app/shared/adapters/license_vendor_zoom.py`
  - `app/shared/adapters/license_vendor_slack.py`
  - `app/shared/adapters/license_vendor_salesforce.py`
  - shared typing/runtime contract in `app/shared/adapters/license_vendor_types.py`
  - compatibility facade retained in `app/shared/adapters/license_vendor_ops.py` to keep call sites and tests stable while reducing module complexity.
- Export surface tightened with explicit `__all__` in `license_vendor_ops.py` so static typing enforces the public adapter contract.

### Validation evidence (this batch)

- `uv run ruff check app/shared/adapters/license.py app/shared/adapters/license_feed_ops.py app/shared/adapters/license_vendor_registry.py app/shared/adapters/license_vendor_ops.py app/shared/adapters/license_vendor_types.py app/shared/adapters/license_vendor_verify.py app/shared/adapters/license_vendor_google.py app/shared/adapters/license_vendor_microsoft.py app/shared/adapters/license_vendor_github.py app/shared/adapters/license_vendor_zoom.py app/shared/adapters/license_vendor_slack.py app/shared/adapters/license_vendor_salesforce.py tests/unit/shared/adapters/test_license_feed_ops.py tests/unit/shared/adapters/test_license_vendor_registry.py` -> passed.
- `uv run mypy app/shared/adapters/license.py app/shared/adapters/license_feed_ops.py app/shared/adapters/license_vendor_registry.py app/shared/adapters/license_vendor_ops.py app/shared/adapters/license_vendor_types.py app/shared/adapters/license_vendor_verify.py app/shared/adapters/license_vendor_google.py app/shared/adapters/license_vendor_microsoft.py app/shared/adapters/license_vendor_github.py app/shared/adapters/license_vendor_zoom.py app/shared/adapters/license_vendor_slack.py app/shared/adapters/license_vendor_salesforce.py --hide-error-context --no-error-summary` -> passed.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/shared/adapters/test_license_feed_ops.py tests/unit/shared/adapters/test_license_vendor_registry.py tests/unit/services/adapters/test_adapter_helper_branches.py tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/services/adapters/test_license_verification_stream_branches.py tests/unit/services/adapters/test_cloud_plus_adapters.py tests/unit/shared/adapters/test_google_workspace.py` -> `123 passed in 8.03s`.
- `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py` -> passed with full gate execution (`876 passed`, coverage gates green, warning-free after test fixture hardening in `tests/unit/llm/test_zombie_analyzer.py`).

### Post-closure sanity check (release-critical)

- Concurrency: vendor dispatch tables are immutable module-level mappings; no shared mutable state added in the split.
- Observability: exception/error propagation remains through existing `ExternalAPIError` pathways in adapter call chains.
- Deterministic replay: vendor resolution and feed normalization stay deterministic and are covered by focused unit tests.
- Snapshot/export stability: stream/revoke/activity wrapper signatures and returned record shapes are unchanged at call sites.
- Failure modes and misconfiguration: unsupported vendor paths remain fail-closed with explicit error messages.

## Additional remediation batch (Valdrics continuation, 2026-02-28Q)

- `VAL-ADAPT-002+` advanced by removing stub-grade behavior from the license adapter resource surfaces:
  - added `app/shared/adapters/license_resource_ops.py` for deterministic, typed resource/usage shaping from license activity rows,
  - implemented `LicenseAdapter.discover_resources()` as activity-backed discovery for license-seat aliases,
  - implemented `LicenseAdapter.get_resource_usage()` as activity-backed seat usage rows with safe defaults (`default_seat_price_usd`, `currency`) and explicit unsupported-service fail-closed behavior.
- Added explicit coverage for resource/usage hardening and failure paths:
  - `tests/unit/shared/adapters/test_license_resource_ops.py`
  - expanded `tests/unit/services/adapters/test_license_activity_and_revoke.py` with discovery/usage and fail-closed assertions.

### Validation evidence (this batch)

- `uv run ruff check app/shared/adapters/license.py app/shared/adapters/license_resource_ops.py tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/shared/adapters/test_license_resource_ops.py` -> passed.
- `uv run mypy app/shared/adapters/license.py app/shared/adapters/license_resource_ops.py --hide-error-context --no-error-summary` -> passed.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/shared/adapters/test_license_resource_ops.py tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/services/adapters/test_cloud_plus_adapters.py tests/unit/shared/adapters/test_license_feed_ops.py tests/unit/shared/adapters/test_license_vendor_registry.py` -> `69 passed`.
- `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py` -> passed (`876 passed`, coverage gates green).

### Post-closure sanity check (release-critical)

- Concurrency: discovery/usage shaping is pure and stateless; no new shared mutable runtime state added.
- Observability: adapter now records `last_error` and logs fail-closed resource/usage fetch failures with vendor/service context.
- Deterministic replay: resource identity normalization and result ordering are deterministic (sorted by resource identifier).
- Snapshot stability/export integrity: usage row schema is explicit and stable (`provider/service/usage_type/resource_id/usage_amount/cost/currency/timestamp/tags`).
- Failure modes/misconfiguration: unsupported resource/service requests return empty results; negative default seat prices are clamped to `0.0`; malformed timestamps fall back safely.

## Additional remediation batch (Valdrics continuation, 2026-02-28R)

- `VAL-CORE-002` remediated in `app/shared/core/pricing.py`:
  - removed legacy hardcoded `paystack_amount_kobo` tier constants from runtime pricing config,
  - checkout/renewal pricing remains derived from canonical USD plan prices + runtime FX conversion in billing service.
- `VAL-BILL-002` remediated in `app/modules/billing/domain/billing/paystack_service_impl.py`:
  - checkout initialization now resolves and passes `plan_code` when available for NGN flows,
  - metadata now records `plan_code` + `pricing_mode` (`fixed_plan_code` vs `dynamic_amount`) for deterministic billing evidence.
- `VAL-BILL-003` remediated in `app/modules/billing/domain/billing/paystack_service_impl.py`:
  - added `exchange_rate_service_factory` injection seam and `_build_exchange_rate_service()` runtime factory,
  - removed direct constructor coupling to `ExchangeRateService` in checkout and renewal paths.
- `VAL-BILL-004` remediated in `app/modules/billing/domain/billing/dunning_service.py`:
  - added `email_service_factory` and `billing_service_factory` DI seams,
  - `retry_payment()` now consumes injected billing factory instead of manual service construction.
- `VAL-API-003` remediated in `app/shared/core/app_routes.py`:
  - added strict router registry validation (`_validate_router_registry`) with fail-closed checks for:
    - empty router definitions,
    - malformed prefixes,
    - duplicate prefixes,
    - missing required prefixes,
    - unexpected prefixes.

### Validation evidence (this batch)

- `DEBUG=false uv run pytest -q --no-cov tests/unit/core/test_app_routes_registry.py tests/unit/services/billing/test_dunning_service.py tests/unit/services/billing/test_paystack_billing_branches.py` -> `54 passed`.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/core/test_pricing_packaging_contract.py tests/unit/core/test_pricing_deep.py tests/unit/services/billing/test_paystack_billing_branches.py` -> `53 passed`.
- `uv run ruff check app/modules/billing/domain/billing/paystack_service_impl.py tests/unit/services/billing/test_paystack_billing_branches.py tests/unit/services/billing/test_dunning_service.py tests/unit/core/test_app_routes_registry.py` -> passed.
- `uv run ruff check app/shared/core/pricing.py app/modules/billing/domain/billing/paystack_service_impl.py tests/unit/services/billing/test_paystack_billing_branches.py` -> passed.
- `uv run mypy app/shared/core/pricing.py app/modules/billing/domain/billing/paystack_service_impl.py app/modules/billing/domain/billing/dunning_service.py app/shared/core/app_routes.py --hide-error-context --no-error-summary` -> passed.
- `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py` -> passed (`876 passed`, enforcement/analytics/LLM gates green, coverage-enterprise-gate generated).

### Post-closure sanity check (release-critical)

- Concurrency: injected factory seams are stateless callables; no shared mutable runtime state added.
- Observability: checkout audit metadata now captures pricing mode deterministically for forensic replay.
- Deterministic replay: `plan_code` resolution is explicit and stable (`monthly`/`annual` normalization + blank normalization to `None`).
- Snapshot stability/export integrity: billing metadata keys (`plan_code`, `pricing_mode`) are additive and backward-safe.
- Failure modes/misconfiguration: router registry now fails closed at startup on missing/duplicate/unexpected prefixes.

## Valdrics remaining finding dispositions (post-remediation review)

- Disposition evidence is now machine-checkable and release-gated via:
  - register artifact: `docs/ops/evidence/valdrix_disposition_register_2026-02-28.json`
  - verifier: `scripts/verify_valdrix_disposition_freshness.py`
  - enterprise gate wiring: `scripts/run_enterprise_tdd_gate.py`
- `VAL-ADAPT-001`: reduced in practice by standardized adapter retry/error pathways and explicit `last_error` handling in Cloud+ adapters; further normalization is tracked with `VAL-ADAPT-002+` decomposition work.
- `VAL-DB-002`: backend resolution complexity retained intentionally with fail-closed semantics and exhaustive session-path tests; no release-critical fail-open path confirmed.
- `VAL-DB-003`: explicit session cleanup kept for deterministic rollback/close behavior across Postgres/SQLite test surfaces; treated as defensive redundancy, not correctness debt.
- `VAL-DB-004`: explicit `import app.models` mapping bootstrap retained as deliberate ORM-registration pattern; no circular import regression observed in current gate.
- `VAL-API-001`: middleware order remains intentional (FastAPI reverse wrapping); operational behavior is correct and currently documented/tested.
- `VAL-API-002`: bearer-token CSRF bypass remains an explicit API contract; machine-checkable auth coverage gate is in CI to prevent unprotected private routes.
- `VAL-API-004`: static Swagger asset serving remains read-only from packaged static directory; no runtime write path is exposed by app routes.
- `VAL-ADAPT-002+`: still open as class-size/vendor-strategy maintainability decomposition backlog, not a correctness/security release blocker after current remediation packs.

## Additional remediation batch (Valdrics continuation, 2026-02-28S)

- `VAL-ADAPT-002+` decomposition advanced by extracting native vendor dispatch orchestration out of `LicenseAdapter`:
  - added `app/shared/adapters/license_native_dispatch.py` with typed, table-driven dispatch for verify, stream, revoke, and activity paths,
  - moved vendor-dispatch map ownership from `app/shared/adapters/license.py` into the new module,
  - kept existing adapter wrapper methods intact to preserve backward-compatible test seams and runtime behavior.
- Added focused dispatch coverage:
  - `tests/unit/shared/adapters/test_license_native_dispatch.py`
  - covers verify dispatch, stream-method resolution, revoke dispatch (SKU/non-SKU), unknown-vendor fail-closed, and stable supported-vendor contract.

### Validation evidence (this batch)

- `uv run ruff check app/shared/adapters/license.py app/shared/adapters/license_native_dispatch.py tests/unit/shared/adapters/test_license_native_dispatch.py` -> passed.
- `uv run mypy app/shared/adapters/license.py app/shared/adapters/license_native_dispatch.py --hide-error-context --no-error-summary` -> passed.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/shared/adapters/test_license_native_dispatch.py tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/services/adapters/test_license_verification_stream_branches.py tests/unit/services/adapters/test_cloud_plus_adapters.py` -> `93 passed`.

### Post-closure sanity check (release-critical)

- Concurrency: dispatch helpers are immutable module-level maps with no mutable shared runtime state.
- Observability: existing adapter warning/error logging paths and `last_error` semantics are unchanged.
- Deterministic replay: vendor operation selection is table-driven and deterministic for a given normalized vendor.
- Snapshot stability/export integrity: public adapter method signatures and emitted row shapes are unchanged.
- Failure modes/misconfiguration: unknown native vendors stay fail-closed (`ExternalAPIError`/`UnsupportedVendorError`) with explicit operator-facing messages.

## Additional remediation batch (Valdrics continuation, 2026-02-28T)

- `VAL-ADAPT-001` hardening pass implemented for cloud-core adapters (AWS/Azure/GCP/CUR):
  - added sanitized adapter error helpers to `app/shared/adapters/base.py`:
    - `_clear_last_error()`
    - `_set_last_error()`
    - `_set_last_error_from_exception()`
  - updated verify flows to clear stale state and set sanitized failure context:
    - `app/shared/adapters/azure.py`
    - `app/shared/adapters/gcp.py`
    - `app/shared/adapters/aws_cur.py`
    - `app/shared/adapters/aws_multitenant.py`
  - adapters now expose deterministic fail-closed operator messages through `last_error` on verification failure.
- Connection services now consume adapter-provided failure context with safe fallback defaults:
  - `app/shared/connections/aws.py`
  - `app/shared/connections/azure.py`
  - `app/shared/connections/gcp.py`

### Validation evidence (this batch)

- `uv run ruff check app/shared/adapters/base.py app/shared/adapters/azure.py app/shared/adapters/gcp.py app/shared/adapters/aws_cur.py app/shared/adapters/aws_multitenant.py app/shared/connections/aws.py app/shared/connections/azure.py app/shared/connections/gcp.py tests/unit/shared/adapters/test_azure_adapter.py tests/unit/shared/adapters/test_gcp_adapter.py tests/unit/shared/adapters/test_aws_cur.py tests/unit/shared/adapters/test_aws_multitenant_branch_paths.py tests/unit/connections/test_cloud_connections_deep.py` -> passed.
- `uv run mypy app/shared/adapters/base.py app/shared/adapters/azure.py app/shared/adapters/gcp.py app/shared/adapters/aws_cur.py app/shared/adapters/aws_multitenant.py app/shared/connections/aws.py app/shared/connections/azure.py app/shared/connections/gcp.py --hide-error-context --no-error-summary` -> passed.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/shared/adapters/test_azure_adapter.py tests/unit/shared/adapters/test_gcp_adapter.py tests/unit/shared/adapters/test_aws_cur.py tests/unit/shared/adapters/test_aws_multitenant_branch_paths.py tests/unit/connections/test_cloud_connections_deep.py` -> `71 passed`.

### Post-closure sanity check (release-critical)

- Concurrency: no shared mutable singleton state introduced; `last_error` remains instance-local and is reset per verification run.
- Observability: failure context remains structured in logs while adapter-facing messages are sanitized via `AdapterError`.
- Deterministic replay: verification outcomes now deterministically include/reset `last_error` for each run, removing stale-message ambiguity.
- Snapshot stability/export integrity: no request/response schema changes; only failure-message selection semantics improved.
- Failure modes/misconfiguration: unsupported-region and credential failures remain fail-closed with explicit operator-facing diagnostics.

## Additional remediation batch (Valdrics continuation, 2026-02-28U)

- Remediated all five explicit `get_resource_usage()` stubs that previously returned unconditional empty lists:
  - `app/shared/adapters/azure.py`
  - `app/shared/adapters/gcp.py`
  - `app/shared/adapters/saas.py`
  - `app/shared/adapters/hybrid.py`
  - `app/shared/adapters/platform.py`
- Added reusable projection module for deterministic resource-usage shaping:
  - `app/shared/adapters/resource_usage_projection.py`
  - bounded lookback window (`30d`, capped), normalized service/resource filtering, stable ordering, and normalized output schema.
- Enhanced manual-feed streaming for Cloud+ adapters to preserve resource usage metadata end-to-end:
  - `app/shared/adapters/hybrid.py`
  - `app/shared/adapters/platform.py`
  - both now propagate `resource_id`, `usage_amount`, and `usage_unit` when present.
- Expanded test coverage to validate projection/filtering/error paths and lookback-safe behavior:
  - `tests/unit/shared/adapters/test_azure_adapter_branch_paths.py`
  - `tests/unit/shared/adapters/test_gcp_adapter.py`
  - `tests/unit/shared/adapters/test_saas_adapter_branch_paths.py`
  - `tests/unit/services/adapters/test_hybrid_additional_branches.py`
  - `tests/unit/services/adapters/test_platform_additional_branches.py`

### Validation evidence (this batch)

- `uv run ruff check app/shared/adapters/resource_usage_projection.py app/shared/adapters/azure.py app/shared/adapters/gcp.py app/shared/adapters/saas.py app/shared/adapters/hybrid.py app/shared/adapters/platform.py tests/unit/shared/adapters/test_azure_adapter_branch_paths.py tests/unit/shared/adapters/test_gcp_adapter.py tests/unit/shared/adapters/test_saas_adapter_branch_paths.py tests/unit/services/adapters/test_hybrid_additional_branches.py tests/unit/services/adapters/test_platform_additional_branches.py` -> passed.
- `uv run mypy app/shared/adapters/resource_usage_projection.py app/shared/adapters/azure.py app/shared/adapters/gcp.py app/shared/adapters/saas.py app/shared/adapters/hybrid.py app/shared/adapters/platform.py --hide-error-context --no-error-summary` -> passed.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/shared/adapters/test_azure_adapter_branch_paths.py tests/unit/shared/adapters/test_gcp_adapter.py tests/unit/shared/adapters/test_saas_adapter_branch_paths.py tests/unit/services/adapters/test_hybrid_additional_branches.py tests/unit/services/adapters/test_platform_additional_branches.py` -> `88 passed`.
- `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py` -> passed (`883 passed`, enforcement/analytics/LLM coverage gates green; `coverage-enterprise-gate.xml` generated).

### Post-closure sanity check (release-critical)

- Concurrency: projection utilities are stateless pure functions; adapter implementations remain instance-local with no shared mutable runtime state.
- Observability: resource-usage lookup failures now emit explicit warning events and set adapter error context (`last_error`/sanitized error paths).
- Deterministic replay: row projection enforces deterministic sorting (`timestamp`, `resource_id`, `service`) and stable field normalization.
- Snapshot stability/export integrity: usage payloads are now consistently shaped with explicit defaults (`currency`, `region`, `source_adapter`) and no placeholder TODO paths.
- Failure modes/misconfiguration: lookups fail closed (`[]`) on upstream errors; bounded lookback prevents unbounded scans; resource/service filters are explicit and case-normalized.

## Additional remediation batch (Valdrics continuation, 2026-02-28V)

- Remediated remaining AWS adapter `get_resource_usage()` placeholders:
  - `app/shared/adapters/aws_cur.py`
  - `app/shared/adapters/aws_multitenant.py`
- `AWSCURAdapter.get_resource_usage` now:
  - runs bounded lookback retrieval via existing CUR ingestion path,
  - normalizes CUR-native fields (`date/amount/line_item_*`) into resource-usage projection inputs,
  - returns deterministic, filtered usage rows for requested service/resource,
  - fail-closes with explicit operator-facing error context (`last_error`) on upstream failures.
- `MultiTenantAWSAdapter.get_resource_usage` now:
  - maps common AWS service aliases (`ec2`, `ebs`, `eip`, `nat`, `rds`, etc.) to discovery resource types,
  - derives inventory-backed usage rows from discovered resources (`usage_amount=1`, `usage_unit=resource`, `cost_usd=0`),
  - supports deterministic service/resource filtering through shared projection utility.
- Expanded AWS tests to codify new contract behavior:
  - `tests/unit/shared/adapters/test_aws_cur.py`
  - `tests/unit/shared/adapters/test_aws_multitenant_branch_paths.py`
  - `tests/unit/adapters/test_aws_adapter.py`

### Validation evidence (this batch)

- `uv run ruff check app/shared/adapters/aws_cur.py app/shared/adapters/aws_multitenant.py tests/unit/shared/adapters/test_aws_cur.py tests/unit/shared/adapters/test_aws_multitenant_branch_paths.py tests/unit/adapters/test_aws_adapter.py` -> passed.
- `uv run mypy app/shared/adapters/aws_cur.py app/shared/adapters/aws_multitenant.py --hide-error-context --no-error-summary` -> passed.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/shared/adapters/test_aws_cur.py tests/unit/shared/adapters/test_aws_multitenant_branch_paths.py tests/unit/adapters/test_aws_adapter.py` -> `48 passed`.
- `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py` -> passed (`883 passed`, enforcement/analytics/LLM coverage gates green; `coverage-enterprise-gate.xml` generated).

### Post-closure sanity check (release-critical)

- Concurrency: AWS usage shaping remains stateless per request; no global mutable runtime caches added.
- Observability: CUR lookup failures now emit explicit warning logs and set deterministic `last_error` context.
- Deterministic replay: service alias mapping and projected output ordering are stable and deterministic for identical inputs.
- Snapshot stability/export integrity: emitted usage schema remains consistent with all other adapter resource-usage surfaces.
- Failure modes/misconfiguration: blank service requests and empty discovery/ingestion paths fail closed (`[]`) without raising unstable runtime errors.

## Additional remediation batch (Valdrics continuation, 2026-02-28W)

- `VAL-DB-001` hardening finalized for explicit tenant-context teardown:
  - added `clear_session_tenant_context()` in `app/shared/db/session.py` to enforce fail-closed state (`tenant_id=None`, `rls_context_set=False`, `rls_system_context=False`) on both session and connection.
  - PostgreSQL sessions now explicitly clear `app.current_tenant_id` with `set_config(..., '', true)` during teardown.
  - `set_session_tenant_id(..., None)` now routes to explicit clear semantics instead of ambiguous "set context" behavior.
  - backend-unknown and set-config failure branches now also force `rls_system_context=False` to avoid stale system-context leakage.
- Scheduler isolation hardening in `app/modules/governance/domain/jobs/processor.py`:
  - tenant context clear moved to `finally` scope inside the per-job savepoint so cleanup executes on success, timeout, cancellation, and handler exceptions.
- Regression coverage added:
  - `tests/unit/db/test_session_branch_paths_2.py`:
    - `set_session_tenant_id(None)` delegation to clear helper,
    - explicit clear-context fail-closed behavior and PostgreSQL clear query assertion,
    - clear-query failure logging path.
  - `tests/unit/governance/jobs/test_job_processor.py`:
    - tenant-context cleanup on success path,
    - tenant-context cleanup on handler-failure path.

### Validation evidence (this batch)

- `uv run ruff check app/shared/db/session.py app/modules/governance/domain/jobs/processor.py tests/unit/db/test_session_branch_paths_2.py tests/unit/governance/jobs/test_job_processor.py` -> passed.
- `uv run mypy app/shared/db/session.py app/modules/governance/domain/jobs/processor.py --hide-error-context --no-error-summary` -> passed.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/db/test_session_branch_paths_2.py` -> `22 passed`.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/governance/jobs/test_job_processor.py` -> `12 passed`.
- `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py` -> passed (`883 passed`; post-closure sanity dimensions all OK; `coverage-enterprise-gate.xml` regenerated).

### Post-closure sanity check (release-critical)

- Concurrency: job processor now enforces deterministic tenant-context teardown in `finally`, eliminating cross-job context retention risk on exception paths.
- Observability: explicit clear/set failure logs (`failed_to_clear_rls_config_in_session`, `failed_to_set_rls_config_in_session`) provide direct operator signals for DB-context anomalies.
- Deterministic replay: context transitions are now explicit and state-machine-like (`set -> execute -> clear`) across all outcomes.
- Snapshot stability/export integrity: no API payload schema changes; remediation is internal session-control behavior only.
- Failure modes/misconfiguration: unresolved backend detection remains fail-closed and now applies symmetric system-context resets during both set and clear flows.

## Additional remediation batch (Valdrics continuation, 2026-02-28X)

- `VAL-ADAPT-002+` decomposition advanced by extracting native-vendor compatibility wrappers out of `LicenseAdapter`:
  - added `app/shared/adapters/license_native_compat.py` with a dedicated `LicenseNativeCompatMixin`.
  - moved native wrapper surfaces into the mixin while preserving existing private method seams:
    - verify wrappers (`_verify_*`, `_verify_native_vendor`)
    - stream wrappers (`_stream_google_workspace_license_costs`, `_stream_microsoft_365_license_costs`)
    - revoke wrappers (`_revoke_*`)
    - activity wrappers (`_list_*_activity`)
  - `app/shared/adapters/license.py` now focuses on orchestration/runtime responsibilities and composes native wrappers via inheritance (`LicenseNativeCompatMixin`), reducing core adapter class size/branch density without breaking existing call sites/tests.
- Type safety hardening:
  - `license_native_compat.py` uses explicit protocol casts (`LicenseVendorRuntime` / `LicenseNativeDispatchRuntime`) so mypy enforces native runtime contract compatibility.

### Validation evidence (this batch)

- `uv run ruff check app/shared/adapters/license.py app/shared/adapters/license_native_compat.py` -> passed.
- `uv run mypy app/shared/adapters/license.py app/shared/adapters/license_native_compat.py --hide-error-context --no-error-summary` -> passed.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/shared/adapters/test_license_native_dispatch.py` -> `6 passed`.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/services/adapters/test_license_verification_stream_branches.py` -> `28 passed`.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/services/adapters/test_license_activity_and_revoke.py` -> `19 passed`.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/shared/adapters/test_google_workspace.py` -> `6 passed`.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/services/adapters/test_cloud_plus_adapters.py` -> `40 passed`.
- `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py` -> passed (`883 passed`; post-closure sanity dimensions all OK; `coverage-enterprise-gate.xml` regenerated).

### Post-closure sanity check (release-critical)

- Concurrency: decomposition introduced no shared mutable global runtime state; native dispatch remains per-instance and request-local.
- Observability: existing native vendor warning/error logs and `last_error` propagation paths are preserved.
- Deterministic replay: wrapper extraction is behavior-preserving; native vendor flow selection and output ordering are unchanged for identical inputs.
- Snapshot stability/export integrity: adapter public/native private seams remain stable, protecting existing regression snapshots and downstream exports.
- Failure modes/misconfiguration: unsupported vendor handling remains fail-closed through dispatch/runtime contracts; native auth guardrails are unchanged.

## Additional remediation batch (Valdrics continuation, 2026-03-01A)

- `VAL-ADAPT-002+` breaking cleanup completed (legacy private wrapper seam removed):
  - removed `app/shared/adapters/license_native_compat.py` and dropped `LicenseNativeCompatMixin` inheritance from `LicenseAdapter`.
  - removed all legacy private native wrapper seams from `LicenseAdapter`:
    - `_verify_*`, `_verify_native_vendor`
    - `_stream_google_workspace_license_costs`, `_stream_microsoft_365_license_costs`
    - `_revoke_*`
    - `_list_*_activity`
  - migrated `app/shared/adapters/license_native_dispatch.py` from method-name string dispatch to direct function dispatch maps over vendor ops, eliminating indirection through adapter-private wrapper methods.
  - `LicenseAdapter` now uses dispatch/runtime interfaces directly (`verify_native_vendor`, `resolve_native_stream_method`, `revoke_native_license`, `list_native_activity`).
- Full test-callsite cleanup completed:
  - updated license adapter test suites to patch/assert dispatch maps and vendor-operation functions directly instead of patching adapter private wrapper methods.
  - no remaining runtime references to removed `LicenseAdapter` native wrapper seams in `app/` or `tests/unit/`.

### Validation evidence (this batch)

- `uv run ruff check app/shared/adapters/license.py app/shared/adapters/license_native_dispatch.py tests/unit/shared/adapters/test_license_native_dispatch.py tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/services/adapters/test_license_verification_stream_branches.py tests/unit/services/adapters/test_cloud_plus_adapters.py` -> passed.
- `uv run mypy app/shared/adapters/license.py app/shared/adapters/license_native_dispatch.py --hide-error-context --no-error-summary` -> passed.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/shared/adapters/test_license_native_dispatch.py` -> `7 passed`.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/services/adapters/test_license_activity_and_revoke.py` -> `19 passed`.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/services/adapters/test_license_verification_stream_branches.py` -> `28 passed`.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/services/adapters/test_cloud_plus_adapters.py` -> `40 passed`.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/shared/adapters/test_google_workspace.py` -> `6 passed`.
- `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py` -> `883 passed` with all gate checks and coverage thresholds satisfied.

### Post-closure sanity check (release-critical)

- Concurrency: dispatch maps are immutable module-level registries of pure function references; no mutable shared adapter wrapper state remains.
- Observability: warning/error events and `last_error` semantics are preserved on the public adapter execution paths.
- Deterministic replay: native dispatch is now strictly table-driven by normalized vendor key and function-map lookup.
- Snapshot stability/export integrity: public adapter outputs and exported usage/cost row schemas are unchanged; only internal invocation topology changed.
- Failure modes/misconfiguration: unsupported vendor and unsupported revoke paths remain fail-closed with explicit `ExternalAPIError` / `UnsupportedVendorError` semantics.

## Additional remediation batch (Valdrics continuation, 2026-03-01B)

- Cloud+ adapter architecture hardening completed for remaining native-vendor branch chains:
  - `app/shared/adapters/saas.py`
  - `app/shared/adapters/platform.py`
  - `app/shared/adapters/hybrid.py`
- Removed stub-grade discovery behavior on Cloud+ adapters by adding deterministic resource projection from recent cost rows:
  - `app/shared/adapters/resource_usage_projection.py` (`discover_resources_from_cost_rows`)
  - `app/shared/adapters/saas.py::discover_resources`
  - `app/shared/adapters/platform.py::discover_resources`
  - `app/shared/adapters/hybrid.py::discover_resources`
- Replaced repetitive vendor `if/elif` chains in both verify and stream flows with table-driven handler resolution:
  - added explicit native verify-handler resolvers per adapter,
  - added explicit native stream-handler resolvers per adapter,
  - centralized native failure handling/logging path in each adapter verify/stream orchestration.
- Added branch tests to lock handler resolution contracts:
  - `tests/unit/shared/adapters/test_saas_adapter_branch_paths.py`
  - `tests/unit/services/adapters/test_adapter_helper_branches.py`
- Added discovery projection coverage:
  - `tests/unit/shared/adapters/test_resource_usage_projection.py`
  - expanded `tests/unit/services/adapters/test_cloud_plus_adapters.py`

### Validation evidence (this batch)

- `uv run ruff check app/shared/adapters/saas.py app/shared/adapters/platform.py app/shared/adapters/hybrid.py app/shared/adapters/resource_usage_projection.py tests/unit/shared/adapters/test_saas_adapter_branch_paths.py tests/unit/services/adapters/test_adapter_helper_branches.py tests/unit/services/adapters/test_cloud_plus_adapters.py tests/unit/shared/adapters/test_resource_usage_projection.py` -> passed.
- `uv run mypy app/shared/adapters/saas.py app/shared/adapters/platform.py app/shared/adapters/hybrid.py app/shared/adapters/resource_usage_projection.py --hide-error-context --no-error-summary` -> passed.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/shared/adapters/test_resource_usage_projection.py tests/unit/shared/adapters/test_saas_adapter_branch_paths.py tests/unit/services/adapters/test_adapter_helper_branches.py tests/unit/services/adapters/test_cloud_plus_adapters.py` -> `88 passed`.
- `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py` -> `883 passed` with all gate checks and coverage thresholds satisfied.

### Post-closure sanity check (release-critical)

- Concurrency: handler maps are method-local immutable dictionaries; no shared mutable global state introduced.
- Observability: native verify/stream failures still emit existing structured warning events with vendor and error context.
- Deterministic replay: native-path selection is now table-driven by normalized vendor key, reducing branch drift risk.
- Snapshot stability/export integrity: discovery payload shape is deterministic and sorted by resource identity/region; no existing cost row schema contracts changed.
- Failure modes/misconfiguration: unsupported vendor and invalid auth mode checks remain explicit fail-closed guards.

## Additional remediation batch (Valdrics continuation, 2026-03-01C)

- Completed no-compat cleanup for `VAL-ADAPT-002+` runtime dispatch:
  - removed `app/shared/adapters/license_vendor_ops.py` compatibility facade from production code,
  - rewired `app/shared/adapters/license_native_dispatch.py` to vendor modules directly (`license_vendor_*` + `license_vendor_verify`) with typed dispatch maps,
  - kept deterministic normalization contracts in dispatch wrappers by binding `feed_utils.parse_timestamp` / `feed_utils.as_float` explicitly.
- Completed callsite cleanup from compatibility facade usage in tests:
  - `tests/unit/services/adapters/test_cloud_plus_adapters.py`
  - `tests/unit/services/adapters/test_license_activity_and_revoke.py`
  - `tests/unit/services/adapters/test_license_verification_stream_branches.py`
- Confirmed Cloud+ CUR discovery hardening remains green in same pass:
  - `app/shared/adapters/aws_cur.py::discover_resources` deterministic projection path,
  - `tests/unit/shared/adapters/test_aws_cur.py` coverage for projection + fail-closed error branch.

### Validation evidence (this batch)

- `uv run ruff check app/shared/adapters/license_native_dispatch.py tests/unit/services/adapters/test_cloud_plus_adapters.py tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/services/adapters/test_license_verification_stream_branches.py tests/unit/shared/adapters/test_license_native_dispatch.py` -> passed.
- `uv run mypy app/shared/adapters/license_native_dispatch.py --hide-error-context --no-error-summary` -> passed.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/shared/adapters/test_license_native_dispatch.py tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/services/adapters/test_license_verification_stream_branches.py tests/unit/services/adapters/test_cloud_plus_adapters.py` -> `97 passed`.
- `uv run ruff check app/shared/adapters/aws_cur.py tests/unit/shared/adapters/test_aws_cur.py` -> passed.
- `uv run mypy app/shared/adapters/aws_cur.py --hide-error-context --no-error-summary` -> passed.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/shared/adapters/test_aws_cur.py` -> `28 passed`.
- `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py` -> `883 passed` with all release-evidence checks and post-closure sanity dimensions satisfied.

### Post-closure sanity check (release-critical)

- Concurrency: dispatch maps are immutable module-level registries; no mutable compatibility seam state remains.
- Observability: native verify/stream/revoke/activity failure logs and `last_error` propagation remain intact.
- Deterministic replay: vendor routing is now strictly table-driven from normalized vendor keys to concrete vendor functions.
- Snapshot stability: no API response schema changes; behavior change is internal invocation topology only.
- Export integrity: cost/resource usage row shapes remain unchanged for downstream report/export consumers.
- Failure modes: unsupported vendors still fail closed (`ExternalAPIError` / `UnsupportedVendorError`) and discovery errors return empty lists with explicit warning logs.
- Operational misconfiguration risk: auth-mode/vendor guards and connector-config validation branches remain enforced with explicit error strings.

## Additional remediation batch (Valdrics continuation, 2026-03-01D)

- Adapter consistency hardening completed across cloud and Cloud+ discovery/usage surfaces:
  - `app/shared/adapters/aws_multitenant.py`
  - `app/shared/adapters/aws_cur.py`
  - `app/shared/adapters/azure.py`
  - `app/shared/adapters/gcp.py`
  - `app/shared/adapters/saas.py`
  - `app/shared/adapters/platform.py`
  - `app/shared/adapters/hybrid.py`
  - `app/shared/adapters/license.py`
- Standardized operation lifecycle for `discover_resources` and `get_resource_usage`:
  - clear stale adapter error state at operation entry (`_clear_last_error()`),
  - set deterministic adapter error state on failures where the method returns empty data.
- Strengthened AWS multitenant fail-closed behavior details:
  - unsupported-region and unmapped-plugin branches now set explicit operator-facing `last_error` messages before returning `[]`.
- Removed stale architecture trace reference to deleted compatibility module:
  - updated `docs/ops/landing_capability_backend_trace_2026-02-28.md` to reference `license_native_dispatch.py` and `license_vendor_*.py` instead of deleted `license_vendor_ops.py`.

### Validation evidence (this batch)

- `uv run ruff check app/shared/adapters/aws_cur.py app/shared/adapters/aws_multitenant.py app/shared/adapters/azure.py app/shared/adapters/gcp.py app/shared/adapters/saas.py app/shared/adapters/platform.py app/shared/adapters/hybrid.py app/shared/adapters/license.py tests/unit/shared/adapters/test_aws_cur.py tests/unit/shared/adapters/test_aws_multitenant_branch_paths.py tests/unit/shared/adapters/test_azure_adapter.py tests/unit/shared/adapters/test_gcp_adapter.py tests/unit/services/adapters/test_cloud_plus_adapters.py tests/unit/services/adapters/test_license_activity_and_revoke.py` -> passed.
- `uv run mypy app/shared/adapters/aws_cur.py app/shared/adapters/aws_multitenant.py app/shared/adapters/azure.py app/shared/adapters/gcp.py app/shared/adapters/saas.py app/shared/adapters/platform.py app/shared/adapters/hybrid.py app/shared/adapters/license.py --hide-error-context --no-error-summary` -> passed.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/shared/adapters/test_aws_cur.py tests/unit/shared/adapters/test_aws_multitenant_branch_paths.py tests/unit/shared/adapters/test_azure_adapter.py tests/unit/shared/adapters/test_gcp_adapter.py tests/unit/services/adapters/test_cloud_plus_adapters.py tests/unit/services/adapters/test_license_activity_and_revoke.py` -> `128 passed`.
- `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py` -> `883 passed` with all release-evidence checks and post-closure sanity dimensions satisfied.

### Post-closure sanity check (release-critical)

- Concurrency: per-operation error state is now reset deterministically at entry; no stale cross-request error contamination.
- Observability: failure branches now emit both structured logs and sanitized `last_error` messages consistently.
- Deterministic replay: discovery/usage error-state transitions are now explicit (`clear -> run -> set on failure`) across providers.
- Snapshot stability: no response-schema changes; hardening is operational semantics only.
- Export integrity: normalized usage/cost payload contracts remain unchanged.
- Failure modes: fail-closed branches now carry explicit operator context instead of silent empty returns.
- Operational misconfiguration: unsupported-region/plugin-mapping branches in AWS multitenant now surface explicit actionable error messages.

## Additional remediation batch (Valdrics continuation, 2026-03-01E)

- Completed remaining private stream-wrapper seam cleanup on adapters:
  - removed `_stream_cost_and_usage_impl` methods from:
    - `app/shared/adapters/azure.py`
    - `app/shared/adapters/gcp.py`
    - `app/shared/adapters/license.py`
  - standardized streaming through public `stream_cost_and_usage(...)` entry points only.
- Updated tests to use public streaming contract instead of private adapter internals:
  - `tests/unit/services/adapters/test_license_verification_stream_branches.py`
- Hardened sitemap determinism for replay/snapshot stability:
  - `dashboard/src/routes/sitemap.xml/+server.ts` now emits `<lastmod>` only when an explicit valid env value is provided (`PUBLIC_SITEMAP_LASTMOD` or `SITEMAP_LASTMOD`).
  - removed request-time `new Date().toISOString()` generation from sitemap output.
- Added deterministic sitemap tests:
  - `dashboard/src/routes/sitemap.xml/sitemap.server.test.ts` now verifies:
    - no `<lastmod>` when unset,
    - stable configured `<lastmod>` when set,
    - invalid configured values are rejected.

### Validation evidence (this batch)

- `uv run ruff check app/shared/adapters/azure.py app/shared/adapters/gcp.py app/shared/adapters/license.py tests/unit/services/adapters/test_license_verification_stream_branches.py` -> passed.
- `uv run mypy app/shared/adapters/azure.py app/shared/adapters/gcp.py app/shared/adapters/license.py --hide-error-context --no-error-summary` -> passed.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/services/adapters/test_license_verification_stream_branches.py tests/unit/shared/adapters/test_azure_adapter.py tests/unit/shared/adapters/test_gcp_adapter.py tests/unit/shared/adapters/test_aws_multitenant_branch_paths.py tests/unit/shared/adapters/test_aws_cur.py tests/unit/services/adapters/test_cloud_plus_adapters.py tests/unit/services/adapters/test_license_activity_and_revoke.py` -> `156 passed`.
- `cd dashboard && npm run test:unit -- --run` -> includes `src/routes/sitemap.xml/sitemap.server.test.ts` pass.
- `DEBUG=false uv run python scripts/run_enterprise_tdd_gate.py` -> `883 passed`.

### Post-closure sanity check (release-critical)

- Concurrency: stream execution now uses only public adapter entry points, reducing private seam mutation/patch risk.
- Observability: native stream fallback warnings and `last_error` semantics in license adapter are preserved unchanged.
- Deterministic replay: sitemap output no longer uses request-time clock values by default.
- Snapshot stability: sitemap snapshots are now stable unless an explicit `lastmod` override is provided.
- Export integrity: adapter cost/usage row schemas and dashboard sitemap structure remain contract-compatible.
- Failure modes: invalid `lastmod` env values are ignored (fail-safe omission instead of malformed XML).
- Operational misconfiguration: explicit env-driven `lastmod` control makes deployment behavior auditable and intentional.

## Additional remediation batch (Valdrics continuation, 2026-03-01F)

- Closed remaining silent fallback path for unsupported native license auth vendors:
  - `app/shared/adapters/license.py`
  - `list_users_activity()` now fails closed for `auth_method=api_key|oauth` when vendor is not mapped to a supported native connector (sets explicit `last_error`, returns `[]`).
  - `stream_cost_and_usage()` now fails closed in the same unsupported-native-auth condition and does not fall back to manual feed rows.
  - extracted shared message helper: `_unsupported_native_vendor_message()`.
- Hardened dashboard e2e backend startup env contract:
  - `dashboard/playwright.config.ts` now sets `DEBUG=false` in backend `webServer` command to prevent invalid bool parsing from inherited shell env values.

### Validation evidence (this batch)

- `uv run ruff check app/shared/adapters/license.py tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/services/adapters/test_license_verification_stream_branches.py` -> passed.
- `uv run mypy app/shared/adapters/license.py --hide-error-context --no-error-summary` -> passed.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/services/adapters/test_license_verification_stream_branches.py` -> `49 passed`.
- `cd dashboard && npx playwright test --list` -> passed (config parse and discovery).
- `cd dashboard && npm run test:e2e -- e2e/critical-paths.spec.ts --grep "robots.txt references sitemap"` -> `1 passed`.
- `DEBUG=false uv run python scripts/run_enterprise_tdd_gate.py` -> `883 passed`.

### Post-closure sanity check (release-critical)

- Concurrency: unsupported-native-auth branches now terminate deterministically without feed fallback side effects.
- Observability: explicit `last_error` and warning events are emitted for unsupported native-auth vendor execution paths.
- Deterministic replay: unsupported vendor behavior is now deterministic across verification/activity/stream phases.
- Snapshot stability: no schema changes; this pass changes fail-closed behavior only.
- Export integrity: no new payload fields; existing adapter output contract preserved.
- Failure modes: unsupported vendor + native auth can no longer silently degrade into manual-feed execution.
- Operational misconfiguration: Playwright backend startup is now resilient to inherited non-boolean `DEBUG` values.

## Additional remediation batch (Valdrics continuation, 2026-03-01G)

- `VAL-CORE-003` hardening completed with process-level tenant-tier cache:
  - `app/shared/core/pricing.py`
  - added bounded TTL runtime cache for `get_tenant_tier()` (`60s`, max `4096` entries),
  - added explicit cache invalidation API `clear_tenant_tier_cache()` for deterministic control,
  - cache now serves repeated tier lookups even when `db.info` is unavailable (non-request contexts), reducing repeated DB hits.
- Plan-change cache coherency hardening:
  - `app/modules/billing/domain/billing/entitlement_policy.py`
  - `sync_tenant_plan(...)` now calls `clear_tenant_tier_cache(tenant_id)` after successful plan sync to prevent stale entitlement reads.
- Runtime architecture cleanup (no-compat dependency indirection):
  - `app/shared/db/session.py`
  - removed compatibility proxy seams `_get_db_impl_ref` / `_get_system_db_impl_ref`,
  - `get_db()` and `get_system_db()` now delegate directly to `_get_db_impl()` / `_get_system_db_impl()`.
- Updated DB session branch tests for direct implementation seam:
  - `tests/unit/db/test_session_branch_paths_2.py` now patches `_get_system_db_impl` directly.
- Added/expanded pricing cache behavior tests:
  - `tests/unit/core/test_pricing_deep.py`
  - `tests/unit/services/billing/test_entitlement_policy.py`

### Validation evidence (this batch)

- `uv run ruff check app/shared/core/pricing.py app/modules/billing/domain/billing/entitlement_policy.py tests/unit/core/test_pricing_deep.py tests/unit/services/billing/test_entitlement_policy.py` -> passed.
- `uv run mypy app/shared/core/pricing.py app/modules/billing/domain/billing/entitlement_policy.py --hide-error-context --no-error-summary` -> passed.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/core/test_pricing_deep.py tests/unit/services/billing/test_entitlement_policy.py` -> `26 passed`.
- `uv run ruff check app/shared/db/session.py tests/unit/db/test_session_branch_paths_2.py` -> passed.
- `uv run mypy app/shared/db/session.py --hide-error-context --no-error-summary` -> passed.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/db/test_session_branch_paths_2.py tests/unit/db/test_session.py tests/unit/core/test_session.py tests/security/test_rls_security.py` -> `34 passed`.
- `DEBUG=false uv run python scripts/run_enterprise_tdd_gate.py` -> `883 passed` (coverage gates and release evidence checks green).

### Post-closure sanity check (release-critical)

- Concurrency: runtime tier cache uses thread-safe lock-guarded mutations; DB dependency functions now have single direct delegation paths (fewer seam races).
- Observability: existing tier-resolution and DB-session warning/error logs preserved; no silent path introduced.
- Deterministic replay: cache invalidation is explicit (`clear_tenant_tier_cache`), and dependency call graph is now deterministic without proxy indirection.
- Snapshot stability: no API response-schema changes; behavior changes are internal runtime/perf hardening only.
- Export integrity: enforcement/reporting/export payload contracts remain unchanged.
- Failure modes: stale tier reads are bounded by TTL and explicit invalidation on plan sync; DB session dependency paths remain fail-closed where enforced.
- Operational misconfiguration: cache behavior remains safe under missing `db.info`; direct dependency seams reduce override drift and hidden aliasing risk.

## Additional remediation batch (Valdrics continuation, 2026-03-01H)

- `VAL-SEC-003` hardening completed for webhook client IP attribution:
  - `app/modules/billing/api/v1/billing.py`
  - `_extract_client_ip()` now trusts `X-Forwarded-For` only when all conditions hold:
    - `TRUST_PROXY_HEADERS=true`,
    - remote peer IP is inside explicit trusted proxy CIDRs,
    - valid `X-Forwarded-For` chain is present.
  - added `_trusted_proxy_networks()` parsing with defensive invalid-CIDR handling.
- Added explicit proxy trust policy controls and validation:
  - `app/shared/core/config.py`
  - new setting `TRUSTED_PROXY_CIDRS` (list),
  - environment safety validator now:
    - rejects invalid CIDRs,
    - requires non-empty `TRUSTED_PROXY_CIDRS` when `TRUST_PROXY_HEADERS=true` in staging/production.
- `VAL-DB-003` cleanup completed by removing redundant manual close calls in DB dependencies:
  - `app/shared/db/session.py`
  - removed explicit `await session.close()` from `_get_db_impl()` and `_get_system_db_impl()`;
  - lifecycle now relies on `async with async_session_maker()` context-manager semantics only.
- Updated tests for new trust policy and session lifecycle semantics:
  - `tests/unit/api/v1/test_billing.py`
  - `tests/unit/reporting/test_billing_api.py`
  - `tests/unit/core/test_config_branch_paths.py`
  - `tests/unit/db/test_session.py`

### Validation evidence (this batch)

- `uv run ruff check app/shared/core/config.py app/modules/billing/api/v1/billing.py app/shared/db/session.py tests/unit/core/test_config_branch_paths.py tests/unit/api/v1/test_billing.py tests/unit/reporting/test_billing_api.py tests/unit/db/test_session.py` -> passed.
- `uv run mypy app/shared/core/config.py app/modules/billing/api/v1/billing.py app/shared/db/session.py --hide-error-context --no-error-summary` -> passed.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/core/test_config_branch_paths.py tests/unit/api/v1/test_billing.py tests/unit/reporting/test_billing_api.py tests/unit/db/test_session.py tests/unit/db/test_session_branch_paths_2.py tests/unit/shared/db/test_session_coverage.py tests/security/test_rls_security.py` -> `105 passed`.
- `DEBUG=false uv run python scripts/run_enterprise_tdd_gate.py` -> `883 passed` (all release evidence checks and coverage thresholds satisfied).

### Post-closure sanity check (release-critical)

- Concurrency: trusted proxy network parsing is request-local and immutable; DB session lifecycle now has single context-manager ownership with no duplicate close paths.
- Observability: invalid trusted CIDR config and webhook IP attribution branches remain explicitly logged.
- Deterministic replay: webhook source-IP attribution is now deterministic under explicit proxy trust policy instead of implicit XFF trust.
- Snapshot stability: no API response schema drift; behavior change is trust policy enforcement and lifecycle simplification.
- Export integrity: reporting/enforcement export payloads and XML artifacts unchanged.
- Failure modes: proxy trust misconfiguration now fails closed for XFF usage; invalid CIDRs fail at config validation.
- Operational misconfiguration: staging/production now requires explicit trusted proxy CIDR allowlist when proxy headers are enabled.

## Additional remediation batch (Valdrics continuation, 2026-03-01I)

- `VAL-CORE-004` compatibility cleanup finalized in tier resolution:
  - `app/shared/core/pricing.py`
  - removed legacy awaitable-scalar compatibility path from `get_tenant_tier(...)`,
  - added explicit fail-closed guard for invalid scalar result types (`tenant_lookup_invalid_result_type`),
  - retained deterministic FREE fallback and cache population on invalid-result paths.
- `VAL-SEC-003` webhook source allowlist governance strengthened:
  - `app/shared/core/config.py`
    - added `PAYSTACK_WEBHOOK_ALLOWED_IPS` setting with explicit default allowlist,
    - added strict billing config validation for non-empty and syntactically valid IPs.
  - `app/modules/billing/api/v1/billing_ops.py`
    - removed hardcoded webhook IP list from runtime logic,
    - webhook origin check now reads from validated settings (`PAYSTACK_WEBHOOK_ALLOWED_IPS`).
- Removed test duplication debt in pricing deep pack:
  - `tests/unit/core/test_pricing_deep.py`
  - replaced async-scalar compatibility test with invalid-result fail-closed test,
  - removed duplicate invalid-plan test definition.

### Validation evidence (this batch)

- `uv run ruff check app/shared/core/pricing.py app/shared/core/config.py app/modules/billing/api/v1/billing_ops.py tests/unit/core/test_pricing_deep.py tests/unit/core/test_config_branch_paths.py tests/unit/reporting/test_billing_api.py` -> passed.
- `uv run mypy app/shared/core/pricing.py app/shared/core/config.py app/modules/billing/api/v1/billing_ops.py --hide-error-context --no-error-summary` -> passed.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/core/test_pricing_deep.py tests/unit/core/test_config_branch_paths.py tests/unit/reporting/test_billing_api.py tests/unit/api/v1/test_billing.py` -> `91 passed`.
- `DEBUG=false uv run python scripts/run_enterprise_tdd_gate.py` -> passed (exit `0`; all preflight sanity and coverage gates completed successfully).

### Post-closure sanity check (release-critical)

- Concurrency: no shared mutable state added; tier fail-closed contract remains pure/request-local plus bounded cache semantics.
- Observability: invalid tier lookup result types now emit explicit error telemetry rather than implicit fallback through exception noise.
- Deterministic replay: tenant-tier resolution is now contract-deterministic (single scalar access path, explicit invalid-type handling).
- Snapshot stability: no API response schema changes.
- Export integrity: report/enforcement export payload contracts unchanged.
- Failure modes: invalid pricing result shapes and malformed paystack webhook allowlist values fail closed.
- Operational misconfiguration: webhook source-IP policy is now explicit, validated configuration rather than embedded constants.

## Additional remediation batch (Valdrics continuation, 2026-03-01J)

- Canonical disposition sync for adapter decomposition track:
  - `VAL-ADAPT-002`: `CLOSED`.
  - `VAL-ADAPT-002+`: `CLOSED` (no-compat cleanup and direct dispatch/runtime interfaces completed).
  - This canonical status supersedes earlier staged notes that described `VAL-ADAPT-002+` as open maintainability backlog during intermediate decomposition batches.
- Frontend audit disposition sync from `VALDRX_CODEBASE_AUDIT_2026-02-28.md.resolved`:
  - `VAL-FE-001` (mobile horizontal overflow): `CLOSED`.
  - `VAL-FE-002` (`sr-only` clipping/layout break): `CLOSED`.
  - `VAL-FE-003` (off-screen mobile header action): `CLOSED`.
  - `VAL-FE-004` (hero toggle clipping on small viewports): `CLOSED`.
  - Closure is enforced by landing layout regression checks:
    - `dashboard/e2e/landing-layout-audit.spec.ts`

### Validation evidence (this batch)

- `cd dashboard && npm run test:e2e -- e2e/landing-layout-audit.spec.ts` -> `2 passed`
  - `prevents horizontal overflow and keeps sr-only clipped`
  - `keeps header actions on-screen at mobile/tablet breakpoint`

### Post-closure sanity check (release-critical)

- Concurrency: no new shared mutable state introduced; this pass is disposition/evidence sync.
- Observability: frontend layout failures remain machine-detectable via dedicated Playwright assertions.
- Deterministic replay: viewport-specific landing layout checks are deterministic and repeatable.
- Snapshot stability: no backend or API schema changes introduced by this batch.
- Export integrity: documentation-only + frontend regression validation pass; export contracts unchanged.
- Failure modes: overflow/sr-only/header/toggle regressions are explicit test failures.
- Operational misconfiguration: no new runtime config surface introduced.

## Additional remediation batch (Valdrix continuation, 2026-03-01M)

- PKG/FIN operational closeout automation added:
  - `scripts/verify_pkg_fin_operational_readiness.py`
  - composes policy, finance guardrail, and telemetry verifiers and emits one machine-readable readiness summary.
- New operational readiness evidence captured:
  - `docs/ops/evidence/pkg_fin_operational_readiness_2026-03-01.json`
- New regression coverage:
  - `tests/unit/ops/test_verify_pkg_fin_operational_readiness.py`

### Validation evidence (this batch)

- `uv run ruff check scripts/verify_pkg_fin_operational_readiness.py tests/unit/ops/test_verify_pkg_fin_operational_readiness.py` -> passed.
- `uv run mypy scripts/verify_pkg_fin_operational_readiness.py --hide-error-context --no-error-summary` -> passed.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/ops/test_verify_pkg_fin_operational_readiness.py tests/unit/ops/test_verify_pkg_fin_policy_decisions.py tests/unit/ops/test_verify_finance_guardrails_evidence.py tests/unit/ops/test_verify_finance_telemetry_snapshot.py` -> `30 passed`.
- `DEBUG=false uv run python3 scripts/run_enforcement_release_evidence_gate.py ... --finance-evidence-required --finance-telemetry-snapshot-required --pricing-benchmark-register-required --pkg-fin-policy-decisions-required` -> passed (`883 passed`).

### Post-closure sanity check (release-critical)

- Concurrency: readiness verifier is stateless/read-only and does not mutate policy or finance artifacts.
- Observability: single JSON output now makes PKG/FIN residuals explicit (`production_observed telemetry`, `segregated_owners governance`).
- Deterministic replay: same evidence inputs yield deterministic readiness outputs.
- Snapshot stability: no API/runtime payload schema changes introduced by this batch.
- Export integrity: existing evidence schemas are reused and re-verified unchanged.
- Failure modes: strict readiness requirements fail closed when postlaunch prerequisites are unmet.
- Operational misconfiguration: malformed or stale evidence fails early through existing composed verifiers.

## Additional remediation batch (Valdrics continuation, 2026-03-01K)

- Billing webhook idempotency and replay hardening:
  - `app/modules/billing/domain/billing/webhook_retry.py`
  - replaced time-based webhook reference fallback with deterministic payload reference resolution (`reference`, `data.reference`, `data.id`, `id`, `event_id`, stable payload hash fallback),
  - added `mark_inline_processed(...)` to complete queued webhook jobs when inline handling succeeds, preventing duplicate worker re-processing.
  - `app/modules/billing/api/v1/billing_ops.py`
  - immediate webhook path now marks queued retry jobs completed after successful inline processing.
- Dunning duplicate-webhook control:
  - `app/modules/billing/domain/billing/dunning_service.py`
  - added `DUNNING_WEBHOOK_DEBOUNCE_SECONDS` (5 minutes),
  - duplicate rapid `invoice.payment_failed` webhooks now return `duplicate_ignored` without incrementing attempt counters.
- Billing precision hardening:
  - `app/modules/billing/domain/billing/paystack_webhook_impl.py`
  - converted charge subunit and FX parsing to decimal-safe normalization,
  - invalid/negative payload values now fail closed with structured warnings.
  - `app/modules/billing/domain/billing/paystack_service_impl.py`
  - introduced decimal-first USD normalization and cent conversion to remove float-rounding drift in checkout/renewal USD paths.
- Executive reporting security signal integration:
  - `app/modules/reporting/domain/leadership_kpis.py`
  - added deterministic enforcement-derived KPI counters:
    - `security_high_risk_decisions`
    - `security_approval_required_decisions`
    - `security_anomaly_signal_decisions`
  - extended leadership CSV summary with these security posture metrics.
- Public edge and mobile layout hardening:
  - `dashboard/src/routes/+layout.svelte`
  - Supabase auth listener now initializes only for authenticated sessions, eliminating public landing client resolution noise.
  - `dashboard/src/app.css`
  - `.main-content` sidebar offset now applies only from tablet+ breakpoints (`min-width: 768px`), preventing mobile layout breakage.
- Operational safety hardening for destructive/admin scripts:
  - `scripts/force_wipe_app.py`
  - `scripts/database_wipe.py`
  - `scripts/emergency_token.py`
  - all now enforce explicit force flags, confirmation phrases, and protected environment controls for break-glass flows.
- Naming consistency:
  - `app/shared/core/config.py`
  - default `APP_NAME` updated to `Valdrics`.

### Validation evidence (this batch)

- `DEBUG=false .venv/bin/pytest -q -o addopts='' tests/unit/modules/reporting/test_webhook_retry.py tests/unit/services/billing/test_dunning_service.py tests/unit/api/v1/test_billing.py tests/unit/modules/reporting/test_leadership_kpis_domain.py tests/unit/services/billing/test_paystack_billing.py tests/unit/services/billing/test_paystack_billing_branches.py tests/unit/core/test_config_audit.py` -> `122 passed`.
- `cd dashboard && npm run test:e2e -- e2e/landing-layout-audit.spec.ts` -> `2 passed`.
- `.venv/bin/python -m py_compile app/modules/billing/api/v1/billing_ops.py app/modules/billing/domain/billing/dunning_service.py app/modules/billing/domain/billing/paystack_service_impl.py app/modules/billing/domain/billing/paystack_webhook_impl.py app/modules/billing/domain/billing/webhook_retry.py app/modules/reporting/domain/leadership_kpis.py scripts/force_wipe_app.py scripts/database_wipe.py scripts/emergency_token.py` -> passed.

### Post-closure sanity check (release-critical)

- Concurrency: inline webhook completion plus worker retries now share deterministic idempotency references; duplicate webhook storms are debounced before state mutation.
- Observability: duplicate webhook suppression, inline completion failures, invalid payload values, and script guard denials emit explicit structured logs.
- Deterministic replay: webhook idempotency keys are now derived from stable payload identity (no time entropy).
- Snapshot stability: landing layout checks remain deterministic across mobile breakpoints and SR-only clipping assertions.
- Export integrity: leadership KPI CSV now includes explicit security posture columns without changing provider/service sort determinism.
- Failure modes: webhook inline-processing success no longer leaves pending jobs that can replay side effects; invalid FX/amount payloads are safely rejected.
- Operational misconfiguration: destructive scripts and emergency-token generation now fail closed unless explicit break-glass controls are supplied.

## Additional remediation batch (Valdrics continuation, 2026-03-01L)

- SaaS/ITAM security-posture parity hardening for identity activity ingestion:
  - `app/shared/adapters/license_vendor_github.py`
    - added organization role lookups (`/memberships/{login}`) with bounded concurrency and lookup caps,
    - added MFA posture signal ingestion from GitHub 2FA-disabled member filter,
    - added normalized role/state/MFA fields per identity record (`org_role`, `membership_state`, `mfa_enabled`).
  - `app/shared/adapters/license_vendor_google.py`
    - added explicit 2SV posture extraction (`isEnrolledIn2Sv`, `isEnforcedIn2Sv`),
    - elevated delegated admin support into `is_admin` semantics,
    - added normalized admin-role field (`super_admin`, `delegated_admin`, `member`).
  - `app/shared/adapters/license_vendor_microsoft.py`
    - replaced static-admin-only posture with directory-role + registration-report enrichment,
    - ingests admin posture from Entra directory roles and Graph registration report,
    - ingests MFA registration posture (`mfa_enabled`) and records admin provenance (`admin_sources`).
- Security metadata propagation into normalized license resource/usage surfaces:
  - `app/shared/adapters/license_resource_ops.py`
  - resource metadata now carries `admin_role`, `mfa_enabled`, and normalized admin-source lineage,
  - usage tags now include `admin_role` and `mfa_enabled` for downstream governance/reporting joins.
- Public-edge auth-noise reduction (landing resilience):
  - `dashboard/src/routes/+layout.server.ts`
  - public anonymous requests now skip session resolution when no Supabase session cookies are present,
  - keeps authenticated public flows intact when Supabase cookies exist.
- Deployment baseline hardening:
  - `koyeb.yaml`
  - raised Koyeb instance class from `nano` to `micro` for safer baseline headroom under ingestion/worker pressure.

### Validation evidence (this batch)

- `DEBUG=false .venv/bin/pytest -q -o addopts='' tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/services/adapters/test_license_verification_stream_branches.py tests/unit/shared/adapters/test_license_resource_ops.py tests/unit/shared/adapters/test_license_native_dispatch.py` -> `60 passed`.
- `cd dashboard && npm run test:unit -- --run src/routes/layout.server.load.test.ts src/routes/layout-public-menu.svelte.test.ts` -> `5 passed`.
- `cd dashboard && npm run test:e2e -- e2e/landing-layout-audit.spec.ts` -> `2 passed`.
- `.venv/bin/python -m py_compile app/shared/adapters/license_vendor_github.py app/shared/adapters/license_vendor_google.py app/shared/adapters/license_vendor_microsoft.py app/shared/adapters/license_resource_ops.py` -> passed.

### Post-closure sanity check (release-critical)

- Concurrency: GitHub membership role lookups are bounded by explicit semaphore + capped member lookup limit to avoid unbounded fan-out.
- Observability: each optional posture source (directory roles, registration report, GitHub 2FA/admin feeds) now logs explicit fetch-failure events without silent data loss.
- Deterministic replay: security posture enrichment is deterministic for a fixed vendor snapshot; merged resource metadata remains stable under repeated ingestion.
- Snapshot stability: landing mobile regression suite still passes after layout server guard changes.
- Export integrity: normalized license usage rows preserve existing schema while extending tags with additive security metadata only.
- Failure modes: SaaS posture APIs fail soft (empty enrichment) while core activity ingestion remains available; no connector-wide outage from one optional endpoint.
- Operational misconfiguration: public anonymous loads no longer require active Supabase session resolution, reducing DNS/config noise impact on the landing surface.

## Additional remediation batch (Valdrics continuation, 2026-03-01N)

Implemented:
1. Landing maintainability hardening:
   - `dashboard/src/lib/components/LandingHero.svelte`
   - extracted component-scoped style payload to `dashboard/src/lib/components/LandingHero.css` and imported it from the component.
   - reduced monolithic Svelte file footprint and isolated style concerns for safer incremental UI refactors.
2. Public-edge bot protection CSP parity:
   - `dashboard/svelte.config.js`
   - added Cloudflare Turnstile domains to CSP (`script-src`, `connect-src`, `frame-src`) so invisible token execution is policy-compliant.
3. Scheduler blast-radius controls for system-scope sweeps:
   - `app/tasks/scheduler_tasks.py`
   - added deterministic scope caps (`_system_sweep_tenant_limit`, `_system_sweep_connection_limit`) and enforced capping in cohort, remediation, acceptance, and enforcement reconciliation sweeps.
   - added explicit `scheduler_scope_capped` warning telemetry when runtime caps are applied.
4. Runtime configuration for sweep caps:
   - `app/shared/core/config.py`
   - added `SCHEDULER_SYSTEM_SWEEP_MAX_TENANTS` and `SCHEDULER_SYSTEM_SWEEP_MAX_CONNECTIONS`.
5. Regression coverage for scheduler cap behavior:
   - `tests/unit/tasks/test_scheduler_tasks_branch_paths_2.py`
   - added deterministic tests for tenant-scope and connection-scope cap enforcement.

Validation:
1. `DEBUG=false uv run pytest -q --no-cov tests/unit/tasks/test_scheduler_tasks_branch_paths_2.py tests/unit/core/test_config_audit.py` -> `34 passed`
2. `uv run ruff check app/tasks/scheduler_tasks.py app/shared/core/config.py tests/unit/tasks/test_scheduler_tasks_branch_paths_2.py` -> passed
3. `cd dashboard && npm run check` -> passed (`0 errors`, `0 warnings`)
4. `cd dashboard && npm run test:unit -- --run src/routes/auth/login/login-page.svelte.test.ts src/routes/onboarding/onboarding-page.svelte.test.ts src/lib/security/turnstile.test.ts src/routes/layout.server.load.test.ts` -> `12 passed`
5. `cd dashboard && npm run test:e2e -- e2e/landing-layout-audit.spec.ts` -> `2 passed`

Post-closure sanity (release-critical):
1. Concurrency: scheduler caps bound global-sweep workload fan-out and reduce incident blast radius under retry pressure.
2. Observability: cap activation emits structured `scheduler_scope_capped` telemetry with scope/total/cap values.
3. Deterministic replay: capped selection is deterministic for a fixed input ordering and configured cap values.
4. Snapshot stability: landing regression snapshots remain stable (`390`/`500` viewport checks green).
5. Export integrity: no reporting/export schema mutations in this batch.
6. Failure modes: missing/invalid sweep cap settings fail safely to bounded defaults.
7. Operational misconfiguration: Turnstile runtime now matches declared CSP policy, preventing silent script/frame policy breakage.

## Additional remediation batch (Valdrics continuation, 2026-03-01O)

Implemented:
1. Distributed circuit-breaker backend unavailability now fails closed in staging/production:
   - `app/shared/remediation/circuit_breaker.py`
   - when distributed state is required but Redis backend is unavailable, `can_execute()` returns `False`,
   - state mutation methods (`record_success`, `record_failure`, `reset`) skip safely and log explicit warnings,
   - status payload now includes backend availability metadata (`distributed_backend_available`, `backend_unavailable_reason`).
2. Hybrid scheduler observability hardening:
   - `app/shared/llm/hybrid_scheduler.py`
   - added OTel spans across run-decision and execution paths:
     - `hybrid_analysis.should_run_full`
     - `hybrid_analysis.run`
     - `hybrid_analysis.full_run`
     - `hybrid_analysis.delta_run`
   - spans now record key attributes, success/error status, and exceptions.
3. Staging/production passive tenancy-isolation evidence checks in acceptance capture:
   - `app/modules/governance/domain/jobs/handlers/acceptance.py`
   - `app/modules/governance/domain/security/audit_log.py`
   - acceptance job now validates freshness/success of latest `TENANCY_ISOLATION_VERIFICATION_CAPTURED` evidence and records integration status under `integration_test.tenancy`,
   - added configurable freshness ceiling:
     - `app/shared/core/config.py`: `TENANT_ISOLATION_EVIDENCE_MAX_AGE_HOURS`.
4. Comprehensive TDD updates for all new control paths:
   - `tests/unit/remediation/test_circuit_breaker_deep.py`
   - `tests/unit/llm/test_hybrid_scheduler.py`
   - `tests/unit/services/jobs/test_acceptance_suite_capture_handler_branches.py`

Validation:
1. `uv run ruff check app/shared/remediation/circuit_breaker.py app/shared/llm/hybrid_scheduler.py app/modules/governance/domain/jobs/handlers/acceptance.py app/modules/governance/domain/security/audit_log.py app/shared/core/config.py tests/unit/remediation/test_circuit_breaker_deep.py tests/unit/llm/test_hybrid_scheduler.py tests/unit/services/jobs/test_acceptance_suite_capture_handler_branches.py` -> passed.
2. `uv run mypy app/shared/remediation/circuit_breaker.py app/shared/llm/hybrid_scheduler.py app/modules/governance/domain/jobs/handlers/acceptance.py app/modules/governance/domain/security/audit_log.py app/shared/core/config.py --hide-error-context` -> passed.
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/remediation/test_circuit_breaker_deep.py tests/unit/llm/test_hybrid_scheduler.py tests/unit/llm/test_hybrid_scheduler_exhaustive.py tests/unit/services/jobs/test_acceptance_suite_capture_handler_branches.py tests/unit/core/test_config_audit.py` -> `57 passed`.
4. `DEBUG=false uv run pytest -q --no-cov tests/unit/tasks/test_scheduler_tasks_branch_paths_2.py tests/unit/ops/test_verify_alembic_head_integrity.py tests/unit/ops/test_verify_alertmanager_channels.py tests/unit/ops/test_verify_pkg_fin_operational_readiness.py` -> `35 passed`.
5. `DEBUG=false uv run pytest -q --no-cov tests/governance/test_azure_rbac_auditor.py tests/governance/test_gcp_iam_auditor.py tests/governance/test_unified_domain_auditor.py` -> `6 passed`.
6. `cd dashboard && npm run check` -> passed (`0 errors`, `0 warnings`).
7. `cd dashboard && npm run test:unit -- --run src/routes/auth/login/login-page.svelte.test.ts src/routes/onboarding/onboarding-page.svelte.test.ts src/lib/security/turnstile.test.ts src/routes/layout.server.load.test.ts` -> `12 passed`.
8. `cd dashboard && npm run test:e2e -- e2e/landing-layout-audit.spec.ts` -> `2 passed`.

Post-closure sanity (release-critical):
1. Concurrency: distributed breaker fail-closed path prevents split-brain mutation when shared backend disappears.
2. Observability: hybrid scheduler spans and breaker-unavailable telemetry make recovery and latency triage explicit.
3. Deterministic replay: acceptance tenancy checks use deterministic latest-evidence lookup and explicit freshness thresholds.
4. Snapshot stability: landing layout audit remains green at mobile breakpoints after hardening batch reruns.
5. Export integrity: no report/export schema drift introduced; integration/audit additions are additive and typed.
6. Failure modes: missing, stale, or failed tenancy evidence now blocks staging/production acceptance readiness by design.
7. Operational misconfiguration: staging/production distributed-state misconfiguration now fails closed instead of silently falling back.

## Additional remediation batch (Valdrics continuation, 2026-03-01P)

Implemented:
1. Frontend architecture decomposition for landing maintainability:
   - extracted hero copy into:
     - `dashboard/src/lib/components/landing/LandingHeroCopy.svelte`
   - extracted realtime signal map card into:
     - `dashboard/src/lib/components/landing/LandingSignalMapCard.svelte`
   - extracted spend scenario simulator into:
     - `dashboard/src/lib/components/landing/LandingRoiSimulator.svelte`
   - extracted ROI calculator section into:
     - `dashboard/src/lib/components/landing/LandingRoiCalculator.svelte`
   - rewired orchestration in:
     - `dashboard/src/lib/components/LandingHero.svelte`
2. Added explicit component-level regression coverage for decomposed sections:
   - `dashboard/src/lib/components/landing/landing_decomposition.svelte.test.ts`

Validation:
1. `cd dashboard && npm run check` -> passed (`0 errors`, `0 warnings`).
2. `cd dashboard && npm run test:unit -- --run src/lib/components/LandingHero.svelte.test.ts src/lib/components/landing/landing_components.svelte.test.ts src/lib/components/landing/landing_decomposition.svelte.test.ts src/routes/auth/login/login-page.svelte.test.ts src/routes/onboarding/onboarding-page.svelte.test.ts src/lib/security/turnstile.test.ts src/routes/layout.server.load.test.ts` -> `21 passed`.
3. `cd dashboard && npm run test:e2e -- e2e/landing-layout-audit.spec.ts` -> `2 passed`.

Post-closure sanity (release-critical):
1. Concurrency: signal-map rotation/observer ownership remains centralized in `LandingHero`, preventing duplicate interval schedulers after decomposition.
2. Observability: telemetry event emitters remained in parent orchestration; CTA, lane, snapshot, and scenario interactions preserve existing instrumentation.
3. Deterministic replay: snapshot/lane/demo selection behavior remains deterministic; decomposed components are pure prop-driven renders.
4. Snapshot stability: mobile overflow, `sr-only` clipping, and mobile header-on-screen audits remain green in Playwright regression checks.
5. Export integrity: no backend schema or export payload changes were introduced by this frontend-only decomposition.
6. Failure modes: ROI/simulator controls now flow through typed callback boundaries with component tests covering numeric parsing and event propagation.
7. Operational misconfiguration: decomposition removes monolith coupling without introducing new runtime config knobs.

## Additional remediation batch (Valdrics continuation, 2026-03-01Q)

Implemented:
1. Landing flow length reduction (buyer-first compression) in:
   - `dashboard/src/lib/components/LandingHero.svelte`
   - removed duplicate workflow/cloud-hook rendering pass from lower-page flow,
   - replaced long in-page ROI calculator block with compact ROI CTA card (`Open Full ROI Planner`),
   - removed redundant standalone cross-surface coverage section and kept a condensed capability preview.
2. Kept the high-conversion content intact:
   - hero + realtime signal map
   - cloud hook/workflow (single pass)
   - realtime simulator
   - plans and free-tier CTA
   - trust/proof section
3. Updated landing regression assertions:
   - `dashboard/src/lib/components/LandingHero.svelte.test.ts`
   - aligned expectations to shorter page structure and condensed capability preview.

Validation:
1. `cd dashboard && npm run check` -> passed (`0 errors`, `0 warnings`).
2. `cd dashboard && npm run test:unit -- --run src/lib/components/LandingHero.svelte.test.ts src/lib/components/landing/landing_components.svelte.test.ts src/lib/components/landing/landing_decomposition.svelte.test.ts src/routes/auth/login/login-page.svelte.test.ts src/routes/onboarding/onboarding-page.svelte.test.ts src/lib/security/turnstile.test.ts src/routes/layout.server.load.test.ts` -> `21 passed`.
3. `cd dashboard && npm run test:e2e -- e2e/landing-layout-audit.spec.ts` -> `2 passed`.

Post-closure sanity (release-critical):
1. Concurrency: snapshot/demo rotation lifecycle remains parent-controlled; no duplicate interval ownership introduced.
2. Observability: CTA and interaction telemetry paths remain intact (`trackCta`, section-view, scenario-adjust).
3. Deterministic replay: landing section ordering and visible-content flow are deterministic per experiment variant.
4. Snapshot stability: mobile overflow and header-on-screen layout audits remain green after compression.
5. Export integrity: no backend export/report schema changes.
6. Failure modes: removed duplicated section pass to reduce content drift/contradictory messaging risk.
7. Operational misconfiguration: no new runtime flags or config surfaces introduced.

## Additional remediation batch (Valdrics continuation, 2026-03-01R)

Implemented:
1. Post-auth ROI intent routing is now explicit:
   - `dashboard/src/lib/auth/publicAuthIntent.ts`
   - `roi_assessment` now resolves to `/roi-planner` (other intents still resolve to `/onboarding`).
2. Added dedicated authenticated ROI planner workspace:
   - `dashboard/src/routes/roi-planner/+page.svelte`
   - full 12-month planner view is available after signup/login and remains revisitable from app nav.
3. Added app navigation discovery for ROI planner:
   - `dashboard/src/routes/+layout.svelte`
   - `dashboard/src/lib/persona.ts`
4. Reduced landing component complexity to production-manageable size:
   - `dashboard/src/lib/components/LandingHero.svelte` reduced from `1020` lines to `609` lines,
   - extracted section components:
     - `dashboard/src/lib/components/landing/LandingCloudHookSection.svelte`
     - `dashboard/src/lib/components/landing/LandingWorkflowSection.svelte`
     - `dashboard/src/lib/components/landing/LandingBenefitsSection.svelte`
     - `dashboard/src/lib/components/landing/LandingPlansSection.svelte`
     - `dashboard/src/lib/components/landing/LandingPersonaSection.svelte`
     - `dashboard/src/lib/components/landing/LandingCapabilitiesSection.svelte`
     - `dashboard/src/lib/components/landing/LandingTrustSection.svelte`
     - `dashboard/src/lib/components/landing/LandingRoiPlannerCta.svelte`
5. ROI calculator component upgraded for reusable enterprise contexts:
   - `dashboard/src/lib/components/landing/LandingRoiCalculator.svelte`
   - supports configurable heading/subtitle/CTA/section ID without duplicating logic.

Validation:
1. `cd dashboard && npm run check` -> passed (`0 errors`, `0 warnings`).
2. `cd dashboard && npm run test:unit -- --run src/lib/auth/publicAuthIntent.test.ts src/routes/auth/login/login-page.svelte.test.ts src/routes/roi-planner/roi-planner-page.svelte.test.ts src/lib/components/LandingHero.svelte.test.ts src/lib/components/landing/landing_decomposition.svelte.test.ts` -> `15 passed`.
3. `cd dashboard && npm run test:e2e -- e2e/landing-layout-audit.spec.ts` -> `2 passed`.

Post-closure sanity (release-critical):
1. Concurrency: landing timers/observers stay parent-controlled; extracted sections are stateless render surfaces.
2. Observability: CTA + funnel attribution hooks remain centralized and unchanged in tracking semantics.
3. Deterministic replay: ROI intent routing is deterministic (`roi_assessment` -> `/roi-planner`) with preserved UTM/persona context.
4. Snapshot stability: mobile overflow and responsive header layout audits remain green after section extraction.
5. Export integrity: no backend export contract changes; changes are frontend routing/composition only.
6. Failure modes: unauthenticated ROI planner access fails safely via `AuthGate` with explicit sign-in path.
7. Operational misconfiguration: no new runtime toggles; route behavior depends only on existing auth context parsing.

## Additional remediation batch (Valdrics continuation, 2026-03-01T)

- Operational kill-switch hardening for destructive scripts:
  - added shared guardrail module `scripts/safety_guardrails.py` for confirmation phrase, environment confirmation, protected-environment bypass, and interactive confirmation token checks.
  - wired into:
    - `scripts/force_wipe_app.py`
    - `scripts/database_wipe.py`
- Emergency-token break-glass hardening:
  - tightened `scripts/emergency_token.py` with:
    - protected-environment bypass requirements,
    - mandatory operator + reason fields,
    - interactive confirmation token,
    - target-role restriction (`owner`/`admin` only),
    - audit event emission for issuance.
  - added new immutable audit event type:
    - `app/modules/governance/domain/security/audit_log.py`
    - `AuditEventType.SECURITY_EMERGENCY_TOKEN_ISSUED`.
- Landing maintainability regression guard:
  - added `scripts/verify_landing_component_budget.py` to enforce `LandingHero.svelte` line-budget and required decomposition-component presence.
  - extended `dashboard/e2e/landing-layout-audit.spec.ts` with a regression check that anonymous landing loads do not trigger unresolved Supabase host errors.

### Validation evidence (this batch)

- `DEBUG=false uv run pytest -q --no-cov tests/unit/ops/test_script_safety_guardrails.py tests/unit/ops/test_destructive_script_validations.py tests/unit/ops/test_emergency_token_guardrails.py tests/unit/ops/test_verify_landing_component_budget.py` -> `27 passed`.
- `DEBUG=false uv run pytest -q --no-cov tests/governance/test_audit_log.py` -> `18 passed`.
- `uv run ruff check scripts/safety_guardrails.py scripts/force_wipe_app.py scripts/database_wipe.py scripts/emergency_token.py scripts/verify_landing_component_budget.py tests/unit/ops/test_script_safety_guardrails.py tests/unit/ops/test_destructive_script_validations.py tests/unit/ops/test_emergency_token_guardrails.py tests/unit/ops/test_verify_landing_component_budget.py app/modules/governance/domain/security/audit_log.py` -> passed.
- `cd dashboard && npx playwright test e2e/landing-layout-audit.spec.ts` -> `3 passed`.

### Post-closure sanity check (release-critical)

- Concurrency: destructive actions now require deliberate, human-in-the-loop confirmations; accidental concurrent invocation risk reduced by explicit guard conditions.
- Observability: emergency token issuance now creates immutable audit evidence with operator context.
- Deterministic replay: guardrail validation is deterministic (`--force`, phrase, environment, protected bypass requirements).
- Snapshot stability: landing layout/mobile overflow regressions re-validated via Playwright spec.
- Export integrity: no export payload or evidence schema contracts changed in this batch.
- Failure modes: misconfigured environments fail closed for wipe/token scripts.
- Operational misconfiguration: protected-environment misuse now requires explicit bypass phrase plus confirmation token.

## Additional remediation batch (Valdrics continuation, 2026-03-01U)

- Hybrid scheduler observability latency hardening:
  - `app/shared/llm/hybrid_scheduler.py`
  - `_hybrid_span(...)` now records deterministic span duration (`hybrid.duration_ms`) on both success and failure paths.
  - adds explicit slow-span warning emission (`hybrid_span_latency_spike`) for spans >= 2000ms to improve latency spike triage.
- Regression coverage extended:
  - `tests/unit/llm/test_hybrid_scheduler.py`
  - validates duration attribute capture on success and error paths,
  - validates slow-span warning behavior.

### Validation evidence (this batch)

- `DEBUG=false uv run pytest -q --no-cov tests/unit/llm/test_hybrid_scheduler.py` -> `7 passed`.
- `uv run ruff check app/shared/llm/hybrid_scheduler.py tests/unit/llm/test_hybrid_scheduler.py` -> passed.
- `uv run mypy app/shared/llm/hybrid_scheduler.py --hide-error-context --no-error-summary` -> passed.

### Post-closure sanity check (release-critical)

- Concurrency: no shared mutable state introduced; span-duration instrumentation remains request/task-local.
- Observability: latency duration is now explicitly captured in every hybrid scheduler span with slow-span warnings.
- Deterministic replay: duration attribute emission is deterministic per span lifecycle.
- Snapshot stability: no API payload/schema changes introduced.
- Export integrity: no export/report format changes.
- Failure modes: exceptions still propagate unchanged while now preserving duration telemetry.
- Operational misconfiguration: no new runtime env dependency required for this instrumentation.

## Additional remediation batch (Valdrics continuation, 2026-03-01V)

- Legacy branding normalization hardening:
  - `app/shared/core/config.py`
  - added `_normalize_branding()` in central settings validation to normalize legacy product names (`Valdrix`, `CloudSentinel*`) to canonical `Valdrics` at runtime.
  - emits explicit structured warning (`legacy_app_name_normalized`) when normalization is applied.
- Added regression coverage:
  - `tests/unit/core/test_config_audit.py::test_settings_normalizes_legacy_brand_name`.
- Updated remaining user-facing dashboard strings from legacy `Valdrix` to `Valdrics` in:
  - `dashboard/src/lib/api.ts`
  - `dashboard/src/app.css`
  - `dashboard/src/lib/components/IdentitySettingsCard.svelte`
  - `dashboard/src/routes/onboarding/+page.svelte`
  - `dashboard/src/routes/settings/+page.svelte`

### Validation evidence (this batch)

- `DEBUG=false uv run pytest -q --no-cov tests/unit/core/test_config_audit.py` -> `10 passed`.
- `uv run ruff check app/shared/core/config.py tests/unit/core/test_config_audit.py` -> passed.
- `uv run mypy app/shared/core/config.py --hide-error-context --no-error-summary` -> passed.
- `cd dashboard && npm run check` -> passed (`0 errors`, `0 warnings`).

### Post-closure sanity check (release-critical)

- Concurrency: branding normalization is settings-local and deterministic; no shared mutable runtime state introduced.
- Observability: normalization emits explicit structured log for operator traceability.
- Deterministic replay: same `APP_NAME` inputs normalize to same canonical output.
- Snapshot stability: no API/schema/payload contract changes.
- Export integrity: no report/export schemas modified.
- Failure modes: legacy names no longer leak into runtime identity surfaces.
- Operational misconfiguration: stale env branding is auto-corrected with warning instead of silent drift.
