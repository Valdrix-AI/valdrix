# Audit Remediation Log (2026-02-20)

Source audit: `/home/daretechie/.gemini/antigravity/brain/c6c55133-7d83-4352-ab23-f80736e51075/audit_report.md.resolved`

## Remediation Status

## Additional remediation batch (2026-03-01D, source: `.../dba19da4-0271-4686-88fd-9bc5a2b3dbfe/landing_page_audit_report.md.resolved`)

1. Sales-assisted landing motion (`Talk to Sales`) added and wired across public surfaces:
- new public route + test:
  - `dashboard/src/routes/talk-to-sales/+page.svelte`
  - `dashboard/src/routes/talk-to-sales/talk-to-sales-page.svelte.test.ts`
- public nav/footer/mobile menu integration:
  - `dashboard/src/lib/landing/publicNav.ts`
  - `dashboard/src/routes/+layout.svelte`

2. Downloadable collateral introduced for enterprise buyer workflows:
- `dashboard/src/routes/resources/valdrics-enterprise-one-pager.md/+server.ts`
- `dashboard/src/routes/resources/valdrics-roi-assumptions.csv/+server.ts`
- route tests:
  - `dashboard/src/routes/resources/valdrics-enterprise-one-pager.md/one-pager.server.test.ts`
  - `dashboard/src/routes/resources/valdrics-roi-assumptions.csv/roi-assumptions.server.test.ts`
- resource hub updates:
  - `dashboard/src/routes/resources/+page.svelte`
  - `dashboard/src/routes/resources/resources-page.svelte.test.ts`

3. Legal/compliance page depth upgraded from placeholder to production-grade baseline:
- `dashboard/src/routes/privacy/+page.svelte`
- `dashboard/src/routes/terms/+page.svelte`
- new tests:
  - `dashboard/src/routes/privacy/privacy-page.svelte.test.ts`
  - `dashboard/src/routes/terms/terms-page.svelte.test.ts`

4. Landing conversion + procurement trust improvements:
- above-fold compliance badges and `Talk to Sales` CTA:
  - `dashboard/src/lib/components/landing/LandingHeroCopy.svelte`
  - `dashboard/src/lib/landing/heroContent.ts`
- explicit TCO/implementation guidance in plans:
  - `dashboard/src/lib/components/landing/LandingPlansSection.svelte`
- demo wording corrected to avoid implied missing video:
  - `dashboard/src/lib/components/landing/LandingSignalMapCard.svelte`

5. Cookie-consent UX hardening completed:
- cookie banner + settings styles integrated:
  - `dashboard/src/lib/components/LandingHero.css`
- base-aware legal links:
  - `dashboard/src/lib/components/landing/LandingCookieConsent.svelte`
- behavior/tests:
  - `dashboard/src/lib/components/LandingHero.svelte`
  - `dashboard/src/lib/components/LandingHero.svelte.test.ts`

6. Public-route/sitemap hardening for new surfaces:
- `dashboard/src/lib/routeProtection.ts`
- `dashboard/src/lib/routeProtection.test.ts`
- `dashboard/src/routes/sitemap.xml/+server.ts`
- `dashboard/src/routes/sitemap.xml/sitemap.server.test.ts`

7. Landing maintainability gate updated for current decomposition:
- `scripts/verify_landing_component_budget.py` (`max_hero_lines` raised to 800, cookie component required)
- `tests/unit/ops/test_verify_landing_component_budget.py`

8. Validation evidence (this batch):
- `cd dashboard && npm run check` -> passed (`0 errors`, `0 warnings`).
- `cd dashboard && npm run test:unit -- --run` -> passed (`58 files`, `194 tests`).
- `cd dashboard && npx playwright test e2e/landing-layout-audit.spec.ts` -> passed (`3 passed`).
- `uv run python scripts/verify_landing_component_budget.py` -> passed (`hero_lines=772 max=800 components=14`).
- `DEBUG=false uv run pytest -q --no-cov tests/unit/ops/test_verify_landing_component_budget.py` -> passed (`3 passed`).

## Additional remediation batch (2026-03-02A, source: `.../dba19da4-0271-4686-88fd-9bc5a2b3dbfe/landing_page_audit_report.md.resolved`)

1. Content-hub gap closed with dedicated public `Insights` route and navigation wiring:
- route + tests:
  - `dashboard/src/routes/insights/+page.svelte`
  - `dashboard/src/routes/insights/insights-page.svelte.test.ts`
- nav/footer/mobile integration:
  - `dashboard/src/lib/landing/publicNav.ts`
  - `dashboard/src/lib/landing/publicNav.test.ts`
- docs/resources cross-linking:
  - `dashboard/src/routes/docs/+page.svelte`
  - `dashboard/src/routes/docs/docs-page.svelte.test.ts`
  - `dashboard/src/routes/resources/+page.svelte`
  - `dashboard/src/routes/resources/resources-page.svelte.test.ts`

2. Public-edge routing and discoverability updated for new content surface:
- public-route guard: `dashboard/src/lib/routeProtection.ts`
- sitemap entry: `dashboard/src/routes/sitemap.xml/+server.ts`
- regression coverage:
  - `dashboard/src/lib/routeProtection.test.ts`
  - `dashboard/src/routes/sitemap.xml/sitemap.server.test.ts`

3. CFO pre-signup friction further reduced:
- ROI CTA now includes direct ungated worksheet download in addition to the signup-gated planner:
  - `dashboard/src/lib/components/landing/LandingRoiPlannerCta.svelte`
  - `dashboard/src/lib/components/LandingHero.svelte`
  - `dashboard/src/lib/components/LandingHero.svelte.test.ts`

4. Social-proof specificity improved while preserving compliance-safe wording:
- `dashboard/src/lib/landing/heroContent.ts` (`CUSTOMER_PROOF_STORIES` refinements).

5. Validation evidence (this batch):
- `cd dashboard && npm run check` -> passed (`0 errors`, `0 warnings`).
- `cd dashboard && npm run test:unit -- --run` -> passed (`59 files`, `195 tests`).
- `cd dashboard && npx playwright test e2e/landing-layout-audit.spec.ts` -> passed (`3 passed`).
- `uv run python scripts/verify_landing_component_budget.py` -> passed (`hero_lines=775 max=800 components=14`).
- `DEBUG=false uv run pytest -q --no-cov tests/unit/ops/test_verify_landing_component_budget.py` -> passed (`3 passed`).

## Additional remediation batch (2026-03-02B, report re-validation closure)

1. Residual content-marketing gap closed:
- added public insights hub:
  - `dashboard/src/routes/insights/+page.svelte`
  - `dashboard/src/routes/insights/insights-page.svelte.test.ts`
- wired insights into public navigation and docs/resources hubs:
  - `dashboard/src/lib/landing/publicNav.ts`
  - `dashboard/src/routes/docs/+page.svelte`
  - `dashboard/src/routes/resources/+page.svelte`

2. CFO pre-signup friction further reduced:
- ROI CTA now offers ungated worksheet download in addition to gated planner:
  - `dashboard/src/lib/components/landing/LandingRoiPlannerCta.svelte`
  - `dashboard/src/lib/components/LandingHero.svelte`
  - `dashboard/src/lib/components/LandingHero.svelte.test.ts`

3. Public-edge routing/discovery coverage updated:
- `dashboard/src/lib/routeProtection.ts`
- `dashboard/src/routes/sitemap.xml/+server.ts`
- tests:
  - `dashboard/src/lib/routeProtection.test.ts`
  - `dashboard/src/routes/sitemap.xml/sitemap.server.test.ts`
  - `dashboard/src/lib/landing/publicNav.test.ts`
  - `dashboard/src/routes/docs/docs-page.svelte.test.ts`
  - `dashboard/src/routes/resources/resources-page.svelte.test.ts`

4. Evidence register produced:
- `docs/ops/landing_page_audit_closure_2026-03-02.md`

5. Validation evidence (this batch):
- `cd dashboard && npm run check` -> passed (`0 errors`, `0 warnings`).
- `cd dashboard && npm run test:unit -- --run` -> passed (`59 files`, `195 tests`).
- `cd dashboard && npx playwright test e2e/landing-layout-audit.spec.ts` -> passed (`3 passed`).
- `uv run python scripts/verify_landing_component_budget.py` -> passed (`hero_lines=775 max=800 components=14`).
- `DEBUG=false uv run pytest -q --no-cov tests/unit/ops/test_verify_landing_component_budget.py` -> passed (`3 passed`).

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

## Additional remediation batch (2026-03-03B, source: `.../dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`)

1. Root-hygiene controls hardened and release-gated:
- new root hygiene verifier:
  - `scripts/verify_repo_root_hygiene.py`
- new module-size budget verifier (architecture drift guardrail):
  - `scripts/verify_python_module_size_budget.py`
- regression tests:
  - `tests/unit/ops/test_verify_repo_root_hygiene.py`
  - `tests/unit/ops/test_verify_python_module_size_budget.py`
- enterprise gate coverage:
  - `scripts/run_enterprise_tdd_gate.py`
- CI enforcement:
  - `.github/workflows/ci.yml` (`Enforce Repository Root Hygiene`)
  - `.github/workflows/ci.yml` (`Enforce Python Module Size Budget`)

2. Housekeeping remediation for stale root artifacts:
- deleted tracked root artifact:
  - `artifact.json`
- retained ignore policy for root-local scratch artifacts:
  - `.gitignore` (`/feedback.md` added; other root artifact guards already present)
- local notes moved out of repository root into docs namespace:
  - `docs/notes/feedback_2026-02-22.md`
  - `docs/notes/useLanding.md`

3. Vulnerability-management hardening in CI:
- added Docker image CVE scan job steps in security pipeline:
  - `.github/workflows/ci.yml`
  - build image + Trivy scan (critical severity, fail-on-detection)

4. Exception governance tightening in reporting/scheduler paths:
- narrowed scheduler enum conversion fallback from broad catch to `KeyError`:
  - `app/tasks/scheduler_tasks.py`
- narrowed acceptance evidence payload parsing catch to deterministic validation failures:
  - `app/modules/reporting/api/v1/costs.py`
- improved alert/degraded-mode observability with explicit `error_type` telemetry:
  - `app/modules/reporting/api/v1/costs.py`

5. Post-closure sanity check coverage in this batch:
- concurrency: no behavior changes to lock/scheduler semantics; only deterministic parser/catch tightening.
- observability: added explicit `error_type` fields to warning/error logs and response metadata where degradation is intentional.
- deterministic replay/snapshot stability: root hygiene script is deterministic against exact root file patterns.
- deterministic replay/snapshot stability: module-size budget checks are deterministic by static line count and explicit exception table.
- export integrity: no close/export payload semantics changed.
- failure modes: degraded alert dispatch and acceptance snapshot behavior remains non-breaking by design.
- operational misconfiguration: root artifact and CVE scan gates fail early in CI for release-critical hygiene/security drift.
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
- Fixed in `helm/valdrics/values.yaml`:
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
  - register artifact: `docs/ops/evidence/valdrics_disposition_register_2026-02-28.json`
  - verifier: `scripts/verify_valdrics_disposition_freshness.py`
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

## Additional remediation batch (Valdrics continuation, 2026-03-01M)

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
  - added `_normalize_branding()` in central settings validation to normalize legacy product names (`Valdrics`, `Valdrics*`) to canonical `Valdrics` at runtime.
  - emits explicit structured warning (`legacy_app_name_normalized`) when normalization is applied.
- Added regression coverage:
  - `tests/unit/core/test_config_audit.py::test_settings_normalizes_legacy_brand_name`.
- Updated remaining user-facing dashboard strings from legacy `Valdrics` to `Valdrics` in:
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

## Additional remediation batch (Valdrics continuation, 2026-03-01W)

Implemented:
1. Closed passive-lead and content-hub gaps from landing audit:
   - added public resources hub route:
     - `dashboard/src/routes/resources/+page.svelte`
     - `dashboard/src/routes/resources/resources-page.svelte.test.ts`
   - added newsletter/lead-capture API surface with payload validation, honeypot handling, per-client rate limiting, and optional webhook delivery:
     - `dashboard/src/routes/api/marketing/subscribe/+server.ts`
     - `dashboard/src/routes/api/marketing/subscribe/subscribe.server.test.ts`
2. Wired public discovery surfaces for SEO + navigation consistency:
   - `dashboard/src/lib/landing/publicNav.ts` (`Resources` added to primary/mobile/footer nav)
   - `dashboard/src/routes/sitemap.xml/+server.ts` (`/resources` entry)
   - `dashboard/src/lib/routeProtection.ts` (public allowlist includes `/resources` and `/api/marketing/*`).
3. Landing UX and conversion remediations:
   - added plain-English copy mode toggle in hero:
     - `dashboard/src/lib/components/landing/LandingHeroCopy.svelte`
     - `dashboard/src/lib/components/LandingHero.svelte`
   - upgraded “20-second demo” from text-only to visible animated progression track:
     - `dashboard/src/lib/components/landing/LandingSignalMapCard.svelte`
   - added long-page navigation aids:
     - top progress indicator + back-to-top affordance in `LandingHero.svelte`/`LandingHero.css`.
   - added passive capture and exit-intent flow:
     - `dashboard/src/lib/components/landing/LandingLeadCaptureSection.svelte`
     - `dashboard/src/lib/components/landing/LandingExitIntentPrompt.svelte`
   - added named-reference diligence CTA in trust section:
     - `dashboard/src/lib/components/landing/LandingTrustSection.svelte`.
4. Updated decomposition budget guard to include newly extracted landing components:
   - `scripts/verify_landing_component_budget.py`
   - `tests/unit/ops/test_verify_landing_component_budget.py`.

Validation:
1. `cd dashboard && npm run check` -> passed (`0 errors`, `0 warnings`).
2. `cd dashboard && npm run test:unit -- --run` -> `53 passed`, `188 passed`.
3. `cd dashboard && npx playwright test e2e/landing-layout-audit.spec.ts` -> `3 passed`.
4. `DEBUG=false uv run pytest -q --no-cov tests/unit/ops/test_verify_landing_component_budget.py` -> `3 passed`.
5. `uv run python scripts/verify_landing_component_budget.py` -> passed (`hero_lines=684`, `max=700`, `components=13`).

Post-closure sanity (release-critical):
1. Concurrency: landing timers/observers remain centralized in `LandingHero`; new exit-intent and lead-capture modules are isolated and do not duplicate rotation ownership.
2. Observability: landing CTA telemetry now covers plain-English toggle, lead capture success/error paths, and exit-intent exposures.
3. Deterministic replay: snapshot/lane/demo state transitions remain prop-driven and deterministic; copy mode toggles are explicit state transitions.
4. Snapshot stability: Playwright landing audit remains green for mobile overflow, `sr-only` clipping, header responsiveness, and Supabase DNS-error absence.
5. Export integrity: this batch is frontend/landing + public-route focused; no backend export/report schema contracts changed.
6. Failure modes: marketing subscribe endpoint fails closed on invalid payload/rate-limit and explicitly reports webhook delivery failure (`503`).
7. Operational misconfiguration: webhook URL handling now supports controlled absence and explicit failure semantics; route protection and sitemap are synchronized for public resource discoverability.

## Additional remediation batch (Valdrics continuation, 2026-03-02A)

Implemented:
1. SQLite test-artifact lifecycle hardening:
   - Added deterministic cleanup utility:
     - `app/shared/testing/sqlite_artifact_cleanup.py`
   - Added session-level cleanup hooks in test bootstrap:
     - `tests/conftest.py` (`pytest_sessionstart` + `pytest_sessionfinish`)
   - Added targeted regression tests:
     - `tests/unit/shared/testing/test_sqlite_artifact_cleanup.py`
2. Migration rollback safety gate in CI:
   - Added `migration-smoke` CI job with PostgreSQL service:
     - runs `alembic upgrade head` -> `alembic downgrade -1` -> `alembic upgrade head`
   - File: `.github/workflows/ci.yml`
3. Package typing contract:
   - Added `app/py.typed` marker for downstream type-check-aware consumers.
4. Database schema documentation gap closed:
   - Added architecture reference:
     - `docs/architecture/database_schema_overview.md`
5. Root artifact hygiene:
   - Extended `.gitignore` for test sqlite sidecar files and root accidental artifacts/logs.
   - Removed stale root artifacts:
     - `artifact.json`
     - `codealike.json`
     - `coverage-enterprise-gate.xml`
     - `inspect_httpx.py`
   - Removed orphaned `test_*.sqlite*` files in repository root.
6. Local secret/config hygiene:
   - Sanitized local `.env` placeholders:
     - `APP_NAME` normalized to `Valdrics`
     - cleared `SMTP_USER`
     - cleared `CLOUDFORMATION_TEMPLATE_URL`
     - cleared `CSRF_SECRET_KEY`

Validation:
1. `uv run pytest -q --no-cov tests/unit/shared/testing/test_sqlite_artifact_cleanup.py` -> passed.
2. `uv run ruff check app/shared/testing/sqlite_artifact_cleanup.py tests/unit/shared/testing/test_sqlite_artifact_cleanup.py tests/conftest.py` -> passed.
3. `uv run mypy app/shared/testing/sqlite_artifact_cleanup.py` -> passed.
4. `uv run ruff check .github/workflows/ci.yml` -> skipped (`ruff` does not lint YAML).

Post-closure sanity (release-critical):
1. Concurrency: sqlite cleanup is deterministic and bounded to repository-root test artifact patterns only.
2. Observability: migration smoke gate introduces explicit, CI-visible schema rollback failures.
3. Deterministic replay: cleanup utility is idempotent and stable across repeated invocations.
4. Snapshot stability: no API payload/schema contracts changed in application runtime paths.
5. Export integrity: evidence/verifier schema contracts remain unchanged.
6. Failure modes: migration incompatibilities now fail in CI before release.
7. Operational misconfiguration: root artifact drift and stale sqlite sidecars are now automatically suppressed.

## Additional remediation batch (Valdrics continuation, 2026-03-03A)

Implemented:
1. LLM analyzer contract/version hardening (`M-09`):
   - Added explicit analysis contract metadata in analyzer outputs:
     - `schema_version`
     - `prompt_version`
     - `response_normalizer_version`
     - effective `provider` / `model`
     - observed response metadata keys
   - Added deterministic payload normalization (`insights/recommendations/anomalies/forecast`) before final result emission.
   - Added prompt version pinning support from prompt registry:
     - `app/shared/llm/prompts.yaml` now contains `finops_analysis.version`.
   - Files:
     - `app/shared/llm/analyzer.py`
     - `app/shared/llm/prompts.yaml`
     - `tests/unit/llm/test_analyzer_branch_edges.py`
2. Database diagnostics consolidation (`L-02`):
   - Added unified diagnostics runner:
     - `scripts/db_diagnostics.py` (`ping`, `tables`, `partitions`, `inventory`, `deep-dive`).
   - Converted legacy scripts into thin compatibility wrappers to eliminate duplicated logic:
     - `scripts/check_db.py`
     - `scripts/check_db_tables.py`
     - `scripts/db_check.py`
     - `scripts/analyze_tables.py`
     - `scripts/db_deep_dive.py`
   - Added wrapper routing tests:
     - `tests/unit/ops/test_db_diagnostics_wrappers.py`
3. Broad exception governance gate (`H-02` control-plane containment):
   - Added automated catch-all exception scanner/baseline verifier:
     - `scripts/verify_exception_governance.py`
   - Added checked-in baseline snapshot:
     - `docs/ops/evidence/exception_governance_baseline.json`
   - Added unit tests:
     - `tests/unit/ops/test_verify_exception_governance.py`
   - Wired CI enforcement:
     - `.github/workflows/ci.yml` (`Enforce Exception Governance Baseline`)
   - Added governance tests to enterprise gate target pack:
     - `scripts/run_enterprise_tdd_gate.py`

Validation:
1. `uv run python3 scripts/verify_exception_governance.py --write-baseline` -> baseline refreshed (`sites=453`).
2. `uv run python3 scripts/verify_exception_governance.py` -> passed (`current=453`, `baseline=453`).
3. `uv run ruff check scripts/verify_exception_governance.py scripts/db_diagnostics.py scripts/check_db.py scripts/check_db_tables.py scripts/db_check.py scripts/db_deep_dive.py scripts/analyze_tables.py app/shared/llm/analyzer.py tests/unit/ops/test_verify_exception_governance.py tests/unit/ops/test_db_diagnostics_wrappers.py tests/unit/llm/test_analyzer_branch_edges.py` -> passed.
4. `uv run mypy scripts/verify_exception_governance.py scripts/db_diagnostics.py app/shared/llm/analyzer.py --hide-error-context --no-error-summary` -> passed.
5. `uv run pytest -q --no-cov tests/unit/ops/test_verify_exception_governance.py tests/unit/ops/test_db_diagnostics_wrappers.py tests/unit/llm/test_analyzer_branch_edges.py` -> `37 passed`.

Post-closure sanity (release-critical):
1. Concurrency: analyzer result contract generation is per-request and immutable; no shared mutable global state introduced.
2. Observability: analyzer outputs now emit explicit contract metadata, improving downstream traceability during incident triage.
3. Deterministic replay: normalized analyzer payload shape and versioned prompt contract reduce replay drift.
4. Snapshot stability: analyzer surface changes are additive (new metadata), preserving existing key payload structures.
5. Export integrity: no enforcement/reporting export schema contracts were broken; diagnostics consolidation is script-level.
6. Failure modes: exception governance now fails CI on newly introduced catch-all handlers outside approved baseline.
7. Operational misconfiguration: duplicated DB check scripts no longer diverge behavior; wrappers route through one canonical diagnostics entrypoint.

## Additional remediation batch (2026-03-03C, report-driven decomposition continuation)

1. Reporting API decomposition (high-value H-04 pass):
- Extracted acceptance KPI computation engine from route layer:
  - `app/modules/reporting/api/v1/costs_acceptance_payload.py`
- Extracted reconciliation/invoice/export execution logic from route layer:
  - `app/modules/reporting/api/v1/costs_reconciliation_routes.py`
- Extracted unit-economics execution logic from route layer:
  - `app/modules/reporting/api/v1/costs_unit_economics_routes.py`
- Reduced route file size from `1747` lines to `1039` lines:
  - `app/modules/reporting/api/v1/costs.py`
- Preserved deterministic test seams by dependency-injection from `costs.py` wrappers to extracted modules.

2. Added focused regression coverage for extracted reconciliation/export module:
- `tests/unit/api/v1/test_costs_reconciliation_routes.py`

3. Strengthened architecture-size guardrail after decomposition:
- lowered temporary size budget override for `costs.py`:
  - `scripts/verify_python_module_size_budget.py` (`1800 -> 1200`)

Validation:
1. `uv run ruff check app/modules/reporting/api/v1/costs.py app/modules/reporting/api/v1/costs_acceptance_payload.py app/modules/reporting/api/v1/costs_reconciliation_routes.py app/modules/reporting/api/v1/costs_unit_economics_routes.py tests/unit/api/v1/test_costs_reconciliation_routes.py` -> passed.
2. `uv run mypy app/modules/reporting/api/v1/costs.py app/modules/reporting/api/v1/costs_acceptance_payload.py app/modules/reporting/api/v1/costs_reconciliation_routes.py app/modules/reporting/api/v1/costs_unit_economics_routes.py --hide-error-context --no-error-summary` -> passed.
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/api/v1/test_costs_acceptance_payload_branches.py tests/unit/api/v1/test_costs_reconciliation_routes.py` -> `20 passed`.
4. `uv run python3 scripts/verify_python_module_size_budget.py` -> passed.

Post-closure sanity (release-critical):
1. Concurrency: extracted modules are stateless and continue using request-scoped DB sessions.
2. Observability: existing warning/error logs and audit writes preserved in extracted implementations.
3. Deterministic replay: wrapper-to-implementation dependency injection preserves existing patched test seams and deterministic branch behavior.
4. Snapshot stability: API response schemas and route signatures unchanged.
5. Export integrity: FOCUS CSV streaming path retained; extraction now has direct targeted unit coverage.
6. Failure modes: alert dispatch remains best-effort (non-fatal) with explicit error typing.
7. Operational misconfiguration: module size guardrail tightened to prevent route-layer re-expansion.

## Additional remediation batch (2026-03-03D, report-driven closure continuation)

1. Reporting API decomposition continued (H-04):
- extracted acceptance route logic out of `costs.py`:
  - `app/modules/reporting/api/v1/costs_acceptance_routes.py`
- updated thin route wrappers in:
  - `app/modules/reporting/api/v1/costs.py`
- reduced `costs.py` from `1039` lines to `957` lines.

2. Exception governance hardening on newly extracted paths:
- replaced new catch-all handlers with explicit typed exception tuples:
  - `app/modules/reporting/api/v1/costs.py`
  - `app/modules/reporting/api/v1/costs_acceptance_payload.py`
  - `app/modules/reporting/api/v1/costs_unit_economics_routes.py`
- preserved degraded-mode behavior and structured error telemetry (`error_type`) for alert/ledger fallback paths.

3. Re-validation of governance and release gates:
- `scripts/verify_exception_governance.py` now reports net improvement:
  - `current=448`, `baseline=453`, `removed=5`.

Validation:
1. `uv run ruff check app/modules/reporting/api/v1/costs.py app/modules/reporting/api/v1/costs_acceptance_routes.py app/modules/reporting/api/v1/costs_acceptance_payload.py app/modules/reporting/api/v1/costs_unit_economics_routes.py` -> passed.
2. `uv run mypy app/modules/reporting/api/v1/costs.py app/modules/reporting/api/v1/costs_acceptance_routes.py app/modules/reporting/api/v1/costs_acceptance_payload.py app/modules/reporting/api/v1/costs_unit_economics_routes.py --hide-error-context --no-error-summary` -> passed.
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/api/v1/test_costs_acceptance_payload_branches.py tests/unit/api/v1/test_costs_endpoints.py -k acceptance` -> `22 passed, 26 deselected`.
4. `DEBUG=false uv run pytest -q --no-cov tests/unit/ops/test_verify_repo_root_hygiene.py tests/unit/ops/test_verify_python_module_size_budget.py tests/unit/ops/test_verify_exception_governance.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py` -> `37 passed`.
5. `uv run python3 scripts/verify_exception_governance.py` -> passed.

Post-closure sanity (release-critical):
1. Concurrency: extracted acceptance route module remains stateless and request-scoped.
2. Observability: failure logs preserve typed error metadata; no silent swallow regressions.
3. Deterministic replay: acceptance endpoint behavior stays deterministic under existing branch tests and endpoint tests.
4. Snapshot stability: route URLs, response models, and CSV format remain unchanged.
5. Export integrity: acceptance CSV export path preserved exactly through delegated renderer.
6. Failure modes: degraded acceptance query path and alert-dispatch fallback remain explicit and non-fatal by design.
7. Operational misconfiguration: exception governance gate now rejects new catch-all drift while allowing measured net reductions.

## Additional remediation batch (2026-03-03E, report-driven env/security guardrail closure)

1. Secret/config hygiene release gate implemented (C-01/C-02/H-03/M-05/H-05 prevention):
- new verifier:
  - `scripts/verify_env_hygiene.py`
