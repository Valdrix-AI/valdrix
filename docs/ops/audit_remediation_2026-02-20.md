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

### Residual non-code actions

- Local `.env` still contains live-pattern secrets on the developer workstation.
  - Verified by `python3 scripts/security/check_local_env_for_live_secrets.py`.
  - This requires external rotation/revocation in provider dashboards; no code patch can rotate third-party credentials.

### Finding reassessment notes

- `H-3` is now remediated via lazy DB runtime initialization in `app/shared/db/session.py`.
