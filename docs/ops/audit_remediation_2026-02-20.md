# Audit Remediation Log (2026-02-20)

Source audit: `/home/daretechie/.gemini/antigravity/brain/c6c55133-7d83-4352-ab23-f80736e51075/audit_report.md.resolved`

## Remediation Status

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

## Consolidated remediation status (Valdrix follow-up, 2026-02-28)

This section consolidates what is now remediated from the Valdrix audit stream so reviewers do not need to reconstruct status across multiple execution updates.

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

## Additional remediation batch (Valdrix continuation, 2026-02-28N)

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

## Additional remediation batch (Valdrix continuation, 2026-02-28O)

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

## Additional remediation batch (Valdrix continuation, 2026-02-28P)

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

## Additional remediation batch (Valdrix continuation, 2026-02-28Q)

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

## Additional remediation batch (Valdrix continuation, 2026-02-28R)

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

## Valdrix remaining finding dispositions (post-remediation review)

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

## Additional remediation batch (Valdrix continuation, 2026-02-28S)

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

## Additional remediation batch (Valdrix continuation, 2026-02-28T)

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

## Additional remediation batch (Valdrix continuation, 2026-02-28U)

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

## Additional remediation batch (Valdrix continuation, 2026-02-28V)

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

## Additional remediation batch (Valdrix continuation, 2026-02-28W)

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

## Additional remediation batch (Valdrix continuation, 2026-02-28X)

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