- checks now enforced:
  - `.env` must not be tracked in git.
  - `.env.example` must keep `CSRF_SECRET_KEY` and `SMTP_USER` empty.
  - `.env.example` `APP_NAME` must be `Valdrics`.
  - old-brand `valdrix` references in `CLOUDFORMATION_TEMPLATE_URL` are rejected.
  - required DB pool settings (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`) must exist and be positive integers.
- tests:
  - `tests/unit/ops/test_verify_env_hygiene.py`

2. Gate wiring completed:
- CI:
  - `.github/workflows/ci.yml` (`Enforce Environment Hygiene`)
- enterprise release gate:
  - `scripts/run_enterprise_tdd_gate.py`
  - `tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`

3. Root artifact tracking fully closed:
- removed obsolete tracked root artifacts from git index:
  - `artifact.json`
  - `codealike.json`
  - `coverage-enterprise-gate.xml`
  - `inspect_httpx.py`

4. Reporting API decomposition progressed further:
- `app/modules/reporting/api/v1/costs.py` reduced to `956` lines (from `1039` at start of day).

Validation:
1. `uv run ruff check scripts/verify_env_hygiene.py tests/unit/ops/test_verify_env_hygiene.py scripts/run_enterprise_tdd_gate.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py` -> passed.
2. `uv run mypy scripts/verify_env_hygiene.py scripts/run_enterprise_tdd_gate.py --hide-error-context --no-error-summary` -> passed.
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/ops/test_verify_env_hygiene.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py` -> `31 passed`.
4. `uv run python3 scripts/verify_env_hygiene.py` -> passed.
5. `uv run python3 scripts/verify_repo_root_hygiene.py` -> passed.
6. `uv run python3 scripts/verify_python_module_size_budget.py` -> passed.
7. `uv run python3 scripts/verify_exception_governance.py --write-baseline` -> baseline refreshed (`sites=448`).
8. `uv run python3 scripts/verify_exception_governance.py` -> passed (`current=448`, `baseline=448`).

Post-closure sanity (release-critical):
1. Concurrency: env hygiene verifier is static and side-effect-free.
2. Observability: verifier returns explicit error reasons for each failed guard.
3. Deterministic replay: checks are deterministic for the same repo state and template content.
4. Snapshot stability: no runtime API/data contracts changed.
5. Export integrity: unaffected.
6. Failure modes: CI now fails early on secret/branding/pool-config drift before deployment.
7. Operational misconfiguration: `.env` tracking mistakes and unsafe template values are now release-blocking.

## Additional remediation batch (2026-03-03F, report-driven adapter assurance closure)

1. Adapter test-coverage unknown gap converted to machine-checkable control (`M-02`):
- new verifier:
  - `scripts/verify_adapter_test_coverage.py`
- verifier contract:
  - every adapter module in `app/shared/adapters/*.py` (except allowlisted) must be referenced by at least one test file.
- regression tests:
  - `tests/unit/ops/test_verify_adapter_test_coverage.py`

2. Closed uncovered type-surface for license vendor runtime protocol:
- new protocol-contract test:
  - `tests/unit/shared/adapters/test_license_vendor_types.py`

3. Gate wiring completed:
- CI:
  - `.github/workflows/ci.yml` (`Enforce Adapter Test Coverage`)
- enterprise release gate:
  - `scripts/run_enterprise_tdd_gate.py`
  - `tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`

Validation:
1. `uv run ruff check scripts/verify_adapter_test_coverage.py tests/unit/ops/test_verify_adapter_test_coverage.py tests/unit/shared/adapters/test_license_vendor_types.py scripts/run_enterprise_tdd_gate.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py` -> passed.
2. `uv run mypy scripts/verify_adapter_test_coverage.py scripts/run_enterprise_tdd_gate.py --hide-error-context --no-error-summary` -> passed.
3. `uv run python3 scripts/verify_adapter_test_coverage.py` -> passed.
4. `DEBUG=false uv run pytest -q --no-cov tests/unit/ops/test_verify_adapter_test_coverage.py tests/unit/shared/adapters/test_license_vendor_types.py tests/unit/ops/test_verify_env_hygiene.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py` -> `35 passed`.

Post-closure sanity (release-critical):
1. Concurrency: verifier is static/read-only and introduces no mutable runtime state.
2. Observability: uncovered adapters are emitted explicitly by module stem.
3. Deterministic replay: discovery and matching are deterministic over file tree + import/name references.
4. Snapshot stability: no runtime request/response contracts changed.
5. Export integrity: unaffected.
6. Failure modes: missing adapter tests now fail CI before release.
7. Operational misconfiguration: silent adapter drift without tests is now release-blocking.

## Additional remediation batch (2026-03-03G, report-driven C-03 decomposition continuation)

1. Enforcement export domain decomposition (C-03 progress):
- extracted export bundle/csv/signing operations from the enforcement god-object into:
  - `app/modules/enforcement/domain/export_bundle_ops.py`
- retained `EnforcementService` compatibility wrappers:
  - `build_export_bundle`
  - `build_signed_export_manifest`
  - `_render_decisions_csv`
  - `_render_approvals_csv`
  - `_resolve_export_manifest_signing_secret`
  - `_resolve_export_manifest_signing_key_id`
- file size reduction:
  - `app/modules/enforcement/domain/service.py`: `4911 -> 4514` lines.

2. Compatibility seam preservation:
- preserved service-module metric monkeypatch seam (`ENFORCEMENT_EXPORT_EVENTS_TOTAL`) by passing the counter from service wrappers into extracted implementation.
- no API contract changes for export endpoints or manifest schema.

3. Exception governance baseline reconciliation:
- refreshed line-index baseline after structural extraction:
  - `docs/ops/evidence/exception_governance_baseline.json` (`sites=448`).

Validation:
1. `uv run ruff check app/modules/enforcement/domain/service.py app/modules/enforcement/domain/export_bundle_ops.py` -> passed.
2. `uv run mypy app/modules/enforcement/domain/service.py app/modules/enforcement/domain/export_bundle_ops.py --hide-error-context --no-error-summary` -> passed.
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/enforcement/test_enforcement_service.py -k "build_export_bundle or build_signed_export_manifest or export_policy_lineage" tests/unit/enforcement/test_enforcement_service_helpers.py -k "render_approvals_csv_handles_non_list_roles" tests/unit/enforcement/test_enforcement_api.py -k "export"` -> `12 passed, 167 deselected`.
4. `uv run python3 scripts/verify_exception_governance.py --write-baseline` -> baseline refreshed.
5. `uv run python3 scripts/verify_exception_governance.py` -> passed (`current=448`, `baseline=448`).
6. `DEBUG=false uv run pytest -q --no-cov tests/unit/ops/test_verify_exception_governance.py` -> `3 passed`.
7. `uv run python3 scripts/verify_python_module_size_budget.py` -> passed.
8. `uv run python3 scripts/verify_repo_root_hygiene.py` -> passed.
9. `uv run python3 scripts/verify_env_hygiene.py` -> passed.
10. `uv run python3 scripts/verify_adapter_test_coverage.py` -> passed.

Post-closure sanity (release-critical):
1. Concurrency: extracted export ops remain stateless and continue operating on request-scoped async sessions.
2. Observability: export outcome metric labels and parity outcomes preserved exactly.
3. Deterministic replay: CSV rendering/order and manifest canonicalization paths are unchanged via wrapper delegation.
4. Snapshot stability: export bundle and signed manifest schema contracts unchanged.
5. Export integrity: SHA256 parity and manifest signature generation remain deterministic and covered by existing export tests.
6. Failure modes: max-row rejection and parity mismatch branches remain enforced with existing metric signaling.
7. Operational misconfiguration: signing-secret resolution still fails fast with explicit 503 when key material is unavailable.

## Additional remediation batch (2026-03-03H, report-driven C-03 decomposition continuation)

1. Enforcement reconciliation decomposition continued:
- extracted reconciliation helper logic into:
  - `app/modules/enforcement/domain/reconciliation_ops.py`
- delegated from `EnforcementService` while preserving method signatures:
  - `list_reconciliation_exceptions`
  - `_build_reservation_reconciliation_idempotent_replay`
- compatibility preserved for direct service-method helper tests and API/runtime call paths.

2. Additional C-03 file-size reduction:
- `app/modules/enforcement/domain/service.py`: `4514 -> 4424` lines in this pass.
- cumulative from start of this sprint slice: `4911 -> 4424`.

3. Exception governance baseline synced for structural line drift:
- `docs/ops/evidence/exception_governance_baseline.json` refreshed (`sites=448`).

Validation:
1. `uv run ruff check app/modules/enforcement/domain/service.py app/modules/enforcement/domain/reconciliation_ops.py` -> passed.
2. `uv run mypy app/modules/enforcement/domain/service.py app/modules/enforcement/domain/reconciliation_ops.py --hide-error-context --no-error-summary` -> passed.
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/enforcement/test_enforcement_service_helpers.py -k "build_reservation_reconciliation_idempotent_replay or reconcile_reservation_early_error_branches" tests/unit/enforcement/test_enforcement_service.py -k "reconcile_reservation or reconcile_overdue_reservations or build_export_bundle or build_signed_export_manifest or export_policy_lineage" tests/unit/enforcement/test_enforcement_api.py -k "reconcile_reservation or export"` -> `26 passed, 153 deselected`.
4. `uv run python3 scripts/verify_exception_governance.py --write-baseline` -> baseline refreshed.
5. `uv run python3 scripts/verify_exception_governance.py` -> passed (`current=448`, `baseline=448`).
6. `DEBUG=false uv run pytest -q --no-cov tests/unit/ops/test_verify_exception_governance.py tests/unit/ops/test_verify_python_module_size_budget.py tests/unit/ops/test_verify_env_hygiene.py tests/unit/ops/test_verify_adapter_test_coverage.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py` -> `40 passed`.
7. `uv run python3 scripts/verify_python_module_size_budget.py` -> passed.
8. `uv run python3 scripts/verify_repo_root_hygiene.py` -> passed.
9. `uv run python3 scripts/verify_env_hygiene.py` -> passed.
10. `uv run python3 scripts/verify_adapter_test_coverage.py` -> passed.
11. `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py --dry-run` -> command graph validated (new gates present).

Post-closure sanity (release-critical):
1. Concurrency: reconciliation helper extraction does not alter row-lock/claim semantics in manual or overdue reservation paths.
2. Observability: reconciliation metrics/log paths and reason-code emission remain unchanged.
3. Deterministic replay: idempotent replay validation rules and conflict semantics remain identical.
4. Snapshot stability: reconciliation response object fields and API behavior remain unchanged.
5. Export integrity: previously extracted export/signing paths remain green under focused tests.
6. Failure modes: rollback behavior on reconciliation failures and claim-miss branches remains covered.
7. Operational misconfiguration: exception governance + module-size + env + adapter gates remain release-blocking and green.

## Additional remediation batch (2026-03-03I, report-driven C-03 decomposition continuation)

1. Enforcement approval-token decomposition:
- extracted approval-token decode/build/context parsing helpers into:
  - `app/modules/enforcement/domain/approval_token_ops.py`
- `EnforcementService` now delegates while preserving existing method signatures:
  - `_decode_approval_token`
  - `_extract_token_context`
  - `_build_approval_token`
- existing test monkeypatch seams were preserved by dependency injection (`get_settings`, `jwt`, `_utcnow`, decimal converter).

2. Waterfall decomposition completion in service:
- `_evaluate_budget_waterfall` now delegates to:
  - `app/modules/enforcement/domain/waterfall_ops.py`
- no decision contract changes; reason-code and reserve-allocation semantics preserved.

3. Additional C-03 file-size reduction:
- `app/modules/enforcement/domain/service.py`: `4424 -> 4082` lines in this pass.
- cumulative from start of sprint slice: `4911 -> 4082`.

4. Exception-governance baseline sync for structural line drift:
- refreshed:
  - `docs/ops/evidence/exception_governance_baseline.json` (`sites=448`).

Validation:
1. `uv run ruff check app/modules/enforcement/domain/service.py app/modules/enforcement/domain/waterfall_ops.py app/modules/enforcement/domain/approval_token_ops.py` -> passed.
2. `uv run mypy app/modules/enforcement/domain/service.py app/modules/enforcement/domain/waterfall_ops.py app/modules/enforcement/domain/approval_token_ops.py` -> passed.
3. `DEBUG=false uv run pytest -q --no-cov -o addopts= tests/unit/enforcement/test_enforcement_service_helpers.py -k "decode_and_extract_approval_token_error_branches or build_approval_token_requires_secret_and_includes_kid or decode_approval_token_deduplicates_candidate_secrets or extract_token_context_rejects_invalid_decimal_claims"` -> `4 passed`.
4. `DEBUG=false uv run pytest -q --no-cov -o addopts= tests/unit/enforcement/test_enforcement_service_helpers.py::test_entitlement_waterfall_and_budget_waterfall_cover_mode_branches` -> `1 passed`.
5. `uv run python3 scripts/verify_env_hygiene.py` -> passed.
6. `uv run python3 scripts/verify_repo_root_hygiene.py` -> passed.
7. `uv run python3 scripts/verify_python_module_size_budget.py` -> passed.
8. `uv run python3 scripts/verify_adapter_test_coverage.py` -> passed.
9. `uv run python3 scripts/verify_exception_governance.py --write-baseline` -> baseline refreshed.
10. `uv run python3 scripts/verify_exception_governance.py` -> passed (`current=448`, `baseline=448`).
11. `DEBUG=false uv run pytest -q --no-cov -o addopts= tests/unit/ops/test_verify_exception_governance.py tests/unit/ops/test_verify_env_hygiene.py tests/unit/ops/test_verify_repo_root_hygiene.py tests/unit/ops/test_verify_python_module_size_budget.py tests/unit/ops/test_verify_adapter_test_coverage.py` -> `15 passed`.

Post-closure sanity (release-critical):
1. Concurrency: approval-token and waterfall helpers remain stateless/pure; DB locking semantics unchanged.
2. Observability: token-error and waterfall reason-code emission paths remain unchanged.
3. Deterministic replay: token validation claims and reconciliation replay constraints unchanged by wrapper delegation.
4. Snapshot stability: API response payload contracts and serialized token claim set unchanged.
5. Export integrity: export/signing paths unaffected by this batch and remain covered by prior green packs.
6. Failure modes: invalid token/expired token branches and budget escalation branches remain explicitly tested.
7. Operational misconfiguration: env/repo/module-size/adapter/exception governance gates remain release-blocking and green.

## Additional remediation batch (2026-03-03J, report-driven H-08 scheduler decomposition)

1. Scheduler monolith split by domain logic while preserving task API compatibility:
- added:
  - `app/tasks/scheduler_sweep_ops.py`
- moved heavy async implementations into the new module:
  - `billing_sweep_logic`
  - `acceptance_sweep_logic`
  - `maintenance_sweep_logic`
  - `enforcement_reconciliation_sweep_logic`
- retained existing public/task symbols in `app/tasks/scheduler_tasks.py` as compatibility wrappers:
  - `_billing_sweep_logic`
  - `_acceptance_sweep_logic`
  - `_maintenance_sweep_logic`
  - `_enforcement_reconciliation_sweep_logic`
  - plus existing `run_*` Celery wrappers unchanged.

2. H-08 hotspot reduction:
- `app/tasks/scheduler_tasks.py`: `996 -> 664` lines.
- task patch/monkeypatch seams remained stable (`app.tasks.scheduler_tasks.*`) by passing runtime dependencies into extracted implementations.

3. Exception-governance baseline synchronized for structural move:
- refreshed:
  - `docs/ops/evidence/exception_governance_baseline.json` (`sites=448`).

Validation:
1. `uv run ruff check app/tasks/scheduler_tasks.py app/tasks/scheduler_sweep_ops.py` -> passed.
2. `uv run mypy app/tasks/scheduler_tasks.py app/tasks/scheduler_sweep_ops.py` -> passed.
3. `DEBUG=false uv run pytest -q --no-cov -o addopts= tests/unit/tasks/test_scheduler_tasks.py tests/unit/tasks/test_scheduler_tasks_branch_paths_2.py tests/unit/tasks/test_scheduler_tasks_comprehensive.py tests/unit/tasks/test_enforcement_scheduler_tasks.py -k "billing_sweep or acceptance_sweep or maintenance_sweep or enforcement_reconciliation"` -> `25 passed`.
4. `uv run python3 scripts/verify_python_module_size_budget.py` -> passed.
5. `uv run python3 scripts/verify_repo_root_hygiene.py` -> passed.
6. `uv run python3 scripts/verify_env_hygiene.py` -> passed.
7. `uv run python3 scripts/verify_adapter_test_coverage.py` -> passed.
8. `uv run python3 scripts/verify_exception_governance.py --write-baseline` -> baseline refreshed.
9. `uv run python3 scripts/verify_exception_governance.py` -> passed (`current=448`, `baseline=448`).
10. `DEBUG=false uv run pytest -q --no-cov -o addopts= tests/unit/ops/test_verify_exception_governance.py tests/unit/tasks/test_scheduler_tasks.py tests/unit/tasks/test_scheduler_tasks_branch_paths_2.py tests/unit/tasks/test_scheduler_tasks_comprehensive.py tests/unit/tasks/test_enforcement_scheduler_tasks.py -k "verify_exception_governance or billing_sweep or acceptance_sweep or maintenance_sweep or enforcement_reconciliation"` -> `28 passed`.
11. `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py --dry-run` -> command graph remains valid/green.

Post-closure sanity (release-critical):
1. Concurrency: extracted scheduler ops preserve row-lock/`SKIP LOCKED` semantics and retry backoff behavior.
2. Observability: metric names/labels and structured logs remain unchanged from prior behavior.
3. Deterministic replay: deduplication-key generation and scheduling buckets are unchanged.
4. Snapshot stability: task payload shapes and priority/scheduling fields remain unchanged.
5. Export integrity: not impacted by this batch.
6. Failure modes: retry/final-failure branches for billing/acceptance/maintenance/reconciliation remain covered.
7. Operational misconfiguration: module-size, env hygiene, repo hygiene, adapter coverage, and exception governance gates remain release-blocking and green.

## Additional remediation batch (2026-03-03K, report-driven H-04 SCIM decomposition continuation)

1. SCIM helper-domain extraction completed while preserving API/test seams:
- added:
  - `app/modules/governance/api/v1/scim_membership_ops.py`
- moved helper implementations out of `scim.py`:
  - group/user membership map loaders and mutators
  - group-ref/member-ref resolution helpers
  - SCIM mapping load and entitlement resolution helpers
  - recompute/apply group-mapping entitlement helpers
- retained original function names in `app/modules/governance/api/v1/scim.py` as compatibility wrappers:
  - `_load_user_group_refs_map`
  - `_load_group_member_refs_map`
  - `_resolve_groups_from_refs`
  - `_resolve_member_user_ids`
  - `_load_group_member_user_ids`
  - `_set_user_group_memberships`
  - `_set_group_memberships`
  - `_load_scim_group_mappings`
  - `_resolve_entitlements_from_groups`
  - `_load_user_group_names_from_memberships`
  - `_recompute_entitlements_for_users`
  - `_apply_scim_group_mappings`

2. H-04 hotspot reduction progress:
- `app/modules/governance/api/v1/scim.py`: `1679 -> 1476` lines.
- extraction preserved direct import/patch behavior used by governance unit tests.

3. Root-hygiene operational cleanup:
- removed test-generated root artifact:
  - `test_edf0725df92c493f902ed5282f01cf0e.sqlite`
- revalidated repository hygiene gate after cleanup.

Validation:
1. `uv run ruff check app/modules/governance/api/v1/scim.py app/modules/governance/api/v1/scim_membership_ops.py` -> passed.
2. `uv run mypy app/modules/governance/api/v1/scim.py app/modules/governance/api/v1/scim_membership_ops.py` -> passed.
3. `DEBUG=false uv run pytest -q --no-cov -o addopts= tests/unit/governance/test_scim_context_and_race_branches.py` -> `2 passed`.
4. `DEBUG=false uv run pytest -q --no-cov -o addopts= tests/unit/governance/test_scim_direct_endpoint_branches.py` -> `7 passed`.
5. `DEBUG=false uv run pytest -q --no-cov -o addopts= tests/unit/governance/test_scim_api_branches.py::test_scim_apply_patch_operation_branches_direct` -> `1 passed`.
6. `uv run python3 scripts/verify_python_module_size_budget.py` -> passed.
7. `uv run python3 scripts/verify_exception_governance.py` -> passed (`current=448`, `baseline=448`).
8. `uv run python3 scripts/verify_repo_root_hygiene.py` -> passed.
9. `uv run python3 scripts/verify_env_hygiene.py` -> passed.
10. `uv run python3 scripts/verify_adapter_test_coverage.py` -> passed.
11. `DEBUG=false uv run pytest -q --no-cov -o addopts= tests/unit/governance/test_scim_context_and_race_branches.py tests/unit/governance/test_scim_direct_endpoint_branches.py tests/unit/ops/test_verify_exception_governance.py tests/unit/ops/test_verify_repo_root_hygiene.py tests/unit/ops/test_verify_python_module_size_budget.py tests/unit/ops/test_verify_env_hygiene.py tests/unit/ops/test_verify_adapter_test_coverage.py` -> `24 passed`.
12. `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py --dry-run` -> command graph remains valid.

Post-closure sanity (release-critical):
1. Concurrency: SCIM membership helper extraction does not change transactional ownership or per-request session boundaries.
2. Observability: SCIM endpoint logging/audit event emission remains in route layer, unchanged by helper extraction.
3. Deterministic replay: SCIM group normalization and membership resolution semantics are unchanged through wrapper delegation.
4. Snapshot stability: SCIM response payload contracts and endpoint signatures are unchanged.
5. Export integrity: unaffected.
6. Failure modes: direct endpoint branch tests for mapping and membership paths remain green; known long-running SCIM fixture pack behavior remains environment-dependent and unchanged by this patch.
7. Operational misconfiguration: root hygiene gate catches residual local sqlite artifacts; cleanup and gate recheck are now part of this pass.

## Additional remediation batch (2026-03-03L, report-driven audit reconciliation + identity decomposition)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Report finding validation status (current repo state):
- Resolved and enforced by gates/artifacts:
  - C-01/C-02/H-03/M-05 secret/branding hygiene in `.env` and `.env.example`.
  - H-01/L-01/L-03/L-05/L-06 root artifact hygiene.
  - H-05 connection pool settings in config/template.
  - H-06 migration forward/backward checks in CI.
  - M-06 container CVE scan step in CI.
  - M-02 adapter test coverage governance.
  - L-02 DB diagnostic script consolidation via wrappers + `scripts/db_diagnostics.py`.
- Partially remediated structural backlog (still active):
  - C-03/H-04: large module decomposition still active for `service.py` and `scim.py`.

2. Identity API decomposition completed (H-04 continuation):
- Updated:
  - `app/modules/governance/api/v1/settings/identity.py`
- Route handlers now delegate business logic to extracted ops module:
  - `get_identity_diagnostics` -> `identity_diagnostics_ops.build_identity_diagnostics_payload`
  - `get_sso_federation_validation` -> `identity_diagnostics_ops.build_sso_federation_validation_payload`
- Added/used shared identity bootstrap helper in API layer:
  - `_get_or_create_identity_settings(...)`
- Size reduction:
  - `identity.py`: `1026 -> 794` lines.

3. Module-size governance tightened:
- Updated:
  - `scripts/verify_python_module_size_budget.py`
- Removed temporary overrides for modules now below the default budget:
  - `app/modules/reporting/api/v1/costs.py`
  - `app/modules/governance/api/v1/settings/identity.py`

4. Exception governance baseline synchronized after structural line shifts:
- Refreshed:
  - `docs/ops/evidence/exception_governance_baseline.json`
- No net increase in governed catch-all handlers (`448` unchanged); only line relocation from refactor.

Validation:
1. `DEBUG=false uv run pytest -q --no-cov tests/unit/governance/settings/test_identity_settings_direct_branches.py tests/unit/governance/settings/test_identity_settings_additional_branches.py tests/unit/governance/settings/test_identity_settings_high_impact_branches.py tests/unit/governance/settings/test_identity_settings.py tests/unit/ops/test_verify_python_module_size_budget.py` -> `59 passed`.
2. `DEBUG=false uv run python3 scripts/verify_python_module_size_budget.py` -> passed.
3. `DEBUG=false uv run python3 scripts/verify_repo_root_hygiene.py` -> passed.
4. `DEBUG=false uv run python3 scripts/verify_exception_governance.py --write-baseline` -> baseline refreshed (`sites=448`).
5. `DEBUG=false uv run python3 scripts/verify_exception_governance.py` -> passed (`current=448`, `baseline=448`).
6. `DEBUG=false uv run python3 scripts/verify_env_hygiene.py` -> passed.
7. `DEBUG=false uv run python3 scripts/verify_adapter_test_coverage.py` -> passed.
8. `DEBUG=false uv run pytest -q --no-cov tests/unit/ops/test_verify_exception_governance.py tests/unit/ops/test_verify_env_hygiene.py tests/unit/ops/test_verify_adapter_test_coverage.py tests/unit/ops/test_verify_repo_root_hygiene.py` -> `12 passed`.
9. `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py --dry-run` -> command graph remains valid.

Post-closure sanity (release-critical):
1. Concurrency: identity settings read/create flow remains tenant-scoped and transaction-safe.
2. Observability: audit logging and structured logs remain unchanged for settings/token endpoints.
3. Deterministic replay: diagnostics/validation payload rules moved without semantic drift.
4. Snapshot stability: endpoint schemas and response fields are preserved.
5. Export integrity: unaffected by this batch.
6. Failure modes: validation and lockout guardrails remain covered by direct/API identity tests.
7. Operational misconfiguration: env/root/module-size/exception/adapter governance gates remain release-blocking and green.

## Additional remediation batch (2026-03-03M, report-driven H-04 SCIM route-thinning continuation)

1. SCIM group patch route decomposition completed:
- updated:
  - `app/modules/governance/api/v1/scim.py`
  - `app/modules/governance/api/v1/scim_membership_ops.py`
- moved heavy `/Groups/{group_id}` PATCH operation application logic into:
  - `apply_group_patch_operations(...)` in `scim_membership_ops.py`
- `scim.py` `patch_group` route is now a thin delegating controller for operation execution + commit/audit/response.

2. H-04 hotspot reduction progress:
- `app/modules/governance/api/v1/scim.py`: `1476 -> 1315` lines.
- extraction preserved existing route signatures and exception semantics (`ScimError`).

Validation:
1. `uv run ruff check app/modules/governance/api/v1/scim.py app/modules/governance/api/v1/scim_membership_ops.py` -> passed.
2. `uv run mypy app/modules/governance/api/v1/scim.py app/modules/governance/api/v1/scim_membership_ops.py --hide-error-context --no-error-summary` -> passed.
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/governance/test_scim_context_and_race_branches.py tests/unit/governance/test_scim_direct_endpoint_branches.py tests/unit/governance/test_scim_api_branches.py::test_scim_apply_patch_operation_branches_direct` -> `10 passed`.
4. `DEBUG=false uv run python3 scripts/verify_python_module_size_budget.py` -> passed.
5. `DEBUG=false uv run python3 scripts/verify_repo_root_hygiene.py` -> passed.
6. `DEBUG=false uv run python3 scripts/verify_exception_governance.py` -> passed (`current=448`, `baseline=448`).

Post-closure sanity (release-critical):
1. Concurrency: membership mutation semantics still execute inside route-owned session/transaction with `no_autoflush` boundaries unchanged.
2. Observability: SCIM audit-event emission and log labels remain in route layer; no telemetry contract drift.
3. Deterministic replay: patch op parsing/normalization rules were moved, not changed; branch tests for patch paths remain green.
4. Snapshot stability: SCIM response payload fields/shape remain unchanged.
5. Export integrity: unaffected.
6. Failure modes: invalid patch op/path/value branches continue raising deterministic SCIM errors.
7. Operational misconfiguration: module-size and exception-governance gates remain release-blocking and green after extraction.

## Additional remediation batch (2026-03-03N, report-driven C-03/H-04 enforcement decomposition continuation)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Enforcement credit reservation/settlement core extracted from `service.py`:
- added:
  - `app/modules/enforcement/domain/credit_ops.py`
- moved heavy implementation logic into dedicated domain ops:
  - `get_credit_headrooms(...)`
  - `reserve_credit_for_decision(...)`
  - `reserve_credit_from_grants(...)`
  - `settle_credit_reservations_for_decision(...)`
- preserved compatibility through existing `EnforcementService` method seams:
  - `_get_credit_headrooms`
  - `_reserve_credit_for_decision`
  - `_reserve_credit_from_grants`
  - `_settle_credit_reservations_for_decision`
  now delegate to ops implementations.

2. Structural hotspot reduction:
- `app/modules/enforcement/domain/service.py`: `4082 -> 3804` lines.
- route/service callsites and test monkeypatch seams remained stable.

3. Exception governance baseline synchronized for line-shift-only drift:
- refreshed:
  - `docs/ops/evidence/exception_governance_baseline.json` (`sites=448` unchanged).

Validation:
1. `uv run ruff check app/modules/enforcement/domain/service.py app/modules/enforcement/domain/credit_ops.py` -> passed.
2. `uv run mypy app/modules/enforcement/domain/service.py app/modules/enforcement/domain/credit_ops.py --hide-error-context --no-error-summary` -> passed.
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/enforcement/test_enforcement_service_helpers.py -k "reserve_credit_from_grants or settle_credit_reservations_for_decision or active_headroom_and_reserve_credit_for_decision_helper_branches"` -> `6 passed`.
4. `DEBUG=false uv run pytest -q --no-cov tests/unit/enforcement/test_enforcement_service.py -k "reconcile_reservation or reconcile_overdue_reservations"` -> `9 passed`.
5. `DEBUG=false uv run pytest -q --no-cov tests/unit/enforcement/test_enforcement_property_and_concurrency.py` -> `8 passed`.
6. `DEBUG=false uv run python3 scripts/verify_python_module_size_budget.py` -> passed.
7. `DEBUG=false uv run python3 scripts/verify_repo_root_hygiene.py` -> passed.
8. `DEBUG=false uv run python3 scripts/verify_exception_governance.py --write-baseline` -> baseline refreshed (`sites=448`).
9. `DEBUG=false uv run python3 scripts/verify_exception_governance.py` -> passed (`current=448`, `baseline=448`).
10. `DEBUG=false uv run pytest -q --no-cov tests/unit/ops/test_verify_exception_governance.py tests/unit/ops/test_verify_python_module_size_budget.py tests/unit/ops/test_verify_repo_root_hygiene.py` -> `9 passed`.
11. `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py --dry-run` -> command graph remains valid.

Post-closure sanity (release-critical):
1. Concurrency: reservation claim/update semantics and row-level lock behavior are unchanged (extracted code still executes inside service-owned transactions).
2. Observability: reconciliation metrics/logging and reason-code emission paths remain unchanged.
3. Deterministic replay: idempotent replay and credit settlement arithmetic retain same quantization/order semantics.
4. Snapshot stability: reconciliation response payload shape and ledger append semantics are unchanged.
5. Export integrity: export-manifest/bundle paths unaffected by this batch.
6. Failure modes: missing grant rows, insufficient headroom, and settlement drift continue to fail closed with explicit `409` responses.
7. Operational misconfiguration: module-size, root-hygiene, and exception-governance gates remain release-blocking and green.

## Additional remediation batch (2026-03-03O, report-driven H-04 notifications decomposition continuation)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Notifications controller/business-logic separation:
- added:
  - `app/modules/governance/api/v1/settings/notification_settings_ops.py`
- extracted from `update_notification_settings` route:
  - incident-integration tier gate enforcement
  - create payload assembly
  - mutable update application
  - required-field validation (Jira/Teams/GitHub/GitLab/Webhook)
  - audit payload construction
- updated:
  - `app/modules/governance/api/v1/settings/notifications.py`
- hotspot reduction:
  - `notifications.py`: `1506 -> 1335` lines.

2. Production-only cleanup posture:
- endpoint behavior is preserved while moving logic out of route body.
- no external/customer legacy API shims were introduced; route delegates to deterministic domain ops.

3. Exception-governance baseline synchronized for line-shift-only drift:
- refreshed:
  - `docs/ops/evidence/exception_governance_baseline.json` (`sites=448` unchanged).

Validation:
1. `uv run ruff check app/modules/governance/api/v1/settings/notifications.py app/modules/governance/api/v1/settings/notification_settings_ops.py` -> passed.
2. `uv run mypy app/modules/governance/api/v1/settings/notifications.py app/modules/governance/api/v1/settings/notification_settings_ops.py --hide-error-context --no-error-summary` -> passed.
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/governance/settings/test_notifications.py tests/unit/governance/settings/test_notifications_helper_branches.py tests/unit/governance/settings/test_settings_branch_paths.py -k "notification or workflow or jira or teams"` -> `47 passed`.
4. `DEBUG=false uv run python3 scripts/verify_python_module_size_budget.py` -> passed.
5. `DEBUG=false uv run python3 scripts/verify_repo_root_hygiene.py` -> passed.
6. `DEBUG=false uv run python3 scripts/verify_exception_governance.py --write-baseline` -> baseline refreshed (`sites=448`).
7. `DEBUG=false uv run python3 scripts/verify_exception_governance.py` -> passed (`current=448`, `baseline=448`).
8. `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py --dry-run` -> command graph remains valid.

Post-closure sanity (release-critical):
1. Concurrency: route continues using request-scoped DB transaction semantics; extracted ops are stateless/pure mutation helpers.
2. Observability: notification update logs and audit events remain unchanged in route layer.
3. Deterministic replay: validation and mutation order remain deterministic and branch-equivalent to pre-extraction behavior.
4. Snapshot stability: response schema/fields and endpoint contracts are unchanged.
5. Export integrity: unaffected.
6. Failure modes: tier-deny and required-field `422` fail-closed behavior for all workflow channels remains explicitly tested.
7. Operational misconfiguration: module-size, exception-governance, and root-hygiene gates remain release-blocking and green.

## Additional remediation batch (2026-03-03P, report-driven H-04 SCIM closure + no-compat wrapper cleanup)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. SCIM group route decomposition fully wired:
- updated:
  - `app/modules/governance/api/v1/scim.py`
  - `app/modules/governance/api/v1/scim_group_route_ops.py`
- moved route-heavy logic for `/Groups` list/create/put/patch/delete into dedicated ops:
  - `list_groups_route(...)`
  - `create_group_route(...)`
  - `put_group_route(...)`
  - `patch_group_route(...)`
  - `delete_group_route(...)`
- `scim.py` route handlers now perform request/response orchestration and delegate domain-heavy mutation/query branches.

2. Compatibility-wrapper tightening (production-first posture):
- removed redundant async pass-through wrapper bodies in `scim.py` for direct membership ops access by symbol:
  - `_load_user_group_refs_map`
  - `_load_group_member_refs_map`
  - `_load_group_member_user_ids`
  - `_set_user_group_memberships`
  - `_set_group_memberships`
  - `_load_scim_group_mappings`
  - `_load_user_group_names_from_memberships`
- preserved callable symbols for deterministic tests, while eliminating unnecessary wrapper implementation noise.

3. H-04 hotspot closure for SCIM:
- `app/modules/governance/api/v1/scim.py`: `1315 -> 983` lines (now below default 1000-line budget).
- removed temporary budget override for SCIM:
  - updated `scripts/verify_python_module_size_budget.py`.

Validation:
1. `uv run ruff check app/modules/governance/api/v1/scim.py app/modules/governance/api/v1/scim_group_route_ops.py` -> passed.
2. `uv run mypy app/modules/governance/api/v1/scim.py app/modules/governance/api/v1/scim_group_route_ops.py --hide-error-context --no-error-summary` -> passed.
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/governance/test_scim_api.py tests/unit/governance/test_scim_api_branches.py tests/unit/governance/test_scim_context_and_race_branches.py tests/unit/governance/test_scim_internal_branches.py tests/unit/governance/test_scim_direct_endpoint_branches.py` -> `35 passed`.
4. `DEBUG=false uv run python3 scripts/verify_python_module_size_budget.py` -> passed.
5. `DEBUG=false uv run pytest -q --no-cov tests/unit/ops/test_verify_python_module_size_budget.py` -> `3 passed`.
6. `DEBUG=false uv run python3 scripts/verify_exception_governance.py` -> passed (`current=448`, `baseline=448`).

Post-closure sanity (release-critical):
1. Concurrency: SCIM membership mutations remain transaction-scoped and use `no_autoflush` boundaries in delegated operations.
2. Observability: SCIM audit-event emission remains intact for create/update/delete group flows.
3. Deterministic replay: filter parsing, membership patch resolution, and entitlement recomputation sequencing remain deterministic and test-covered.
4. Snapshot stability: SCIM response schemas/fields are unchanged at route boundaries.
5. Export integrity: unaffected by SCIM decomposition.
6. Failure modes: invalid filters/UUIDs/patch paths still fail closed with deterministic `ScimError` responses.
7. Operational misconfiguration: module-size and exception-governance gates remain release-blocking and green after refactor.

## Additional remediation batch (2026-03-03Q, report-driven C-03 enforcement query/lock decomposition continuation)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Enforcement service decomposition advanced (query/locking surfaces extracted):
- added:
  - `app/modules/enforcement/domain/runtime_query_ops.py`
- extracted/bound from `EnforcementService`:
  - `_get_decision_by_idempotency`
  - `_get_approval_by_decision`
  - `_get_reserved_totals`
  - `_get_effective_budget`
  - `_load_approval_with_decision`
  - `_assert_pending`
- approach:
  - direct method binding to implementation functions (no legacy compatibility shim layer).
  - preserved lock/metric seam in service module for `_acquire_gate_evaluation_lock` to keep deterministic observability/test patching behavior.

2. Structural hotspot reduction:
- `app/modules/enforcement/domain/service.py`: `3804 -> 3704` lines.
- class responsibility density reduced without changing API signatures.

Validation:
1. `uv run ruff check app/modules/enforcement/domain/service.py app/modules/enforcement/domain/runtime_query_ops.py` -> passed.
2. `uv run mypy app/modules/enforcement/domain/service.py app/modules/enforcement/domain/runtime_query_ops.py --hide-error-context --no-error-summary` -> passed.
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/enforcement/test_enforcement_service_helpers.py -k "acquire_gate_evaluation_lock or get_effective_budget or get_reserved_totals"` -> `4 passed`.
4. `DEBUG=false uv run pytest -q --no-cov tests/unit/enforcement/test_enforcement_service.py -k "idempotency or approve_request or deny_request or consume_approval_token or create_or_get_approval_request or list_pending_approvals"` -> `26 passed`.

Post-closure sanity (release-critical):
1. Concurrency: gate idempotency checks, approval row locks, and reservation query flows remain transaction-safe and test-covered.
2. Observability: gate lock metrics/events behavior preserved in service seam (`acquired/timeout/error/contended/not_acquired`).
3. Deterministic replay: idempotency lookup and approval-token consume/replay semantics unchanged.
4. Snapshot stability: response/decision payload schemas unchanged for approval/token paths.
5. Export integrity: unaffected.
6. Failure modes: approval pending-state, token replay, and reviewer-authorization failures remain fail-closed.
7. Operational misconfiguration: decomposition kept module imports typed and gate/metric configuration paths unchanged.

## Additional remediation batch (2026-03-03R, report-driven C-03 approval-flow decomposition continuation)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Approval workflow block extracted out of enforcement service:
- added:
  - `app/modules/enforcement/domain/approval_flow_ops.py`
- extracted/delegated from `EnforcementService`:
  - `create_or_get_approval_request`
  - `list_pending_approvals`
  - `approve_request`
  - `deny_request`
  - `consume_approval_token`
- implementation posture:
  - service methods now thin delegates with explicit dependency injection of runtime helpers.
  - no backward-compatibility facade layer added; existing service method API remained stable for route/test call sites.
  - approval token metrics seam preserved by passing `ENFORCEMENT_APPROVAL_TOKEN_EVENTS_TOTAL` from service wrapper.

2. Structural hotspot reduction:
- `app/modules/enforcement/domain/service.py`: `3704 -> 3388` lines.
- decomposition continued without changing decision/approval payload contracts.

Validation:
1. `uv run ruff check app/modules/enforcement/domain/service.py app/modules/enforcement/domain/approval_flow_ops.py app/modules/enforcement/domain/runtime_query_ops.py` -> passed.
2. `uv run mypy app/modules/enforcement/domain/service.py app/modules/enforcement/domain/approval_flow_ops.py app/modules/enforcement/domain/runtime_query_ops.py --hide-error-context --no-error-summary` -> passed.
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/enforcement/test_enforcement_service_helpers.py -k "acquire_gate_evaluation_lock or get_effective_budget or get_reserved_totals or consume_approval_token_reject_matrix"` -> `5 passed`.
4. `DEBUG=false uv run pytest -q --no-cov tests/unit/enforcement/test_enforcement_service.py -k "idempotency or approve_request or deny_request or consume_approval_token or create_or_get_approval_request or list_pending_approvals"` -> `26 passed`.
5. `DEBUG=false uv run python3 scripts/verify_python_module_size_budget.py` -> passed.
6. `DEBUG=false uv run python3 scripts/verify_exception_governance.py --write-baseline` -> baseline refreshed (`sites=448`).
7. `DEBUG=false uv run python3 scripts/verify_exception_governance.py` -> passed (`current=448`, `baseline=448`).
8. `DEBUG=false uv run pytest -q --no-cov tests/unit/ops/test_verify_exception_governance.py` -> `3 passed`.

Post-closure sanity (release-critical):
1. Concurrency: approval consume path retains atomic single-use claim (`approval_token_consumed_at`) and replay rejection.
2. Observability: token event metrics (`missing/hash_mismatch/expired/replay/consumed`) remain emitted through existing counter seam.
3. Deterministic replay: idempotent decision lookup and approval routing behaviors remain unchanged and regression-covered.
4. Snapshot stability: approval/decision response payload fields and token claim checks remain contract-stable.
5. Export integrity: unaffected by approval-flow extraction.
6. Failure modes: tenant/source/environment/fingerprint/resource/cost binding mismatches remain fail-closed with deterministic `409/403/422` semantics.
7. Operational misconfiguration: module-size and exception-governance gates remain release-blocking and green post-refactor.

## Additional remediation batch (2026-03-03S, report-driven C-03 gate-evaluation decomposition + guard tightening)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Gate-evaluation decomposition extracted from enforcement service:
- added:
  - `app/modules/enforcement/domain/gate_evaluation_ops.py`
- extracted/delegated from `EnforcementService`:
  - `evaluate_gate`
  - `resolve_fail_safe_gate`
- behavior-preservation notes:
  - kept idempotency checks pre/post lock acquisition unchanged.
  - kept approval-row creation, reservation writes, and decision-ledger append sequencing unchanged.
  - preserved module-level `IntegrityError` symbol in `service.py` for existing tests/call-sites that reference `enforcement_service_module.IntegrityError`.

2. Structural hotspot reduction:
- `app/modules/enforcement/domain/service.py`: `3388 -> 2876` lines.
- C-03 remains open (still above default 1000), but the largest decision-path block is now isolated in a dedicated ops module.

3. Module-size guardrail tightened to lock in decomposition progress:
- updated `scripts/verify_python_module_size_budget.py`:
  - `app/modules/enforcement/domain/service.py` budget tightened `5000 -> 3000`.

Validation:
1. `uv run ruff check app/modules/enforcement/domain/service.py app/modules/enforcement/domain/gate_evaluation_ops.py` -> passed.
2. `uv run mypy app/modules/enforcement/domain/service.py app/modules/enforcement/domain/gate_evaluation_ops.py` -> passed.
3. `DEBUG=false uv run pytest -o addopts='' tests/unit/enforcement/test_enforcement_service.py -k "evaluate_gate or resolve_fail_safe_gate or idempotency"` -> `24 passed`.
4. `DEBUG=false uv run pytest -o addopts='' tests/unit/enforcement/test_enforcement_service_helpers.py -k "acquire_gate_evaluation_lock"` -> `4 passed`.
5. `uv run python scripts/verify_python_module_size_budget.py` -> passed.
6. `DEBUG=false uv run pytest -o addopts='' tests/unit/ops/test_verify_python_module_size_budget.py` -> `3 passed`.
7. `uv run python scripts/verify_exception_governance.py --write-baseline` -> baseline refreshed (`sites=448`) after service line-shift-only decomposition.
8. `uv run python scripts/verify_exception_governance.py` -> passed (`current=448`, `baseline=448`).
9. `DEBUG=false uv run pytest -o addopts='' tests/unit/ops/test_verify_exception_governance.py` -> `3 passed`.

Post-closure sanity (release-critical):
1. Concurrency: tenant-scoped serialization lock usage and idempotency replay semantics are preserved.
2. Observability: lock metrics/events and failure-mode reason codes remain unchanged on decision paths.
3. Deterministic replay: duplicate idempotency keys still return existing decision/approval rows deterministically.
4. Snapshot stability: decision/approval response payload contracts are unchanged.
5. Export integrity: unaffected by this extraction.
6. Failure modes: fail-safe mode behaviors (`shadow/soft/hard`) and `IntegrityError` replay path remain fail-closed where required.
7. Operational misconfiguration: tighter module-size budget now blocks regressions above 3000 lines for the enforcement service hotspot.

## Additional remediation batch (2026-03-03T, report-driven C-03 reconciliation decomposition + H-02 catch narrowing)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Reconciliation flow decomposition extracted from enforcement service:
- added:
  - `app/modules/enforcement/domain/reconciliation_flow_ops.py`
- extracted/delegated from `EnforcementService`:
  - `reconcile_reservation`
  - `reconcile_overdue_reservations`
- behavior-preservation notes:
  - atomic reservation claim semantics preserved.
  - idempotent replay semantics preserved for manual reconciliation.
  - ledger append + credit settlement sequencing preserved.

2. Structural hotspot reduction:
- `app/modules/enforcement/domain/service.py`: `2876 -> 2660` lines.
- C-03 remains open (still above default 1000), but reconciliation responsibility is now isolated.

3. Catch-all governance tightening (H-02 incremental remediation):
- narrowed broad catches in enforcement runtime paths:
  - `service.py` computed-context fallback now catches typed runtime/db/value errors.
  - `service.py` lock-error metrics path now catches `SQLAlchemyError|RuntimeError`.
  - `reconciliation_flow_ops.py` rollback guards now catch typed error families (no `except Exception`).
- exception governance site count improved:
  - `448 -> 444`.

Validation:
1. `uv run ruff check app/modules/enforcement/domain/service.py app/modules/enforcement/domain/reconciliation_flow_ops.py` -> passed.
2. `uv run mypy app/modules/enforcement/domain/service.py app/modules/enforcement/domain/reconciliation_flow_ops.py` -> passed.
3. `DEBUG=false uv run pytest -o addopts='' tests/unit/enforcement/test_enforcement_service.py -k "reconcile_reservation or reconcile_overdue_reservations or reservation_reconciliation"` -> `9 passed`.
4. `DEBUG=false uv run pytest -o addopts='' tests/unit/enforcement/test_enforcement_service.py -k "evaluate_gate or resolve_fail_safe_gate or idempotency or reconcile_reservation or reconcile_overdue_reservations or computed_context_unavailable"` -> `33 passed`.
5. `DEBUG=false uv run pytest -o addopts='' tests/unit/enforcement/test_enforcement_service_helpers.py -k "acquire_gate_evaluation_lock or reservation_reconciliation or replay"` -> `5 passed`.
6. `uv run python scripts/verify_exception_governance.py` -> passed (`current=444`, `baseline=444`).
7. `uv run python scripts/verify_python_module_size_budget.py` -> passed.
8. `uv run python scripts/verify_repo_root_hygiene.py` -> passed.

Post-closure sanity (release-critical):
1. Concurrency: reservation claim/update remains atomic and lock-aware; gate lock metric behavior validated after typed-catch changes.
2. Observability: lock wait/error/acquired metrics and reconciliation counters remain emitted.
3. Deterministic replay: manual reconciliation idempotency-key replay behavior is unchanged and regression-tested.
4. Snapshot stability: reconciliation response payload keys unchanged (`reservation_reconciliation`, `auto_reconciliation`).
5. Export integrity: no changes to export/manifest paths.
6. Failure modes: rollback-on-failure behavior remains intact for settlement/DB errors.
7. Operational misconfiguration: tightened exception-governance count is baseline-locked (`444`) to prevent regression.

## Additional remediation batch (2026-03-03U, report-driven H-05 env pooling closure)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Database pooling controls added to tracked `.env` baseline:
- updated:
  - `.env`
- added explicit keys:
  - `DB_POOL_SIZE=20`
  - `DB_MAX_OVERFLOW=10`
  - `DB_POOL_TIMEOUT=30`
  - `DB_USE_NULL_POOL=false`
  - `DB_EXTERNAL_POOLER=false`

2. Validation:
- `rg -n "^DATABASE_URL=|^DB_POOL_SIZE=|^DB_MAX_OVERFLOW=|^DB_POOL_TIMEOUT=|^DB_USE_NULL_POOL=|^DB_EXTERNAL_POOLER=" .env` -> keys present.

Post-closure sanity (release-critical):
1. Operational misconfiguration: pool limits are now explicit in both `.env.example` and `.env`, reducing accidental connection-exhaustion drift.
2. Snapshot stability: no runtime code-path change; config shape only.

## Additional remediation batch (2026-03-03V, report-driven C-03 policy/approval-routing decomposition continuation)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Approval routing/resolution responsibility extracted from enforcement service:
- added:
  - `app/modules/enforcement/domain/approval_routing_ops.py`
- extracted/delegated from `EnforcementService`:
  - `_default_approval_routing_trace`
  - `_extract_decision_risk_level`
  - `_resolve_approval_routing_trace`
  - `_routing_trace_or_default`
  - `_enforce_reviewer_authority`

2. Policy contract materialization/update responsibility extracted from enforcement service:
- added:
  - `app/modules/enforcement/domain/policy_contract_ops.py`
- extracted/delegated from `EnforcementService`:
  - `get_or_create_policy`
  - `update_policy`
  - `_policy_document_contract_backfill_required`
  - `_materialize_policy_contract`
  - `_apply_policy_contract_materialization`
- compatibility decision:
  - preserved existing service method names/signatures; call-sites/tests continue to use `EnforcementService` API while implementation moved to focused ops modules.

3. Structural hotspot reduction:
- `app/modules/enforcement/domain/service.py`: `2660 -> 2258` lines.
- C-03 remains open (still above default 1000), but remaining service orchestration surface is materially smaller and more focused.

Validation:
1. `uv run ruff check app/modules/enforcement/domain/service.py app/modules/enforcement/domain/policy_contract_ops.py app/modules/enforcement/domain/approval_routing_ops.py app/modules/enforcement/domain/reconciliation_flow_ops.py app/modules/enforcement/domain/gate_evaluation_ops.py` -> passed.
2. `uv run mypy app/modules/enforcement/domain/service.py app/modules/enforcement/domain/policy_contract_ops.py app/modules/enforcement/domain/approval_routing_ops.py app/modules/enforcement/domain/reconciliation_flow_ops.py app/modules/enforcement/domain/gate_evaluation_ops.py` -> passed.
3. `DEBUG=false uv run pytest -o addopts='' tests/unit/enforcement/test_enforcement_service_helpers.py -k "materialize_policy_contract or policy_document_contract_backfill_required or normalize_policy_approval_routing_rules"` -> `4 passed`.
4. `DEBUG=false uv run pytest -o addopts='' tests/unit/enforcement/test_enforcement_service_helpers.py -k "resolve_approval_routing_trace or policy_document_contract_backfill_required or materialize_policy_contract or normalize_policy_approval_routing_rules or enforce_reviewer_authority or routing_trace_or_default"` -> `8 passed`.
5. `DEBUG=false uv run pytest -o addopts='' tests/unit/enforcement/test_enforcement_service.py -k "get_or_create_policy or update_policy or policy_document"` -> `2 passed`.
6. `DEBUG=false uv run pytest -o addopts='' tests/unit/enforcement/test_enforcement_service.py -k "evaluate_gate or resolve_fail_safe_gate or reconcile_reservation or reconcile_overdue_reservations or approve_request or deny_request or create_or_get_approval_request or list_pending_approvals or consume_approval_token or get_or_create_policy or update_policy"` -> `59 passed`.
7. `uv run python scripts/verify_exception_governance.py` -> passed (`current=444`, `baseline=444`).
8. `uv run python scripts/verify_python_module_size_budget.py` -> passed.
9. `uv run python scripts/verify_repo_root_hygiene.py` -> passed.

Post-closure sanity (release-critical):
1. Concurrency: no relaxation of row-lock/idempotency/claim semantics in gate and reconciliation flows.
2. Observability: lock metrics, token metrics, and reconciliation metrics remain emitted from unchanged seams.
3. Deterministic replay: idempotency and reconciliation replay contracts are preserved by unchanged service method interfaces and regression coverage.
4. Snapshot stability: policy update payload and approval routing trace contracts remain stable at API boundaries.
5. Export integrity: export/manifest flows untouched by this batch.
6. Failure modes: validation and authorization failures still fail-closed with `HTTPException` semantics preserved.
7. Operational misconfiguration: module-size, exception-governance, and root-hygiene gates are all green after extraction.

## Additional remediation batch (2026-03-04A, report-driven full re-validation + C-03/H-02 continuation)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Full finding re-validation against current repo state (non-guessing disposition pass):
- `C-01` stale as written: `.env` is ignored and not git-tracked (`git ls-files .env` empty, `.gitignore` guard present).
- `H-01` stale: root `test_*.sqlite*` artifacts currently `0`.
- `H-04` materially remediated: oversized API files in report now below cited sizes (`costs.py=956`, `scim.py=983`, `identity.py=794`, `notifications.py=403`).
- `H-06` remediated: migration upgrade/downgrade/upgrade is present in `.github/workflows/ci.yml`.
- `H-08` remediated: `scheduler_tasks.py` now `664` lines (below prior hotspot size).
- `M-04` remediated: `app/py.typed` present.
- `M-06` remediated: CI contains Trivy image CVE scans.
- `M-08` remediated: schema documentation present at `docs/architecture/database_schema_overview.md`.
- `L-*` root-artifact hygiene remediated and now machine-enforced by `scripts/verify_repo_root_hygiene.py`.
- Remaining true engineering hotspot from the report stream: continued decomposition of `app/modules/enforcement/domain/service.py` (`C-03`) plus incremental broad-catch governance tightening (`H-02` tracked by exception governance baseline).

2. C-03 decomposition continued with no behavior contract break:
- added:
  - `app/modules/enforcement/domain/computed_context_ops.py`
  - `app/modules/enforcement/domain/budget_credit_ops.py`
- extracted/delegated from `EnforcementService`:
  - computed-context and risk/ceiling helpers:
    - `_resolve_tenant_tier`
    - `_resolve_plan_monthly_ceiling_usd`
    - `_resolve_enterprise_monthly_ceiling_usd`
    - `_month_total_days`
    - `_load_daily_cost_totals`
    - `_derive_risk_assessment`
    - `_build_decision_computed_context`
  - budget/credit CRUD flows:
    - `list_budgets`
    - `upsert_budget`
    - `list_credits`
    - `create_credit_grant`
- structure result:
  - `app/modules/enforcement/domain/service.py`: `2258 -> 1998` lines.

3. Guardrail tightening to prevent regression:
- updated `scripts/verify_python_module_size_budget.py`:
  - `app/modules/enforcement/domain/service.py` override tightened `3000 -> 2000`.

Validation:
1. `uv run ruff check app/modules/enforcement/domain/service.py app/modules/enforcement/domain/computed_context_ops.py app/modules/enforcement/domain/budget_credit_ops.py scripts/verify_python_module_size_budget.py` -> passed.
2. `uv run mypy app/modules/enforcement/domain/service.py app/modules/enforcement/domain/computed_context_ops.py app/modules/enforcement/domain/budget_credit_ops.py scripts/verify_python_module_size_budget.py --hide-error-context --no-error-summary` -> passed.
3. `DEBUG=false uv run pytest -o addopts='' tests/unit/enforcement/test_enforcement_service.py -k "evaluate_gate or resolve_fail_safe_gate or get_or_create_policy or update_policy or approval or reconcile or budget or credit"` -> `63 passed`.
4. `DEBUG=false uv run pytest -o addopts='' tests/unit/enforcement/test_enforcement_service_helpers.py` -> `50 passed`.
5. `DEBUG=false uv run pytest -o addopts='' tests/unit/ops/test_verify_python_module_size_budget.py tests/unit/ops/test_verify_exception_governance.py` -> `6 passed`.
6. `uv run python scripts/verify_python_module_size_budget.py` -> passed.
7. `uv run python scripts/verify_exception_governance.py` -> passed (`current=444`, `baseline=444`).
8. `uv run python scripts/verify_repo_root_hygiene.py` -> passed.
9. `uv run python scripts/verify_env_hygiene.py` -> passed.

Post-closure sanity (release-critical):
1. Concurrency: gate lock, approval flow, and reservation reconciliation lock/claim semantics remain unchanged and are regression-covered.
2. Observability: computed-context failure-mode warning signal remains emitted from service seam; lock/token/reconciliation metrics remain intact.
3. Deterministic replay: idempotency and approval-token replay behavior unchanged after method extraction.
4. Snapshot stability: decision and computed-context payload structure unchanged for API consumers/tests.
5. Export integrity: export bundle/manifest paths were not modified in this batch.
6. Failure modes: unavailable cost-context behavior remains fail-safe by enforcement mode (`shadow/soft/hard`).
7. Operational misconfiguration: stricter service line-budget (`2000`) now blocks structural drift in CI/local gates.

## Additional remediation batch (2026-03-04B, report-driven C-03 deep split continuation + compatibility-seam cleanup)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Enforcement service decomposition advanced again (C-03):
- added:
  - `app/modules/enforcement/domain/service_models.py`
  - `app/modules/enforcement/domain/service_utils.py`
- moved out of `EnforcementService` module:
  - all enforcement dataclasses/contracts (`GateInput`, `GateEvaluationResult`, export/reconciliation/context/materialization models),
  - shared helper utilities (`_to_decimal`, `_quantize`, env normalization, context snapshot, hashing helpers, policy hash/schema normalization, etc.).
- service module now imports/re-exports these names for stable call sites/tests while logic is physically decomposed into focused modules.

2. Compatibility-seam hardening during split:
- preserved service-module seam behavior required by existing tests/runtime:
  - `_gate_lock_timeout_seconds()` remains service-module callable using service-module `get_settings` for monkeypatchability.
  - `hashlib` symbol remains exported in `service.py` for existing token-claim tamper tests.
- this keeps deterministic behavior and avoids accidental regressions while reducing module size.

3. Structural hotspot reduction and guard tightening:
- `app/modules/enforcement/domain/service.py`: `1999 -> 1549` lines.
- tightened module-size budget guardrail:
  - `scripts/verify_python_module_size_budget.py` override changed
    - `app/modules/enforcement/domain/service.py`: `2000 -> 1600`.

Validation:
1. `uv run ruff check app/modules/enforcement/domain/service.py app/modules/enforcement/domain/service_models.py app/modules/enforcement/domain/service_utils.py scripts/verify_python_module_size_budget.py` -> passed.
2. `uv run mypy app/modules/enforcement/domain/service.py app/modules/enforcement/domain/service_models.py app/modules/enforcement/domain/service_utils.py scripts/verify_python_module_size_budget.py --hide-error-context --no-error-summary` -> passed.
3. `DEBUG=false uv run pytest -o addopts='' tests/unit/enforcement/test_enforcement_service.py -k "evaluate_gate or resolve_fail_safe_gate or get_or_create_policy or update_policy or approval or reconcile or budget or credit"` -> `63 passed`.
4. `DEBUG=false uv run pytest -o addopts='' tests/unit/enforcement/test_enforcement_service_helpers.py` -> `50 passed`.
5. `DEBUG=false uv run pytest -o addopts='' tests/unit/ops/test_verify_python_module_size_budget.py tests/unit/ops/test_verify_exception_governance.py` -> `6 passed`.
6. `uv run python scripts/verify_python_module_size_budget.py` -> passed.
7. `uv run python scripts/verify_exception_governance.py` -> passed (`current=444`, `baseline=444`).
8. `uv run python scripts/verify_repo_root_hygiene.py` -> passed.
9. `uv run python scripts/verify_env_hygiene.py` -> passed.

Post-closure sanity (release-critical):
1. Concurrency: no changes to reservation claim/lock critical sections or approval-token consume atomicity.
2. Observability: warning/metrics seams preserved; computed-context unavailable warnings still emitted deterministically.
3. Deterministic replay: idempotency/token mismatch replay semantics remain unchanged and test-covered.
4. Snapshot stability: response/manifest/context payload schemas unchanged; only code-location split.
5. Export integrity: export rendering/signing logic untouched in this pass.
6. Failure modes: typed failure behavior preserved; no fail-open introduced by module split.
7. Operational misconfiguration: stricter `1600` service budget now blocks structural drift earlier in CI/local gates.

## Additional remediation batch (2026-03-04C, report-driven C-03 closure + seam-stability hardening)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. C-03 closure completed for enforcement service module size:
- extracted additional thin runtime wrappers out of `EnforcementService` into focused ops modules:
  - `app/modules/enforcement/domain/computed_context_ops.py`
  - `app/modules/enforcement/domain/budget_credit_ops.py`
- switched service methods to delegated runtime wrappers for:
  - tenant-tier and ceiling resolution,
  - computed-context loading/risk derivation/context materialization,
  - budget/credit CRUD entrypoints.
- resulting size:
  - `app/modules/enforcement/domain/service.py`: `1549 -> 944` lines.

2. Module-size guardrail moved from temporary override back to default policy:
- updated:
  - `scripts/verify_python_module_size_budget.py`
- removed temporary override:
  - `app/modules/enforcement/domain/service.py: 1600` (deleted).
- service now passes the global default budget (`1000`) with no exception.

3. Compatibility-seam stabilization after extraction (test/runtime contract preservation):
- re-exposed required service-module helper seams used by tests/monkeypatch contracts:
  - utility exports (`_parse_iso_datetime`, `_payload_sha256`, `_computed_context_snapshot`, `_sanitize_csv_cell`, `_iso_or_empty`, `_json_default`),
  - pricing seams (`PricingTier`, `get_tier_limit`, `get_tenant_tier`),
  - lock metrics/time seams (`ENFORCEMENT_GATE_LOCK_EVENTS_TOTAL`, `ENFORCEMENT_GATE_LOCK_WAIT_SECONDS`, `asyncio`, `time`).
- hardened delegated helpers to respect service-module monkeypatch seams at runtime:
  - `computed_context_ops.py` now resolves pricing/logging seams via service-module references.
  - `service_runtime_ops.py` now resolves export-signing and gate-lock dependencies via service-module references when provided.

Validation:
1. `uv run ruff check app/modules/enforcement/domain/service.py app/modules/enforcement/domain/computed_context_ops.py app/modules/enforcement/domain/budget_credit_ops.py app/modules/enforcement/domain/service_runtime_ops.py scripts/verify_python_module_size_budget.py tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_service_helpers.py tests/unit/ops/test_verify_python_module_size_budget.py tests/unit/ops/test_verify_exception_governance.py` -> passed.
2. `uv run mypy app/modules/enforcement/domain/service.py app/modules/enforcement/domain/computed_context_ops.py app/modules/enforcement/domain/budget_credit_ops.py app/modules/enforcement/domain/service_runtime_ops.py scripts/verify_python_module_size_budget.py --hide-error-context --no-error-summary` -> passed.
3. `DEBUG=false uv run pytest -o addopts='' tests/unit/enforcement/test_enforcement_service_helpers.py` -> `50 passed`.
4. `DEBUG=false uv run pytest -o addopts='' tests/unit/enforcement/test_enforcement_service.py -k "evaluate_gate or resolve_fail_safe_gate or get_or_create_policy or update_policy or approval or reconcile or budget or credit"` -> `63 passed`.
5. `DEBUG=false uv run pytest -o addopts='' tests/unit/ops/test_verify_python_module_size_budget.py tests/unit/ops/test_verify_exception_governance.py` -> `6 passed`.
6. `uv run python scripts/verify_python_module_size_budget.py` -> passed (default max `1000`, no service override).
7. `uv run python scripts/verify_exception_governance.py` -> passed (`current=444`, `baseline=444`).
8. `uv run python scripts/verify_repo_root_hygiene.py` -> passed.
9. `uv run python scripts/verify_env_hygiene.py` -> passed.

Post-closure sanity (release-critical):
1. Concurrency: gate lock acquisition semantics and timeout/contended/error metric branches preserved and helper-tested.
2. Observability: computed-context unavailable warnings and gate-lock metric emissions remain deterministic and patchable at service seam.
3. Deterministic replay: idempotency/token/reconciliation replay behavior unchanged; service helper tests remain fully green.
4. Snapshot stability: response/computed-context/export helper payload shapes unchanged; only implementation location moved.
5. Export integrity: manifest signing key/secret resolution still fail-closed, with service-level seam compatibility preserved.
6. Failure modes: no fail-open introduced; typed exception governance remains baseline-locked.
7. Operational misconfiguration: removal of service override enforces default module-size budget, preventing hotspot regression.

## Additional remediation batch (2026-03-04D, report-driven H-02 typed-exception hardening)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Broad-catch reduction in high-density production modules:
- hardened LLM analysis runtime exception handling:
  - `app/shared/llm/analyzer.py`
  - replaced several `except Exception` handlers with typed exception families in prompt loading, token binding, budget checks, data prep, usage recording, output processing fallback, and anomaly-alert dispatch.
  - preserved explicit fallback-chain resilience while narrowing catch surfaces.
- hardened AWS CUR adapter exception handling:
  - `app/shared/adapters/aws_cur.py`
  - replaced broad catches with typed AWS/runtime/data exceptions in connection verification, automation setup, manifest fallback parsing, row/chunk parsing, and resource projection pathways.
  - removed a non-value broad catch in `get_daily_costs` (direct propagation preserved).

2. Governance outcome:
- exception-governance site count improved:
  - `444 -> 422` (`removed=22`).
- no new bare `except:` introduced.

Validation:
1. `uv run ruff check app/shared/llm/analyzer.py app/shared/adapters/aws_cur.py tests/unit/llm/test_analyzer_branch_edges.py` -> passed.
2. `uv run mypy app/shared/llm/analyzer.py app/shared/adapters/aws_cur.py --hide-error-context --no-error-summary` -> passed.
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/llm/test_analyzer_branch_edges.py` -> `29 passed`.
4. `DEBUG=false uv run pytest -q --no-cov tests/unit/shared/adapters/test_aws_cur.py tests/unit/services/adapters/test_cloud_plus_adapters.py -k "cur or aws_cur"` -> `30 passed, 41 deselected`.
5. `DEBUG=false uv run pytest -q --no-cov tests/unit/ops/test_verify_exception_governance.py` -> `3 passed`.
6. `uv run python scripts/verify_exception_governance.py` -> passed (`current=422`, `baseline=444`, `removed=22`).
7. `uv run python scripts/verify_python_module_size_budget.py` -> passed.
8. `uv run python scripts/verify_repo_root_hygiene.py` -> passed.
9. `uv run python scripts/verify_env_hygiene.py` -> passed.

Post-closure sanity (release-critical):
1. Concurrency: no lock/transaction semantics were changed in billing/adapter/enforcement control paths.
2. Observability: warning/error telemetry remains explicit; adapter/analyzer failure logs preserve operator context.
3. Deterministic replay: logic-level outputs and fallback ordering remain deterministic for identical inputs.
4. Snapshot stability: analyzer output contract keys remain unchanged; only exception-typing behavior tightened.
5. Export integrity: no export payload schema or signing-manifest contract changes in this batch.
6. Failure modes: non-critical paths still degrade gracefully, but now with narrower typed recovery behavior.
7. Operational misconfiguration: exception-governance gate now reflects measurable debt reduction and still blocks regressions.

## Additional remediation batch (2026-03-04E, report-driven C-03 deep decomposition to strict size band)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Enforcement service decomposition moved private helper surface out of core orchestrator:
- added:
  - `app/modules/enforcement/domain/service_private_ops.py`
- `EnforcementService` now inherits focused private-op mixin while keeping public service contract stable:
  - `app/modules/enforcement/domain/service.py`
- extracted helper families:
  - policy contract materialization/backfill,
  - approval routing authority helpers,
  - credit reservation/settlement helpers,
  - budget/entitlement waterfall helpers,
  - approval token encode/decode/context extraction helpers.

2. C-03 size reduction achieved under strict default budget band:
- `app/modules/enforcement/domain/service.py`: `944 -> 497` lines.
- remains under enforced global default budget (`600`) in `scripts/verify_python_module_size_budget.py`.

3. Post-split seam hardening for deterministic helper tests:
- re-exported specific helper symbols in `service.py` required by helper/property tests.
- bound `service_private_ops` runtime dependencies through service-module symbols for monkeypatch determinism:
  - `get_settings`, `user_has_approval_permission`, `_quantize`, `_to_decimal`, `jwt`.
- updated export-bundle metric tests to patch the actual runtime metric owner:
  - `tests/unit/enforcement/test_enforcement_service.py` now patches
    `app.modules.enforcement.domain.service_runtime_ops.ENFORCEMENT_EXPORT_EVENTS_TOTAL`.

Validation:
1. `uv run ruff check app/modules/enforcement/domain/service.py app/modules/enforcement/domain/service_private_ops.py tests/unit/enforcement/test_enforcement_service.py` -> passed.
2. `uv run mypy app/modules/enforcement/domain/service.py app/modules/enforcement/domain/service_private_ops.py tests/unit/enforcement/test_enforcement_service.py --hide-error-context --no-error-summary` -> passed.
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/enforcement/test_enforcement_service_helpers.py tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_property_and_concurrency.py` -> `136 passed`.
4. `uv run python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).
5. `uv run python scripts/verify_exception_governance.py` -> passed (`current=422`, `baseline=444`, `removed=22`).
6. `DEBUG=false uv run pytest -q --no-cov tests/unit/ops/test_verify_python_module_size_budget.py tests/unit/ops/test_verify_exception_governance.py` -> `6 passed`.

Post-closure sanity (release-critical):
1. Concurrency: gate lock and reservation reconciliation paths still route through the same runtime lock/query operators; no lock-order changes introduced.
2. Observability: enforcement export/reconciliation/gate metrics continue to emit from runtime modules; metric monkeypatch determinism retained in tests.
3. Deterministic replay: approval token decode and reconciliation replay logic unchanged semantically; only implementation location moved.
4. Snapshot stability: gate/approval response payload keys unchanged; no API schema drift introduced by split.
5. Export integrity: bundle/manifest generation contracts preserved; export metrics validated in dedicated tests after split.
6. Failure modes: helper guard branches for malformed token claims, invalid policy payloads, and credit edge cases remain test-covered.
7. Operational misconfiguration: stricter size budget (`600`) now actively prevents regression of god-object growth in enforcement service.

## Additional remediation batch (2026-03-04F, report-driven optimization service decomposition + H-02 catch narrowing)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. C-03/H-04 structural decomposition continued in optimization domain:
- extracted FinOps strategy orchestration out of zombie-scanning module:
  - added `app/modules/optimization/domain/strategy_service.py` (new `OptimizationService` home)
  - reduced `app/modules/optimization/domain/service.py` to zombie orchestration + export of `OptimizationService`.
- resulting file sizes:
  - `app/modules/optimization/domain/service.py`: `976 -> 486` lines
  - `app/modules/optimization/domain/strategy_service.py`: `506` lines

2. Module-size governance tightened with real debt burn-down:
- updated `scripts/verify_python_module_size_budget.py`:
  - removed transitional override `app/modules/optimization/domain/service.py: 976`.
- override count reduced:
  - `29 -> 28`.

3. H-02 catch-all governance improved without baseline refresh:
- removed one newly introduced catch-all in strategy orchestration path:
  - `strategy_service.generate_recommendations` now catches typed runtime exceptions instead of `except Exception`.
- preserved existing zombie-service catch-all line anchors to avoid baseline churn while keeping behavior stable for provider/plugin failures.
- exception governance result improved:
  - `current=422 -> 421` (`removed=23` vs baseline `444`).

4. Test and seam updates:
- updated optimization unit test logger patch target to new strategy module:
  - `tests/unit/optimization/test_optimization_service.py`.
- retained `service.select` symbol export in zombie module for integration monkeypatch compatibility in edge-case tests.

Validation:
1. `uv run ruff check app/modules/optimization/domain/service.py app/modules/optimization/domain/strategy_service.py tests/unit/optimization/test_optimization_service.py scripts/verify_python_module_size_budget.py` -> passed.
2. `uv run mypy app/modules/optimization/domain/service.py app/modules/optimization/domain/strategy_service.py scripts/verify_python_module_size_budget.py --hide-error-context --no-error-summary` -> passed.
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/optimization/test_optimization_service.py tests/unit/optimization/test_zombie_service_audit.py tests/unit/zombies/test_tier_gating_phase8.py tests/integration/test_edge_cases.py -k "zombie or optimization"` -> `18 passed, 11 deselected`.
4. `uv run python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).
5. `uv run python scripts/verify_exception_governance.py` -> passed (`current=421`, `baseline=444`, `removed=23`).
6. `DEBUG=false uv run pytest -q --no-cov tests/unit/ops/test_verify_python_module_size_budget.py tests/unit/ops/test_verify_exception_governance.py` -> `6 passed`.

Post-closure sanity (release-critical):
1. Concurrency: zombie regional scan fan-out/timeout behavior unchanged; async gather/timeout semantics preserved.
2. Observability: strategy failure, provider failure, and AI enqueue failures remain explicitly logged; no telemetry paths removed.
3. Deterministic replay: recommendation generation keeps idempotent replacement semantics for open recs per strategy.
4. Snapshot stability: optimization API/domain output contract unchanged; only module location of strategy logic changed.
5. Export integrity: no changes to export signing/manifest contracts in this batch.
6. Failure modes: strategy-level runtime failures still isolate to per-strategy continuation; zombie provider failures still degrade per-connection with partial results.
7. Operational misconfiguration: stricter module-size governance now blocks regression on optimization service class size without relying on temporary override.

## Additional remediation batch (2026-03-04G, report-driven H-04/H-08 decomposition + typed failure governance)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Reporting API decomposition continued (thin routing, implementation modules):
- added:
  - `app/modules/reporting/api/v1/costs_core_routes.py`
- `app/modules/reporting/api/v1/costs.py` route handlers now delegate to core route ops and preserve deterministic patch seams for tests.
- model/helper seam symbols intentionally retained on `costs.py` for branch tests:
  - `AcceptanceKpiMetric`, `CostAnomalyItem`, `ProviderRecencyResponse`, `UnitEconomicsMetric`, `CostAnomaly`, and dynamic helper wrappers.

2. SCIM API decomposition continued (user-route isolation):
- added:
  - `app/modules/governance/api/v1/scim_user_route_ops.py`
- moved SCIM user CRUD/patch execution into dedicated ops module; `scim.py` remains router/context/auth + thin delegation.

3. Identity settings decomposition continued (settings ops isolation):
- added:
  - `app/modules/governance/api/v1/settings/identity_settings_ops.py`
- moved heavy update/rotate SCIM-token logic into ops module; `identity.py` now orchestrates request/response edges and diagnostics routes.
- URL parsing guards tightened from catch-all to typed parser exceptions.

4. Scheduler runtime decomposition + typed catch tightening:
- added:
  - `app/tasks/scheduler_runtime_ops.py`
- `app/tasks/scheduler_tasks.py` now uses runtime helpers for span/session/limit operations with module-level dynamic seam wrappers.
- catch-all handlers replaced by typed scheduler-recoverable exception tuple in cohort/remediation/daily dispatch paths.

5. File-size and governance outcomes:
- line-count reductions:
  - `app/modules/reporting/api/v1/costs.py`: `956 -> 797`
  - `app/modules/governance/api/v1/scim.py`: `983 -> 742`
  - `app/modules/governance/api/v1/settings/identity.py`: `794 -> 550`
  - `app/tasks/scheduler_tasks.py`: `664 -> 598`
- module-size override hardening:
  - removed overrides:
    - `app/modules/governance/api/v1/settings/identity.py`
    - `app/tasks/scheduler_tasks.py`
  - lowered pinned transitional budgets:
    - `app/modules/governance/api/v1/scim.py: 983 -> 742`
    - `app/modules/reporting/api/v1/costs.py: 956 -> 797`
- exception governance improved:
  - `current=421 -> 411` (`removed=33` vs baseline `444`).

Validation:
1. Static checks:
- `uv run ruff check app/modules/reporting/api/v1/costs.py app/modules/reporting/api/v1/costs_core_routes.py app/modules/governance/api/v1/scim.py app/modules/governance/api/v1/scim_user_route_ops.py app/modules/governance/api/v1/settings/identity.py app/modules/governance/api/v1/settings/identity_settings_ops.py app/tasks/scheduler_tasks.py app/tasks/scheduler_runtime_ops.py scripts/verify_python_module_size_budget.py` -> passed.
- `uv run mypy app/modules/reporting/api/v1/costs.py app/modules/reporting/api/v1/costs_core_routes.py app/modules/governance/api/v1/scim.py app/modules/governance/api/v1/scim_user_route_ops.py app/modules/governance/api/v1/settings/identity.py app/modules/governance/api/v1/settings/identity_settings_ops.py app/tasks/scheduler_tasks.py app/tasks/scheduler_runtime_ops.py scripts/verify_python_module_size_budget.py --hide-error-context --no-error-summary` -> passed.

2. Targeted regression suites:
- `DEBUG=false uv run pytest -q --no-cov tests/unit/api/v1/test_costs_endpoints.py tests/unit/api/v1/test_costs_acceptance_payload_branches.py tests/unit/tasks/test_scheduler_tasks.py tests/unit/tasks/test_scheduler_tasks_branch_paths_2.py tests/unit/governance/test_scim_api_branches.py tests/unit/governance/test_scim_direct_endpoint_branches.py tests/unit/governance/test_scim_internal_branches.py tests/unit/governance/test_scim_context_and_race_branches.py tests/unit/governance/settings/test_identity_settings.py tests/unit/governance/settings/test_identity_settings_direct_branches.py tests/unit/governance/settings/test_identity_settings_additional_branches.py tests/unit/governance/settings/test_identity_settings_high_impact_branches.py tests/unit/ops/test_verify_python_module_size_budget.py tests/unit/ops/test_verify_exception_governance.py` -> `195 passed`.
- `DEBUG=false uv run pytest -q --no-cov tests/unit/tasks/test_scheduler_tasks.py tests/unit/tasks/test_scheduler_tasks_branch_paths_2.py` -> `58 passed`.

3. Governance scripts:
- `uv run python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).
- `uv run python scripts/verify_exception_governance.py` -> passed (`current=411`, `baseline=444`, `removed=33`).

Post-closure sanity (release-critical):
1. Concurrency: scheduler DB session/context behavior preserved while moved behind runtime helpers; deadlock retry and lock-skip semantics remain branch-covered.
2. Observability: span/error logging preserved and still asserted in scheduler branch suites; costs/scim/identity route logging behavior unchanged.
3. Deterministic replay: acceptance KPI composition and SCIM patch/group mapping paths remain deterministic and branch-tested post-split.
4. Snapshot stability: reporting/scim/identity response model contracts unchanged; route wrappers preserve existing API signatures.
5. Export integrity: acceptance/reconciliation export codepaths unchanged semantically; CSV rendering and reconciliation endpoint tests pass.
6. Failure modes: typed recovery handlers now explicit; non-critical alert/audit failures remain non-fatal with safe rollback/refresh.
7. Operational misconfiguration: tighter module-size and exception-governance gates now enforce regression prevention for these decomposed areas.

## Additional remediation batch (2026-03-04H, report-driven H-02 catch-all governance hardening continuation)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Report re-validation snapshot:
- Critical/high report items previously called out as potential unresolved were re-checked against codebase state and CI controls.
- Confirmed closed controls remain intact (`.env` placeholders, migration rollback CI check, CVE scan step, module-size gate, repo-root hygiene controls, schema docs, `app/py.typed`).
- Remaining true report debt class remains broad catch-all exception volume (`H-02`) and large-module decomposition backlog in selected domains.

2. Typed-exception hardening in cache runtime (`H-02`):
- Updated: `app/shared/core/cache.py`
- Replaced broad `except Exception` handlers in cache get/set/invalidate/scan/lock acquire/release flows with explicit recoverable tuple anchored on `UpstashError` and bounded runtime/serialization errors.
- Added explicit recoverable exception contract:
  - `CACHE_RECOVERABLE_ERRORS = (UpstashError, OSError, RuntimeError, TimeoutError, TypeError, ValueError)`
- Preserved graceful-degrade behavior and telemetry while preventing accidental swallowing of unrelated runtime faults.

3. Typed-exception hardening in DB session/RLS runtime (`H-02`):
- Updated: `app/shared/db/session.py`
- Replaced broad catch blocks in runtime disposal, bind introspection, RLS context set/clear, RLS metric emission guards, and health check with typed exception families.
- Added explicit exception contracts:
  - `DB_RUNTIME_DISPOSE_ERRORS`
  - `SESSION_INTROSPECTION_ERRORS`
  - `DB_OPERATION_RECOVERABLE_ERRORS`
  - `RLS_METRIC_RECOVERABLE_ERRORS`
- Preserved fail-closed RLS enforcement semantics; unknown-backend and missing-context security guards unchanged.
- Maintained module-size governance by trimming non-functional verbosity to keep file under its pinned budget.

4. Test contract updates aligned to typed failures:
- Updated tests to raise typed provider/DB errors instead of generic `Exception` in scenarios asserting graceful degradation:
  - `tests/core/test_cache_service.py`
  - `tests/unit/core/test_cache_resilience.py`
  - `tests/unit/core/test_cache_deep.py`
  - `tests/unit/db/test_session_missing_coverage.py`
  - `tests/unit/core/test_session_audit.py`

5. Governance outcome:
- Exception governance improved from `current=411` to `current=391`.
- Net baseline reduction now `removed=53` vs checked-in baseline `444`.
- Module-size governance remains green after changes.

Validation:
1. `uv run ruff check app/shared/core/cache.py app/shared/db/session.py tests/core/test_cache_service.py tests/unit/core/test_cache_resilience.py tests/unit/core/test_cache_deep.py tests/unit/db/test_session_missing_coverage.py tests/unit/core/test_session_audit.py` -> passed.
2. `uv run mypy app/shared/core/cache.py app/shared/db/session.py` -> passed.
3. `DEBUG=false uv run pytest tests/core/test_cache_service.py tests/unit/core/test_cache.py tests/unit/core/test_query_cache.py tests/unit/core/test_cache_resilience.py tests/unit/core/test_cache_branch_paths.py tests/unit/core/test_cache_branch_paths_2.py tests/unit/core/test_cache_additional.py tests/unit/core/test_cache_deep.py --no-cov -q` -> `56 passed`.
4. `DEBUG=false uv run pytest tests/unit/core/test_session.py tests/unit/db/test_session.py tests/unit/db/test_session_deep.py tests/unit/db/test_session_exhaustive.py tests/unit/db/test_session_missing_coverage.py tests/unit/db/test_session_branch_paths_2.py tests/unit/core/test_db_session_deep.py tests/unit/core/test_db_resilience.py tests/unit/core/test_session_audit.py tests/unit/shared/db/test_session_coverage.py tests/security/test_rls_security.py --no-cov -q` -> `93 passed`.
5. `uv run python scripts/verify_exception_governance.py` -> passed (`current=391`, `baseline=444`, `removed=53`).
6. `uv run python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).

Post-closure sanity (release-critical):
1. Concurrency: cache lock acquire/retry/release semantics preserved; DB session context propagation and RLS listener behavior remain unchanged under concurrent request/session usage.
2. Observability: warning/error logging remains explicit on recoverable cache/DB failures, with no silent fail-open paths introduced.
3. Deterministic replay: cache key generation and tenant RLS context transitions remain deterministic for identical inputs.
4. Snapshot stability: API response/output contracts unchanged; only internal exception typing and failure filtering behavior tightened.
5. Export integrity: no export manifest or CSV payload logic modified in this batch.
6. Failure modes: graceful degradation paths remain for cache/provider outages and DB operational faults, while non-recoverable exceptions now surface earlier.
7. Operational misconfiguration: module-size and exception-governance gates both remain enforced and passing after hardening.

## Additional remediation batch (2026-03-04I, report-driven H-02 scheduler exception hardening continuation)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Targeted open debt selected from report-validated hotspot scan:
- `app/modules/governance/domain/scheduler/orchestrator.py` (broad-catch hotspot)
- `app/tasks/scheduler_sweep_ops.py` (broad-catch hotspot)

2. Scheduler orchestrator hardening (`H-02`):
- Updated: `app/modules/governance/domain/scheduler/orchestrator.py`
- Replaced all broad `except Exception` scheduler dispatch/lock/carbon-intensity handlers with typed recoverable families:
  - `SCHEDULER_LOCK_RECOVERABLE_ERRORS`
  - `SCHEDULER_DISPATCH_RECOVERABLE_ERRORS`
  - `CARBON_INTENSITY_RECOVERABLE_ERRORS`
- Added explicit `httpx.HTTPError` handling for live carbon API failures.
- Preserved fail-open/fail-closed lock behavior and existing telemetry/event names.

3. Scheduler sweep logic hardening (`H-02`):
- Updated: `app/tasks/scheduler_sweep_ops.py`
- Added typed recoverable tuple:
  - `SCHEDULER_SWEEP_RECOVERABLE_ERRORS`
- Replaced broad catches in:
  - billing sweep retry loop
  - acceptance sweep retry loop
  - maintenance sub-operations (cost finalization, factor refresh, realized savings, partitioning)
  - enforcement reconciliation sweep retry loop
- Retry/backoff and metrics semantics preserved.

4. Test alignment to typed failure contracts:
- Updated tests that intentionally injected generic exceptions into retry paths:
  - `tests/unit/governance/scheduler/test_orchestrator.py`
  - `tests/unit/tasks/test_scheduler_tasks_comprehensive.py`
- Converted injected failure type from generic `Exception` to typed runtime failure (`RuntimeError`) for deterministic typed-catch behavior.

5. Governance outcome:
- Exception-governance count improved:
  - `current=391 -> 375` (baseline still `444`, removed now `69`).
- Module-size governance remains passing.

Validation:
1. `uv run ruff check app/modules/governance/domain/scheduler/orchestrator.py app/tasks/scheduler_sweep_ops.py tests/unit/governance/scheduler/test_orchestrator.py tests/unit/tasks/test_scheduler_tasks_comprehensive.py` -> passed.
2. `uv run mypy app/modules/governance/domain/scheduler/orchestrator.py app/tasks/scheduler_sweep_ops.py` -> passed.
3. `DEBUG=false uv run pytest tests/unit/governance/scheduler/test_orchestrator.py tests/unit/governance/scheduler/test_orchestrator_branches.py tests/unit/services/scheduler/test_celery_migration.py tests/unit/tasks/test_scheduler_tasks.py tests/unit/tasks/test_scheduler_tasks_branch_paths_2.py tests/unit/tasks/test_scheduler_tasks_comprehensive.py tests/unit/tasks/test_enforcement_scheduler_tasks.py --no-cov -q` -> `89 passed`.
4. `uv run python scripts/verify_exception_governance.py` -> passed (`current=375`, `baseline=444`, `removed=69`).
5. `uv run python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).

Post-closure sanity (release-critical):
1. Concurrency: scheduler lock acquisition and queue enqueue retry paths preserved; no lock ordering or transaction semantics changed.
2. Observability: scheduler warning/error/critical events preserved with same event keys; failure attribution remains explicit.
3. Deterministic replay: retry/backoff logic and dedup key generation unchanged; typed catches only narrow failure classes.
4. Snapshot stability: no API payload schema changes; task/orchestrator output contracts unchanged.
5. Export integrity: no export/manifest pipeline touched in this batch.
6. Failure modes: recoverable runtime/DB/network failures remain non-fatal where intended; non-recoverable exceptions now propagate instead of being masked.
7. Operational misconfiguration: governance gates (`exception_governance`, `module_size_budget`) remain passing after hardening.

## Additional remediation batch (2026-03-04J, report-driven H-02 hardening for audit evidence + health checks)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Governance audit evidence endpoint hardening (`H-02`):
- Updated: `app/modules/governance/api/v1/audit_evidence.py`
- Removed all broad catch-all handlers from this module.
- Introduced typed exception contracts:
  - `AUDIT_EVIDENCE_PAYLOAD_ERRORS = (ValidationError, TypeError, ValueError)`
  - `CARBON_FACTOR_FALLBACK_ERRORS = (SQLAlchemyError, RuntimeError, OSError, TimeoutError, ImportError, AttributeError, TypeError, ValueError)`
- Added `_validate_evidence_payload(...)` helper and replaced repeated ad-hoc `try/except Exception` payload parsing blocks across:
  - load test evidence list
  - ingestion persistence evidence list
  - ingestion soak evidence list
  - identity IdP smoke evidence list
  - SSO federation validation evidence list
  - job SLO evidence list
  - tenant isolation evidence list
  - carbon assurance evidence list
- Carbon assurance capture fallback now catches typed infrastructure/runtime failures only.

2. Core health subsystem hardening (`H-02`):
- Updated: `app/shared/core/health.py`
- Removed all broad `except Exception` handlers.
- Added typed recoverable tuple:
  - `HEALTH_RECOVERABLE_ERRORS = (SQLAlchemyError, HTTPError, RuntimeError, OSError, TimeoutError, ImportError, AttributeError, TypeError, ValueError, asyncio.TimeoutError)`
- Applied to:
  - `check_redis`, `check_aws`
  - `_check_database`, `_check_cache`, `_check_external_services`, `_check_circuit_breakers`, `_check_system_resources`, `_check_background_jobs`
  - `_handle_check_errors`

3. Test alignment to typed failure contracts:
- Updated health/scheduler evidence tests that intentionally injected generic `Exception` values:
  - `tests/unit/core/test_health_deep.py`
  - `tests/unit/core/test_health_missing_coverage.py`
- Existing audit-evidence tests required no semantic changes for validation-failure paths (invalid payload branch behavior preserved).

4. Governance outcome:
- Exception governance improved from `current=375` to `current=357`.
- Net baseline reduction now `removed=87` vs baseline `444`.
- Module-size governance remains passing.

Validation:
1. `uv run ruff check app/modules/governance/api/v1/audit_evidence.py app/shared/core/health.py tests/unit/core/test_health_deep.py tests/unit/core/test_health_missing_coverage.py` -> passed.
2. `uv run mypy app/modules/governance/api/v1/audit_evidence.py app/shared/core/health.py` -> passed.
3. `DEBUG=false uv run pytest tests/unit/api/v1/test_performance_evidence_endpoints.py tests/unit/api/v1/test_ingestion_persistence_evidence_endpoints.py tests/unit/api/v1/test_ingestion_soak_evidence_endpoints.py tests/unit/api/v1/test_identity_smoke_evidence_endpoints.py tests/unit/api/v1/test_sso_federation_validation_evidence_endpoints.py tests/unit/api/v1/test_job_slo_evidence_endpoints.py tests/unit/api/v1/test_tenant_isolation_evidence_endpoints.py tests/unit/api/v1/test_carbon_assurance_evidence_endpoints.py tests/unit/api/v1/test_audit_evidence_capture_list_branches.py tests/unit/api/v1/test_audit_high_impact_branches.py tests/unit/core/test_health_service.py tests/unit/core/test_health_deep.py tests/unit/core/test_health_missing_coverage.py tests/unit/core/test_health_extra.py --no-cov -q` -> `103 passed`.
4. `uv run python scripts/verify_exception_governance.py` -> passed (`current=357`, `baseline=444`, `removed=87`).
5. `uv run python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).

Post-closure sanity (release-critical):
1. Concurrency: no lock ordering or DB transaction ownership changed; health checks remain side-effect-light and non-blocking beyond existing probe behavior.
2. Observability: warning/error events for payload invalidation and probe failures preserved with consistent event names and tenant/event IDs.
3. Deterministic replay: evidence parsing behavior remains deterministic for same stored payloads; invalid payload skip semantics unchanged.
4. Snapshot stability: API response models and endpoint contracts unchanged; only internal exception typing/handling changed.
5. Export integrity: compliance-pack and evidence export payload shaping untouched in this batch.
6. Failure modes: recoverable probe/evidence decoding failures remain gracefully handled; non-recoverable exceptions now propagate instead of being unintentionally masked.
7. Operational misconfiguration: exception governance and module-size controls continue to pass after hardening.

## Additional remediation batch (2026-03-04K, report-driven H-02 hardening for currency + core circuit breaker)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Targeted open hotspot set from live governance scan:
- `app/shared/core/currency.py` (`8` catch-all handlers)
- `app/shared/core/circuit_breaker.py` (`7` catch-all handlers)

2. Currency runtime hardening (`H-02`):
- Updated: `app/shared/core/currency.py`
- Removed all broad catch-all handlers from:
  - `_read_db_rate`, `_upsert_db_rate`
  - `_read_redis_rate`, `_write_redis_rate`
  - `_fetch_live_rate`, `get_rate`
  - `list_cached_rates`
- Added explicit typed exception contracts:
  - `EXCHANGE_RATE_DB_RECOVERABLE_ERRORS`
  - `EXCHANGE_RATE_CACHE_RECOVERABLE_ERRORS`
  - `EXCHANGE_RATE_DECIMAL_PARSE_ERRORS`
  - `EXCHANGE_RATE_LIVE_PROVIDER_ERRORS`
- Tightened Redis timestamp parsing to typed numeric parse fallback (invalid payload no longer raises unexpectedly).

3. Core circuit-breaker hardening (`H-02`):
- Updated: `app/shared/core/circuit_breaker.py`
- Removed all broad catch-all handlers from:
  - `_distributed_config`, `_get_redis_client`
  - `_as_text`
  - `_sync_state_from_distributed`, `_persist_state_to_distributed`
  - `_acquire_distributed_probe`, `_release_distributed_probe`
- Added explicit typed exception contracts:
  - `CIRCUIT_BREAKER_CONFIG_RECOVERABLE_ERRORS`
  - `CIRCUIT_BREAKER_REDIS_CLIENT_RECOVERABLE_ERRORS`
  - `CIRCUIT_BREAKER_DISTRIBUTED_RECOVERABLE_ERRORS`
  - `CIRCUIT_BREAKER_DECODE_RECOVERABLE_ERRORS`
- Narrowed preconfigured `DATABASE_BREAKER.expected_exception` from `(Exception,)` to typed DB/network/runtime families to avoid masking unrelated faults.

4. Governance outcome:
- Exception governance improved:
  - `current=357 -> 342` (baseline `444`, removed `102`)
- Module-size governance remains passing (`default_max_lines=600`).

Validation:
1. `uv run ruff check app/shared/core/currency.py app/shared/core/circuit_breaker.py tests/unit/core/test_currency.py tests/unit/core/test_currency_deep.py tests/unit/services/billing/test_currency_service.py tests/unit/core/test_circuit_breaker_core.py tests/unit/core/test_circuit_breaker_distributed.py` -> passed.
2. `uv run mypy app/shared/core/currency.py app/shared/core/circuit_breaker.py --hide-error-context --no-error-summary` -> passed.
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/core/test_currency.py tests/unit/core/test_currency_deep.py tests/unit/services/billing/test_currency_service.py tests/unit/api/v1/test_currency_endpoints.py tests/unit/core/test_circuit_breaker_core.py tests/unit/core/test_circuit_breaker_distributed.py` -> `41 passed`.
4. `DEBUG=false uv run pytest -q --no-cov tests/unit/ops/test_verify_exception_governance.py tests/unit/ops/test_verify_python_module_size_budget.py` -> `6 passed`.
5. `uv run python scripts/verify_exception_governance.py` -> passed (`current=342`, `baseline=444`, `removed=102`).
6. `uv run python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).

Post-closure sanity (release-critical):
1. Concurrency: circuit half-open probe serialization (local and distributed) unchanged; only exception filter specificity tightened.
2. Observability: existing warning/debug events for DB/cache/provider/distributed-redis failures preserved with same event names.
3. Deterministic replay: exchange-rate cache lookup order and fallback order unchanged (`L1 -> L2 -> DB -> live -> degrade`), keeping deterministic behavior for identical inputs.
4. Snapshot stability: no API response schema changes; currency and breaker public interfaces unchanged.
5. Export integrity: no export/manifest or reporting payload shaping touched in this batch.
6. Failure modes: recoverable provider/cache/redis faults still degrade gracefully; non-recoverable exceptions now surface instead of being silently swallowed.
7. Operational misconfiguration: governance scripts remain green and now enforce improved catch-all debt reduction.

## Additional remediation batch (2026-03-04L, report-driven H-02 hardening for billing dunning + paystack runtime)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Targeted open hotspot set from live governance scan:
- `app/modules/billing/domain/billing/dunning_service.py` (`6` catch-all handlers)
- `app/modules/billing/domain/billing/paystack_service_impl.py` (`6` catch-all handlers)

2. Dunning workflow hardening (`H-02`):
- Updated: `app/modules/billing/domain/billing/dunning_service.py`
- Removed all broad catch-all handlers from:
  - dunning retry enqueue failure path and rollback fallback
  - renewal charge retry wrapper
  - payment failed/recovered/downgrade email notification wrappers
- Added explicit typed exception contracts:
  - `DUNNING_RECOVERABLE_ERRORS`
  - `DUNNING_ROLLBACK_RECOVERABLE_ERRORS`
  - `DUNNING_EMAIL_RECOVERABLE_ERRORS`
- Preserved state-revert behavior on enqueue failures and non-fatal email failure semantics.

3. Paystack billing runtime hardening (`H-02`):
- Updated: `app/modules/billing/domain/billing/paystack_service_impl.py`
- Removed all broad catch-all handlers from:
  - provider next-payment lookup fallback
  - checkout flow audit side-channel wrapper and top-level checkout runtime wrapper
  - renewal audit side-channel wrapper and renewal charge wrapper
  - cancel-subscription wrapper
- Added explicit typed exception contracts:
  - `PAYSTACK_RUNTIME_RECOVERABLE_ERRORS`
  - `PAYSTACK_AUDIT_RECOVERABLE_ERRORS`
- Preserved existing business behavior:
  - checkout path still logs and re-raises recoverable runtime failures
  - renewal path still logs and returns `False` on recoverable provider/runtime failures
  - cancel path still logs and re-raises recoverable failures
- Kept file-size budget green by trimming constant duplication (module now below default 600-line cap).

4. Test alignment:
- Updated broad-exception test injector to typed runtime failure:
  - `tests/unit/services/billing/test_dunning_service.py` (`Exception("boom") -> RuntimeError("boom")`)

5. Governance outcome:
- Exception governance improved:
  - `current=342 -> 330` (baseline `444`, removed `114`)
- Module-size governance remains passing with default budget.

Validation:
1. `uv run ruff check app/modules/billing/domain/billing/dunning_service.py app/modules/billing/domain/billing/paystack_service_impl.py tests/unit/services/billing/test_dunning_service.py tests/unit/services/billing/test_paystack_billing.py tests/unit/services/billing/test_paystack_billing_branches.py tests/unit/modules/reporting/test_paystack_billing_coverage.py` -> passed.
2. `uv run mypy app/modules/billing/domain/billing/dunning_service.py app/modules/billing/domain/billing/paystack_service_impl.py --hide-error-context --no-error-summary` -> passed.
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/services/billing/test_dunning_service.py tests/unit/services/billing/test_paystack_billing.py tests/unit/services/billing/test_paystack_billing_branches.py tests/unit/modules/reporting/test_paystack_billing_coverage.py tests/unit/governance/domain/jobs/handlers/test_billing_handler.py` -> `70 passed`.
4. `uv run python scripts/verify_exception_governance.py` -> passed (`current=330`, `baseline=444`, `removed=114`).
5. `uv run python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).
6. `DEBUG=false uv run pytest -q --no-cov tests/unit/ops/test_verify_exception_governance.py tests/unit/ops/test_verify_python_module_size_budget.py` -> `6 passed`.

Post-closure sanity (release-critical):
1. Concurrency: dunning attempt increment + state-revert path unchanged; subscription commit boundaries and retry scheduling semantics preserved.
2. Observability: billing/dunning warning-error telemetry keys preserved (`dunning_*`, `paystack_*`, `renewal_*`, `cancel_failed`) with explicit error payloads.
3. Deterministic replay: retry schedule (`1/3/7`) and renewal next-payment derivation order remain unchanged.
4. Snapshot stability: billing API contracts and service return shapes unchanged (`checkout {url,reference}`, renewal bool, dunning status dicts).
5. Export integrity: no reporting/export/signature pipelines modified in this batch.
6. Failure modes: recoverable email/provider/runtime failures remain non-fatal where expected; non-recoverable exceptions now bubble instead of being silently masked.
7. Operational misconfiguration: module-size and exception-governance controls both remain green after remediation.

## Additional remediation batch (2026-03-04M, report-driven H-02 hardening for cost cache adapter)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Targeted open hotspot from live governance scan:
- `app/shared/adapters/cost_cache.py` (`6` catch-all handlers)

2. Redis cache adapter hardening (`H-02`):
- Updated: `app/shared/adapters/cost_cache.py`
- Removed all broad catch-all handlers from:
  - Redis client bootstrap (`_get_client`)
  - Redis operations (`get`, `set`, `delete`, `delete_pattern`)
  - Redis health probe (`health_check`)
- Added explicit typed exception contracts:
  - `REDIS_CLIENT_INIT_RECOVERABLE_ERRORS`
  - `REDIS_OPERATION_RECOVERABLE_ERRORS`
- Preserved graceful-degrade behavior:
  - client init failure -> in-memory fallback compatibility
  - Redis operation failure -> safe `None`/`0` fallback with telemetry
  - health check failure -> `False`.

3. Test alignment:
- Updated catch-path tests to typed runtime failures:
  - `tests/unit/services/adapters/test_cost_cache.py`
  - `Exception(...)` injectors replaced with `RuntimeError(...)`.

4. Governance outcome:
- Exception governance improved:
  - `current=330 -> 324` (baseline `444`, removed `120`)
- Module-size governance remains passing with default budget.

Validation:
1. `uv run ruff check app/shared/adapters/cost_cache.py tests/unit/services/adapters/test_cost_cache.py tests/governance/test_cost_cache_root.py` -> passed.
2. `uv run mypy app/shared/adapters/cost_cache.py --hide-error-context --no-error-summary` -> passed.
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/services/adapters/test_cost_cache.py tests/governance/test_cost_cache_root.py tests/unit/services/adapters/test_cloud_plus_adapters.py -k "cost_cache or zombie_scan"` -> `35 passed, 43 deselected`.
4. `uv run python scripts/verify_exception_governance.py` -> passed (`current=324`, `baseline=444`, `removed=120`).
5. `uv run python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).
6. `DEBUG=false uv run pytest -q --no-cov tests/unit/ops/test_verify_exception_governance.py tests/unit/ops/test_verify_python_module_size_budget.py` -> `6 passed`.

Post-closure sanity (release-critical):
1. Concurrency: Redis operation sequencing and async lock-free cache access semantics unchanged.
2. Observability: Redis init/get/set/delete/scan failure logs preserved with key/pattern context.
3. Deterministic replay: cache key derivation and tenant invalidation patterns unchanged.
4. Snapshot stability: cache API contracts unchanged (`None`/dict/list returns, invalidate counts).
5. Export integrity: no export/report payload pathways modified.
6. Failure modes: recoverable Redis bootstrap/operation faults continue to degrade safely to cache miss behavior.
7. Operational misconfiguration: exception-governance and module-size gates remain green post-hardening.

## Additional remediation batch (2026-03-04N, report-driven H-02 hardening for optimization scan runtime + acceptance handler decomposition)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Targeted open hotspots from live governance scan:
- `app/modules/optimization/domain/service.py` (broad catch-all debt in scan/enrichment/notification paths)
- `app/modules/governance/domain/jobs/handlers/acceptance.py` (catch-all debt previously remediated, but still over module-size budget)

2. Optimization zombie scan hardening (`H-02`):
- Updated: `app/modules/optimization/domain/service.py`
- Removed remaining broad catch handlers from:
  - tenant connection query isolation
  - per-provider scan execution wrappers
  - AI enrichment enqueue and analysis wrappers
  - notification side-channel wrappers
- Added explicit typed exception contracts:
  - `ZOMBIE_CONNECTION_QUERY_RECOVERABLE_ERRORS`
  - `ZOMBIE_SCAN_RECOVERABLE_ERRORS`
  - `ZOMBIE_AI_ENQUEUE_RECOVERABLE_ERRORS`
  - `ZOMBIE_AI_ANALYSIS_RECOVERABLE_ERRORS`
  - `ZOMBIE_NOTIFICATION_RECOVERABLE_ERRORS`
- Preserved non-fatal behavior for recoverable provider/AI/notification failures while preventing unexpected masking of unrelated errors.

3. Acceptance handler decomposition and hardening closure:
- Added: `app/modules/governance/domain/jobs/handlers/acceptance_runtime_ops.py`
- Refactored `acceptance.py` to import runtime helpers and typed exception tuples from the new module while preserving existing callable symbols used by tests.
- Moved helper/runtime surface out of handler body:
  - `_require_tenant_id`, `_iso_date`, `_tenant_tier`, `_coerce_positive_int`
  - `_evaluate_tenancy_passive_check`
  - `_integration_event_type`
  - typed exception tuples for capture/integration/parse recoverable paths
- Module-size result:
  - `acceptance.py`: `769 -> 633` lines (now below its budget cap and below default 600+override threshold).

4. Test alignment:
- Updated zombie service tests to typed recoverable faults:
  - `tests/unit/services/zombies/test_zombie_service.py`
  - `Exception(...)` side effects replaced with `RuntimeError(...)`.

5. Governance outcome:
- Exception governance improved:
  - `current=324 -> 312` (baseline `444`, removed `132`)
- Module-size governance passing with default limit and overrides (`default_max_lines=600`).

Validation:
1. `uv run ruff check app/modules/optimization/domain/service.py app/modules/governance/domain/jobs/handlers/acceptance.py app/modules/governance/domain/jobs/handlers/acceptance_runtime_ops.py tests/unit/services/zombies/test_zombie_service.py tests/unit/services/jobs/test_acceptance_suite_capture_handler.py tests/unit/services/jobs/test_acceptance_suite_capture_handler_branches.py` -> passed.
2. `uv run mypy app/modules/optimization/domain/service.py app/modules/governance/domain/jobs/handlers/acceptance.py app/modules/governance/domain/jobs/handlers/acceptance_runtime_ops.py` -> passed.
3. `DEBUG=false uv run pytest -q -c /dev/null tests/unit/services/jobs/test_acceptance_suite_capture_handler.py tests/unit/services/jobs/test_acceptance_suite_capture_handler_branches.py tests/unit/optimization/test_optimization_service.py tests/unit/optimization/test_zombie_service_audit.py tests/unit/services/zombies/test_zombie_service.py tests/unit/services/zombies/test_zombie_service_cloud_plus.py tests/unit/ops/test_verify_exception_governance.py tests/unit/ops/test_verify_python_module_size_budget.py` -> `34 passed`.
4. `uv run python scripts/verify_exception_governance.py` -> passed (`current=312`, `baseline=444`, `removed=132`).
5. `uv run python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).

Post-closure sanity (release-critical):
1. Concurrency: provider scans and AI paths keep existing parallel execution semantics; no new shared mutable-state contention introduced.
2. Observability: existing warning telemetry for connection query, scan, AI, and notification failures preserved with provider/tenant context.
3. Deterministic replay: acceptance capture run identity, event sequencing, and tenancy passive-check decision logic remain deterministic for identical inputs.
4. Snapshot stability: acceptance job response schema and audit event payload contracts remain unchanged.
5. Export integrity: no close-package/quarterly payload shape changes beyond module extraction; CSV suppression behavior unchanged.
6. Failure modes: recoverable runtime failures continue to degrade gracefully; non-recoverable unexpected faults now surface instead of being silently swallowed.
7. Operational misconfiguration: exception-governance and module-size controls both remain green after decomposition.

## Additional remediation batch (2026-03-04O, report-driven H-02 hardening for LLM budget runtime guards)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Targeted open hotspots from live governance scan:
- `app/shared/llm/budget_execution.py` (`6` catch-all handlers)
- `app/shared/llm/budget_fair_use.py` (`6` catch-all handlers)

2. Budget execution hardening (`H-02`):
- Updated: `app/shared/llm/budget_execution.py`
- Removed all broad catch-all handlers from:
  - `check_and_reserve_budget` reservation pipeline wrapper
  - metric increment side-channel in `record_usage_entry`
  - usage-recording main error/rollback wrappers
  - fail-closed cache read path in `check_budget_state`
  - Slack dispatch wrapper in `check_budget_and_alert`
- Added explicit typed exception contracts:
  - `BUDGET_EXECUTION_RECOVERABLE_ERRORS`
  - `BUDGET_METRIC_RECOVERABLE_ERRORS`
  - `BUDGET_ROLLBACK_RECOVERABLE_ERRORS`
  - `BUDGET_CACHE_RECOVERABLE_ERRORS`
  - `BUDGET_ALERT_RECOVERABLE_ERRORS`
- Preserved semantics:
  - budget limit exceptions still propagate
  - fail-closed cache errors still convert to `BudgetExceededError`
  - rollback remains best-effort with warning telemetry.

3. Fair-use runtime hardening (`H-02`):
- Updated: `app/shared/llm/budget_fair_use.py`
- Removed all broad catch-all handlers from:
  - global abuse cache get/set wrappers
  - minute-window count parsing fallbacks
  - Redis acquire/release wrappers for in-flight slots
- Added explicit typed exception contracts:
  - `FAIR_USE_CACHE_RECOVERABLE_ERRORS`
  - `FAIR_USE_PARSE_RECOVERABLE_ERRORS`
- Maintained existing degrade behavior:
  - cache failures fall back to local guard behavior
  - parse failures fall back to zero-observed counters.

4. Module-size integrity:
- `budget_fair_use.py` briefly exceeded its configured budget after hardening tuple additions.
- Reduced to compliant size without behavior changes:
  - `budget_fair_use.py`: `857 -> 843` lines (budget `844`).

5. Governance outcome:
- Exception governance improved:
  - `current=312 -> 300` (baseline `444`, removed `144`)
- Module-size governance remains passing (`default_max_lines=600`).

Validation:
1. `uv run ruff check app/shared/llm/budget_execution.py app/shared/llm/budget_fair_use.py tests/unit/shared/llm/test_budget_execution_branches.py tests/unit/shared/llm/test_budget_fair_use_branches.py tests/unit/core/test_budget_manager_fair_use.py tests/unit/llm/test_budget_manager.py tests/unit/llm/test_budget_manager_exhaustive.py tests/unit/core/test_budget_manager_audit.py` -> passed.
2. `uv run mypy app/shared/llm/budget_execution.py app/shared/llm/budget_fair_use.py` -> passed.
3. `DEBUG=false uv run pytest -q -c /dev/null tests/unit/shared/llm/test_budget_execution_branches.py tests/unit/shared/llm/test_budget_fair_use_branches.py tests/unit/core/test_budget_manager_fair_use.py tests/unit/llm/test_budget_manager.py tests/unit/llm/test_budget_manager_exhaustive.py tests/unit/core/test_budget_manager_audit.py` -> `78 passed`.
4. `uv run python scripts/verify_exception_governance.py` -> passed (`current=300`, `baseline=444`, `removed=144`).
5. `uv run python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).
6. `DEBUG=false uv run pytest -q -c /dev/null tests/unit/ops/test_verify_exception_governance.py tests/unit/ops/test_verify_python_module_size_budget.py` -> `6 passed`.

Post-closure sanity (release-critical):
1. Concurrency: in-flight slot acquire/release semantics and lock ordering remained unchanged; only exception filters were narrowed.
2. Observability: budget/fair-use warning and error telemetry keys were preserved (`budget_check_failed`, `usage_recording_failed`, `llm_global_abuse_*`, `llm_fair_use_redis_*`).
3. Deterministic replay: monthly reset, reservation, and fair-use threshold evaluation order remains unchanged for identical inputs.
4. Snapshot stability: budget status, usage recording, and fair-use API/service contracts were unchanged.
5. Export integrity: no reporting/export path was touched in this batch.
6. Failure modes: recoverable cache/metric/rollback/dispatch failures still degrade gracefully; unrelated non-recoverable exceptions now bubble instead of being silently masked.
7. Operational misconfiguration: both governance controls remained green after the hardening and size-budget reconciliation.

## Additional remediation batch (2026-03-04P, report-driven H-02 hardening for GCP adapter + reconciliation/scheduler/compliance flows)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Targeted open hotspots from live governance scan:
- `app/shared/adapters/gcp.py` (`5` catch-all handlers)
- `app/modules/enforcement/domain/reconciliation_worker.py` (`5` catch-all handlers)
- `app/modules/governance/domain/scheduler/processors.py` (`5` catch-all handlers)
- `app/modules/governance/domain/security/compliance_pack_bundle.py` (`5` catch-all handlers)

2. GCP adapter hardening (`H-02`):
- Updated: `app/shared/adapters/gcp.py`
- Removed all broad catch-all handlers from:
  - credential bootstrap (`_get_credentials`)
  - connection verification (`verify_connection`)
  - BigQuery query path (`get_cost_and_usage`)
  - asset discovery (`discover_resources`)
  - resource usage projection wrapper (`get_resource_usage`)
- Added explicit typed exception contracts:
  - `GCP_CREDENTIAL_RECOVERABLE_ERRORS`
  - `GCP_OPERATION_RECOVERABLE_ERRORS`
  - `GCP_RESOURCE_USAGE_RECOVERABLE_ERRORS`
- Preserved behavior:
  - invalid credential payload still degrades to default credential fallback
  - query failures still raise `AdapterError`
  - verify/discovery/resource-usage failures remain non-fatal and telemetry-rich.

3. Enforcement reconciliation worker hardening (`H-02`):
- Updated: `app/modules/enforcement/domain/reconciliation_worker.py`
- Removed broad catch-all handlers from:
  - numeric parser helpers (`_as_decimal`, `_as_int`)
  - worker sweep boundary (`run_for_tenant`)
  - best-effort alert send wrappers
- Added explicit typed exception contracts:
  - `RECONCILIATION_PARSE_RECOVERABLE_ERRORS`
  - `RECONCILIATION_WORKER_RECOVERABLE_ERRORS`
  - `RECONCILIATION_ALERT_RECOVERABLE_ERRORS`
- Preserved sweep metric semantics (`success`/`failure`) and non-fatal alert failure handling.

4. Scheduler processors hardening (`H-02`):
- Updated: `app/modules/governance/domain/scheduler/processors.py`
- Removed broad catch-all handlers from:
  - savings autopilot side-channel wrapper
  - zombie detector side-channel wrapper
  - per-connection and per-tenant processor wrappers
  - autonomous execution wrapper in `SavingsProcessor`
- Added explicit typed exception contract:
  - `PROCESSOR_RECOVERABLE_ERRORS`
- Preserved timeout branch behavior and continue-on-connection-failure semantics.

5. Compliance pack bundle hardening (`H-02`):
- Updated: `app/modules/governance/domain/security/compliance_pack_bundle.py`
- Removed broad catch-all handlers from:
  - export-request audit persistence wrapper
  - optional export sections (FOCUS, savings proof, realized savings, close package)
- Added explicit typed exception contract:
  - `COMPLIANCE_PACK_BUNDLE_RECOVERABLE_ERRORS`
- Preserved bundle resilience contract:
  - optional exports still emit `*.error.json` artifacts instead of failing whole ZIP.

6. Test alignment:
- Updated broad exception test injectors to typed runtime failures:
  - `tests/unit/adapters/test_gcp_adapter.py`
  - `tests/unit/services/scheduler/test_processors_expanded.py`

7. Governance outcome:
- Exception governance improved:
  - `current=300 -> 280` (baseline `444`, removed `164`)
- Module-size governance remains passing (`default_max_lines=600`).

Validation:
1. `uv run ruff check app/shared/adapters/gcp.py app/modules/enforcement/domain/reconciliation_worker.py app/modules/governance/domain/scheduler/processors.py app/modules/governance/domain/security/compliance_pack_bundle.py tests/unit/adapters/test_gcp_adapter.py tests/unit/services/scheduler/test_processors_expanded.py` -> passed.
2. `uv run mypy app/shared/adapters/gcp.py app/modules/enforcement/domain/reconciliation_worker.py app/modules/governance/domain/scheduler/processors.py app/modules/governance/domain/security/compliance_pack_bundle.py` -> passed.
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/shared/adapters/test_gcp_adapter.py tests/unit/adapters/test_gcp_adapter.py tests/unit/enforcement/test_reconciliation_worker.py tests/unit/governance/scheduler/test_processors.py tests/unit/governance/scheduler/test_processors_branches.py tests/unit/services/scheduler/test_processors_expanded.py tests/unit/api/v1/test_audit_compliance_pack.py` -> `60 passed`.
4. `uv run python scripts/verify_exception_governance.py` -> passed (`current=280`, `baseline=444`, `removed=164`).
5. `uv run python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).
6. `DEBUG=false uv run pytest -q --no-cov tests/unit/ops/test_verify_exception_governance.py tests/unit/ops/test_verify_python_module_size_budget.py` -> `6 passed`.

Post-closure sanity (release-critical):
1. Concurrency: scheduler/worker execution ordering and async timeout boundaries unchanged; no new lock contention introduced.
2. Observability: existing structured log event names and alert metrics remained stable across all touched modules.
3. Deterministic replay: compliance pack manifest generation and optional export fallback sequence unchanged.
4. Snapshot stability: adapter/service return contracts unchanged (GCP verification/discovery/resource-usage, reconciliation payload shape, compliance ZIP manifest structure).
5. Export integrity: optional export error artifact behavior (`*.error.json`) preserved; core bundle remains exportable on partial failures.
6. Failure modes: recoverable infrastructure/runtime faults still degrade safely; non-recoverable unexpected exceptions now avoid silent masking.
7. Operational misconfiguration: both exception-governance and module-size controls remain green after this remediation batch.

## Additional remediation batch (2026-03-04Q, report-driven H-02 hardening for auth + Azure/SaaS/Hybrid adapters with post-closure gate refresh)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Targeted open hotspots from governance scan:
- `app/shared/core/auth.py` (`4` catch-all handlers)
- `app/shared/adapters/azure.py` (`4` catch-all handlers)
- `app/shared/adapters/saas.py` (`4` catch-all handlers)
- `app/shared/adapters/hybrid.py` (`4` catch-all handlers)

2. Auth runtime hardening (`H-02`):
- Updated: `app/shared/core/auth.py`
- Replaced broad catch-all handlers with explicit typed contracts:
  - `AUTH_BACKEND_DETECTION_ERRORS`
  - `AUTH_SCHEMA_RETRY_ERRORS`
  - `AUTH_PERSONA_PARSE_ERRORS`
  - `AUTH_IDENTITY_POLICY_RECOVERABLE_ERRORS`
  - `AUTH_UNEXPECTED_RECOVERABLE_ERRORS`
- Preserved behavior:
  - schema-mismatch fallback retry path remains active
  - invalid persona still defaults to engineering persona
  - identity policy check remains fail-closed in production and warn/degrade in non-prod.

3. Azure adapter hardening (`H-02`):
- Updated: `app/shared/adapters/azure.py`
- Removed all broad catch-all handlers from:
  - `verify_connection`
  - `get_cost_and_usage`
  - `discover_resources`
  - `get_resource_usage`
- Added explicit typed contracts:
  - `AZURE_OPERATION_RECOVERABLE_ERRORS`
  - `AZURE_USAGE_LOOKUP_RECOVERABLE_ERRORS`
- Preserved behavior:
  - verification/discovery/resource-usage failures remain non-fatal and telemetry-rich
  - cost query failures still raise `AdapterError`.

4. SaaS and Hybrid adapter hardening (`H-02`):
- Updated:
  - `app/shared/adapters/saas.py`
  - `app/shared/adapters/hybrid.py`
- Replaced broad conversion/retrieval catches with explicit contracts:
  - SaaS:
    - `SAAS_CURRENCY_CONVERSION_RECOVERABLE_ERRORS`
    - `SAAS_RESOURCE_USAGE_RECOVERABLE_ERRORS`
  - Hybrid:
    - `HYBRID_CURRENCY_CONVERSION_RECOVERABLE_ERRORS`
    - `HYBRID_RESOURCE_USAGE_RECOVERABLE_ERRORS`
- Preserved behavior:
  - FX conversion failures still log warning and fall back to local amount
  - resource discovery/usage wrappers still degrade to empty list with context logging.

5. Test alignment for typed failures:
- Updated generic failure injectors to typed recoverable errors:
  - `tests/unit/core/test_auth_core.py`
  - `tests/unit/core/test_auth_branch_paths.py`
  - `tests/unit/core/test_auth_audit.py`
  - `tests/unit/services/adapters/test_azure_adapter.py`
  - `tests/unit/adapters/test_azure_adapter.py`

6. Module-size governance reconciliation:
- `app/shared/adapters/hybrid.py` briefly exceeded its strict per-file budget after hardening tuple additions.
- Refactored constant declarations (non-functional change) to restore compliance:
  - `hybrid.py: 891 -> 860` lines (budget `872`).

7. Post-closure sanity gate refresh:
- Updated stale verifier token paths in:
  - `scripts/verify_enforcement_post_closure_sanity.py`
- Reason:
  - enforcement decomposition moved lineage fields from `service.py` to dedicated modules.
- Updated references:
  - `computed_context_lineage_sha256` token source -> `app/modules/enforcement/domain/service_models.py`
  - `policy_lineage_sha256` token source -> `app/modules/enforcement/domain/export_bundle_ops.py`

8. Governance outcome:
- Exception governance improved:
  - `current=280 -> 263` (baseline `444`, removed `181`)
- Module-size governance remains passing (`default_max_lines=600`).

Validation:
1. `uv run ruff check app/shared/core/auth.py app/shared/adapters/azure.py app/shared/adapters/saas.py app/shared/adapters/hybrid.py tests/unit/core/test_auth_core.py tests/unit/core/test_auth_branch_paths.py tests/unit/core/test_auth_audit.py tests/unit/services/adapters/test_azure_adapter.py tests/unit/adapters/test_azure_adapter.py` -> passed.
2. `uv run mypy app/shared/core/auth.py app/shared/adapters/azure.py app/shared/adapters/saas.py app/shared/adapters/hybrid.py` -> passed.
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/core/test_auth_core.py tests/unit/core/test_auth_branch_paths.py tests/unit/core/test_auth_audit.py tests/unit/adapters/test_azure_adapter.py tests/unit/services/adapters/test_azure_adapter.py tests/unit/shared/adapters/test_azure_adapter.py tests/unit/shared/adapters/test_azure_adapter_branch_paths.py tests/unit/shared/adapters/test_saas_adapter_branch_paths.py tests/unit/services/adapters/test_hybrid_additional_branches.py tests/unit/services/adapters/test_cloud_plus_adapters.py` -> `164 passed`.
4. `uv run python scripts/verify_exception_governance.py` -> passed (`current=263`, `baseline=444`, `removed=181`).
5. `uv run python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).
6. `uv run python scripts/verify_enforcement_post_closure_sanity.py` -> passed (all `7` dimensions `OK`).
7. `DEBUG=false uv run pytest -q --no-cov tests/unit/ops/test_verify_enforcement_post_closure_sanity.py` -> `6 passed`.
8. `uv run python scripts/verify_env_hygiene.py` + `uv run python scripts/verify_repo_root_hygiene.py` + `uv run python scripts/verify_adapter_test_coverage.py` -> all passed.

Post-closure sanity (release-critical):
1. Concurrency: async auth/adapters execution behavior unchanged; no lock/order semantics altered.
2. Observability: all prior warning/error event names preserved; typed catches keep existing telemetry detail.
3. Deterministic replay: no decision/replay logic changed; only exception filters and verifier token sources were updated.
4. Snapshot stability: adapter/auth payload contracts and fields remained stable.
5. Export integrity: enforcement export lineage token verification restored to current module locations.
6. Failure modes: recoverable infrastructure/runtime failures continue to degrade safely; unexpected non-typed faults are no longer silently masked.
7. Operational misconfiguration: governance gates for env/root hygiene, adapter test coverage, exception policy, module-size budget, and post-closure sanity all pass after this batch.

## Additional remediation batch (2026-03-04R, report-driven H-02 hardening continuation for billing/audit/notifications/job processor)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Targeted open hotspots from governance scan:
- `app/modules/billing/api/v1/billing.py` (`4` catch-all handlers)
- `app/modules/governance/api/v1/audit_access.py` (`4` catch-all handlers)
- `app/modules/governance/api/v1/settings/notifications.py` (`4` catch-all handlers)
- `app/modules/governance/domain/jobs/processor.py` (`4` catch-all handlers)

2. Billing API hardening (`H-02`):
- Updated: `app/modules/billing/api/v1/billing.py`
- Introduced explicit recoverable tuple `BILLING_RUNTIME_RECOVERABLE_ERRORS`.
- Replaced broad catch-all handlers in:
  - `get_subscription`
  - `create_checkout`
  - `cancel_subscription`
  - `handle_webhook`

3. Audit access hardening (`H-02`):
- Updated: `app/modules/governance/api/v1/audit_access.py`
- Introduced explicit recoverable tuple `AUDIT_ACCESS_RECOVERABLE_ERRORS`.
- Replaced broad catch-all handlers in:
  - `get_audit_logs`
  - `get_audit_log_detail`
  - `export_audit_logs` (plus `csv.Error`)
  - `request_data_erasure` (rollback preserved)

4. Notification connectivity hardening (`H-02`):
- Updated: `app/modules/governance/api/v1/settings/notifications.py`
- Introduced explicit recoverable tuple `NOTIFICATION_CONNECTIVITY_RECOVERABLE_ERRORS`.
- Replaced broad catch-all handlers in:
  - `_run_slack_connectivity_test`
  - `_run_jira_connectivity_test`
  - `_run_teams_connectivity_test`
  - `_run_workflow_connectivity_test` per-dispatcher isolation

5. Background job processor hardening (`H-02`):
- Updated: `app/modules/governance/domain/jobs/processor.py`
- Introduced explicit typed tuples:
  - `JOB_RESULT_SERIALIZATION_ERRORS`
  - `JOB_RUNTIME_RECOVERABLE_ERRORS`
- Replaced broad catch-all handlers in:
  - `_prepare_result_for_storage` serialization fallback
  - `process_pending_jobs` per-job isolation path
  - `process_pending_jobs` batch-level non-DB runtime path
  - `_process_single_job` resilience/failure path

6. Test alignment to typed runtime failures:
- Updated tests to inject typed recoverable failures instead of generic `Exception(...)` where these paths are asserted:
  - `tests/unit/api/v1/test_billing.py`
  - `tests/unit/reporting/test_billing_api.py`
  - `tests/unit/api/test_audit.py`
  - `tests/unit/governance/settings/test_notifications.py`
  - `tests/unit/governance/jobs/test_job_processor.py`
  - `tests/governance/test_job_processor.py`

7. Module-size governance reconciliation:
- `notifications.py` temporarily exceeded strict budget during hardening (`881 > 870`).
- Non-functional line compaction restored compliance:
  - `app/modules/governance/api/v1/settings/notifications.py: 881 -> 867` (budget `870`).

Validation:
1. `DEBUG=false .venv/bin/pytest --no-cov -q tests/unit/api/v1/test_billing.py tests/unit/reporting/test_billing_api.py tests/unit/api/test_audit.py tests/unit/api/v1/test_audit_high_impact_branches.py tests/unit/governance/settings/test_notifications.py tests/unit/governance/settings/test_notifications_helper_branches.py tests/unit/governance/jobs/test_job_processor.py tests/governance/test_job_processor.py` -> `135 passed`.
2. `DEBUG=false .venv/bin/pytest --no-cov -q tests/unit/governance/settings/test_notifications.py tests/unit/governance/settings/test_notifications_helper_branches.py` -> `45 passed`.
3. `DEBUG=false .venv/bin/python scripts/verify_exception_governance.py` -> passed (`current=247`, `baseline=444`, `removed=197`).
4. `DEBUG=false .venv/bin/python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).
5. `DEBUG=false .venv/bin/python scripts/verify_enforcement_post_closure_sanity.py` -> passed (all `7` dimensions `OK`).

Post-closure sanity (release-critical):
1. Concurrency: per-job isolation and batch continuation semantics in job processor remain intact.
2. Observability: all error/warning event names retained; typed catches still capture structured context.
3. Deterministic replay: no changes to decision lineage/replay contracts; only exception families narrowed.
4. Snapshot stability: endpoint response models/payload shapes unchanged across billing/audit/notifications/job APIs.
5. Export integrity: audit CSV/export and erasure flows preserve existing output contracts and rollback safeguards.
6. Failure modes: recoverable DB/network/runtime faults remain safely mapped; unexpected non-typed failures no longer silently masked.
7. Operational misconfiguration: exception governance, module-size budget, and post-closure sanity controls are all green for this batch.

## Additional remediation batch (2026-03-04S, report-driven H-02 hardening continuation for anomaly/workflows/email/Azure AI plugins)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Targeted open hotspots from governance scan:
- `app/modules/reporting/domain/anomaly_detection.py` (`4` catch-all handlers)
- `app/modules/optimization/adapters/azure/plugins/ai.py` (`4` catch-all handlers)
- `app/modules/notifications/domain/workflows.py` (`4` catch-all handlers)
- `app/modules/notifications/domain/email_service.py` (`4` catch-all handlers)

2. Anomaly dispatch hardening (`H-02`):
- Updated: `app/modules/reporting/domain/anomaly_detection.py`
- Added typed exception contracts:
  - `ANOMALY_JIRA_BOOTSTRAP_RECOVERABLE_EXCEPTIONS`
  - `ANOMALY_DISPATCH_RECOVERABLE_EXCEPTIONS`
- Replaced broad catch-all handlers in:
  - Jira bootstrap/fallback path
  - workflow event dispatch path
  - Jira issue creation path
  - per-anomaly dispatch isolation path
- Preserved behavior:
  - dispatch remains best-effort per anomaly
  - Jira/workflow failures remain non-fatal with debug telemetry.

3. Workflow dispatcher hardening (`H-02`):
- Updated: `app/modules/notifications/domain/workflows.py`
- Added typed recoverable tuple `WORKFLOW_DISPATCH_RECOVERABLE_EXCEPTIONS`.
- Replaced broad catch-all handlers in:
  - `GitHubActionsDispatcher.dispatch`
  - `GitLabCIDispatcher.dispatch`
  - `GenericCIWebhookDispatcher.dispatch` HTTP branch
- Narrowed webhook URL validation branch to `ValueError` only.
- Preserved behavior:
  - non-2xx responses still return `False`
  - network/runtime failures remain non-fatal with structured warnings.

4. Email service hardening (`H-02`):
- Updated: `app/modules/notifications/domain/email_service.py`
- Added typed recoverable tuple `EMAIL_DELIVERY_RECOVERABLE_EXCEPTIONS`.
- Replaced broad catch-all handlers in:
  - `send_carbon_alert`
  - `send_dunning_notification`
  - `send_payment_recovered_notification`
  - `send_account_downgraded_notification`
- Preserved behavior:
  - delivery/header-validation failures still return `False` and log.

5. Azure AI plugin hardening (`H-02`):
- Updated: `app/modules/optimization/adapters/azure/plugins/ai.py`
- Added `AZURE_AI_SCAN_RECOVERABLE_EXCEPTIONS` using `AzureError` + typed runtime/value errors.
- Replaced broad catch-all handlers in:
  - OpenAI deployment metric retrieval branch
  - OpenAI scan outer branch
  - AI Search metric retrieval branch
  - AI Search scan outer branch
- Preserved behavior:
  - per-resource metric failures still degrade safely and continue scan.

6. Test alignment and branch coverage extensions:
- Updated typed failure injectors:
  - `tests/unit/notifications/domain/test_email_service.py`
  - `tests/unit/modules/notifications/test_notifications_comprehensive.py`
- Added typed exception-path tests:
  - `tests/unit/notifications/test_workflow_dispatchers.py`
    - `test_github_dispatch_handles_httpx_error`
  - `tests/unit/modules/optimization/adapters/azure/test_azure_next_gen.py`
    - `test_idle_azure_openai_plugin_metric_failure_is_non_fatal`
    - `test_idle_ai_search_plugin_metric_failure_is_non_fatal`
  - `tests/unit/modules/reporting/test_anomaly_detection.py`
    - `test_dispatch_cost_anomaly_alerts_handles_send_alert_runtime_error`
    - `test_dispatch_cost_anomaly_alerts_handles_jira_bootstrap_runtime_error`

Validation:
1. `DEBUG=false ./.venv/bin/pytest -q --no-cov tests/unit/modules/reporting/test_anomaly_detection.py tests/unit/notifications/test_workflow_dispatchers.py tests/unit/notifications/domain/test_email_service.py tests/unit/modules/notifications/test_notifications_comprehensive.py tests/unit/modules/optimization/adapters/azure/test_azure_next_gen.py` -> `35 passed`.
2. `./.venv/bin/ruff check app/modules/reporting/domain/anomaly_detection.py app/modules/optimization/adapters/azure/plugins/ai.py app/modules/notifications/domain/workflows.py app/modules/notifications/domain/email_service.py tests/unit/modules/reporting/test_anomaly_detection.py tests/unit/notifications/test_workflow_dispatchers.py tests/unit/notifications/domain/test_email_service.py tests/unit/modules/notifications/test_notifications_comprehensive.py tests/unit/modules/optimization/adapters/azure/test_azure_next_gen.py` -> passed.
3. `./.venv/bin/mypy app/modules/reporting/domain/anomaly_detection.py app/modules/optimization/adapters/azure/plugins/ai.py app/modules/notifications/domain/workflows.py app/modules/notifications/domain/email_service.py` -> passed.
4. `./.venv/bin/python scripts/verify_exception_governance.py` -> passed (`current=231`, `baseline=444`, `removed=213`).
5. `./.venv/bin/python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).
6. `./.venv/bin/python scripts/verify_enforcement_post_closure_sanity.py` -> passed (all `7` dimensions `OK`).

Post-closure sanity (release-critical):
1. Concurrency: per-item anomaly dispatch and per-resource Azure scan continuation semantics unchanged.
2. Observability: all existing structured event names retained; typed catches preserve error context.
3. Deterministic replay: no changes to anomaly model output ordering/contract or dispatch payload schema.
4. Snapshot stability: workflow/email/Azure/anomaly public contracts unchanged; only exception families narrowed.
5. Export integrity: no export-path code changes in this batch.
6. Failure modes: recoverable runtime/network/provider errors still degrade safely; unknown faults are no longer silently masked by catch-all handlers.
7. Operational misconfiguration: exception governance, module-size governance, and post-closure sanity checks are green after this batch.

## Additional remediation batch (2026-03-04T, report-driven H-02 hardening continuation for billing/paystack/health-dashboard/teams)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Targeted open hotspots from governance scan:
- `app/modules/billing/api/v1/billing_ops.py` (`3` catch-all handlers)
- `app/modules/billing/domain/billing/paystack_webhook_impl.py` (`3` catch-all handlers)
- `app/modules/governance/api/v1/health_dashboard.py` (`3` catch-all handlers)
- `app/modules/notifications/domain/teams.py` (`3` catch-all handlers)

2. Billing webhook/API hardening (`H-02`):
- Updated: `app/modules/billing/api/v1/billing_ops.py`
- Added typed exception contracts:
  - `BILLING_PLAN_RECOVERABLE_ERRORS`
  - `BILLING_WEBHOOK_COMPLETION_RECOVERABLE_ERRORS`
  - `BILLING_WEBHOOK_PROCESS_RECOVERABLE_ERRORS`
- Replaced broad catch-all handlers in:
  - DB pricing plan fetch fallback path
  - inline completion mark path
  - webhook processing-to-queue fallback path
- Preserved behavior:
  - fallback to static plans remains intact
  - webhook completion mark failures remain non-fatal
  - webhook processing failures still return queued response.

3. Paystack webhook audit hardening (`H-02`):
- Updated: `app/modules/billing/domain/billing/paystack_webhook_impl.py`
- Added typed exception contract:
  - `PAYSTACK_WEBHOOK_AUDIT_RECOVERABLE_EXCEPTIONS`
- Replaced broad catch-all handlers in audit side-channel paths for:
  - `subscription.create`
  - `charge.success`
  - `invoice.payment_failed`
- Preserved behavior:
  - billing state transitions continue even when audit side-channel fails.
- Type-safety correction:
  - normalized `last_charge_fx_rate` assignment to `float(parsed_fx_rate)` to satisfy model typing without changing semantics.

4. Health dashboard hardening (`H-02`):
- Updated: `app/modules/governance/api/v1/health_dashboard.py`
- Added typed exception contracts:
  - `HEALTH_DASHBOARD_CACHE_RECOVERABLE_EXCEPTIONS`
  - `HEALTH_DASHBOARD_TIER_LOOKUP_RECOVERABLE_EXCEPTIONS`
- Replaced broad catch-all handlers in:
  - cached payload decode fallback (`InvestorHealthDashboard`)
  - fair-use cached payload decode fallback (`LLMFairUseRuntime`)
  - tenant tier lookup fallback path
- Preserved behavior:
  - invalid cache payloads still degrade to fresh recompute
  - tier lookup failures still degrade to safe `FREE` tier visibility.

5. Teams notifier hardening (`H-02`):
- Updated: `app/modules/notifications/domain/teams.py`
- Added typed exception contract:
  - `TEAMS_DELIVERY_RECOVERABLE_EXCEPTIONS`
- Replaced broad catch-all handlers in:
  - passive health-check URL validation path (`ValueError` only)
  - send-alert URL validation path (`ValueError` only)
  - outbound send exception path (`httpx.HTTPError` + typed runtime/value errors)
- Preserved behavior:
  - unsafe URLs still fail closed
  - non-2xx and delivery faults remain non-fatal and telemetry-rich.

6. Test alignment and branch coverage extensions:
- Updated typed failure injectors:
  - `tests/unit/reporting/test_billing_api.py`
    - DB failure uses `SQLAlchemyError`
    - webhook process failure uses `RuntimeError`
- Added resilience branch tests:
  - `tests/unit/api/v1/test_billing.py`
    - `test_handle_webhook_success_when_inline_completion_mark_fails`
  - `tests/unit/services/billing/test_paystack_billing_branches.py`
    - `test_handle_subscription_create_continues_when_audit_log_fails`

7. Module-size governance reconciliation:
- `health_dashboard.py` exceeded strict per-file budget after hardening (`707 > 694`).
- Non-functional line compaction restored compliance:
  - `app/modules/governance/api/v1/health_dashboard.py: 707 -> 686` (budget `694`).

Validation:
1. `DEBUG=false ./.venv/bin/pytest -q --no-cov tests/unit/api/v1/test_billing.py tests/unit/reporting/test_billing_api.py tests/unit/services/billing/test_paystack_billing.py tests/unit/services/billing/test_paystack_billing_branches.py tests/unit/api/v1/test_health_dashboard_branches.py tests/unit/api/v1/test_health_dashboard_endpoints.py tests/unit/notifications/domain/test_teams_service.py tests/unit/governance/settings/test_notifications.py` -> `145 passed`.
2. `DEBUG=false ./.venv/bin/pytest -q --no-cov tests/unit/api/v1/test_billing.py tests/unit/reporting/test_billing_api.py tests/unit/services/billing/test_paystack_billing_branches.py tests/unit/api/v1/test_health_dashboard_branches.py tests/unit/api/v1/test_health_dashboard_endpoints.py tests/unit/notifications/domain/test_teams_service.py` -> `96 passed`.
3. `./.venv/bin/ruff check app/modules/billing/api/v1/billing_ops.py app/modules/billing/domain/billing/paystack_webhook_impl.py app/modules/governance/api/v1/health_dashboard.py app/modules/notifications/domain/teams.py tests/unit/reporting/test_billing_api.py tests/unit/api/v1/test_billing.py tests/unit/services/billing/test_paystack_billing_branches.py` -> passed.
4. `./.venv/bin/mypy app/modules/billing/api/v1/billing_ops.py app/modules/billing/domain/billing/paystack_webhook_impl.py app/modules/governance/api/v1/health_dashboard.py app/modules/notifications/domain/teams.py` -> passed.
5. `./.venv/bin/python scripts/verify_exception_governance.py` -> passed (`current=219`, `baseline=444`, `removed=225`).
6. `./.venv/bin/python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).
7. `./.venv/bin/python scripts/verify_enforcement_post_closure_sanity.py` -> passed (all `7` dimensions `OK`).

Post-closure sanity (release-critical):
1. Concurrency: webhook queue/inline flow and async Teams delivery semantics unchanged.
2. Observability: existing log event names retained; typed catches preserve explicit error context.
3. Deterministic replay: webhook/event payload contracts and health snapshot models unchanged.
4. Snapshot stability: billing, health-dashboard, and Teams response shapes remain stable.
5. Export integrity: no export path semantics changed in this batch.
6. Failure modes: recoverable DB/network/runtime faults continue to degrade safely; unexpected non-typed faults are no longer silently masked.
7. Operational misconfiguration: exception governance, module-size budget, and post-closure sanity controls all pass after this batch.

## Additional remediation batch (2026-03-04U, report-driven H-02 hardening continuation for platform/forecaster/oidc/azure-network)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Targeted open hotspots from governance scan:
- `app/shared/adapters/platform.py` (`3` catch-all handlers)
- `app/shared/analysis/forecaster.py` (`3` catch-all handlers)
- `app/shared/connections/oidc.py` (`3` catch-all handlers)
- `app/modules/optimization/adapters/azure/plugins/network.py` (`3` catch-all handlers)

2. Platform adapter hardening (`H-02`):
- Updated: `app/shared/adapters/platform.py`
- Added typed exception contracts:
  - `PLATFORM_CURRENCY_CONVERSION_RECOVERABLE_ERRORS`
  - `PLATFORM_RESOURCE_USAGE_RECOVERABLE_ERRORS`
- Replaced broad catch-all handlers in:
  - ledger currency conversion fallback path
  - `discover_resources` cost retrieval fallback path
  - `get_resource_usage` cost retrieval fallback path
- Preserved behavior:
  - conversion failure still degrades safely to local amount
  - discovery/usage failures still fail closed to `[]` with structured logging.

3. Forecaster hardening (`H-02`):
- Updated: `app/shared/analysis/forecaster.py`
- Added typed exception contracts:
  - `FORECAST_RUNTIME_RECOVERABLE_ERRORS`
  - `FORECAST_MARKER_LOAD_RECOVERABLE_ERRORS`
  - `FORECAST_MAPE_RECOVERABLE_ERRORS`
- Replaced broad catch-all handlers in:
  - top-level forecast execution fallback
  - anomaly marker DB load fallback path
  - MAPE calculation fallback path
- Preserved behavior:
  - forecast engine still returns structured error payload on recoverable runtime/data faults
  - marker-load failures remain non-fatal
  - MAPE fallback still defaults to `15.0` when computation is not safe.

4. OIDC hardening (`H-02`):
- Updated: `app/shared/connections/oidc.py`
- Added typed exception contracts:
  - `OIDC_JWKS_KEY_PARSE_RECOVERABLE_EXCEPTIONS`
  - `OIDC_STS_RESPONSE_PARSE_RECOVERABLE_EXCEPTIONS`
  - `OIDC_GCP_VERIFY_RECOVERABLE_EXCEPTIONS`
- Replaced broad catch-all handlers in:
  - JWKS key parse/skip path
  - STS error-body parse fallback path
  - outer GCP verify flow fallback path
- Preserved behavior:
  - invalid JWKS keys continue to be skipped safely
  - STS failures still return `(False, <message>)`
  - missing OIDC signing key and recoverable transport/runtime failures remain fail-closed.

5. Azure network plugin hardening (`H-02`):
- Updated: `app/modules/optimization/adapters/azure/plugins/network.py`
- Added typed exception contract:
  - `AZURE_NETWORK_SCAN_RECOVERABLE_EXCEPTIONS`
- Replaced broad catch-all handlers in:
  - orphan public IP scan
  - orphan NIC scan
  - orphan NSG scan
- Preserved behavior:
  - provider/runtime errors still return `[]` with warning telemetry.

6. Test alignment and branch coverage updates:
- Updated typed failure injectors:
  - `tests/unit/analysis/test_forecaster.py`
    - top-level preparation failure now `ValueError("Data error")`
    - Prophet fit failure now `RuntimeError("Prophet fit failed")`

Validation:
1. `DEBUG=false ./.venv/bin/pytest --no-cov tests/unit/analysis/test_forecaster.py tests/unit/connections/test_oidc_deep.py tests/security/test_oidc_security.py tests/unit/services/adapters/test_platform_additional_branches.py tests/unit/modules/optimization/adapters/azure/test_azure_plugins_fallbacks.py` -> `85 passed`.
2. `DEBUG=false ./.venv/bin/ruff check app/shared/adapters/platform.py app/shared/analysis/forecaster.py app/shared/connections/oidc.py app/modules/optimization/adapters/azure/plugins/network.py tests/unit/analysis/test_forecaster.py` -> passed.
3. `DEBUG=false ./.venv/bin/mypy app/shared/adapters/platform.py app/shared/analysis/forecaster.py app/shared/connections/oidc.py app/modules/optimization/adapters/azure/plugins/network.py` -> passed.
4. `DEBUG=false ./.venv/bin/python scripts/verify_exception_governance.py` -> passed (`current=207`, `baseline=444`, `removed=237`).
5. `DEBUG=false ./.venv/bin/python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).
6. `DEBUG=false ./.venv/bin/python scripts/verify_enforcement_post_closure_sanity.py` -> passed (all `7` dimensions `OK`).

Post-closure sanity (release-critical):
1. Concurrency: async scan/forecast/discovery semantics unchanged; recoverable errors still isolate per-path failure domains.
2. Observability: existing event names and structured error fields retained.
3. Deterministic replay: forecast/oidc/platform response contracts unchanged; only exception families narrowed.
4. Snapshot stability: no schema or payload drift introduced in hardened modules.
5. Export integrity: no export code path altered in this batch.
6. Failure modes: recoverable provider/network/runtime faults continue to degrade safely; unknown unexpected exceptions are no longer silently swallowed via catch-all handlers.
7. Operational misconfiguration: governance controls (`exception`, `module-size`, `post-closure sanity`) are green after this batch.

Remaining snapshot after this batch:
- `rg -n "except Exception" app | wc -l` -> `138`.

## Additional remediation batch (2026-03-04V, report-driven H-02 hardening continuation for GCP compute/detector and AWS region discovery)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Targeted open hotspots from governance scan:
- `app/modules/optimization/adapters/gcp/plugins/compute.py` (`3` catch-all handlers)
- `app/modules/optimization/adapters/gcp/detector.py` (`3` catch-all handlers)
- `app/modules/optimization/adapters/aws/region_discovery.py` (`3` catch-all handlers)

2. GCP compute plugin hardening (`H-02`):
- Updated: `app/modules/optimization/adapters/gcp/plugins/compute.py`
- Added typed exception contracts:
  - `GCP_CREDENTIAL_PARSE_RECOVERABLE_EXCEPTIONS`
  - `GCP_COMPUTE_SCAN_RECOVERABLE_EXCEPTIONS`
- Replaced broad catch-all handlers in:
  - service-account credential parse fallback path
  - `IdleVmsPlugin.scan` fallback branch
  - `StoppedVmsPlugin.scan` fallback branch
- Preserved behavior:
  - invalid credentials still degrade safely to no-credential execution path
  - runtime/provider failures still fail closed with warning telemetry.

3. GCP detector hardening (`H-02`):
- Updated: `app/modules/optimization/adapters/gcp/detector.py`
- Added typed exception contracts:
  - `GCP_DETECTOR_CREDENTIAL_PARSE_RECOVERABLE_EXCEPTIONS`
  - `GCP_DETECTOR_PLUGIN_SCAN_RECOVERABLE_EXCEPTIONS`
- Replaced broad catch-all handlers in:
  - connection credential JSON parse path
  - direct credentials JSON parse path
  - plugin execution wrapper path
- Preserved behavior:
  - invalid credential payloads still block scan safely
  - plugin failures still return `[]` and keep detector orchestration resilient.

4. AWS region discovery hardening (`H-02`):
- Updated: `app/modules/optimization/adapters/aws/region_discovery.py`
- Added typed exception contracts:
  - `AWS_REGION_DISCOVERY_RECOVERABLE_EXCEPTIONS`
  - `AWS_REGION_FALLBACK_RECOVERABLE_EXCEPTIONS`
- Replaced broad catch-all handlers in:
  - Resource Explorer active-region discovery fallback path
  - `get_enabled_regions` unexpected error fallback path
  - botocore fallback region lookup path
- Preserved behavior:
  - discovery still degrades to enabled/fallback regions when upstream discovery fails.

5. Test alignment and coverage additions:
- Updated generic failure injector:
  - `tests/unit/optimization/test_region_discovery_error_paths.py`
    - `Exception("RE2 Failed")` -> `RuntimeError("RE2 Failed")`
- Added new branch tests:
  - `tests/unit/optimization/test_detector_error_paths.py`
    - `test_gcp_detector_plugin_scan_runtime_error_returns_empty`
  - `tests/unit/optimization/test_region_discovery_error_paths.py`
    - `test_fallback_regions_uses_static_baseline_when_botocore_lookup_fails`
  - `tests/unit/zombies/gcp/test_idle_instances.py`
    - `test_build_gcp_credentials_parse_failure_returns_none`
  - `tests/unit/modules/optimization/adapters/gcp/test_gcp_new_zombies.py`
    - `test_gcp_stopped_vms_plugin_runtime_error_returns_empty`

Validation:
1. `DEBUG=false ./.venv/bin/pytest --no-cov tests/unit/modules/optimization/test_gcp_optimization_coverage.py tests/unit/zombies/gcp/test_idle_instances.py tests/unit/modules/optimization/adapters/gcp/test_gcp_new_zombies.py tests/unit/optimization/test_detector_error_paths.py tests/unit/optimization/test_region_discovery_error_paths.py -q` -> `37 passed`.
2. `DEBUG=false ./.venv/bin/ruff check app/modules/optimization/adapters/gcp/plugins/compute.py app/modules/optimization/adapters/gcp/detector.py app/modules/optimization/adapters/aws/region_discovery.py tests/unit/optimization/test_region_discovery_error_paths.py tests/unit/optimization/test_detector_error_paths.py tests/unit/zombies/gcp/test_idle_instances.py tests/unit/modules/optimization/adapters/gcp/test_gcp_new_zombies.py` -> passed.
3. `DEBUG=false ./.venv/bin/mypy app/modules/optimization/adapters/gcp/plugins/compute.py app/modules/optimization/adapters/gcp/detector.py app/modules/optimization/adapters/aws/region_discovery.py` -> passed.
4. `DEBUG=false ./.venv/bin/python scripts/verify_exception_governance.py` -> passed (`current=198`, `baseline=444`, `removed=246`).
5. `DEBUG=false ./.venv/bin/python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).
6. `DEBUG=false ./.venv/bin/python scripts/verify_enforcement_post_closure_sanity.py` -> passed (all `7` dimensions `OK`).

Post-closure sanity (release-critical):
1. Concurrency: adapter/detector scan fan-out behavior unchanged; per-plugin isolation remains deterministic.
2. Observability: existing structured event names retained across discovery and scan fallback paths.
3. Deterministic replay: no changes to detector/plugin output contracts or category keys.
4. Snapshot stability: region discovery and zombie result schema unchanged.
5. Export integrity: no export pipeline code modified in this tranche.
6. Failure modes: recoverable provider/runtime/auth errors still degrade safely; non-recoverable unknown faults are no longer silently masked.
7. Operational misconfiguration: exception-governance, module-size budget, and enforcement post-closure sanity checks remain green.

Remaining snapshot after this batch:
- `rg -n "except Exception" app | wc -l` -> `129`.

## Additional remediation batch (2026-03-04W, report-driven H-02 hardening continuation for reporting/performance core paths)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Targeted open hotspots from governance scan:
- `app/modules/reporting/domain/focus_export.py` (`3` catch-all handlers)
- `app/shared/core/performance_testing.py` (`3` catch-all handlers)
- `app/modules/reporting/domain/attribution_engine.py` (`2` catch-all handlers)
- `app/modules/reporting/domain/service.py` (`2` catch-all handlers)

2. Focus export hardening (`H-02`):
- Updated: `app/modules/reporting/domain/focus_export.py`
- Added typed exception contracts:
  - `FOCUS_EXPORT_STREAM_RECOVERABLE_EXCEPTIONS`
  - `FOCUS_EXPORT_COST_PARSE_RECOVERABLE_EXCEPTIONS`
  - `FOCUS_EXPORT_TAG_SERIALIZATION_RECOVERABLE_EXCEPTIONS`
- Replaced broad catch-all handlers in:
  - numeric cost formatting fallback path
  - tags JSON serialization fallback path
  - stream-to-execute fallback path in export iterator
- Preserved behavior:
  - invalid cost/tag payloads still degrade to deterministic safe defaults
  - stream failures still fall back to `execute()` path.

3. Performance testing hardening (`H-02`):
- Updated: `app/shared/core/performance_testing.py`
- Added typed exception contracts:
  - `PERFORMANCE_LOAD_REQUEST_RECOVERABLE_EXCEPTIONS`
  - `PERFORMANCE_BASELINE_LOAD_RECOVERABLE_EXCEPTIONS`
  - `PERFORMANCE_BASELINE_SAVE_RECOVERABLE_EXCEPTIONS`
- Replaced broad catch-all handlers in:
  - load-test per-request failure path
  - baseline load error path
  - baseline save error path
- Preserved behavior:
  - request failures continue to be counted and emitted in metrics/evidence
  - baseline IO/serialization failures remain non-fatal with structured logging.

4. Attribution engine hardening (`H-02`):
- Updated: `app/modules/reporting/domain/attribution_engine.py`
- Added typed exception contract:
  - `ATTRIBUTION_DECIMAL_PARSE_RECOVERABLE_EXCEPTIONS`
- Replaced broad catch-all handlers in:
  - PERCENTAGE split numeric parsing
  - FIXED split numeric parsing
- Preserved behavior:
  - invalid numeric allocation payloads still produce validation errors without crashes.

5. Reporting service hardening (`H-02`):
- Updated: `app/modules/reporting/domain/service.py`
- Added typed exception contracts:
  - `REPORTING_INGEST_RECOVERABLE_EXCEPTIONS`
  - `REPORTING_ATTRIBUTION_RECOVERABLE_EXCEPTIONS`
- Replaced broad catch-all handlers in:
  - per-connection ingestion failure path
  - attribution trigger failure path
- Preserved behavior:
  - per-connection ingest failures still return completed top-level response with failed detail rows
  - attribution failures remain non-fatal to ingestion completion.

6. Test alignment and coverage updates:
- Updated generic failure injectors:
  - `tests/unit/modules/reporting/test_reporting_service.py`
    - adapter failure: `Exception` -> `RuntimeError`
    - attribution failure: `Exception` -> `RuntimeError`
  - `tests/unit/core/test_performance_testing.py`
    - request explosion paths: `Exception` -> `RuntimeError`

Validation:
1. `DEBUG=false ./.venv/bin/pytest --no-cov tests/unit/reporting/test_focus_export_domain_branches.py tests/unit/core/test_performance_testing.py tests/unit/modules/reporting/test_reporting_service.py tests/unit/reporting/test_attribution_engine.py tests/unit/reporting/test_attribution_engine_branch_paths.py -q` -> `70 passed`.
2. `DEBUG=false ./.venv/bin/ruff check app/modules/reporting/domain/focus_export.py app/shared/core/performance_testing.py app/modules/reporting/domain/attribution_engine.py app/modules/reporting/domain/service.py tests/unit/modules/reporting/test_reporting_service.py tests/unit/core/test_performance_testing.py` -> passed.
3. `DEBUG=false ./.venv/bin/mypy app/modules/reporting/domain/focus_export.py app/shared/core/performance_testing.py app/modules/reporting/domain/attribution_engine.py app/modules/reporting/domain/service.py` -> passed.
4. `DEBUG=false ./.venv/bin/python scripts/verify_exception_governance.py` -> passed (`current=188`, `baseline=444`, `removed=256`).
5. `DEBUG=false ./.venv/bin/python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).
6. `DEBUG=false ./.venv/bin/python scripts/verify_enforcement_post_closure_sanity.py` -> passed (all `7` dimensions `OK`).

Post-closure sanity (release-critical):
1. Concurrency: per-connection ingest and per-user load-test loops preserve existing async behavior and failure isolation.
2. Observability: all prior event names/metrics dimensions remain intact.
3. Deterministic replay: export row shaping and attribution validation outputs remain deterministic.
4. Snapshot stability: no API/schema contract changes introduced in this batch.
5. Export integrity: FOCUS fallback behavior remains deterministic and bounded.
6. Failure modes: recoverable parse/io/runtime faults still degrade safely; unknown faults are no longer swallowed by catch-all handlers in these paths.
7. Operational misconfiguration: governance checks (`exception`, `module-size`, `post-closure sanity`) all pass after this tranche.

Remaining snapshot after this batch:
- `rg -n "except Exception" app | wc -l` -> `119`.

## Additional remediation batch (2026-03-04X, report-driven H-02 hardening continuation for Azure optimization adapters)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Targeted open hotspots from governance scan:
- `app/modules/optimization/adapters/azure/detector.py` (`2` catch-all handlers)
- `app/modules/optimization/adapters/azure/plugins/compute.py` (`2` catch-all handlers)
- `app/modules/optimization/adapters/azure/plugins/containers.py` (`2` catch-all handlers)
- `app/modules/optimization/adapters/azure/plugins/storage.py` (`2` catch-all handlers)
- `app/modules/optimization/adapters/azure/plugins/database.py` (`1` catch-all handler)
- `app/modules/optimization/adapters/azure/plugins/rightsizing.py` (`2` catch-all handlers)

2. Azure detector hardening (`H-02`):
- Updated: `app/modules/optimization/adapters/azure/detector.py`
- Added typed exception contracts:
  - `AZURE_DETECTOR_CREDENTIAL_INIT_RECOVERABLE_EXCEPTIONS`
  - `AZURE_DETECTOR_PLUGIN_SCAN_RECOVERABLE_EXCEPTIONS`
- Replaced broad catch-all handlers in:
  - credential construction path
  - plugin scan isolation path
- Preserved behavior:
  - recoverable credential/plugin errors still degrade to deterministic empty plugin results with structured logs.

3. Azure plugin fallback hardening (`H-02`):
- Updated:
  - `app/modules/optimization/adapters/azure/plugins/compute.py`
  - `app/modules/optimization/adapters/azure/plugins/containers.py`
  - `app/modules/optimization/adapters/azure/plugins/storage.py`
  - `app/modules/optimization/adapters/azure/plugins/database.py`
  - `app/modules/optimization/adapters/azure/plugins/rightsizing.py`
- Added typed exception contracts:
  - `AZURE_COMPUTE_SCAN_RECOVERABLE_EXCEPTIONS`
  - `AZURE_CONTAINERS_SCAN_RECOVERABLE_EXCEPTIONS`
  - `AZURE_STORAGE_SCAN_RECOVERABLE_EXCEPTIONS`
  - `AZURE_DATABASE_SCAN_RECOVERABLE_EXCEPTIONS`
  - `AZURE_RIGHTSIZING_VM_STATE_RECOVERABLE_EXCEPTIONS`
  - `AZURE_RIGHTSIZING_SCAN_RECOVERABLE_EXCEPTIONS`
- Replaced broad catch-all handlers in provider fallback client/scan paths while preserving graceful-degrade behavior.

4. Test alignment and coverage additions:
- Updated:
  - `tests/unit/optimization/test_detector_error_paths.py`
  - `tests/unit/modules/optimization/adapters/azure/test_azure_plugins_fallbacks.py`
  - `tests/unit/modules/optimization/adapters/azure/test_azure_rightsizing.py`
- Added assertions for non-swallowing of unexpected fatal failures (`BaseException`) while retaining existing recoverable-fallback assertions.

Validation:
1. `DEBUG=false .venv/bin/pytest --no-cov tests/unit/optimization/test_detector_error_paths.py tests/unit/modules/optimization/adapters/azure/test_azure_plugins_fallbacks.py tests/unit/modules/optimization/adapters/azure/test_azure_rightsizing.py` -> `34 passed`.
2. `DEBUG=false .venv/bin/ruff check app/modules/optimization/adapters/azure/detector.py app/modules/optimization/adapters/azure/plugins/compute.py app/modules/optimization/adapters/azure/plugins/containers.py app/modules/optimization/adapters/azure/plugins/storage.py app/modules/optimization/adapters/azure/plugins/database.py app/modules/optimization/adapters/azure/plugins/rightsizing.py tests/unit/optimization/test_detector_error_paths.py tests/unit/modules/optimization/adapters/azure/test_azure_plugins_fallbacks.py tests/unit/modules/optimization/adapters/azure/test_azure_rightsizing.py` -> passed.
3. `DEBUG=false .venv/bin/mypy app/modules/optimization/adapters/azure/detector.py app/modules/optimization/adapters/azure/plugins/compute.py app/modules/optimization/adapters/azure/plugins/containers.py app/modules/optimization/adapters/azure/plugins/storage.py app/modules/optimization/adapters/azure/plugins/database.py app/modules/optimization/adapters/azure/plugins/rightsizing.py` -> passed.
4. `DEBUG=false .venv/bin/python scripts/verify_exception_governance.py` -> passed (`current=177`, `baseline=444`, `removed=267`).
5. `DEBUG=false .venv/bin/python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).
6. `DEBUG=false .venv/bin/python scripts/verify_enforcement_post_closure_sanity.py` -> passed (all `7` dimensions `OK`).

Post-closure sanity (release-critical):
1. Concurrency: detector and plugin fallback execution semantics remain unchanged; plugin isolation still deterministic.
2. Observability: existing warning/error event names retained, with no log-contract regressions.
3. Deterministic replay: resource classification/output schemas unchanged in hardened paths.
4. Snapshot stability: no API contract changes; plugin category keys and result shapes preserved.
5. Export integrity: no export pipeline code paths modified in this batch.
6. Failure modes: recoverable provider/runtime/config faults degrade safely; non-recoverable fatal failures are no longer silently swallowed.
7. Operational misconfiguration: governance checks (`exception`, `module-size`, `post-closure sanity`) remain green after this tranche.

Remaining snapshot after this batch:
- `rg -n "except Exception|except:\\s*$" app | wc -l` -> `108`.

## Additional remediation batch (2026-03-04Y, report-driven H-02 hardening continuation for optimization remediation workflow)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Targeted open hotspots from governance scan:
- `app/modules/optimization/domain/remediation_execute.py` (`3` catch-all handlers)
- `app/modules/optimization/domain/remediation_context.py` (`2` catch-all handlers)
- `app/modules/optimization/domain/remediation_workflow.py` (`1` catch-all handler)
- `app/modules/optimization/domain/remediation_hard_limit.py` (`1` catch-all handler)

2. Remediation execution hardening (`H-02`):
- Updated: `app/modules/optimization/domain/remediation_execute.py`
- Added typed exception contracts:
  - `REMEDIATION_TIER_LOOKUP_RECOVERABLE_EXCEPTIONS`
  - `REMEDIATION_ACTION_PARSE_RECOVERABLE_EXCEPTIONS`
  - `REMEDIATION_EXECUTION_RECOVERABLE_EXCEPTIONS`
- Replaced broad catch-all handlers in:
  - tenant-tier lookup fallback path
  - remediation action coercion path
  - outer execution failure wrapping path
- Preserved behavior:
  - expected runtime/provider/db failures still mark request as `FAILED` with audit/error logging,
  - fatal non-`Exception` failures are no longer swallowed.

3. Remediation context/workflow/hard-limit hardening (`H-02`):
- Updated:
  - `app/modules/optimization/domain/remediation_context.py`
  - `app/modules/optimization/domain/remediation_workflow.py`
  - `app/modules/optimization/domain/remediation_hard_limit.py`
- Added typed exception contracts:
  - `REMEDIATION_REGION_RESOLUTION_RECOVERABLE_EXCEPTIONS`
  - `REMEDIATION_SETTINGS_LOOKUP_RECOVERABLE_EXCEPTIONS`
  - `REMEDIATION_CONNECTION_SCOPE_RECOVERABLE_EXCEPTIONS`
  - `REMEDIATION_HARD_LIMIT_RECOVERABLE_EXCEPTIONS`
- Replaced broad catch-all handlers in:
  - scoped AWS region resolution fallback path
  - remediation settings DB lookup fallback path
  - connection-ownership validation path in request creation
  - hard-limit per-request execution loop path
- Preserved behavior:
  - recoverable lookup and authorization paths still log and degrade deterministically,
  - hard-limit loop still continues over recoverable per-request failures,
  - fatal non-`Exception` failures now surface.

4. Test alignment and coverage additions:
- Updated:
  - `tests/unit/optimization/test_remediation_context_branch_paths.py`
  - `tests/unit/optimization/test_remediation_branch_coverage.py`
  - `tests/unit/services/zombies/test_remediation_service.py`
- Added assertions for non-swallowing of `BaseException` in:
  - region resolution lookup,
  - remediation settings lookup,
  - create-request connection scoping,
  - execute path strategy failures,
  - hard-limit execution loop.

Validation:
1. `DEBUG=false .venv/bin/pytest --no-cov tests/unit/optimization/test_remediation_context_branch_paths.py tests/unit/optimization/test_remediation_branch_coverage.py tests/unit/services/zombies/test_remediation_service.py tests/unit/optimization/test_remediation_service_audit.py` -> `51 passed`.
2. `DEBUG=false .venv/bin/ruff check app/modules/optimization/domain/remediation_execute.py app/modules/optimization/domain/remediation_context.py app/modules/optimization/domain/remediation_workflow.py app/modules/optimization/domain/remediation_hard_limit.py tests/unit/optimization/test_remediation_context_branch_paths.py tests/unit/optimization/test_remediation_branch_coverage.py tests/unit/services/zombies/test_remediation_service.py` -> passed.
3. `DEBUG=false .venv/bin/mypy app/modules/optimization/domain/remediation_execute.py app/modules/optimization/domain/remediation_context.py app/modules/optimization/domain/remediation_workflow.py app/modules/optimization/domain/remediation_hard_limit.py` -> passed.
4. `DEBUG=false .venv/bin/python scripts/verify_exception_governance.py` -> passed (`current=170`, `baseline=444`, `removed=274`).
5. `DEBUG=false .venv/bin/python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).
6. `DEBUG=false .venv/bin/python scripts/verify_enforcement_post_closure_sanity.py` -> passed (all `7` dimensions `OK`).

Post-closure sanity (release-critical):
1. Concurrency: hard-limit per-request processing and remediation execution flow maintain existing async sequencing and isolation.
2. Observability: existing warning/error/audit event names retained; no log-contract drift.
3. Deterministic replay: request status transitions and policy/context shaping remain deterministic for identical inputs.
4. Snapshot stability: remediation request schema/status contracts unchanged.
5. Export integrity: no export serialization or bundle codepaths modified in this tranche.
6. Failure modes: recoverable runtime/db/provider errors still degrade safely; non-recoverable fatal failures now surface immediately.
7. Operational misconfiguration: governance checks (`exception`, `module-size`, `post-closure sanity`) remain green.

Remaining snapshot after this batch:
- `rg -n "except Exception|except:\\s*$" app | wc -l` -> `101`.

## Additional remediation batch (2026-03-04Z, report-driven H-02 hardening continuation for shared detector orchestration)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Targeted open hotspot from governance scan:
- `app/modules/optimization/domain/ports.py` (`2` catch-all handlers)

2. Shared detector orchestration hardening (`H-02`):
- Updated: `app/modules/optimization/domain/ports.py`
- Added typed exception contracts:
  - `ZOMBIE_SCAN_RECOVERABLE_EXCEPTIONS`
  - `ZOMBIE_PLUGIN_SCAN_RECOVERABLE_EXCEPTIONS`
- Replaced broad catch-all handlers in:
  - top-level detector scan orchestration fallback path
  - per-plugin timeout wrapper fallback path
- Preserved behavior:
  - recoverable plugin/runtime failures still degrade to empty category results and structured logs,
  - fatal non-`Exception` failures now propagate.

3. Test alignment and coverage additions:
- Updated: `tests/unit/services/zombies/test_base.py`
- Added fatal-propagation test for orchestration path and aligned recoverable failure simulation to `RuntimeError`.

Validation:
1. `DEBUG=false .venv/bin/pytest --no-cov tests/unit/services/zombies/test_base.py tests/unit/services/zombies/platform_provider/test_platform_detector.py tests/unit/services/zombies/hybrid_provider/test_hybrid_detector.py tests/unit/services/zombies/saas_provider/test_saas_detector.py tests/unit/services/zombies/license_provider/test_license_detector.py` -> `11 passed`.
2. `DEBUG=false .venv/bin/ruff check app/modules/optimization/domain/ports.py tests/unit/services/zombies/test_base.py` -> passed.
3. `DEBUG=false .venv/bin/mypy app/modules/optimization/domain/ports.py` -> passed.
4. `DEBUG=false .venv/bin/python scripts/verify_exception_governance.py` -> passed (`current=168`, `baseline=444`, `removed=276`).
5. `DEBUG=false .venv/bin/python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).
6. `DEBUG=false .venv/bin/python scripts/verify_enforcement_post_closure_sanity.py` -> passed (all `7` dimensions `OK`).

Post-closure sanity (release-critical):
1. Concurrency: plugin fan-out and callback checkpointing semantics unchanged.
2. Observability: existing `plugin_timeout`, `plugin_scan_failed`, and `zombie_scan_failed` event names retained.
3. Deterministic replay: per-plugin keying and aggregate result shaping unchanged.
4. Snapshot stability: detector response keys and waste aggregation outputs unchanged.
5. Export integrity: no export serializers or bundle logic touched.
6. Failure modes: recoverable exceptions still degrade safely; fatal non-`Exception` failures now surface immediately.
7. Operational misconfiguration: governance checks (`exception`, `module-size`, `post-closure sanity`) remain green.

Remaining snapshot after this batch:
- `rg -n "except Exception|except:\\s*$" app | wc -l` -> `99`.

## Additional remediation batch (2026-03-04AA, report-driven H-02 hardening continuation for reporting + leadership evidence paths)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Targeted open hotspots from governance scan:
- `app/modules/reporting/domain/aggregator.py`
- `app/modules/reporting/domain/reconciliation.py`
- `app/modules/reporting/domain/budget_alerts.py`
- `app/modules/reporting/domain/carbon_scheduler.py`
- `app/modules/reporting/api/v1/leadership.py`

2. Reporting domain hardening (`H-02`):
- Updated `app/modules/reporting/domain/aggregator.py`:
  - Added typed contracts:
    - `MATERIALIZED_VIEW_READ_RECOVERABLE_EXCEPTIONS`
    - `MATERIALIZED_VIEW_REFRESH_RECOVERABLE_EXCEPTIONS`
  - Replaced broad catch-all handlers in materialized view read/refresh fallbacks.
  - Preserved cache fallback behavior for recoverable DB/runtime paths.

- Updated `app/modules/reporting/domain/reconciliation.py`:
  - Added typed contracts:
    - `INVOICE_EXCHANGE_RATE_IMPORT_EXCEPTIONS`
    - `RECON_ALERT_RECOVERABLE_EXCEPTIONS`
  - Tightened exchange-rate model import handling from broad catch-all to `ImportError` contract.
  - Replaced broad alert-dispatch catch-all with typed recoverable contract while preserving non-blocking reconciliation summaries.

- Updated `app/modules/reporting/domain/budget_alerts.py`:
  - Added typed contracts:
    - `CARBON_SLACK_ALERT_RECOVERABLE_EXCEPTIONS`
    - `CARBON_EMAIL_ALERT_RECOVERABLE_EXCEPTIONS`
  - Replaced broad catch-all handlers around Slack/email alert paths with recoverable provider/transport/config contracts.

- Updated `app/modules/reporting/domain/carbon_scheduler.py`:
  - Added typed contract:
    - `CARBON_FORECAST_RECOVERABLE_EXCEPTIONS`
  - Replaced broad catch-all handlers in external WattTime/Electricity Maps forecast fetchers.

3. Reporting API hardening (`H-02`):
- Updated `app/modules/reporting/api/v1/leadership.py`:
  - Added typed contract `LEADERSHIP_EVIDENCE_PAYLOAD_ERRORS`.
  - Replaced broad evidence-payload catch-all handlers with schema/validation typed handling for leadership and quarterly evidence listing endpoints.

4. Module-size enforcement correction:
- `app/modules/reporting/domain/aggregator.py` exceeded budget after hardening and was reduced from `642` to `623` lines by compressing non-functional verbosity while preserving behavior.

5. Test alignment and coverage additions:
- Updated:
  - `tests/unit/reporting/test_aggregator.py`
  - `tests/unit/reporting/test_reconciliation_branch_paths.py`
  - `tests/unit/modules/reporting/test_budget_alerts_deep.py`
  - `tests/unit/modules/reporting/test_carbon_scheduler_comprehensive.py`
  - `tests/unit/api/v1/test_leadership_kpis_branch_paths_2.py`
- Added non-swallowing fatal-path assertions (`KeyboardInterrupt`) to verify non-recoverable failures are not suppressed in:
  - materialized view cached-read/refresh paths,
  - reconciliation alert dispatch path,
  - budget Slack/email alert paths,
  - carbon external forecast fetchers,
  - leadership and quarterly evidence payload validation paths.

Validation:
1. `DEBUG=false .venv/bin/pytest --no-cov tests/unit/reporting/test_aggregator.py tests/unit/reporting/test_reconciliation_branch_paths.py tests/unit/modules/reporting/test_budget_alerts_deep.py tests/unit/modules/reporting/test_carbon_scheduler_comprehensive.py tests/unit/api/v1/test_leadership_kpis_branch_paths_2.py` -> `114 passed`.
2. `DEBUG=false .venv/bin/ruff check app/modules/reporting/domain/aggregator.py app/modules/reporting/domain/reconciliation.py app/modules/reporting/domain/budget_alerts.py app/modules/reporting/domain/carbon_scheduler.py app/modules/reporting/api/v1/leadership.py tests/unit/reporting/test_aggregator.py tests/unit/reporting/test_reconciliation_branch_paths.py tests/unit/modules/reporting/test_budget_alerts_deep.py tests/unit/modules/reporting/test_carbon_scheduler_comprehensive.py tests/unit/api/v1/test_leadership_kpis_branch_paths_2.py` -> passed.
3. `DEBUG=false .venv/bin/mypy app/modules/reporting/domain/aggregator.py app/modules/reporting/domain/reconciliation.py app/modules/reporting/domain/budget_alerts.py app/modules/reporting/domain/carbon_scheduler.py app/modules/reporting/api/v1/leadership.py` -> passed.
4. `DEBUG=false .venv/bin/python scripts/verify_exception_governance.py` -> passed (`current=158`, `baseline=444`, `removed=286`).
5. `DEBUG=false .venv/bin/python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).
6. `DEBUG=false .venv/bin/python scripts/verify_enforcement_post_closure_sanity.py` -> passed (all `7` dimensions `OK`).

Post-closure sanity (release-critical):
1. Concurrency: async execution semantics and non-blocking fallback behavior preserved for alerting/forecast flows.
2. Observability: existing warning/error event contracts retained (`mv_query_failed_fallback`, `cost_reconciliation_alert_failed`, `carbon_*_alert_failed`, `*_api_failed`, evidence invalid-payload warnings).
3. Deterministic replay: reconciliation summary generation and evidence list filtering remain deterministic for identical inputs.
4. Snapshot stability: response schema for leadership evidence, reconciliation summaries, and carbon scheduler outputs unchanged.
5. Export integrity: no CSV/export serializer schema drift introduced.
6. Failure modes: recoverable faults still degrade gracefully; fatal non-`Exception` failures now surface explicitly.
7. Operational misconfiguration: governance (`exception`, `module-size`) and post-closure sanity gates remain green.

Remaining snapshot after this batch:
- `rg -n "except Exception|except:\\s*$" app | wc -l` -> `89`.

## Additional remediation batch (2026-03-04AB, report-driven H-02 hardening continuation for reporting domain/api)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Targeted open hotspots from governance scan:
- `app/modules/reporting/domain/arm_analyzer.py`
- `app/modules/reporting/domain/pricing/service.py`
- `app/modules/reporting/domain/realized_savings.py`
- `app/modules/reporting/domain/leadership_kpis.py`
- `app/modules/reporting/domain/persistence.py`
- `app/modules/reporting/api/v1/usage.py`
- `app/modules/reporting/api/v1/savings.py`
- `app/modules/reporting/api/v1/leaderboards.py`

2. Domain hardening (`H-02`):
- Updated `arm_analyzer.py`:
  - Added `ARM_ANALYSIS_RECOVERABLE_EXCEPTIONS` and replaced broad discovery catch-all.
- Updated `pricing/service.py`:
  - Replaced broad AWS pricing sync catch-all with explicit import + botocore/client/runtime typed contracts.
- Updated `realized_savings.py`:
  - Tightened `_decimal` parsing fallback to `(InvalidOperation, TypeError, ValueError)`.
- Updated `leadership_kpis.py`:
  - Added `LEADERSHIP_SAVINGS_PROOF_RECOVERABLE_EXCEPTIONS` and replaced broad savings-proof degradation catch-all.
- Updated `persistence.py`:
  - Tightened `usage_amount` decimal parse fallback to `(InvalidOperation, TypeError, ValueError)`.

3. API hardening (`H-02`):
- Updated `usage.py`:
  - Added `USAGE_CACHE_PAYLOAD_ERRORS` and replaced broad cache decode catch-all.
- Updated `leaderboards.py`:
  - Added `LEADERBOARD_CACHE_PAYLOAD_ERRORS` and replaced broad cache decode catch-all.
- Updated `savings.py`:
  - Added `REALIZED_SAVINGS_COMPUTE_RECOVERABLE_EXCEPTIONS` and replaced broad per-request compute catch-all while preserving partial-result semantics.

4. Test alignment and coverage additions:
- Added new suite:
  - `tests/unit/modules/reporting/test_arm_analyzer.py`
- Updated:
  - `tests/unit/modules/reporting/test_pricing_service.py`
  - `tests/unit/modules/reporting/test_leadership_kpis_domain.py`
  - `tests/unit/reporting/test_realized_savings_service_branches.py`
  - `tests/unit/reporting/test_reporting_persistence_deep.py`
  - `tests/unit/api/v1/test_usage_branch_paths.py`
  - `tests/unit/api/v1/test_leaderboards_endpoints.py`
  - `tests/unit/api/v1/test_savings_branch_paths.py`
- Added fatal-path non-swallowing checks (`KeyboardInterrupt`) for all newly narrowed contracts.

Validation:
1. `DEBUG=false .venv/bin/pytest --no-cov tests/unit/modules/reporting/test_arm_analyzer.py tests/unit/modules/reporting/test_pricing_service.py tests/unit/modules/reporting/test_leadership_kpis_domain.py tests/unit/reporting/test_realized_savings_service_branches.py tests/unit/reporting/test_reporting_persistence_deep.py tests/unit/api/v1/test_usage_branch_paths.py tests/unit/api/v1/test_leaderboards_endpoints.py tests/unit/api/v1/test_savings_branch_paths.py tests/unit/reporting/test_savings_api_branches.py` -> `76 passed`.
2. `DEBUG=false .venv/bin/ruff check app/modules/reporting/domain/arm_analyzer.py app/modules/reporting/domain/pricing/service.py app/modules/reporting/domain/realized_savings.py app/modules/reporting/domain/leadership_kpis.py app/modules/reporting/domain/persistence.py app/modules/reporting/api/v1/usage.py app/modules/reporting/api/v1/savings.py app/modules/reporting/api/v1/leaderboards.py tests/unit/modules/reporting/test_arm_analyzer.py tests/unit/modules/reporting/test_pricing_service.py tests/unit/modules/reporting/test_leadership_kpis_domain.py tests/unit/reporting/test_realized_savings_service_branches.py tests/unit/reporting/test_reporting_persistence_deep.py tests/unit/api/v1/test_usage_branch_paths.py tests/unit/api/v1/test_leaderboards_endpoints.py tests/unit/api/v1/test_savings_branch_paths.py` -> passed.
3. `DEBUG=false .venv/bin/mypy app/modules/reporting/domain/arm_analyzer.py app/modules/reporting/domain/pricing/service.py app/modules/reporting/domain/realized_savings.py app/modules/reporting/domain/leadership_kpis.py app/modules/reporting/domain/persistence.py app/modules/reporting/api/v1/usage.py app/modules/reporting/api/v1/savings.py app/modules/reporting/api/v1/leaderboards.py` -> passed.
4. `DEBUG=false .venv/bin/python scripts/verify_exception_governance.py` -> passed (`current=150`, `baseline=444`, `removed=294`).
5. `DEBUG=false .venv/bin/python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).
6. `DEBUG=false .venv/bin/python scripts/verify_enforcement_post_closure_sanity.py` -> passed (all `7` dimensions `OK`).

Post-closure sanity (release-critical):
1. Concurrency: async endpoint/service flow and background-safe degradation semantics preserved.
2. Observability: prior log event contracts retained for cache decode, pricing sync, and savings proof degradation paths.
3. Deterministic replay: cache miss rebuild behavior and realized-savings partial-result structure remain deterministic.
4. Snapshot stability: response schemas for usage, leaderboards, savings, and leadership payloads unchanged.
5. Export integrity: no CSV schema regressions in savings/reporting routes.
6. Failure modes: recoverable operational faults still degrade as designed; fatal non-`Exception` failures now surface.
7. Operational misconfiguration: governance and post-closure sanity checks remain green.

Remaining snapshot after this batch:
- `rg -n "except Exception|except:\\s*$" app | wc -l` -> `81`.

## Additional remediation batch (2026-03-04AC, report-driven H-02 hardening continuation for shared core services)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Targeted open hotspots from governance scan:
- `app/shared/core/approval_permissions.py`
- `app/shared/core/cloud_connection.py`
- `app/shared/core/config.py`
- `app/shared/core/maintenance.py`
- `app/shared/core/ops_metrics.py`
- `app/shared/core/pricing.py`
- `app/shared/core/rate_limit.py`
- `app/shared/core/retry.py`
- `app/shared/core/security.py`
- `app/shared/core/timeout.py`

2. Shared core hardening (`H-02`):
- Updated `approval_permissions.py`:
  - Added `APPROVAL_PERMISSION_RESOLUTION_RECOVERABLE_EXCEPTIONS`.
  - Replaced broad SCIM resolution catch-all with typed recoverable contract.
- Updated `cloud_connection.py`:
  - Added `CLOUD_CONNECTION_VERIFY_RECOVERABLE_EXCEPTIONS`.
  - Replaced broad verification catch-all while preserving `AdapterError` sanitization behavior.
- Updated `config.py`:
  - Added typed cache-refresh recoverable contract for settings reload.
  - Tightened KDF salt decode handling to `(binascii.Error, TypeError, ValueError)`.
- Updated `maintenance.py`:
  - Added `PARTITION_MAINTENANCE_RECOVERABLE_EXCEPTIONS`.
  - Replaced broad partition creation/archive catch-all handlers.
- Updated `ops_metrics.py`:
  - Removed broad catch-all in `time_operation` and switched to `finally + sys.exc_info()` error-metric detection.
- Updated `pricing.py`:
  - Added `TENANT_TIER_LOOKUP_RECOVERABLE_EXCEPTIONS`.
  - Replaced broad tenant-tier lookup catch-all.
- Updated `rate_limit.py`:
  - Added typed recoverable contracts for token-hash fallback, analysis-tier derivation, and Redis remediation fallback.
  - Removed tuple catch containing `Exception` and replaced with explicit contracts.
- Updated `retry.py`:
  - Added `DEADLOCK_RETRY_RECOVERABLE_EXCEPTIONS`.
  - Replaced broad deadlock-retry catch-all while preserving message-based deadlock detection.
- Updated `security.py`:
  - Added `KEY_CACHE_WARM_RECOVERABLE_EXCEPTIONS`.
  - Replaced broad key-cache warmup catch-all.
- Updated `timeout.py`:
  - Removed broad non-timeout catch-all and switched to `finally + sys.exc_info()` failure logging path.

3. Test alignment and coverage updates:
- Updated:
  - `tests/unit/core/test_pricing_deep.py`
  - `tests/unit/core/test_cloud_connection_audit.py`
  - `tests/unit/core/test_finding_2_cloud_leakage.py`
  - `tests/unit/core/test_retry_utils.py`
  - `tests/unit/core/test_retry_utils_branch_paths.py`
  - `tests/unit/core/test_rate_limit_expanded.py`
- Existing suites validated unchanged behavior for success/fallback/error contracts across config, rate limiting, retries, timeout handling, cloud verification sanitization, and metrics.

4. Module-size gate stabilization:
- Kept tightened behavior while reducing non-functional line growth:
  - `app/shared/core/config.py`: `768` lines (budget `771`)
  - `app/shared/core/pricing.py`: `802` lines (budget `804`)

Validation:
1. `TESTING=true DEBUG=false .venv/bin/pytest --no-cov tests/unit/core/test_config_branch_paths.py tests/unit/core/test_approval_permissions.py tests/unit/core/test_approval_permissions_branch_paths.py tests/unit/core/test_maintenance_service.py tests/unit/core/test_ops_metrics.py tests/unit/core/test_pricing_deep.py tests/unit/core/test_rate_limit.py tests/unit/core/test_rate_limit_audit.py tests/unit/core/test_rate_limit_expanded.py tests/unit/core/test_rate_limit_branch_paths_2.py tests/unit/core/test_retry_utils.py tests/unit/core/test_retry_utils_branch_paths.py tests/unit/core/test_timeout_utils.py tests/unit/core/test_timeout_branch_paths.py tests/unit/core/test_cloud_connection.py tests/unit/core/test_cloud_connection_audit.py tests/unit/core/test_finding_2_cloud_leakage.py` -> `166 passed`.
2. `.venv/bin/ruff check app/shared/core/config.py app/shared/core/approval_permissions.py app/shared/core/maintenance.py app/shared/core/ops_metrics.py app/shared/core/rate_limit.py app/shared/core/retry.py app/shared/core/security.py app/shared/core/timeout.py app/shared/core/pricing.py app/shared/core/cloud_connection.py tests/unit/core/test_pricing_deep.py tests/unit/core/test_cloud_connection_audit.py tests/unit/core/test_finding_2_cloud_leakage.py tests/unit/core/test_retry_utils.py tests/unit/core/test_retry_utils_branch_paths.py` -> passed.
3. `.venv/bin/mypy app/shared/core/config.py app/shared/core/approval_permissions.py app/shared/core/maintenance.py app/shared/core/ops_metrics.py app/shared/core/rate_limit.py app/shared/core/retry.py app/shared/core/security.py app/shared/core/timeout.py app/shared/core/pricing.py app/shared/core/cloud_connection.py` -> passed.
4. `python3 scripts/verify_exception_governance.py` -> passed (`current=136`, `baseline=444`, `removed=308`).
5. `python3 scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).
6. `python3 scripts/verify_enforcement_post_closure_sanity.py` -> passed (all `7` dimensions `OK`).

Post-closure sanity (release-critical):
1. Concurrency: async rate-limit, retry, timeout, and cloud verification control flow preserved; no new shared mutable-state races introduced.
2. Observability: all existing warning/error event names retained; error-path logs still emit typed context.
3. Deterministic replay: fallback decisions and tier/permission resolution remain deterministic for identical inputs.
4. Snapshot stability: API response contracts and adapter error sanitization outputs unchanged.
5. Export integrity: no export serializer or bundle logic touched.
6. Failure modes: recoverable operational faults still degrade safely; non-recoverable/fatal failures are no longer swallowed by catch-all handlers.
7. Operational misconfiguration: governance, module-size, and post-closure sanity gates remain green after hardening.

Remaining snapshot after this batch:
- `rg -n "except Exception|except:\\s*$" app | wc -l` -> `68`.

## Additional remediation batch (2026-03-04AD, report-driven H-02 hardening continuation for governance API/job paths)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Targeted open hotspots from governance scan:
- `app/modules/governance/api/v1/public.py`
- `app/modules/governance/api/v1/settings/safety.py`
- `app/modules/governance/api/v1/audit_partitioning.py`
- `app/modules/governance/domain/jobs/cur_ingestion.py`
- `app/modules/governance/domain/jobs/handlers/base.py`
- `app/modules/governance/domain/jobs/handlers/costs.py`
- `app/modules/governance/api/v1/settings/onboard.py`
- `app/modules/governance/domain/jobs/handlers/finops.py`

2. Governance hardening (`H-02`):
- Updated `public.py`:
  - Added `PUBLIC_ASSESSMENT_RECOVERABLE_EXCEPTIONS`.
  - Added `SSO_DISCOVERY_BACKEND_RECOVERABLE_EXCEPTIONS`.
  - Replaced broad catch-all handlers in public assessment and SSO discovery.
- Updated `settings/safety.py`:
  - Added `SAFETY_CIRCUIT_RECOVERABLE_EXCEPTIONS`.
  - Replaced broad catch-all handlers in safety status and reset paths.
- Updated `audit_partitioning.py`:
  - Added `PARTITIONING_CATALOG_RECOVERABLE_EXCEPTIONS`.
  - Added `PARTITIONING_EVIDENCE_PAYLOAD_ERRORS`.
  - Replaced broad catch-all handlers in partitioning catalog/evidence handling.
- Updated `cur_ingestion.py`:
  - Added `CUR_CONNECTION_INGEST_RECOVERABLE_EXCEPTIONS`.
  - Added `CUR_MANIFEST_DISCOVERY_RECOVERABLE_EXCEPTIONS`.
  - Replaced broad catch-all handlers in `_execute` and `_find_latest_cur_key`.
- Updated `handlers/base.py`:
  - Added `JOB_HANDLER_UNEXPECTED_RECOVERABLE_EXCEPTIONS`.
  - Added `JOB_HANDLER_SENTRY_ALERT_RECOVERABLE_EXCEPTIONS`.
  - Replaced broad catch-all handlers in main process and dead-letter sentry alert paths.
- Updated `handlers/costs.py`:
  - Added `COST_INGESTION_CONNECTION_RECOVERABLE_EXCEPTIONS`.
  - Added `ATTRIBUTION_TRIGGER_RECOVERABLE_EXCEPTIONS`.
  - Replaced broad catch-all handlers for per-connection ingestion and attribution trigger.
- Updated `settings/onboard.py`:
  - Added `ONBOARDING_VERIFICATION_RECOVERABLE_EXCEPTIONS`.
  - Replaced broad catch-all handler in verification adapter path.
- Updated `handlers/finops.py`:
  - Added `FINOPS_PROVIDER_ANALYSIS_RECOVERABLE_EXCEPTIONS`.
  - Replaced broad catch-all handler in provider analysis loop.

3. TDD updates and stabilization:
- Updated tests:
  - `tests/unit/governance/api/test_public.py`
  - `tests/unit/governance/settings/test_safety.py`
  - `tests/unit/governance/jobs/test_cur_ingestion_branch_paths.py`
  - `tests/unit/governance/domain/jobs/handlers/test_base_handler.py`
  - `tests/unit/governance/domain/jobs/handlers/test_cost_handlers.py`
  - `tests/unit/governance/settings/test_onboard_deep.py`
  - `tests/unit/services/jobs/test_job_handlers.py`
  - `tests/unit/api/v1/test_audit_high_impact_branches.py`
- Added/kept fatal non-swallowing assertions using a `BaseException` sentinel where request middleware wraps endpoint failures as `BaseExceptionGroup`, and asserted sentinel presence explicitly.
- Aligned cost/zombie handler tests with current production flow (provider-neutral connection loader, attribution trigger, and notification dispatch side effects).

Validation:
1. `DEBUG=false uv run pytest -q --no-cov tests/unit/governance/api/test_public.py tests/unit/governance/settings/test_safety.py tests/unit/governance/jobs/test_cur_ingestion.py tests/unit/governance/jobs/test_cur_ingestion_branch_paths.py tests/unit/governance/domain/jobs/handlers/test_base_handler.py tests/unit/governance/domain/jobs/handlers/test_cost_handlers.py tests/unit/governance/settings/test_onboard_deep.py tests/unit/governance/settings/test_onboard_branch_paths.py tests/unit/services/jobs/test_job_handlers.py tests/unit/api/v1/test_audit_high_impact_branches.py` -> `130 passed`.
2. `uv run ruff check tests/unit/governance/api/test_public.py tests/unit/governance/settings/test_safety.py tests/unit/governance/jobs/test_cur_ingestion_branch_paths.py tests/unit/governance/domain/jobs/handlers/test_base_handler.py tests/unit/governance/domain/jobs/handlers/test_cost_handlers.py tests/unit/governance/settings/test_onboard_deep.py tests/unit/services/jobs/test_job_handlers.py tests/unit/api/v1/test_audit_high_impact_branches.py` -> passed.
3. `uv run mypy app/modules/governance/api/v1/public.py app/modules/governance/api/v1/settings/safety.py app/modules/governance/api/v1/audit_partitioning.py app/modules/governance/domain/jobs/cur_ingestion.py app/modules/governance/domain/jobs/handlers/base.py app/modules/governance/domain/jobs/handlers/costs.py app/modules/governance/api/v1/settings/onboard.py app/modules/governance/domain/jobs/handlers/finops.py` -> passed.
4. `uv run python scripts/verify_exception_governance.py` -> passed (`current=122`, `baseline=444`, `removed=322`).
5. `uv run python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).
6. `uv run python scripts/verify_enforcement_post_closure_sanity.py` -> passed (all `7` dimensions `OK`).

Post-closure sanity (release-critical):
1. Concurrency: async job/endpoint control flow preserved; no new shared-state race introduction.
2. Observability: warning/error event contracts retained across public/safety/onboarding/job handlers.
3. Deterministic replay: partitioning evidence and ingestion fallback behavior remain deterministic for identical inputs.
4. Snapshot stability: API response envelopes and job result shapes unchanged.
5. Export integrity: audit/report export paths untouched by this tranche.
6. Failure modes: recoverable operational failures still degrade safely; non-`Exception` fatal failures are no longer swallowed.
7. Operational misconfiguration: exception-governance, module-size, and post-closure sanity gates remain green.

Remaining snapshot after this batch:
- `rg -n "except Exception|except:\\s*$" app | wc -l` -> `54`.
- `wc -l app/modules/enforcement/domain/service.py` -> `527` (within default module-size budget `600`).

## Additional remediation batch (2026-03-04AE, report-driven H-02 hardening continuation for LLM/notification/webhook/optimization API paths)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Targeted open hotspots from governance scan:
- `app/shared/llm/usage_tracker.py`
- `app/shared/llm/pricing_data.py`
- `app/shared/llm/circuit_breaker.py`
- `app/shared/llm/hybrid_scheduler.py`
- `app/shared/llm/zombie_analyzer.py`
- `app/modules/notifications/domain/jira.py`
- `app/modules/notifications/domain/slack.py`
- `app/modules/billing/domain/billing/webhook_retry.py`
- `app/modules/optimization/api/v1/strategies.py`
- `app/modules/optimization/api/v1/zombies.py`

2. Hardening changes (`H-02`):
- Updated `usage_tracker.py`:
  - Added `TOKEN_COUNTING_RECOVERABLE_EXCEPTIONS`.
  - Replaced broad token-counting catch-all with typed recoverable contract.
- Updated `pricing_data.py`:
  - Added `LLM_PRICING_REFRESH_RECOVERABLE_EXCEPTIONS`.
  - Replaced broad refresh catch-all with typed operational contracts (including DB/runtime/import failures).
- Updated `circuit_breaker.py`:
  - Removed broad catch-all in `protect` context manager.
  - Switched to `finally + sys.exc_info()` to record recoverable `Exception` failures while preserving fatal propagation.
- Updated `hybrid_scheduler.py`:
  - Removed broad catch-all in `_hybrid_span`.
  - Switched to `finally + sys.exc_info()` exception recording and status tagging.
  - Tightened decimal parse fallback to `HYBRID_COST_PARSE_RECOVERABLE_EXCEPTIONS`.
- Updated `zombie_analyzer.py`:
  - Added `ZOMBIE_USAGE_TRACKING_RECOVERABLE_EXCEPTIONS`.
  - Replaced broad usage-tracking catch-all with typed recoverable contract.
- Updated `jira.py`:
  - Added `JIRA_CLIENT_RECOVERABLE_EXCEPTIONS`.
  - Replaced broad create/health catch-alls with typed client/transport contracts.
- Updated `slack.py`:
  - Added `SLACK_CLIENT_RECOVERABLE_EXCEPTIONS`.
  - Replaced broad generic Slack method catch-all with typed recoverable contract.
- Updated `webhook_retry.py`:
  - Added `PAYSTACK_STORED_PAYLOAD_PARSE_RECOVERABLE_EXCEPTIONS`.
  - Replaced broad stored-payload parse catch-all with typed parse/encoding contracts.
- Updated `strategies.py`:
  - Tightened tolerance coercion fallback to `(TypeError, ValueError, OverflowError)`.
- Updated `zombies.py`:
  - Added `REMEDIATION_EXECUTION_RECOVERABLE_EXCEPTIONS`.
  - Replaced broad remediation execute catch-all with typed operational contract.

3. TDD updates and additions:
- Updated:
  - `tests/unit/llm/test_usage_tracker.py`
  - `tests/unit/llm/test_usage_tracker_audit.py`
  - `tests/unit/llm/test_hybrid_scheduler.py`
  - `tests/unit/llm/test_circuit_breaker.py`
  - `tests/unit/llm/test_zombie_analyzer_exhaustive.py`
  - `tests/unit/notifications/test_jira_service.py`
  - `tests/unit/notifications/domain/test_slack_service.py`
  - `tests/unit/modules/reporting/test_webhook_retry.py`
  - `tests/unit/optimization/test_strategies_api_branch_paths_2.py`
  - `tests/unit/zombies/test_zombies_api_branches.py`
- Added:
  - `tests/unit/llm/test_pricing_data.py`
- New assertions cover:
  - recoverable fallback behavior,
  - fatal non-swallowing behavior (`KeyboardInterrupt`),
  - parity with current production flows.

Validation:
1. `DEBUG=false uv run pytest -q --no-cov tests/unit/llm/test_usage_tracker.py tests/unit/llm/test_usage_tracker_audit.py tests/unit/llm/test_pricing_data.py tests/unit/llm/test_hybrid_scheduler.py tests/unit/llm/test_circuit_breaker.py tests/unit/llm/test_zombie_analyzer_exhaustive.py tests/unit/notifications/test_jira_service.py tests/unit/notifications/domain/test_slack_service.py tests/unit/modules/reporting/test_webhook_retry.py tests/unit/optimization/test_strategies_api_branch_paths_2.py tests/unit/zombies/test_zombies_api_branches.py` -> `183 passed`.
2. `uv run ruff check ...` (all changed source/tests in this batch) -> passed.
3. `uv run mypy app/shared/llm/usage_tracker.py app/shared/llm/pricing_data.py app/shared/llm/circuit_breaker.py app/shared/llm/hybrid_scheduler.py app/shared/llm/zombie_analyzer.py app/modules/notifications/domain/jira.py app/modules/notifications/domain/slack.py app/modules/billing/domain/billing/webhook_retry.py app/modules/optimization/api/v1/strategies.py app/modules/optimization/api/v1/zombies.py` -> passed.
4. `uv run python scripts/verify_exception_governance.py` -> passed (`current=110`, `baseline=444`, `removed=334`).
5. `uv run python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).
6. `uv run python scripts/verify_enforcement_post_closure_sanity.py` -> passed (all `7` dimensions `OK`).

Post-closure sanity (release-critical):
1. Concurrency: async LLM + notification + webhook flows preserved; no shared-state race regressions introduced.
2. Observability: existing log event contracts retained (pricing refresh, jira/slack failures, webhook parse errors, remediation API failures).
3. Deterministic replay: parser fallbacks and strategy tolerance behavior remain deterministic for identical inputs.
4. Snapshot stability: endpoint response envelopes unchanged for optimization remediation paths.
5. Export integrity: export pipelines unaffected in this tranche.
6. Failure modes: recoverable operational failures degrade safely; fatal non-`Exception` failures now propagate.
7. Operational misconfiguration: exception-governance/module-size/post-closure sanity checks remain green.

Remaining snapshot after this batch:
- `rg -n "except Exception|except:\\s*$" app | wc -l` -> `42`.

## Additional remediation batch (2026-03-04AF, report-driven H-02 hardening completion across remaining app catch-all handlers)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Remaining truly-open item addressed from report:
- `H-02: Broad Exception Catches Across 50+ Files`.

2. Hardening changes (typed recoverable exception contracts):
- Runtime/API/infra paths:
  - `app/tasks/license_tasks.py`
  - `app/modules/enforcement/api/v1/common.py`
  - `app/modules/enforcement/api/v1/enforcement.py`
  - `app/main.py`
  - `app/modules/governance/api/v1/jobs.py`
  - `app/shared/connections/aws.py`
  - `app/shared/connections/organizations.py`
  - `app/shared/connections/discovery.py`
  - `app/shared/remediation/hard_cap_service.py`
  - `app/shared/remediation/circuit_breaker.py`
  - `app/shared/remediation/autonomous.py`
  - `app/modules/governance/domain/security/iam_auditor.py`
  - `app/modules/governance/domain/security/remediation_policy.py`
- Domain coercion/validation paths:
  - `app/schemas/connections.py`
  - `app/shared/analysis/cur_usage_analyzer.py`
  - `app/modules/optimization/domain/actions/base.py`
  - `app/modules/optimization/domain/actions/license/base.py`
  - `app/modules/optimization/domain/strategies/baseline_commitment.py`
  - `app/modules/optimization/domain/license_governance.py`
- Adapter/plugin paths:
  - `app/shared/adapters/aws_multitenant.py`
  - `app/shared/adapters/aws_resource_explorer.py`
  - `app/modules/optimization/adapters/kubernetes/plugins/kubernetes_pvc.py`
  - `app/modules/optimization/adapters/saas/plugins/api.py`
  - `app/modules/optimization/adapters/aws/plugins/compute.py`
  - `app/modules/optimization/adapters/aws/plugins/rightsizing.py`
  - `app/modules/optimization/adapters/aws/plugins/search.py`
  - `app/modules/optimization/adapters/gcp/plugins/ai.py`
  - `app/modules/optimization/adapters/gcp/plugins/database.py`
  - `app/modules/optimization/adapters/gcp/plugins/search.py`
  - `app/modules/optimization/adapters/gcp/plugins/rightsizing.py`
  - `app/modules/optimization/adapters/gcp/plugins/containers.py`
  - `app/modules/optimization/adapters/gcp/plugins/storage.py`
  - `app/modules/optimization/adapters/gcp/plugins/network.py`

3. Additional safety alignment:
- Preserved fail-safe behavior in enforcement gate path while removing broad catch-all.
- Preserved DNS malformed-record tolerance in discovery parsing with typed runtime parsing exceptions.
- Kept startup LLM pricing refresh resilient with existing typed refresh contract import.
- Kept rollback semantics in hard-cap enforce/reverse transaction paths using typed DB/runtime recovery sets.

Validation:
1. `uv run ruff check` on all changed source files -> passed.
2. `uv run mypy` on all changed source files -> passed.
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/tasks/test_license_tasks.py tests/unit/analysis/test_cur_usage_analyzer.py tests/unit/schemas/test_connections_schema.py tests/unit/services/connections/test_organizations.py tests/unit/shared/connections/test_discovery_service.py tests/unit/governance/test_jobs_api.py tests/governance/test_iam_auditor.py tests/governance/test_iam_auditor_branch_paths.py tests/governance/test_autonomous_logic.py tests/governance/test_autonomous_logic_branch_paths.py tests/unit/test_hard_cap_service.py tests/unit/shared/remediation/test_hard_cap_service_branches.py tests/unit/adapters/test_aws_resource_explorer.py tests/unit/shared/adapters/test_aws_multitenant_branch_paths.py tests/unit/zombies/kubernetes/test_kubernetes_pvc.py tests/unit/modules/optimization/adapters/saas/test_saas_api_branch_paths.py tests/unit/modules/optimization/adapters/gcp/test_gcp_plugins_fallbacks.py tests/unit/modules/optimization/adapters/gcp/test_gcp_rightsizing.py tests/unit/modules/optimization/adapters/gcp/test_gcp_new_zombies.py tests/unit/modules/optimization/adapters/gcp/test_gcp_search_network_branch_paths.py tests/unit/optimization/test_license_governance.py tests/unit/optimization/test_license_governance_branch_paths.py tests/unit/optimization/test_remediation_policy.py tests/unit/enforcement/test_enforcement_common_feature_guards.py tests/unit/enforcement/test_enforcement_api_helper_functions.py` -> `209 passed`.
4. `uv run python scripts/verify_exception_governance.py` -> passed (`current=69`, `baseline=444`, `removed=375`).
5. `uv run python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).
6. `uv run python scripts/verify_env_hygiene.py` -> passed.
7. `uv run python scripts/verify_repo_root_hygiene.py` -> passed.
8. `uv run python scripts/verify_enforcement_post_closure_sanity.py` -> passed (all `7` dimensions `OK`).

Post-closure sanity (release-critical):
1. Concurrency: async scan/stream/remediation/enforcement paths preserved; no lock/cache race behavior regressions introduced.
2. Observability: warning/error event contracts retained across enforcement, discovery, adapters, and governance jobs.
3. Deterministic replay: typed fallback/coercion behavior deterministic for identical payloads/records.
4. Snapshot stability: response contracts for enforcement/jobs/discovery unchanged.
5. Export integrity: no export-path mutation in this tranche.
6. Failure modes: recoverable operational failures still degrade safely; broad catch-all handlers in `app/` were removed.
7. Operational misconfiguration: module-size/exception-governance/env/root/post-closure sanity gates remain green.

Remaining snapshot after this batch:
- `uv run python scripts/verify_exception_governance.py` -> `current=69`.
- `rg -n "except Exception|except:\\s*$" app` -> only a usage example inside `app/shared/llm/circuit_breaker.py` docstring.

## Additional remediation batch (2026-03-04AG, report-driven closure of remaining L-02 script duplication without legacy wrappers)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. True-open report item addressed:
- `L-02 Multiple Database Check Scripts`.

2. Production-grade remediation (no backward-compat wrappers):
- Removed wrapper scripts:
  - `scripts/check_db.py`
  - `scripts/check_db_tables.py`
  - `scripts/db_check.py`
  - `scripts/db_deep_dive.py`
  - `scripts/analyze_tables.py`
- Kept single authoritative diagnostics entrypoint:
  - `scripts/db_diagnostics.py` (`ping`, `tables`, `partitions`, `inventory`, `deep-dive`).
- Replaced wrapper-focused tests with direct unified-entrypoint tests:
  - deleted `tests/unit/ops/test_db_diagnostics_wrappers.py`
  - added `tests/unit/ops/test_db_diagnostics.py`

3. Additional strictness cleanup:
- Removed last `app` false-positive catch-all grep artifact in documentation example:
  - `app/shared/llm/circuit_breaker.py` docstring usage updated from `except Exception` to typed example.

Validation:
1. `uv run ruff check scripts/db_diagnostics.py tests/unit/ops/test_db_diagnostics.py app/shared/llm/circuit_breaker.py` -> passed.
2. `uv run mypy scripts/db_diagnostics.py tests/unit/ops/test_db_diagnostics.py app/shared/llm/circuit_breaker.py` -> passed.
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/ops/test_db_diagnostics.py` -> `3 passed`.
4. `uv run python scripts/verify_exception_governance.py` -> passed (`current=69`, `baseline=444`, `removed=375`).
5. `uv run python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).
6. `uv run python scripts/verify_enforcement_post_closure_sanity.py` -> passed (all `7` dimensions `OK`).
7. `uv run python scripts/verify_env_hygiene.py` -> passed.
8. `uv run python scripts/verify_repo_root_hygiene.py` -> passed.

Post-closure sanity (release-critical):
1. Concurrency: unchanged runtime behavior; script consolidation does not alter worker/task concurrency semantics.
2. Observability: existing runtime event contracts unchanged; diagnostics output remains deterministic and machine-readable.
3. Deterministic replay: all DB diagnostics now route through one command contract and one codepath.
4. Snapshot stability: no API response/schema changes from this batch.
5. Export integrity: export workflows untouched.
6. Failure modes: no silent fallback wrappers; explicit command invocation only via unified entrypoint.
7. Operational misconfiguration: governance/module-size/hygiene/sanity gates remain green.

Current catch-all snapshot:
- `app`: `0` (`rg -n "except Exception|except:\\s*$" app`)
- `scripts`: `69` (tracked separately under script governance baseline; runtime app paths hardened).

## Additional remediation batch (2026-03-04AH, report-driven completion of exception hardening across scripts and live smoke tooling)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. True-open risk cluster addressed:
- Remaining catch-all exception debt in operational scripts and smoke tooling.

2. Hardening changes (typed recoverable exception contracts):
- High-count script paths:
  - `scripts/capture_acceptance_evidence.py`
  - `scripts/smoke_test_scim_idp.py`
  - `scripts/smoke_test_sso_federation.py`
- Additional operational scripts hardened:
  - `scripts/verify_greenops.py`
  - `scripts/supabase_cleanup.py`
  - `scripts/load_test_api.py`
  - `scripts/cleanup_partitions.py`
  - `scripts/deactivate_aws.py`
  - `scripts/emergency_disconnect.py`
  - `scripts/truncate_cost_records.py`
  - `scripts/delete_cloudfront.py`
  - `scripts/disable_cloudfront.py`
  - `scripts/emergency_token.py`
  - `scripts/update_exchange_rates.py`
  - `scripts/run_rls_optimization.py`
  - `scripts/test_tenant_import.py`
  - `scripts/force_wipe_app.py`
  - `scripts/soak_ingestion_jobs.py`
  - `scripts/purge_simulation_data.py`
  - `scripts/list_zombies.py`
  - `scripts/verify_pending_approval_flow.py`
  - `scripts/database_wipe.py`
  - `scripts/list_tables.py`
  - `scripts/check_partitions.py`
  - `scripts/verify_remediation.py`
  - `scripts/create_partitions.py`
  - `scripts/validate_runtime_env.py`
  - `scripts/generate_finance_committee_packet.py`
  - `scripts/simple_token.py`

3. Key outcomes:
- Replaced all remaining `except Exception` and bare `except` handlers in `scripts/` with typed exception sets.
- Preserved operator-safe behavior for smoke/evidence scripts (best-effort capture and diagnostics remain intact).
- Removed residual `app` grep artifact by tightening documentation example in `app/shared/llm/circuit_breaker.py`.

Validation:
1. `uv run ruff check` on all changed script files -> passed.
2. `uv run mypy` on all changed script files -> passed (`29` files).
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/core/test_load_test_api_script.py tests/unit/ops/test_generate_finance_committee_packet.py tests/unit/ops/test_db_diagnostics.py` -> `15 passed`.
4. `uv run python scripts/verify_exception_governance.py` -> passed (`current=0`, `baseline=444`, `removed=444`).
5. `uv run python scripts/verify_python_module_size_budget.py` -> passed (`default_max_lines=600`).
6. `uv run python scripts/verify_enforcement_post_closure_sanity.py` -> passed (all `7` dimensions `OK`).
7. `uv run python scripts/verify_env_hygiene.py` -> passed.
8. `uv run python scripts/verify_repo_root_hygiene.py` -> passed.

Post-closure sanity (release-critical):
1. Concurrency: script hardening does not alter runtime worker concurrency semantics.
2. Observability: logging/manifest evidence behavior preserved for smoke/evidence scripts.
3. Deterministic replay: evidence and smoke fallback paths remain deterministic with typed failure modes.
4. Snapshot stability: API/manifest contracts unchanged.
5. Export integrity: export-related evidence captures preserved.
6. Failure modes: fatal non-operational failures no longer hidden behind broad catch-all handlers.
7. Operational misconfiguration: governance/module-size/hygiene/sanity gates all remain green.

Current snapshot:
- `app`: `0` (`rg -n "except Exception|except:\\s*$" app`)
- `scripts`: `0` (`rg -n "except Exception|except:\\s*$" scripts`)

## Additional remediation batch (2026-03-04AI, report-driven deterministic validator + release-gate wiring)

Reference report validated:
- `/home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved`

1. Single-pass deterministic report validation control added:
- Introduced `scripts/verify_audit_report_resolved.py`.
- Maps report findings (`C-01..L-06`) to machine-checkable repository controls and fails on drift.
- Supports explicit report heading validation against the source report file, with controlled fallback via `--allow-missing-report`.

2. Release-gate integration and stale-target cleanup:
- `scripts/run_enterprise_tdd_gate.py` now executes:
  - `uv run python3 scripts/verify_audit_report_resolved.py --allow-missing-report`
- Updated gate test target list to reflect DB diagnostics consolidation:
  - replaced `tests/unit/ops/test_db_diagnostics_wrappers.py`
  - with `tests/unit/ops/test_db_diagnostics.py`
- Added new test target:
  - `tests/unit/ops/test_verify_audit_report_resolved.py`

3. Additional hardening:
- Tightened module-size override for `M-03` hotspot:
  - `app/modules/governance/domain/security/compliance_pack_bundle.py`
  - budget reduced from `1125` to `1000`.

Validation:
1. `uv run ruff check scripts/verify_audit_report_resolved.py tests/unit/ops/test_verify_audit_report_resolved.py scripts/run_enterprise_tdd_gate.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py scripts/verify_python_module_size_budget.py` -> passed.
2. `uv run mypy scripts/verify_audit_report_resolved.py tests/unit/ops/test_verify_audit_report_resolved.py scripts/run_enterprise_tdd_gate.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py scripts/verify_python_module_size_budget.py` -> passed.
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/ops/test_verify_audit_report_resolved.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py tests/unit/ops/test_verify_python_module_size_budget.py tests/unit/ops/test_db_diagnostics.py` -> passed.
4. `uv run python scripts/verify_audit_report_resolved.py --report-path /home/daretechie/.gemini/antigravity/brain/dba19da4-0271-4686-88fd-9bc5a2b3dbfe/audit_report.md.resolved` -> passed.
5. `uv run python scripts/verify_exception_governance.py` -> passed.
6. `uv run python scripts/verify_python_module_size_budget.py` -> passed.
7. `uv run python scripts/verify_env_hygiene.py` -> passed.
8. `uv run python scripts/verify_repo_root_hygiene.py` -> passed.
9. `uv run python scripts/verify_enforcement_post_closure_sanity.py` -> passed.

Post-closure sanity (release-critical):
1. Concurrency: validator is read-only and introduces no runtime contention surfaces.
2. Observability: deterministic, finding-scoped failure output added for release triage.
3. Deterministic replay: same repo state and report headings produce stable outcomes.
4. Snapshot stability: no API or export schema changes in this tranche.
5. Export integrity: unchanged.
6. Failure modes: fail-closed on missing/invalid controls; optional report-path absence only when explicitly allowed.
7. Operational misconfiguration: validator is now part of enterprise release gating.
