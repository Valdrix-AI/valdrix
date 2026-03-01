# Enforcement Control Plane Gap Register (2026-02-23)

This document converts the three requirement sets provided in the current review thread into a code-backed gap register and execution tracker.

## Current Open Items (Canonical, 2026-02-27)

This is the single source of truth for what is still open. Historical sections below may contain older `Partial`/transition notes and should not override this list.

1. `PKG-*` (`OPEN`): packaging/commercial backlog remains active (`PKG-001..PKG-032`), with `PKG-003`, `PKG-006`, `PKG-007`, `PKG-008`, `PKG-010`, `PKG-014`, `PKG-015`, and `PKG-020` now implemented baseline.
2. `FIN-*` (`OPEN`): financial model/guardrail backlog remains active (`FIN-001..FIN-008` + `FIN-GATE-*`).

Everything else in enforcement runtime hardening is treated as `DONE` baseline with regression-watch posture.

Pre-launch policy lock note (2026-02-28F):
1. Launch-blocking PKG/FIN decisions are now explicitly codified and verified:
   - pricing boundary policy,
   - synthetic pre-launch telemetry handling,
   - founder-acting approval governance mode.
2. Remaining `PKG-*` / `FIN-*` work is now primarily post-launch policy operations (production telemetry and pricing-motion governance), not implementation readiness for platform launch.

Execution update (2026-02-28E): closure audit rerun
1. Re-ran full non-dry-run release-evidence gate with all current evidence contracts:
   - stress + failure injection + finance guardrails + finance telemetry + pricing benchmark + PKG/FIN decision artifact.
   - Result: passed (`860 passed`) with all coverage thresholds satisfied.
2. Re-ran additional backend regression suites for modified non-gate pricing/remediation modules:
   - `tests/unit/api/v1/test_billing.py`
   - `tests/unit/services/billing/test_paystack_billing_branches.py`
   - `tests/unit/optimization/test_remediation_policy.py`
   - `tests/unit/zombies/test_zombies_api_branches.py`
   - Result: `72 passed`.
3. Re-ran modified frontend pricing checks:
   - `npm run test:unit -- --run src/routes/pricing/pricing.load.test.ts` -> `4 passed`
   - `npm run check` -> `0 errors`, `0 warnings`.
4. Re-ran static quality checks on changed/new Python files:
   - `uv run ruff check ...` -> passed.
   - `uv run mypy ... --hide-error-context --no-error-summary` -> passed.
5. Current interpretation:
   - engineering/test hardening in this scope is green,
   - remaining open backlog is policy/telemetry-governance (`PKG-*`, `FIN-*`) rather than unresolved implementation defects.

Recent staged closures (2026-02-27, single-sprint hardening pass):
1. `CI-EVID-001` (`DONE`): CI green-run promotion packet captured.
   - Artifact: `docs/evidence/ci-green-2026-02-27.md`
   - Gate status: `scripts/run_enforcement_release_evidence_gate.py` passed (`815 passed`, coverage gates satisfied).
2. `BENCH-DOC-001` (`DONE`): benchmark-alignment hardening documentation profile published.
   - Artifact: `docs/ops/benchmark_alignment_profiles_2026-02-27.md`
   - Covers:
     - Kubernetes webhook production guidance profile,
     - CEL portability profile,
     - Terraform ordering profile.
3. `BSAFE-009` (`DONE`): staged stress artifact captured, attached, and verified.
   - Artifact: `docs/ops/evidence/enforcement_stress_artifact_2026-02-27.json`
4. `BSAFE-010` (`DONE`): staged failure-injection artifact captured from real FI scenario test execution, attached, and verified.
   - Artifact: `docs/ops/evidence/enforcement_failure_injection_2026-02-27.json`
5. `PKG-006` (`DONE` baseline): machine-verifiable feature enforceability matrix added for paid-tier capabilities.
   - Artifacts:
     - `docs/ops/feature_enforceability_matrix_2026-02-27.json`
     - `scripts/generate_feature_enforceability_matrix.py`
     - `scripts/verify_feature_enforceability_matrix.py`
6. `PKG-007` (`DONE` baseline): Enterprise entitlements switched from dynamic `set(FeatureFlag)` to explicit curated roster (`ENTERPRISE_FEATURES`) with regression guards.
7. `PKG-008` (`DONE` baseline): feature maturity metadata (`GA|Beta|Preview`) added to pricing source-of-truth and exposed in plan payloads (`/api/v1/billing/features`, `/api/v1/billing/plans`).
8. `PKG-003` (`DONE` baseline): enforcement runtime now enforces feature-tier gates at API boundaries.
   - `POLICY_CONFIGURATION` gates: enforcement gate/policy/approval/action/reservation surfaces.
   - `API_ACCESS` gates: enforcement ledger/export surfaces.
9. `PKG-014` (`DONE` baseline): previously catalog-only `API_ACCESS` and `POLICY_CONFIGURATION` now have explicit runtime enforcement checks.
10. `FIN-GATE` automation baseline (`DONE`): machine-verifiable finance guardrail artifact contract added and release-gate wiring enabled when finance evidence is supplied.
   - Artifacts:
     - `docs/ops/evidence/finance_guardrails_TEMPLATE.json`
     - `docs/ops/evidence/finance_guardrails_2026-02-27.json`
     - `scripts/verify_finance_guardrails_evidence.py`
     - `docs/ops/pkg_fin_decision_memo_2026-02-27.md`
11. `PKG-020` automation baseline (`DONE`): machine-verifiable pricing benchmark evidence register added with freshness/class-coverage guards.
   - Artifacts:
     - `docs/ops/evidence/pricing_benchmark_register_TEMPLATE.json`
     - `docs/ops/evidence/pricing_benchmark_register_2026-02-27.json`
     - `scripts/verify_pricing_benchmark_register.py`
     - `docs/ops/pkg_fin_decision_memo_2026-02-27.md`
12. `PKG/FIN` policy-decision automation baseline (`DONE`): machine-verifiable decision artifact added to enforce that pricing/packaging motions carry explicit policy choices and approval sign-offs, backed by at least 2 months of telemetry.
   - Artifacts:
     - `docs/ops/evidence/pkg_fin_policy_decisions_TEMPLATE.json`
     - `docs/ops/evidence/pkg_fin_policy_decisions_2026-02-28.json`
     - `scripts/verify_pkg_fin_policy_decisions.py`
     - `docs/ops/pkg_fin_decision_memo_2026-02-27.md`
13. `FIN` live telemetry automation baseline (`DONE`): machine-verifiable telemetry snapshot + monthly committee packet generator + optional gate wiring added for live FIN packet automation.
   - Artifacts:
     - `docs/ops/evidence/finance_telemetry_snapshot_TEMPLATE.json`
     - `docs/ops/evidence/finance_telemetry_snapshot_2026-02-28.json`
     - `docs/ops/evidence/finance_committee_packet_assumptions_TEMPLATE.json`
     - `docs/ops/evidence/finance_committee_packet_assumptions_2026-02-28.json`
     - `scripts/collect_finance_telemetry_snapshot.py`
     - `scripts/verify_finance_telemetry_snapshot.py`
     - `scripts/generate_finance_committee_packet.py`
14. `PKG-010` (`DONE` baseline): free-tier LLM compute guardrails and telemetry gates are now machine-verifiable in finance telemetry snapshots.
   - Artifacts:
     - `scripts/collect_finance_telemetry_snapshot.py`
     - `scripts/verify_finance_telemetry_snapshot.py`
     - `docs/ops/evidence/finance_telemetry_snapshot_TEMPLATE.json`
     - `docs/ops/evidence/finance_telemetry_snapshot_2026-02-28.json`
     - `tests/unit/ops/test_collect_finance_telemetry_snapshot.py`
     - `tests/unit/ops/test_verify_finance_telemetry_snapshot.py`
15. `PKG-015` (`DONE` baseline): B-launch readiness gate is now machine-checkable and enforced in enterprise gate command construction.
   - Artifacts:
     - `scripts/verify_pkg015_launch_gate.py`
     - `scripts/run_enterprise_tdd_gate.py`
     - `tests/unit/ops/test_verify_pkg015_launch_gate.py`
     - `tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`

Execution update (2026-02-28H): immediate PKG/FIN evidence hardening controls completed
1. CI now enforces evidence artifacts as mandatory inputs for enterprise release gate:
   - stress artifact required,
   - failure-injection artifact required,
   - finance guardrails required,
   - finance telemetry snapshot required,
   - pricing benchmark register required,
   - PKG/FIN policy-decision artifact required.
   - Evidence: `.github/workflows/ci.yml` (`enterprise-tdd-quality-gate` env contract).
2. PKG/FIN verifier now rejects placeholder values in approval and decision fields:
   - blocks tokens such as `example.com`, `.example`, `TBD`, `TODO`, `placeholder`, `replace_me`, `yyyy`.
   - Evidence: `scripts/verify_pkg_fin_policy_decisions.py`, `tests/unit/ops/test_verify_pkg_fin_policy_decisions.py`.
3. Added monthly finance evidence refresh gate with CI reminder posture:
   - `scripts/verify_monthly_finance_evidence_refresh.py`
   - wired as always-on command in `scripts/run_enterprise_tdd_gate.py`,
   - validates freshness (`max_age_days`) + capture-cycle coherence (`max_capture_spread_days`),
   - supports bounded timestamp skew to avoid same-day false positives.
   - Evidence: `tests/unit/ops/test_verify_monthly_finance_evidence_refresh.py`, `tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`.

Execution update (2026-02-28I): Valdrix codebase audit validation + remediation batch
1. Validated and remediated confirmed security/runtime defects from `VALDRX_CODEBASE_AUDIT_2026-02-28.md.resolved`:
   - `VAL-DB-001`: hardened RLS session posture by introducing explicit `rls_system_context` marker and fail-closed behavior for ambiguous (unset/non-system) DB query context in non-testing runtime.
     - Code: `app/shared/db/session.py`
     - Propagation: explicit system-context markers added in non-request session paths (`oidc`, `scim token lookup`, `scheduler`, `jobs SSE/internal processor`, `CUR ingestion`, `LLM pricing refresh`, `FX service`).
   - `VAL-BILL-005`: dunning enqueue failure now reverts ATTENTION transition and retry metadata to prevent persisted partial state without an actual scheduled retry job.
     - Code: `app/modules/billing/domain/billing/dunning_service.py`
   - `VAL-SEC-001`: removed hardcoded CSRF test fallback; test mode now uses env-provided key or derived ephemeral key.
     - Code: `app/main.py`
   - `VAL-SEC-003`: webhook IP extraction now ignores `X-Forwarded-For` unless proxy header trust is explicitly enabled (`TRUST_PROXY_HEADERS`).
     - Code: `app/modules/billing/api/v1/billing.py`, `app/shared/core/config.py`
   - `VAL-CORE-003/004`: added per-session tenant-tier cache and removed awaitable scalar branch to reduce repeated tenant lookups and normalize lookup behavior.
     - Code: `app/shared/core/pricing.py`
2. Validated as non-defects / architecture backlog (not immediate security correctness bugs):
   - middleware ordering note (`VAL-API-001`) already documented in-code and intentional,
   - bearer-token CSRF bypass (`VAL-API-002`) is constrained to non-cookie auth flow,
   - static docs assets (`VAL-API-004`) already have SRI attachment and static-only mount behavior,
   - adapter retry-loop duplication is now remediated via shared helper (`app/shared/adapters/http_retry.py`) and rollout across license/saas/platform/hybrid adapters.
   - residual `VAL-ADAPT-002+` scope is class-size/vendor-strategy decomposition (maintainability architecture backlog), not immediate hotfix blockers.
3. Regression evidence:
   - Targeted suites: `212 passed`.
   - Command:
     - `DEBUG=false uv run pytest -q --no-cov tests/unit/db/test_session_branch_paths_2.py tests/unit/core/test_main.py tests/unit/services/billing/test_dunning_service.py tests/unit/core/test_pricing_deep.py tests/unit/api/v1/test_billing.py tests/unit/connections/test_oidc_deep.py tests/unit/shared/connections/test_oidc_service.py tests/unit/governance/jobs/test_cur_ingestion.py tests/unit/governance/jobs/test_cur_ingestion_branch_paths.py tests/unit/governance/test_jobs_api.py tests/unit/governance/test_scim_api.py tests/unit/governance/test_scim_api_branches.py tests/unit/governance/test_scim_context_and_race_branches.py tests/unit/governance/test_scim_internal_branches.py tests/unit/governance/test_scim_direct_endpoint_branches.py tests/unit/tasks/test_scheduler_tasks.py tests/unit/tasks/test_scheduler_tasks_branch_paths_2.py`
   - Static checks:
     - `uv run ruff check ...` -> passed.
     - `uv run mypy ... --hide-error-context --no-error-summary` -> passed.

Execution update (2026-02-28J): adapter retry abstraction remediation
1. Closed retry-loop duplication across Cloud+ adapters by introducing a shared retry primitive:
   - `app/shared/adapters/http_retry.py::execute_with_http_retry()`
   - normalized retryable HTTP status handling, transport retry behavior, and `ExternalAPIError` mapping.
2. Refactored adapters to consume the shared retry primitive:
   - `app/shared/adapters/license.py`
   - `app/shared/adapters/saas.py`
   - `app/shared/adapters/platform.py`
   - `app/shared/adapters/hybrid.py`
3. Hardened deterministic connector parsing:
   - extracted Google Workspace license connector parser to `app/shared/adapters/license_config.py`,
   - adapter runtime now uses typed parsed config instead of ad-hoc nested dict parsing.
4. Regression evidence:
   - `DEBUG=false uv run pytest -q --no-cov tests/unit/services/adapters/test_cloud_plus_adapters.py tests/unit/services/adapters/test_platform_hybrid_adapters.py tests/unit/services/adapters/test_platform_additional_branches.py tests/unit/services/adapters/test_hybrid_additional_branches.py tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/services/adapters/test_license_verification_stream_branches.py tests/unit/shared/adapters/test_saas_adapter_branch_paths.py` -> `155 passed`.
   - Added direct unit coverage for new abstractions:
     - `tests/unit/shared/adapters/test_http_retry.py`
     - `tests/unit/shared/adapters/test_license_config.py`
5. Remaining adapter backlog scope:
   - class-size and vendor-strategy decomposition (`VAL-ADAPT-002+`) remains a maintainability refactor backlog item (non-hotfix severity).

Execution update (2026-02-28K): Valdrix audit follow-up (targeted closures + decomposition pass)
1. Closed `VAL-CORE-001` (implicit maturity mapping risk):
   - `app/shared/core/pricing.py` now defines explicit preview maturity membership and enforces exact/complete feature-maturity coverage invariants.
   - Startup fails closed if any `FeatureFlag` is missing from maturity classification.
2. Closed `VAL-BILL-001` (stale plan code resolution risk):
   - `app/modules/billing/domain/billing/paystack_service_impl.py` now resolves `plan_codes` and `annual_plan_codes` lazily from live settings instead of capturing once in `__init__`.
3. Advanced `VAL-ADAPT-002` decomposition:
   - Extracted vendor verify/revoke/activity operation implementations into `app/shared/adapters/license_vendor_ops.py`.
   - `app/shared/adapters/license.py` now delegates those vendor operations through wrappers, reducing adapter density and improving test seam isolation.
4. Regression evidence:
   - `uv run ruff check app/shared/core/pricing.py app/modules/billing/domain/billing/paystack_service_impl.py app/shared/adapters/license.py app/shared/adapters/license_vendor_ops.py tests/unit/services/adapters/test_license_verification_stream_branches.py` -> passed.
   - `uv run mypy app/shared/core/pricing.py app/modules/billing/domain/billing/paystack_service_impl.py app/shared/adapters/license.py app/shared/adapters/license_vendor_ops.py --hide-error-context --no-error-summary` -> passed.
   - `DEBUG=false uv run pytest -q --no-cov tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/services/adapters/test_license_verification_stream_branches.py tests/unit/services/billing/test_paystack_billing_branches.py tests/unit/core/test_pricing_packaging_contract.py` -> `76 passed`.
5. Remaining architecture backlog:
   - `VAL-ADAPT-002+` still has additional class-size/vendor-strategy extraction scope; this is maintainability backlog, not a release-blocking runtime defect.

Execution update (2026-02-28L): consolidated remediation state sync
1. Consolidated remediated Valdrix items now reflected in code + docs:
   - `VAL-DB-001`, `VAL-BILL-005`, `VAL-SEC-001`, `VAL-SEC-003`, `VAL-CORE-003/004`,
   - `VAL-CORE-001`, `VAL-BILL-001`, `VAL-ADAPT-003`, `VAL-ADAPT-004`.
2. `VAL-ADAPT-002` status:
   - decomposition materially advanced via `app/shared/adapters/license_vendor_ops.py` (vendor verify/revoke/activity extraction),
   - adapter wrapper seam preserved in `app/shared/adapters/license.py` for stable behavior and patch-based tests.
3. Remaining non-hotfix scope:
   - `VAL-ADAPT-002+` further class-size/vendor-strategy splitting remains maintainability backlog, not a release-blocking runtime/security issue.

Execution update (2026-02-28M): license stream-cost decomposition follow-up
1. Advanced `VAL-ADAPT-002` by extracting native stream-cost implementations from `app/shared/adapters/license.py` into `app/shared/adapters/license_vendor_ops.py`:
   - Google Workspace stream-cost path.
   - Microsoft 365 stream-cost path.
2. Preserved adapter behavior and patch seams:
   - `LicenseAdapter._stream_google_workspace_license_costs()` and `LicenseAdapter._stream_microsoft_365_license_costs()` remain as wrappers that delegate to vendor ops.
   - Existing stream fallback behavior (`native -> manual feed`) and external error semantics remain unchanged.
3. Validation evidence:
   - `uv run ruff check app/shared/adapters/license.py app/shared/adapters/license_vendor_ops.py` -> passed.
   - `uv run mypy app/shared/adapters/license.py app/shared/adapters/license_vendor_ops.py --hide-error-context --no-error-summary` -> passed.
   - `DEBUG=false uv run pytest -q --no-cov tests/unit/services/adapters/test_license_verification_stream_branches.py tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/services/adapters/test_cloud_plus_adapters.py tests/unit/shared/adapters/test_google_workspace.py` -> `91 passed`.

Execution update (2026-02-28N): Valdrix continuation (auth coverage + paginator + billing entitlement sync)
1. Closed `VAL-SEC-002` with machine-checkable route-auth verification:
   - added `scripts/verify_api_auth_coverage.py` (recursive dependency scan + explicit public allowlist),
   - wired as a mandatory enterprise gate command in `scripts/run_enterprise_tdd_gate.py`,
   - hardened explicit auth on:
     - `app/modules/governance/api/v1/jobs.py` (`/internal/process` now depends on `require_internal_job_secret`),
     - `app/modules/governance/api/v1/settings/llm.py` (`/llm/models` now depends on authenticated user context).
2. Advanced `VAL-ADAPT-005` with shared AWS paginator abstraction:
   - added `app/shared/adapters/aws_pagination.py::iter_aws_paginator_pages()`,
   - applied to:
     - `app/shared/adapters/aws_resource_explorer.py`,
     - `app/shared/adapters/aws_cur.py` (`s3.list_objects_v2` bounded traversal cap + warning).
3. Closed `VAL-BILL-006` by centralizing entitlement plan synchronization:
   - added `app/modules/billing/domain/billing/entitlement_policy.py`,
   - replaced scattered direct `Tenant.plan` update statements in:
     - `app/modules/billing/domain/billing/dunning_service.py`,
     - `app/modules/billing/domain/billing/paystack_webhook_impl.py`,
   - added tier normalization + rowcount guardrails for deterministic, fail-closed sync semantics.
4. Post-closure sanity checks:
   - concurrency: duplicate webhook/dunning branch behavior preserved by existing queue/idempotency tests,
   - observability: auth-coverage and entitlement sync add explicit log events for gate visibility,
   - deterministic replay/snapshot stability/export integrity: no schema or export contract changes introduced in this pass,
   - failure modes/misconfiguration: anonymous LLM model access now rejects (`401`) and internal job processing requires explicit secret dependency.
5. Validation evidence:
   - `uv run ruff check app/modules/governance/api/v1/jobs.py app/modules/governance/api/v1/settings/llm.py scripts/verify_api_auth_coverage.py app/shared/adapters/aws_pagination.py app/shared/adapters/aws_resource_explorer.py app/shared/adapters/aws_cur.py scripts/run_enterprise_tdd_gate.py app/modules/billing/domain/billing/entitlement_policy.py app/modules/billing/domain/billing/dunning_service.py app/modules/billing/domain/billing/paystack_webhook_impl.py tests/unit/ops/test_verify_api_auth_coverage.py tests/unit/shared/adapters/test_aws_pagination.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py tests/unit/services/billing/test_entitlement_policy.py tests/unit/services/billing/test_dunning_service.py tests/unit/services/billing/test_paystack_billing_branches.py tests/unit/governance/settings/test_llm_settings.py` -> passed.
   - `uv run mypy app/modules/governance/api/v1/jobs.py app/modules/governance/api/v1/settings/llm.py app/shared/adapters/aws_pagination.py app/shared/adapters/aws_resource_explorer.py app/shared/adapters/aws_cur.py scripts/verify_api_auth_coverage.py scripts/run_enterprise_tdd_gate.py app/modules/billing/domain/billing/entitlement_policy.py app/modules/billing/domain/billing/dunning_service.py app/modules/billing/domain/billing/paystack_webhook_impl.py --hide-error-context --no-error-summary` -> passed.
   - `TESTING=true DEBUG=false uv run python3 scripts/verify_api_auth_coverage.py` -> `Auth coverage check passed.`
   - `DEBUG=false uv run pytest -q --no-cov tests/unit/services/billing/test_entitlement_policy.py tests/unit/services/billing/test_dunning_service.py tests/unit/services/billing/test_paystack_billing_branches.py tests/unit/ops/test_verify_api_auth_coverage.py tests/unit/shared/adapters/test_aws_pagination.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py tests/unit/governance/test_jobs_api.py tests/unit/governance/settings/test_llm_settings.py` -> `98 passed`.

Execution update (2026-02-28O): VAL-ADAPT-002+ decomposition continuation (license adapter)
1. Advanced `VAL-ADAPT-002+` by extracting manual-feed and vendor-resolution concerns out of `app/shared/adapters/license.py`:
   - added `app/shared/adapters/license_feed_ops.py`:
     - manual feed validation,
     - manual feed cost-row shaping/window filtering,
     - manual feed activity consolidation and normalization helpers.
   - added `app/shared/adapters/license_vendor_registry.py`:
     - canonical alias-to-native-vendor resolution.
2. Replaced conditional-heavy vendor dispatch in `LicenseAdapter` with table-driven routing while preserving existing method seams:
   - verify dispatch map (`_VERIFY_METHOD_BY_VENDOR`),
   - revoke dispatch map (`_REVOKE_METHOD_BY_VENDOR`),
   - activity dispatch map (`_ACTIVITY_METHOD_BY_VENDOR`),
   - native stream dispatch map (`_NATIVE_STREAM_METHOD_BY_VENDOR`).
   - wrapper methods (`_revoke_*`, `_list_*_activity`, `_verify_*`) retained to avoid behavioral drift and preserve existing test patch points.
3. Added dedicated helper tests:
   - `tests/unit/shared/adapters/test_license_feed_ops.py`
   - `tests/unit/shared/adapters/test_license_vendor_registry.py`
4. Post-closure sanity checks:
   - concurrency: no mutable shared global state introduced; helper modules are pure/stateless,
   - observability: existing adapter warning/error log events preserved in main adapter and vendor ops,
   - deterministic replay/snapshot stability: no schema/export/serialization contracts changed,
   - failure modes: native/manual fallback semantics preserved and re-verified in branch coverage packs,
   - operational misconfiguration: alias resolution remains fail-closed (`None`) for unsupported manual/unknown vendor combinations.
5. Validation evidence:
   - `uv run ruff check app/shared/adapters/license.py app/shared/adapters/license_feed_ops.py app/shared/adapters/license_vendor_registry.py tests/unit/shared/adapters/test_license_feed_ops.py tests/unit/shared/adapters/test_license_vendor_registry.py tests/unit/services/adapters/test_license_verification_stream_branches.py tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/services/adapters/test_adapter_helper_branches.py tests/unit/services/adapters/test_cloud_plus_adapters.py tests/unit/shared/adapters/test_google_workspace.py` -> passed.
   - `uv run mypy app/shared/adapters/license.py app/shared/adapters/license_feed_ops.py app/shared/adapters/license_vendor_registry.py --hide-error-context --no-error-summary` -> passed.
   - `DEBUG=false uv run pytest -q --no-cov tests/unit/shared/adapters/test_license_feed_ops.py tests/unit/shared/adapters/test_license_vendor_registry.py tests/unit/services/adapters/test_adapter_helper_branches.py tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/services/adapters/test_license_verification_stream_branches.py tests/unit/services/adapters/test_cloud_plus_adapters.py tests/unit/shared/adapters/test_google_workspace.py` -> `123 passed`.

Execution update (2026-02-27): FIN evidence contract + release-gate wiring
1. Added strict finance evidence verifier:
   - `scripts/verify_finance_guardrails_evidence.py`
   - Verifies:
     - timestamp/window validity,
     - tier-level unit economics consistency,
     - blended margin and discount-impact recomputation,
     - stress-scenario consistency,
     - `FIN-GATE-1..5` boolean integrity and threshold compliance.
2. Added finance evidence artifacts:
   - `docs/ops/evidence/finance_guardrails_TEMPLATE.json`
   - `docs/ops/evidence/finance_guardrails_2026-02-27.json`
   - `docs/ops/evidence/README.md` updated with finance capture/verify contract.
3. Release gate wiring extended:
   - `scripts/run_enterprise_tdd_gate.py`
     - env support:
       - `ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_PATH`
       - `ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_REQUIRED`
       - `ENFORCEMENT_FINANCE_GUARDRAILS_EVIDENCE_MAX_AGE_HOURS`
   - `scripts/run_enforcement_release_evidence_gate.py`
     - CLI support:
       - `--finance-evidence-path`
       - `--finance-evidence-required`
       - `--finance-max-age-hours`
4. Added regression coverage:
   - `tests/unit/ops/test_verify_finance_guardrails_evidence.py`
   - `tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
   - `tests/unit/supply_chain/test_run_enforcement_release_evidence_gate.py`
   - `tests/unit/ops/test_release_artifact_templates_pack.py`
5. Status note:
   - This closes FIN gate automation baseline only.
   - `FIN-001..FIN-008` remain open until production telemetry and pricing-policy decisions are approved.

Execution update (2026-02-27): PKG-020 pricing benchmark evidence register + gate wiring
1. Added strict pricing benchmark register verifier:
   - `scripts/verify_pricing_benchmark_register.py`
   - Verifies:
     - HTTPS source URL integrity,
     - source class integrity (`vendor_pricing_page`, `industry_benchmark_report`, `standards_guidance`, `analyst_report`),
     - crawl recency against max-source-age policy,
     - minimum source count and minimum confidence thresholds,
     - summary recomputation integrity,
     - `PKG-GATE-020` boolean integrity.
2. Added pricing benchmark evidence artifacts:
   - `docs/ops/evidence/pricing_benchmark_register_TEMPLATE.json`
   - `docs/ops/evidence/pricing_benchmark_register_2026-02-27.json`
   - `docs/ops/evidence/README.md` updated with capture/verify contract.
3. Release gate wiring extended:
   - `scripts/run_enterprise_tdd_gate.py`
     - env support:
       - `ENFORCEMENT_PRICING_BENCHMARK_REGISTER_PATH`
       - `ENFORCEMENT_PRICING_BENCHMARK_REGISTER_REQUIRED`
       - `ENFORCEMENT_PRICING_BENCHMARK_MAX_SOURCE_AGE_DAYS`
   - `scripts/run_enforcement_release_evidence_gate.py`
     - CLI support:
       - `--pricing-benchmark-register-path`
       - `--pricing-benchmark-register-required`
       - `--pricing-benchmark-max-source-age-days`
4. Added regression coverage:
   - `tests/unit/ops/test_verify_pricing_benchmark_register.py`
   - `tests/unit/ops/test_pricing_benchmark_register_pack.py`
   - `tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
   - `tests/unit/supply_chain/test_run_enforcement_release_evidence_gate.py`
   - `tests/unit/ops/test_release_artifact_templates_pack.py`
5. Status note:
   - This closes PKG-020 automation baseline.
   - Policy decisions for remaining packaging/commercial backlog still require pricing committee approval.

Execution update (2026-02-27): PKG-003 + PKG-014 runtime gate hardening
1. Implemented API-boundary feature enforcement guards:
   - `app/modules/enforcement/api/v1/common.py`
   - `app/modules/enforcement/api/v1/enforcement.py`
   - `app/modules/enforcement/api/v1/policy_budget_credit.py`
   - `app/modules/enforcement/api/v1/approvals.py`
   - `app/modules/enforcement/api/v1/actions.py`
   - `app/modules/enforcement/api/v1/reservations.py`
   - `app/modules/enforcement/api/v1/exports.py`
   - `app/modules/enforcement/api/v1/ledger.py`
2. Guard behavior hardening:
   - tier resolution now supports tenant-plan fallback via DB lookup to avoid stale caller tier payload drift.
3. Added comprehensive test coverage:
   - `tests/unit/enforcement/test_enforcement_common_feature_guards.py`
   - `tests/unit/enforcement/test_enforcement_feature_runtime_gating.py`
   - updated direct wrapper tests for explicit tier context:
     - `tests/unit/enforcement/test_enforcement_endpoint_wrapper_coverage.py`
     - `tests/unit/enforcement/test_approvals_api_direct.py`
4. Regenerated and verified enforceability artifact:
   - `docs/ops/feature_enforceability_matrix_2026-02-27.json`
   - `scripts/verify_feature_enforceability_matrix.py` -> passed.
5. Release evidence gate reconfirmed after runtime gate hardening:
   - `uv run python3 scripts/run_enforcement_release_evidence_gate.py --stress-evidence-path docs/ops/evidence/enforcement_stress_artifact_2026-02-27.json --failure-evidence-path docs/ops/evidence/enforcement_failure_injection_2026-02-27.json --stress-required-database-engine postgresql`
   - result: passed (`815 passed`, coverage thresholds satisfied).

Execution update (2026-02-28): PKG/FIN policy-decision evidence gate wiring
1. Added strict PKG/FIN policy decision verifier:
   - `scripts/verify_pkg_fin_policy_decisions.py`
   - Enforces:
     - explicit pricing-policy choices (`flat_floor|spend_based|hybrid`),
     - explicit migration strategy + window,
     - explicit growth/pro commercial boundary choices,
     - approval sign-offs (`finance`, `product`, `go-to-market`),
     - telemetry window sufficiency (`>= 2` months) with required tier coverage.
2. Added policy-decision evidence artifacts:
   - `docs/ops/evidence/pkg_fin_policy_decisions_TEMPLATE.json`
   - `docs/ops/evidence/pkg_fin_policy_decisions_2026-02-28.json`
   - `docs/ops/evidence/README.md` updated with capture/verify contract.
3. Release-gate wiring extended:
   - `scripts/run_enterprise_tdd_gate.py`
     - env support:
       - `ENFORCEMENT_PKG_FIN_POLICY_DECISIONS_PATH`
       - `ENFORCEMENT_PKG_FIN_POLICY_DECISIONS_REQUIRED`
       - `ENFORCEMENT_PKG_FIN_POLICY_DECISIONS_MAX_AGE_HOURS`
   - `scripts/run_enforcement_release_evidence_gate.py`
     - CLI support:
       - `--pkg-fin-policy-decisions-path`
       - `--pkg-fin-policy-decisions-required`
       - `--pkg-fin-policy-decisions-max-age-hours`
4. Regression coverage added:
   - `tests/unit/ops/test_verify_pkg_fin_policy_decisions.py`
   - `tests/unit/ops/test_pkg_fin_policy_decisions_pack.py`
   - `tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
   - `tests/unit/supply_chain/test_run_enforcement_release_evidence_gate.py`
   - `tests/unit/ops/test_release_artifact_templates_pack.py`
5. End-to-end closure validation rerun:
   - `DEBUG=false uv run python3 scripts/run_enforcement_release_evidence_gate.py --stress-evidence-path docs/ops/evidence/enforcement_stress_artifact_2026-02-27.json --failure-evidence-path docs/ops/evidence/enforcement_failure_injection_2026-02-27.json --finance-evidence-path docs/ops/evidence/finance_guardrails_2026-02-27.json --pricing-benchmark-register-path docs/ops/evidence/pricing_benchmark_register_2026-02-27.json --pkg-fin-policy-decisions-path docs/ops/evidence/pkg_fin_policy_decisions_2026-02-28.json --finance-evidence-required --pricing-benchmark-register-required --pkg-fin-policy-decisions-required`
   - result: passed (`845 passed`) with all coverage gates satisfied.
6. Status note:
   - automation baseline for policy-decision evidence is closed,
   - decision execution remains governed by live telemetry refresh cadence (`FIN-*` operational follow-through).

Execution update (2026-02-28G): PKG/FIN decision-backlog sign-off contract hardening
1. Strengthened `scripts/verify_pkg_fin_policy_decisions.py` with a canonical decision-backlog contract:
   - requires `decision_backlog.required_decision_ids` to exactly match the tracked PKG/FIN decision set,
   - requires `decision_backlog.decision_items[*]` coverage for every required ID with explicit owner, owner function, resolution, approval record, and approval timestamp,
   - requires `target_date` and `success_criteria` for all `scheduled_postlaunch` decisions,
   - enforces launch-blocking items to be prelaunch-locked for a passing release state.
2. Added explicit release gates for decision backlog governance:
   - `pkg_fin_gate_backlog_coverage_complete`
   - `pkg_fin_gate_launch_blockers_resolved`
   - `pkg_fin_gate_postlaunch_commitments_scheduled`
3. Updated evidence artifacts/docs to the hardened contract:
   - `docs/ops/evidence/pkg_fin_policy_decisions_TEMPLATE.json`
   - `docs/ops/evidence/pkg_fin_policy_decisions_2026-02-28.json`
   - `docs/ops/evidence/README.md`
4. Added TDD coverage for new failure modes:
   - `tests/unit/ops/test_verify_pkg_fin_policy_decisions.py`
   - `tests/unit/ops/test_pkg_fin_policy_decisions_pack.py`
   - `tests/unit/ops/test_release_artifact_templates_pack.py`
5. Validation rerun:
   - `DEBUG=false uv run pytest -q --no-cov tests/unit/ops/test_verify_pkg_fin_policy_decisions.py tests/unit/ops/test_pkg_fin_policy_decisions_pack.py tests/unit/ops/test_release_artifact_templates_pack.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py tests/unit/supply_chain/test_run_enforcement_release_evidence_gate.py` -> `48 passed`
   - `uv run python3 scripts/verify_pkg_fin_policy_decisions.py --evidence-path docs/ops/evidence/pkg_fin_policy_decisions_2026-02-28.json --max-artifact-age-hours 744` -> passed.

Execution update (2026-02-28): FIN live telemetry + committee packet automation
1. Added finance telemetry snapshot collector and verifier:
   - `scripts/collect_finance_telemetry_snapshot.py`
   - `scripts/verify_finance_telemetry_snapshot.py`
2. Added monthly finance committee packet generator:
   - `scripts/generate_finance_committee_packet.py`
   - outputs:
     - finance guardrail artifact JSON,
     - committee packet JSON,
     - tier/scenario CSV exports,
     - optional alert webhook dispatch on gate failure.
3. Added telemetry evidence and assumptions templates:
   - `docs/ops/evidence/finance_telemetry_snapshot_TEMPLATE.json`
   - `docs/ops/evidence/finance_telemetry_snapshot_2026-02-28.json`
   - `docs/ops/evidence/finance_committee_packet_assumptions_TEMPLATE.json`
   - `docs/ops/evidence/finance_committee_packet_assumptions_2026-02-28.json`
4. Expanded release-gate wiring:
   - `scripts/run_enterprise_tdd_gate.py`
     - `ENFORCEMENT_FINANCE_TELEMETRY_SNAPSHOT_PATH`
     - `ENFORCEMENT_FINANCE_TELEMETRY_SNAPSHOT_REQUIRED`
     - `ENFORCEMENT_FINANCE_TELEMETRY_SNAPSHOT_MAX_AGE_HOURS`
   - `scripts/run_enforcement_release_evidence_gate.py`
     - `--finance-telemetry-snapshot-path`
     - `--finance-telemetry-snapshot-required`
     - `--finance-telemetry-max-age-hours`
5. Regression/tests:
   - `tests/unit/ops/test_verify_finance_telemetry_snapshot.py`
   - `tests/unit/ops/test_collect_finance_telemetry_snapshot.py`
   - `tests/unit/ops/test_generate_finance_committee_packet.py`
   - `tests/unit/ops/test_finance_telemetry_snapshot_pack.py`
   - updated:
     - `tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
     - `tests/unit/supply_chain/test_run_enforcement_release_evidence_gate.py`
     - `tests/unit/ops/test_release_artifact_templates_pack.py`
6. Execution evidence:
   - `DEBUG=false uv run pytest --no-cov -q tests/unit/ops/test_verify_finance_telemetry_snapshot.py tests/unit/ops/test_collect_finance_telemetry_snapshot.py tests/unit/ops/test_generate_finance_committee_packet.py tests/unit/ops/test_finance_telemetry_snapshot_pack.py tests/unit/ops/test_release_artifact_templates_pack.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py tests/unit/supply_chain/test_run_enforcement_release_evidence_gate.py` -> `48 passed`.
   - `uv run ruff check ...` (new telemetry scripts/tests + gate files) -> passed.
   - `uv run mypy scripts/verify_finance_guardrails_evidence.py scripts/verify_finance_telemetry_snapshot.py scripts/collect_finance_telemetry_snapshot.py scripts/generate_finance_committee_packet.py scripts/run_enterprise_tdd_gate.py scripts/run_enforcement_release_evidence_gate.py --hide-error-context --no-error-summary` -> passed.
   - `DEBUG=false uv run python3 scripts/run_enforcement_release_evidence_gate.py --stress-evidence-path docs/ops/evidence/enforcement_stress_artifact_2026-02-27.json --failure-evidence-path docs/ops/evidence/enforcement_failure_injection_2026-02-27.json --finance-evidence-path docs/ops/evidence/finance_guardrails_2026-02-27.json --finance-telemetry-snapshot-path docs/ops/evidence/finance_telemetry_snapshot_2026-02-28.json --pricing-benchmark-register-path docs/ops/evidence/pricing_benchmark_register_2026-02-27.json --pkg-fin-policy-decisions-path docs/ops/evidence/pkg_fin_policy_decisions_2026-02-28.json --finance-evidence-required --finance-telemetry-snapshot-required --pricing-benchmark-register-required --pkg-fin-policy-decisions-required` -> passed (`860 passed`, coverage gates satisfied).

Execution update (2026-02-27): release evidence DB-backend provenance hardening
1. Stress artifact capture now records runtime DB backend metadata from `/health`:
   - `runtime.database_engine` plus health probe context are emitted by `scripts/load_test_api.py`.
2. Stress verifier now enforces backend contract:
   - `scripts/verify_enforcement_stress_evidence.py` requires `runtime.database_engine` to match `--required-database-engine` (default `postgresql`).
3. Enterprise/release gate wiring now passes backend requirement explicitly:
   - env: `ENFORCEMENT_STRESS_EVIDENCE_REQUIRED_DATABASE_ENGINE`
   - release gate CLI: `--stress-required-database-engine`
4. Docs/template contract updated:
   - `docs/ops/enforcement_stress_evidence_2026-02-25.md`
   - `docs/ops/enforcement_failure_injection_matrix_2026-02-25.md`
   - `docs/ops/evidence/enforcement_stress_artifact_TEMPLATE.json`
5. Post-change validation result against recaptured PostgreSQL staged artifact:
   - `uv run python scripts/verify_enforcement_stress_evidence.py --evidence-path docs/ops/evidence/enforcement_stress_artifact_2026-02-27.json --min-duration-seconds 30 --min-concurrent-users 10 --required-database-engine postgresql --max-p95-seconds 2.0 --max-error-rate-percent 1.0 --min-throughput-rps 0.5` -> passed.
6. Release evidence gate wiring check:
   - `uv run python scripts/run_enforcement_release_evidence_gate.py --stress-evidence-path docs/ops/evidence/enforcement_stress_artifact_2026-02-27.json --failure-evidence-path docs/ops/evidence/enforcement_failure_injection_2026-02-27.json --stress-required-database-engine postgresql --dry-run` -> passed.

## Execution update (2026-02-27): BSAFE-009 + BSAFE-010 staged evidence closure

1. Root-cause hardening applied for local/staged stress reliability:
   - auth schema-mismatch probe now avoids nested savepoints on SQLite backends to prevent `no such savepoint` auth failures under concurrent load.
   - Evidence: `app/shared/core/auth.py` and tests in `tests/unit/core/test_auth_branch_paths.py`.
2. `BSAFE-009` staged stress artifact captured with release workload floor:
   - `rounds=3`, `duration_seconds=30`, `concurrent_users=10`
   - `error_rate=0.0%`, `p95=0.0644s`, `min_throughput_rps=59.6013`
   - Verified via `scripts/verify_enforcement_stress_evidence.py`.
3. `BSAFE-010` staged failure-injection artifact captured from real FI test execution:
   - Generated with `scripts/generate_enforcement_failure_injection_evidence.py`
   - Scenarios `FI-001..FI-005` all passed with summary integrity fields.
   - Verified via `scripts/verify_enforcement_failure_injection_evidence.py`.
4. Combined release-evidence gate passed end-to-end:
   - `scripts/run_enforcement_release_evidence_gate.py` completed successfully and invoked enterprise TDD gate (`815 passed`, coverage gates satisfied).

## Scope of this gap review

Requirement pack A:
- Real-time decision point (deterministic engine, immutable ledger, idempotency + reservation)
- Pre-provision hooks (K8s admission, Terraform/CI preflight, signed approval tokens)
- Economic policy model (policy-as-code, approval routing, fail-open/fail-closed per environment)
- Credits/entitlements waterfall (allocations, emergency credits, reservation lifecycle)

Requirement pack B:
- `app/modules/enforcement/` with policies, decisions/ledger, approvals, actions orchestration
- API surface for gate, approvals, policies, budgets, credits

Requirement pack C:
- Decision engine derived inputs and outputs
- HITL pattern parity with optimization remediation
- Approval token claim/binding requirements

## Audit method (fact-only)

- Reviewed enforcement API/domain/model code paths.
- Reviewed related auth/approval-permission and pricing modules.
- Verified enforcement test suite health.

Validation run:
- `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_api.py tests/unit/enforcement/test_enforcement_property_and_concurrency.py tests/unit/enforcement/test_reconciliation_worker.py tests/unit/tasks/test_enforcement_scheduler_tasks.py tests/governance/test_hard_limit_enforcement.py`
- Result: `69 passed in 110.20s`

## Already implemented (do not re-open)

1. Enforcement module exists and is mounted at `/api/v1/enforcement`.
   - Evidence: `app/modules/enforcement/**`, `app/shared/core/app_routes.py`

2. Synchronous gate endpoints exist for Terraform and K8s admission.
   - Evidence: `app/modules/enforcement/api/v1/enforcement.py`

3. Gate decision enum includes `ALLOW`, `DENY`, `REQUIRE_APPROVAL`, `ALLOW_WITH_CREDITS`.
   - Evidence: `app/models/enforcement.py`

4. Deterministic evaluation with policy versioning + idempotency exists.
   - Evidence: `app/modules/enforcement/domain/service.py`, `app/models/enforcement.py`

5. Immutable append-only decision ledger exists.
   - Evidence: `app/models/enforcement.py` (`before_update`/`before_delete` listeners), `app/modules/enforcement/api/v1/ledger.py`

6. HITL approvals and signed approval token issuance/consumption/replay checks exist.
   - Evidence: `app/modules/enforcement/api/v1/approvals.py`, `app/modules/enforcement/domain/service.py`

7. Policies, budgets, credits, reservations, exports endpoints exist.
   - Evidence: `app/modules/enforcement/api/v1/policy_budget_credit.py`, `reservations.py`, `exports.py`

## Current capability baseline (fact-checked)

| Capability | Current status | Evidence |
|---|---|---|
| Synchronous gate decisions for Terraform and K8s admission | Implemented | `app/modules/enforcement/api/v1/enforcement.py` |
| Decision outputs include `ALLOW`, `DENY`, `REQUIRE_APPROVAL`, `ALLOW_WITH_CREDITS` | Implemented | `app/models/enforcement.py` |
| Deterministic decisioning with policy versioning + idempotency + budget/credit waterfall | Implemented with caveats | `app/modules/enforcement/domain/service.py`, `app/models/enforcement.py` |
| Immutable append-only decision ledger + ledger API | Implemented | `app/models/enforcement.py`, `app/modules/enforcement/api/v1/ledger.py` |
| HITL approvals with signed token + consume + replay protection | Implemented | `app/modules/enforcement/api/v1/approvals.py`, `app/modules/enforcement/domain/service.py` |
| Policy/Budget/Credit APIs | Implemented | `app/modules/enforcement/api/v1/policy_budget_credit.py` |
| Reservation lifecycle + reconciliation APIs | Implemented | `app/modules/enforcement/api/v1/reservations.py`, `app/modules/enforcement/domain/service.py` |
| Enforcement export parity + archive APIs | Implemented | `app/modules/enforcement/api/v1/exports.py` |

Capability caveats currently tracked:
1. Gate response token semantics contract finalization: `ECP-014`.

## Current role access model (fact-checked)

| Role | Effective capabilities in current API layer | Evidence |
|---|---|---|
| `member` (and above) | Gate calls; approval request/queue/approve/deny/consume; read policy/budget/credit | `app/modules/enforcement/api/v1/enforcement.py`, `app/modules/enforcement/api/v1/approvals.py`, `app/modules/enforcement/api/v1/policy_budget_credit.py` |
| `admin` (and owner) | Policy/budget/credit writes; reservations; ledger; exports | `app/modules/enforcement/api/v1/policy_budget_credit.py`, `app/modules/enforcement/api/v1/reservations.py`, `app/modules/enforcement/api/v1/ledger.py`, `app/modules/enforcement/api/v1/exports.py` |
| `owner` | Role-check bypass (`owner > admin > member`) | `app/shared/core/auth.py` |

Approval-permission note:
- Reviewer authority is also permission-gated by approval permission resolution (`owner` defaults all, `admin` defaults nonprod, SCIM can grant additional permissions). See `app/shared/core/approval_permissions.py`.
- User persona is not a permission boundary; role is the boundary (`owner/admin/member`). See `app/models/tenant.py` and `app/shared/core/auth.py`.

## Latest checklist mapping (current state)

| Checklist item | Tracking outcome |
|---|---|
| `POST /gate/cloud-event` missing | Closed as `ECP-009` (`DONE`, 2026-02-25) |
| Decision engine computed `forecast_eom`/`burn_rate`/`risk` missing in enforcement | Closed as `ECP-001` (`DONE`, 2026-02-25) |
| Plan/feature-flag entitlement stage missing in enforcement waterfall | Closed as `ECP-002` (`DONE`, 2026-02-25) |
| Terraform preflight endpoint present | Closed as `ECP-007` (`DONE`, 2026-02-25) |
| K8s endpoint is generic `GateRequest`, not native `AdmissionReview` | Closed as `ECP-006` (`DONE`, 2026-02-25) |
| Signed approval token with replay/tamper controls | Implemented baseline |
| Token claims missing `project_id` + explicit `max_cost_delta` semantics | Closed as `ECP-010` (`DONE`, 2026-02-25) |
| Approval routing is partial; no configurable routing graph/two-person rule | Closed as `ECP-003` (`DONE`, 2026-02-24), with policy routing + maker-checker separation |
| Fail-open/fail-closed is source-level, not per-environment | Closed as `ECP-005` (`DONE`, 2026-02-24), with source x environment mode matrix |
| Reservation lifecycle exists, but credit grant decrement path is incomplete | Closed as `ECP-004` (`DONE`, 2026-02-24) |
| Ledger lacks first-class `approval_id` linkage fields | Closed as `ECP-008` (`DONE`, 2026-02-25) |
| Forecast/anomaly exists in reporting, not wired into enforcement decisions | Closed as `ECP-001` (`DONE`, 2026-02-25) |

## Gap tracker (open work)

### Tracking board

| ID | Priority | Status | Needed for enterprise gate baseline | Area |
|---|---|---|---|---|
| ECP-001 | P0 | DONE | Yes | Decision engine computed context |
| ECP-002 | P0 | DONE | Yes | Entitlement waterfall completeness |
| ECP-003 | P0 | DONE | Yes | Approval routing + RBAC hardening |
| ECP-004 | P0 | DONE | Yes | Credit consumption lifecycle correctness |
| ECP-005 | P0 | DONE | Yes | Policy model granularity per environment |
| ECP-006 | P1 | DONE | Yes | K8s admission contract compatibility |
| ECP-007 | P1 | DONE | Yes | Terraform/CI preflight integration contract |
| ECP-008 | P1 | DONE | Yes | Ledger enrichment for approval linkage |
| ECP-009 | P1 | DONE | Optional | Cloud-event gate endpoint |
| ECP-010 | P1 | DONE | Yes | Approval token claim completeness |
| ECP-011 | P2 | DONE | No | Actions orchestration domain expansion |
| ECP-012 | P0 | DONE | Yes | Reservation concurrency serialization |
| ECP-013 | P1 | DONE | Yes | Policy-as-code engine formalization |
| ECP-014 | P2 | DONE | No | Gate approval-token issuance contract |

### ECP-001: Decision engine computed context is missing

- Why needed:
  - Requirement pack C expects gate-time computation of `forecast_eom`, `burn_rate`, and risk context, not only caller-provided estimates.
- Current state:
  - Gate consumes `estimated_monthly_delta_usd` and `estimated_hourly_delta_usd` directly from request payload.
  - No enforcement-domain integration to reporting forecast/anomaly or optimization inventory.
- Evidence:
  - `app/modules/enforcement/api/v1/schemas.py`
  - `app/modules/enforcement/domain/service.py`
  - Forecast/anomaly endpoints exist outside enforcement (`app/modules/reporting/api/v1/costs.py`) but are not used by enforcement.
- Required change:
  1. Add deterministic derived context builder in enforcement domain.
  2. Persist derived context snapshot into decision payload/ledger fields.
  3. Version the computation rules with policy version.
- Acceptance criteria:
  1. Gate response and ledger include computed fields (`forecast_eom`, `burn_rate`, `risk_class`, etc.).
  2. Same input + same data snapshot always produces same computed outputs.
  3. Unit tests cover deterministic behavior and stale-data fallback semantics.

Status update (2026-02-25): DONE
- Closure summary:
  - Added deterministic computed context builder in enforcement gate flow with explicit snapshot fields:
    - `mtd_spend_usd`, `burn_rate_daily_usd`, `forecast_eom_usd`
    - anomaly signal (`anomaly_kind`, `anomaly_delta_usd`, `anomaly_percent`)
    - risk assessment (`risk_class`, `risk_score`, `risk_factors`)
    - context metadata (`context_version`, policy version, month window, observed data days, data-source mode).
  - Wired computed context into gate response contract via `computed_context`.
  - Persisted computed context core values on decision rows and append-only decision ledger rows (`burn_rate_daily_usd`, `forecast_eom_usd`, `risk_class`, `risk_score`, `anomaly_signal`).
  - Embedded computed risk into decision request metadata (`risk_level` fallback + computed risk fields) so approval routing can consume deterministic risk without caller-supplied risk tags.
  - Added explicit fallback semantics for missing/unavailable cost history (`data_source_mode = none|all_status|unavailable`) with deterministic zeroed forecast/burn outputs.
- Evidence:
  - `app/modules/enforcement/domain/service.py` (`_build_decision_computed_context`, `_load_daily_cost_totals`, `_derive_risk_assessment`, gate/fail-safe integration, `gate_result_to_response`)
  - `app/models/enforcement.py` (`EnforcementDecision` + `EnforcementDecisionLedger` computed context columns)
  - `migrations/versions/i5j6k7l8m9n0_add_enforcement_decision_computed_context_fields.py`
  - `app/modules/enforcement/api/v1/schemas.py` (`GateDecisionResponse.computed_context`, ledger item context fields)
  - `app/modules/enforcement/api/v1/ledger.py` (ledger API mapping for computed context fields)
  - Tests:
    - `tests/unit/enforcement/test_enforcement_service.py` (computed context deterministic values + no-history fallback + ledger persistence)
    - `tests/unit/enforcement/test_enforcement_api.py` (gate response includes computed context, ledger endpoint includes context fields)
  - Validation:
    - `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_api.py tests/unit/enforcement/test_enforcement_property_and_concurrency.py` -> `83 passed`
    - `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_property_and_concurrency.py tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_api.py tests/unit/enforcement/test_reconciliation_worker.py tests/unit/tasks/test_enforcement_scheduler_tasks.py tests/governance/test_hard_limit_enforcement.py` -> `91 passed`

### ECP-002: Entitlement waterfall does not match required order

- Why needed:
  - Requirement pack C defines deterministic order:
    1) plan limits, 2) project allocation, 3) reserved credits, 4) org emergency credits, 5) enterprise ceiling.
- Current state:
  - Current waterfall effectively uses allocation headroom + aggregated credits headroom.
  - No explicit stage for plan limits or enterprise ceiling in enforcement decisions.
  - No separate reserved vs emergency credit pools.
- Evidence:
  - `app/modules/enforcement/domain/service.py` (`_evaluate_budget_waterfall`, `_get_active_credit_headroom`)
  - `app/shared/core/pricing.py` (plan limits exist globally, not applied in enforcement)
  - `app/models/enforcement.py` (single `scope_key` budget/credit model)
- Required change:
  1. Add explicit waterfall stage evaluation with stable reason codes per stage.
  2. Add policy/data fields for reserved vs emergency credits.
  3. Apply plan/enterprise ceilings in decision engine.
- Acceptance criteria:
  1. Decision payload includes per-stage pass/fail and consumed amounts.
  2. Reason codes uniquely identify first limiting stage.
  3. Tests validate stage precedence and edge cases.

Status update (2026-02-25): DONE
- Closure summary:
  - Implemented deterministic entitlement waterfall in enforcement with explicit stages:
    1) plan limit, 2) project allocation, 3) reserved credits, 4) org emergency credits, 5) enterprise ceiling.
  - Added policy-level ceiling fields to enforcement policy model and API (`plan_monthly_ceiling_usd`, `enterprise_monthly_ceiling_usd`).
  - Added split credit pools (`reserved`, `emergency`) to credit grants and reservation allocations, with deterministic reserve ordering and pool-aware persistence.
  - Updated gate evaluation to include stage snapshot and entitlement trace in decision payload:
    - `entitlement_reason_code`
    - `entitlement_waterfall`
    - split credit reservation details.
  - Preserved existing compatibility behavior for unconfigured project budgets (`no_budget_configured`) while enforcing explicit ceilings when present.
- Evidence:
  - `app/models/enforcement.py` (`EnforcementPolicy` ceiling fields; `EnforcementCreditGrant.pool_type`; `EnforcementCreditReservationAllocation.credit_pool_type`)
  - `migrations/versions/h4i5j6k7l8m9_add_enforcement_entitlement_waterfall_fields.py`
  - `app/modules/enforcement/api/v1/schemas.py` (policy ceiling + credit pool schema fields)
  - `app/modules/enforcement/api/v1/policy_budget_credit.py` (policy/credit API persistence for new fields)
  - `app/modules/enforcement/domain/service.py` (`evaluate_gate`, `_get_credit_headrooms`, `_reserve_credit_for_decision`, `_evaluate_entitlement_waterfall`)
  - Tests:
    - `tests/unit/enforcement/test_enforcement_service.py` (plan ceiling enforcement, enterprise ceiling enforcement, reserved→emergency credit ordering)
    - `tests/unit/enforcement/test_enforcement_api.py` (policy ceiling API round-trip, emergency credit create/read)
  - Validation:
    - `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_api.py tests/unit/enforcement/test_enforcement_property_and_concurrency.py` -> `81 passed`
    - `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_property_and_concurrency.py tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_api.py tests/unit/enforcement/test_reconciliation_worker.py tests/unit/tasks/test_enforcement_scheduler_tasks.py tests/governance/test_hard_limit_enforcement.py` -> `89 passed`

### ECP-003: Approval routing and endpoint RBAC are too permissive for target model

- Why needed:
  - Requirement pack A/B asks for admin/owner approval controls and optionally two-person rule for production actions.
- Current state:
  - Approval API routes are role-gated at `member`.
  - Service enforces prod/nonprod permission checks, but no configurable routing graph/quorum logic.
  - Existing approver permissions are remediation-scoped (`remediation.approve.nonprod|prod`) and reused for enforcement approvals.
  - SCIM group mappings already support approval permission assignment, but the enforcement approver-group model is not explicitly formalized as a contract.
- Evidence:
  - `app/modules/enforcement/api/v1/approvals.py`
  - `app/modules/enforcement/domain/service.py` (`approve_request`)
  - `app/shared/core/approval_permissions.py`
- Required change:
  1. Tighten endpoint dependencies for approval queue/review paths.
  2. Introduce configurable routing rules by env/action/cost/risk.
  3. Add optional two-person rule for production classes.
  4. Define enforcement-specific approver permission model and map it to SCIM group mappings as the primary enterprise control path.
- Acceptance criteria:
  1. Member role cannot approve unless explicitly granted by policy/routing.
  2. Production approvals can enforce dual approval where configured.
  3. Decision/approval records retain routing trace for audit.
  4. Identity settings + SCIM mappings can express and audit approver-group ownership for enforcement actions.

Status update (2026-02-24): DONE
- Closure summary:
  - Added policy-driven approval routing rules (`env`, `action_prefix`, `monthly_delta`, `risk_level`) with deterministic normalization and validation.
  - Added explicit production/nonproduction requester-reviewer separation controls (`maker-checker` style, default enabled for prod).
  - Added approval-level routing trace persistence (`routing_rule_id`, `routing_trace`) for auditability on approve/deny/export.
  - Enforced reviewer authority on both approve and deny paths using:
    1) routing-allowed reviewer roles,
    2) SCIM/role-based approval permission checks,
    3) requester/reviewer separation when configured.
  - Filtered approval queue responses to approvals the current reviewer is authorized to act on.
  - Hardened default boundary: members now require explicit routing allowance plus approval permission; SCIM permission alone is not sufficient.
- Evidence:
  - `app/models/enforcement.py` (`EnforcementPolicy` routing/separation fields, `EnforcementApprovalRequest` routing trace fields)
  - `migrations/versions/f3c4d5e6a7b8_add_enforcement_approval_routing_fields.py`
  - `app/modules/enforcement/api/v1/schemas.py` (`ApprovalRoutingRule`, policy routing/separation fields)
  - `app/modules/enforcement/api/v1/policy_budget_credit.py` (policy routing/separation persistence surface)
  - `app/modules/enforcement/domain/service.py` (`_normalize_policy_approval_routing_rules`, `_resolve_approval_routing_trace`, `_enforce_reviewer_authority`, approve/deny/queue enforcement)
  - `app/modules/enforcement/api/v1/approvals.py` (queue filtering + routing rule response fields)
  - Tests:
    - `tests/unit/enforcement/test_enforcement_service.py` (explicit-member-route requirement, requester/reviewer separation, deny authority enforcement)
    - `tests/unit/enforcement/test_enforcement_api.py` (policy routing rule wiring for member approvers, separation-aware token issuance helper)
    - Validation: `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_api.py` -> `70 passed`

### ECP-004: Credit consumption lifecycle is incomplete

- Why needed:
  - Requirement pack A/C expects deterministic credit reservation and consumption lifecycle.
- Current state:
  - Credit headroom is computed from `remaining_amount_usd`.
  - Creation sets `remaining_amount_usd`, but reservation/reconciliation does not decrement grant balances.
  - Headroom evaluation is not serialized against budget/credit rows for distinct idempotency keys during concurrent gate calls.
- Evidence:
  - `app/modules/enforcement/domain/service.py` (`create_credit_grant`, `_get_active_credit_headroom`, reservation reconcile paths)
  - `app/models/enforcement.py` (`EnforcementCreditGrant.remaining_amount_usd`)
- Required change:
  1. Add atomic debit/credit operations for grant balances tied to reservation lifecycle.
  2. Persist reservation-to-credit-allocation mapping (not only aggregate amounts on decision rows).
  3. Handle expiration/rollback semantics cleanly.
- Acceptance criteria:
  1. Grant balances change consistently with reservation create/release/reconcile.
  2. Double-spend is prevented under concurrency.
  3. Reconciliation exceptions include per-grant impact diagnostics.

Status update (2026-02-24): DONE
- Closure summary:
  - Added first-class credit reservation allocation model and persistence.
  - Added atomic reserve-time debit of `EnforcementCreditGrant.remaining_amount_usd`.
  - Added deterministic settlement/refund lifecycle across deny, approval-expiry, manual reconcile, and overdue auto-reconcile.
  - Added per-grant credit settlement diagnostics in reservation reconciliation payloads and reconciliation exception listing.
- Evidence:
  - `app/models/enforcement.py` (`EnforcementCreditReservationAllocation`)
  - `migrations/versions/e8f5a1c2d3f4_add_enforcement_credit_reservation_allocations.py`
  - `app/modules/enforcement/domain/service.py` (`_reserve_credit_for_decision`, `_settle_credit_reservations_for_decision`, updated `evaluate_gate`/`deny_request`/`reconcile_reservation`/`reconcile_overdue_reservations`)
  - `app/modules/enforcement/api/v1/schemas.py` + `app/modules/enforcement/api/v1/reservations.py` (`credit_settlement` diagnostics surface)
  - Tests:
    - `tests/unit/enforcement/test_enforcement_service.py` (credit reserve/debit, deny refund, partial consume settle, exception diagnostics)
    - Validation: `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_property_and_concurrency.py tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_api.py tests/unit/enforcement/test_reconciliation_worker.py tests/unit/tasks/test_enforcement_scheduler_tasks.py tests/governance/test_hard_limit_enforcement.py` -> `80 passed`

### ECP-012: Reservation concurrency is not serialized for distinct idempotency keys

- Why needed:
  - Requirement pack A expects reservation safety beyond single-key idempotency reuse.
  - Concurrent distinct gate requests can observe stale shared headroom and over-reserve.
- Current state:
  - Single-key idempotency is enforced by `(tenant_id, source, idempotency_key)` uniqueness.
  - Budget/credit headroom read path is not protected by resource-level locking around reserve decisions.
- Evidence:
  - `app/models/enforcement.py` (idempotency unique constraint)
  - `app/modules/enforcement/domain/service.py` (`evaluate_gate`, `_get_reserved_totals`, `_get_active_credit_headroom`)
- Required change:
  1. Add deterministic serialization strategy for reserve-critical section (for example DB locking or transactional compare-and-swap model).
  2. Ensure atomic reserve bookkeeping for both allocation and credit dimensions.
  3. Add contention-safe retry/error semantics.
- Acceptance criteria:
  1. Concurrent distinct-key gate requests cannot over-reserve shared headroom.
  2. Property/concurrency tests prove no oversubscription drift under load.
  3. Decision reason codes and telemetry expose lock/contention outcomes.

Status update (2026-02-24): DONE
- Closure summary:
  - Added tenant-scoped reserve-critical serialization lock in gate evaluation path.
  - Added post-lock idempotency re-check to prevent duplicate work after lock wait.
  - Added concurrency regression test proving no oversubscription under distinct idempotency keys.
- Evidence:
  - `app/modules/enforcement/domain/service.py` (`_acquire_gate_evaluation_lock`, `evaluate_gate` lock + re-check flow)
  - `tests/unit/enforcement/test_enforcement_property_and_concurrency.py` (`test_concurrency_distinct_keys_do_not_oversubscribe_budget_reservations`)
  - Validation: `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_property_and_concurrency.py tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_api.py` -> `62 passed`

### ECP-005: Fail-open/fail-closed controls are not per-environment

- Why needed:
  - Requirement pack A asks for environment-specific fail-open/fail-closed knobs.
- Current state:
  - Enforcement mode is configured by source (`terraform_mode`, `k8s_admission_mode`) only.
  - Environment influences approval requirement, but not mode policy matrix.
- Evidence:
  - `app/models/enforcement.py` (`EnforcementPolicy`)
  - `app/modules/enforcement/domain/service.py` (`mode` selection)
- Required change:
  1. Extend policy model to source x environment mode matrix (for example, prod hard, nonprod soft).
  2. Keep deterministic fallback behavior on timeout/error per environment mode.
- Acceptance criteria:
  1. Policy API supports environment-specific mode configuration.
  2. Fail-safe path respects environment mode.
  3. Regression tests cover source/environment matrix.

Status update (2026-02-24): DONE
- Closure summary:
  - Added per-environment fail-mode matrix fields to policy model:
    - Terraform: `terraform_mode_prod`, `terraform_mode_nonprod`
    - K8s admission: `k8s_admission_mode_prod`, `k8s_admission_mode_nonprod`
  - Kept deterministic source-level defaults while adding explicit `prod/nonprod` overrides.
  - Added mode resolver in enforcement service so gate and fail-safe paths select mode by `source x normalized_environment`.
  - Persisted mode selection trace (`mode_scope`) into decision response payload for audit/debug reproducibility.
- Evidence:
  - `app/models/enforcement.py` (environment mode matrix fields on `EnforcementPolicy`)
  - `migrations/versions/g2h3i4j5k6l7_add_enforcement_policy_environment_mode_matrix.py`
  - `app/modules/enforcement/api/v1/schemas.py` (`PolicyResponse` + `PolicyUpdateRequest` environment mode fields)
  - `app/modules/enforcement/api/v1/policy_budget_credit.py` (policy API read/write for matrix fields)
  - `app/modules/enforcement/domain/service.py` (`_resolve_policy_mode`, `evaluate_gate`, `resolve_fail_safe_gate`)
  - Tests:
    - `tests/unit/enforcement/test_enforcement_service.py` (terraform matrix, k8s matrix, fail-safe matrix)
    - `tests/unit/enforcement/test_enforcement_api.py` (policy endpoint round-trip for environment matrix)
    - `tests/unit/enforcement/test_enforcement_property_and_concurrency.py` (matrix-aware hard-mode concurrency guard)
  - Validation:
    - `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_api.py` -> `73 passed`
    - `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_property_and_concurrency.py tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_api.py tests/unit/enforcement/test_reconciliation_worker.py tests/unit/tasks/test_enforcement_scheduler_tasks.py tests/governance/test_hard_limit_enforcement.py` -> `86 passed`

### ECP-006: K8s admission endpoint is not native AdmissionReview contract

- Why needed:
  - Pre-provision K8s controller integrations typically require Kubernetes AdmissionReview request/response shape.
- Current state:
  - K8s gate endpoint accepts generic `GateRequest`.
- Evidence:
  - `app/modules/enforcement/api/v1/enforcement.py`
  - `app/modules/enforcement/api/v1/schemas.py`
- Required change:
  1. Add AdmissionReview-compatible endpoint/adapter.
  2. Map decision and reason codes to webhook response schema.
- Acceptance criteria:
  1. Validating webhook can call endpoint without custom wrapper.
  2. Response includes reject/allow message payload compatible with K8s API server.

Status update (2026-02-25): DONE
- Closure summary:
  - Added native AdmissionReview-compatible endpoint:
    - `POST /api/v1/enforcement/gate/k8s/admission/review`
  - Implemented AdmissionReview request/response schema compatibility (`apiVersion`, `kind`, `request.uid` echo, `response.allowed`, `status`, `warnings`, `auditAnnotations`).
  - Added deterministic request mapping from webhook payload into enforcement gate input:
    - project/environment from labels/annotations,
    - action from admission operation,
    - resource reference from resource/namespace/name,
    - cost deltas from explicit admission annotations.
  - Added strict annotation validation for cost fields (`422` on invalid decimal annotation values) to prevent ambiguous runtime behavior.
- Evidence:
  - `app/modules/enforcement/api/v1/schemas.py` (`K8sAdmissionReviewPayload`, `K8sAdmissionReviewResponse` and supporting models)
  - `app/modules/enforcement/api/v1/enforcement.py` (`gate_k8s_admission_review`, admission mapping helpers)
  - Tests:
    - `tests/unit/enforcement/test_enforcement_api.py` (`test_gate_k8s_admission_review_contract_allow`)
    - `tests/unit/enforcement/test_enforcement_api.py` (`test_gate_k8s_admission_review_uses_annotation_cost_inputs_for_deny`)
    - `tests/unit/enforcement/test_enforcement_api.py` (`test_gate_k8s_admission_review_rejects_invalid_cost_annotation`)

### ECP-007: Terraform/CI preflight integration contract is under-defined

- Why needed:
  - Requirement pack A expects a robust preflight gate flow for CI pipelines.
- Current state:
  - `POST /gate/terraform` exists, but no dedicated CI token/retry state contract beyond generic idempotency.
- Evidence:
  - `app/modules/enforcement/api/v1/enforcement.py`
  - `app/modules/enforcement/api/v1/schemas.py`
- Required change:
  1. Define explicit preflight contract (fingerprint, retry semantics, token handoff).
  2. Add integration docs/examples for Terraform and CI systems.
- Acceptance criteria:
  1. Pipeline can deterministically retry with same idempotency key/fingerprint.
  2. Approval continuation path is documented and testable end-to-end.

Status update (2026-02-25): DONE
- Closure summary:
  - Added explicit Terraform preflight contract endpoint:
    - `POST /api/v1/enforcement/gate/terraform/preflight`
  - Added preflight request/response models with run/stage context, deterministic continuation bindings, and explicit approval consume path.
  - Added deterministic retry semantics:
    - optional `expected_request_fingerprint` check before gate evaluation,
    - deterministic idempotency fallback key (`terraform:{run_id}:{stage}`) when not supplied.
  - Added end-to-end continuation flow validation from preflight -> approval -> token consume with expected binding checks.
- Evidence:
  - `app/modules/enforcement/api/v1/schemas.py` (`TerraformPreflightRequest`, `TerraformPreflightResponse`, continuation models)
  - `app/modules/enforcement/api/v1/enforcement.py` (`gate_terraform_preflight`, `_run_gate_input`)
  - `app/modules/enforcement/domain/service.py` (`compute_request_fingerprint`)
  - Tests:
    - `tests/unit/enforcement/test_enforcement_api.py` (`test_gate_terraform_preflight_contract_and_retry_binding`)
    - `tests/unit/enforcement/test_enforcement_api.py` (`test_gate_terraform_preflight_rejects_retry_fingerprint_mismatch`)
    - `tests/unit/enforcement/test_enforcement_api.py` (`test_gate_terraform_preflight_approval_continuation_end_to_end`)

### ECP-008: Ledger does not have first-class approval linkage fields

- Why needed:
  - Requirement pack C asks for explicit approval linkage in immutable audit.
- Current state:
  - Ledger stores `approval_required` and payload hashes, but not dedicated `approval_id`/approval status linkage columns.
- Evidence:
  - `app/models/enforcement.py` (`EnforcementDecisionLedger`)
  - `app/modules/enforcement/domain/service.py` (`_append_decision_ledger_entry`)
- Required change:
  1. Extend ledger schema with approval linkage columns.
  2. Capture linkage at decision creation and approval transitions.
- Acceptance criteria:
  1. Ledger query can answer "which approval authorized this decision" without payload parsing.
  2. Immutability guarantees remain intact.

Status update (2026-02-25): DONE
- Closure summary:
  - Added first-class immutable ledger linkage fields:
    - `approval_request_id`
    - `approval_status`
  - Appended approval-linked ledger snapshots at:
    - initial decision creation (with pending approval when created inline),
    - manual approval request creation for existing decisions,
    - approval transitions (`approved`, `denied`, `expired`).
  - Preserved append-only guarantees (no ledger updates/deletes introduced).
- Evidence:
  - `app/models/enforcement.py` (`EnforcementDecisionLedger.approval_request_id`, `approval_status`)
  - `migrations/versions/j6k7l8m9n0p1_add_enforcement_ledger_approval_linkage_fields.py`
  - `app/modules/enforcement/domain/service.py` (`_append_decision_ledger_entry`, approval create/approve/deny/expire call sites)
  - `app/modules/enforcement/api/v1/schemas.py` (`DecisionLedgerItem.approval_request_id`, `approval_status`)
  - `app/modules/enforcement/api/v1/ledger.py` (ledger API mapping for approval linkage fields)
  - Tests:
    - `tests/unit/enforcement/test_enforcement_service.py` (pending/approved linkage snapshots, create-request linkage snapshot)
    - `tests/unit/enforcement/test_enforcement_api.py` (ledger endpoint payload coverage for approval linkage fields)

### ECP-009: Cloud-event gate endpoint is missing

- Why needed:
  - Requirement pack B lists optional post-provision cloud-event gate.
- Current state:
  - `CLOUD_EVENT` enum exists, endpoint does not.
- Evidence:
  - `app/models/enforcement.py`
  - `app/modules/enforcement/api/v1/enforcement.py`
- Required change:
  1. Add `/api/v1/enforcement/gate/cloud-event`.
  2. Define source-specific schema normalization and reason codes.
- Acceptance criteria:
  1. Endpoint parity with other gate sources.
  2. Covered by API + service tests.

Status update (2026-02-25): DONE
- Closure summary:
  - Added cloud-event gate endpoint:
    - `POST /api/v1/enforcement/gate/cloud-event`
  - Added structured cloud-event request schema with CloudEvents v1.0 core attributes.
  - Implemented deterministic mapping into enforcement gate input:
    - default idempotency from event id (`cloudevent:{id}`),
    - normalized project/environment/action/resource mapping,
    - event metadata capture with payload hash (`cloud_event_data_sha256`) for audit safety.
  - Added optional retry-fingerprint assertion for deterministic CI/event replay semantics.
- Evidence:
  - `app/modules/enforcement/api/v1/schemas.py` (`CloudEventEnvelope`, `CloudEventGateRequest`)
  - `app/modules/enforcement/api/v1/enforcement.py` (`gate_cloud_event`, `_build_cloud_event_gate_input`)
  - Spec references:
    - CloudEvents v1.0.2 core context attributes (`id`, `source`, `specversion`, `type`): https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md
    - CNCF CloudEvents project overview: https://cloudevents.io/
  - Tests:
    - `tests/unit/enforcement/test_enforcement_api.py` (`test_gate_cloud_event_uses_event_id_idempotency_and_contract`)
    - `tests/unit/enforcement/test_enforcement_api.py` (`test_gate_cloud_event_rejects_retry_fingerprint_mismatch`)
    - `tests/unit/enforcement/test_enforcement_api.py` (`test_gate_cloud_event_hard_mode_can_deny_by_budget`)

### ECP-010: Approval token claims are missing project binding and explicit max-cost claim set

- Why needed:
  - Requirement pack C asks token claims to include tenant/project/env/fingerprint/max_cost_delta/expiry/decision/approval.
- Current state:
  - Token includes tenant, env, fingerprint, decision, approval, source, max monthly delta, resource reference.
  - `project_id` is missing in signed claims.
- Evidence:
  - `app/modules/enforcement/domain/service.py` (`_build_approval_token`, `_extract_token_context`, `consume_approval_token`)
- Required change:
  1. Add `project_id` claim and validate it on consume.
  2. Clarify/encode `max_cost_delta` policy (monthly/hourly bounds).
- Acceptance criteria:
  1. Token cannot be replayed across project boundaries.
  2. Cost-bound checks enforce configured max delta semantics.

Status update (2026-02-25): DONE
- Closure summary:
  - Extended signed approval token contract with explicit binding claims:
    - `project_id`
    - `max_monthly_delta_usd`
    - `max_hourly_delta_usd`
  - Enforced consume-time validation for project, monthly max-delta, and hourly max-delta bindings.
  - Added optional caller-side `expected_project_id` assertion on consume endpoint for explicit pipeline binding checks.
- Evidence:
  - `app/modules/enforcement/domain/service.py` (`_build_approval_token`, `_decode_approval_token`, `_extract_token_context`, `consume_approval_token`)
  - `app/modules/enforcement/api/v1/schemas.py` (`ApprovalTokenConsumeRequest.expected_project_id`, `ApprovalTokenConsumeResponse.max_hourly_delta_usd`)
  - `app/modules/enforcement/api/v1/approvals.py` (consume endpoint request/response wiring)
  - Tests:
    - `tests/unit/enforcement/test_enforcement_service.py` (claim-shape validation, project binding mismatch, hourly cost mismatch)
    - `tests/unit/enforcement/test_enforcement_api.py` (expected-project mismatch + consume response includes hourly bound)

### ECP-014: Gate response token semantics are not contract-finalized

- Why needed:
  - Proposed API contract allows `approval_token` in gate response under approved/auto-approved paths.
  - Current flow issues token during approval action, not during gate decision response.
- Current state:
  - Gate response schema includes `approval_token`, but evaluate-gate path currently returns `None`.
  - Token issuance happens in approval flow.
- Evidence:
  - `app/modules/enforcement/api/v1/schemas.py` (`GateDecisionResponse.approval_token`)
  - `app/modules/enforcement/domain/service.py` (`gate_result_to_response`, `approve_request`)
- Required change:
  1. Decide policy: keep token approval-flow-only or support gate-issued token for explicit auto-approved cases.
  2. If enabling gate-issued tokens, constrain by policy and bind token to decision fingerprint/resource/cost.
  3. Document behavior in API contract and integration guides.
- Acceptance criteria:
  1. Contract is explicit and tested for all decision outcomes.
  2. No token is emitted on paths that bypass required review policy.
  3. Replay/tamper guarantees remain unchanged.

Status update (2026-02-25): DONE
- Closure summary:
  - Finalized gate token policy contract as `approval_flow_only`:
    - gate responses do not issue approval tokens directly,
    - approval token issuance remains constrained to approval-review flow.
  - Added explicit response field (`approval_token_contract`) to gate and preflight responses.
  - Added tests to assert token contract behavior on gate/preflight and cloud-event paths.
- Evidence:
  - `app/modules/enforcement/api/v1/schemas.py` (`GateDecisionResponse.approval_token_contract`, `TerraformPreflightResponse.approval_token_contract`)
  - `app/modules/enforcement/domain/service.py` (`gate_result_to_response` contract field emission)
  - `tests/unit/enforcement/test_enforcement_api.py` (`test_gate_terraform_uses_idempotency_key`, `test_gate_terraform_preflight_contract_and_retry_binding`, cloud-event contract tests)

### ECP-013: Policy-as-code engine is not formalized

- Why needed:
  - Requirement pack C asks for policy-as-code for budgets/entitlements and approval routing.
  - Current model is database-config driven but lacks a formal versioned rule language/evaluator artifact.
- Current state:
  - Enforcement policy exists as DB fields and service logic, without explicit DSL/runtime (for example OPA/Rego/CEL or internal equivalent).
- Evidence:
  - `app/models/enforcement.py` (`EnforcementPolicy`)
  - `app/modules/enforcement/domain/service.py` (hardcoded policy evaluation flow)
- Required change:
  1. Define policy representation format and versioning contract.
  2. Implement deterministic evaluator boundary with testable rule fixtures.
  3. Add policy validation/linting and rollout controls.
- Acceptance criteria:
  1. Policies can be represented and reviewed as code artifacts (or equivalent declarative documents).
  2. Evaluator outputs are deterministic and reproducible for a given policy version + input snapshot.
  3. Approval routing and entitlement waterfall can be expressed without code edits.

Status update (2026-02-25): DONE
- Closure summary:
  - Added an explicit, versioned policy-document contract (`valdrix.enforcement.policy.v1`) as first-class schema.
  - Implemented deterministic policy canonicalization + SHA-256 digesting and persisted both on `enforcement_policies`:
    - `policy_document_schema_version`
    - `policy_document_sha256`
    - `policy_document` (canonical payload)
  - Updated policy update flow so the policy document is authoritative when provided; scalar fields are materialized from the document and stored consistently.
  - Added service-level backfill materialization for legacy/missing policy-document rows at policy load time.
  - Wired policy APIs to return contract fields and accept policy-document input payloads.
- Evidence:
  - `app/modules/enforcement/domain/policy_document.py` (policy contract models + canonical hash helpers)
  - `app/modules/enforcement/domain/service.py` (`_materialize_policy_contract`, `_apply_policy_contract_materialization`, policy backfill checks)
  - `app/models/enforcement.py` (policy document contract columns on `EnforcementPolicy`)
  - `app/modules/enforcement/api/v1/policy_budget_credit.py` (policy document request/response wiring)
  - `app/modules/enforcement/api/v1/schemas.py` (policy contract types sourced from domain contract module)
  - `migrations/versions/k7l8m9n0p1q2_add_enforcement_policy_document_contract_fields.py`
  - Tests:
    - `tests/unit/enforcement/test_enforcement_service.py` (`test_update_policy_materializes_policy_document_contract_and_hash`, `test_update_policy_uses_policy_document_as_authoritative_contract`)
    - `tests/unit/enforcement/test_enforcement_api.py` (`test_policy_upsert_accepts_policy_document_contract` + policy endpoint contract assertions)
- Validation:
  - `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_api.py tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_property_and_concurrency.py`
  - Result: `101 passed`

### ECP-011: Actions orchestration subdomain is not explicit

- Why needed:
  - Requirement pack B proposes explicit actions orchestration domain.
- Status update (2026-02-25): DONE
- Implemented scope:
  1. Added explicit orchestration domain service in `app/modules/enforcement/domain/actions.py`:
     - idempotent action request creation with deterministic fallback idempotency keys,
     - queue leasing with optimistic claim semantics and lease TTL,
     - lifecycle transitions (`QUEUED` -> `RUNNING` -> `SUCCEEDED|FAILED|CANCELLED`),
     - policy-governed retry controls (`action_max_attempts`, `action_retry_backoff_seconds`, `action_lease_ttl_seconds`).
  2. Added API surface in `app/modules/enforcement/api/v1/actions.py`:
     - `POST /actions/requests`, `GET /actions/requests`, `GET /actions/requests/{action_id}`,
     - `POST /actions/lease`, `POST /actions/requests/{action_id}/complete`,
     - `POST /actions/requests/{action_id}/fail`, `POST /actions/requests/{action_id}/cancel`.
  3. Added persistence model + migration:
     - `EnforcementActionExecution` in `app/models/enforcement.py`,
     - `migrations/versions/l8m9n0p1q2r3_add_enforcement_action_executions.py`.
  4. Kept decision/approval linkage explicit via `decision_id` and optional `approval_request_id`.
- Evidence:
  - `app/modules/enforcement/domain/actions.py`
  - `app/modules/enforcement/api/v1/actions.py`
  - `app/modules/enforcement/api/v1/schemas.py`
  - `app/modules/enforcement/api/v1/enforcement.py` (router wiring)
  - `app/models/enforcement.py`
  - `migrations/versions/l8m9n0p1q2r3_add_enforcement_action_executions.py`
  - Tests:
    - `tests/unit/enforcement/test_enforcement_actions_service.py`
    - `tests/unit/enforcement/test_enforcement_actions_api.py`
- Validation:
  - `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_actions_service.py tests/unit/enforcement/test_enforcement_actions_api.py`
  - Result: `8 passed`
  - `uv run pytest --no-cov -q tests/unit/enforcement`
  - Result: `128 passed`

## Immediate implementation sequence (recommended)

Phase 1 (P0 safety/correctness):
1. ECP-004 credit lifecycle correctness
2. ECP-003 approval routing/RBAC hardening
3. ECP-002 entitlement waterfall completion
4. ECP-005 per-environment fail-mode policy

Phase 2 (P0/P1 decision quality and audit):
1. ECP-001 computed context enrichment
2. ECP-010 token claim completion
3. ECP-008 ledger linkage enrichment
4. ECP-013 policy-as-code formalization

Phase 3 (integration surface):
1. ECP-006 K8s AdmissionReview compatibility
2. ECP-007 Terraform/CI contract hardening
3. ECP-009 cloud-event endpoint (if required for post-provision control)
4. ECP-011 actions orchestration domain
5. ECP-012 concurrency serialization hardening (if not completed in phase 1/2)
6. ECP-014 gate token issuance contract finalization

## Tight MVP wedge (fastest credible control-plane story)

Use this path when speed-to-credible-B matters more than full-model completeness.

1. Terraform gate integration first (`/gate/terraform`) with deterministic idempotency + clear CI retry semantics.
2. HITL approval flow hardening using current remediation-style approve/execute pattern, with SCIM-managed approver groups as the enterprise default control model.
3. Decision ledger + export parity as mandatory audit evidence surface.
4. Budget allocations + credits waterfall with correctness fixes (credit decrement + concurrency serialization).
5. K8s native AdmissionReview compatibility after Terraform path is stable.

MVP caveat:
- This wedge is credible only if approval authority boundaries and reservation accounting correctness are closed (`ECP-003`, `ECP-004`, `ECP-012`).

## What to do now (execution runbook)

Use this as the direct implementation checklist.

### Step 1: Open and assign work items

1. Create one issue per `ECP-*` item.
2. Tag each issue with:
   - `area:enforcement`
   - `priority:P0|P1|P2`
   - `type:gap-closure`
3. Assign owner lanes:
   - API/RBAC lane: `ECP-003`, `ECP-006`, `ECP-007`, `ECP-014`
   - Data/model lane: `ECP-002`, `ECP-004`, `ECP-008`, `ECP-012`
   - Policy/decision lane: `ECP-001`, `ECP-005`, `ECP-010`, `ECP-013`
   - Platform lane: `ECP-009`, `ECP-011`

### Step 2: Ship the minimum credible batch first (P0)

Batch A (authorization boundary):
1. `ECP-003` enforce approver boundary model.
2. Make approval endpoints/admin-review path explicit.
3. Define SCIM-managed approver-group contract for enforcement.

Batch B (money correctness):
1. `ECP-004` implement credit decrement lifecycle.
2. `ECP-012` serialize reserve-critical section for concurrent distinct idempotency keys.
3. Add property/concurrency tests proving no oversubscription.

Batch C (policy correctness):
1. `ECP-002` complete entitlement waterfall stages.
2. `ECP-005` add per-environment fail-mode policy controls.

Exit gate for P0:
1. No known double-spend/over-reserve path.
2. Approval boundary is auditable and policy-defined.
3. Waterfall behavior is deterministic and stage-traceable.

### Step 3: Ship audit and contract completeness (P1)

1. `ECP-001` computed context (`forecast_eom`, `burn_rate`, `risk`) in enforcement decisions.
2. `ECP-010` token claim completeness (`project_id`, cost bound semantics).
3. `ECP-008` first-class approval linkage in ledger.
4. `ECP-013` policy-as-code formalization and versioned evaluation model.

Exit gate for P1:
1. Decision artifacts are sufficient for forensic replay/audit.
2. Approval token contract is fully bound and replay-safe.
3. Policy behavior is reviewable and versioned.

### Step 4: Integration expansion (P1/P2)

1. `ECP-006` native Kubernetes `AdmissionReview` compatibility.
2. `ECP-007` Terraform/CI preflight contract finalization.
3. `ECP-009` optional cloud-event gate endpoint.
4. `ECP-011` explicit actions orchestration subdomain.
5. `ECP-014` finalize gate token emission contract.

Exit gate for integration expansion:
1. Terraform and Kubernetes integrations are production-contract stable.
2. HITL token semantics are explicit across all decision outcomes.

### Step 5: Keep packaging and entitlement truth aligned

1. Ensure every paid capability is enforced by backend feature/tier gates.
2. Remove or downgrade any packaging flag not backed by runtime enforcement.
3. Keep `TIER_CONFIG` and public pricing payloads synchronized.
4. For BSL + public repo posture, keep enterprise differentiators explicit, curated, and contract-safe.

## Commercial licensing and packaging recommendations

These are the current strategic recommendations for this repo posture.

1. Keep BSL + public repo for now; this matches current licensing/commercial boundary docs.
2. Tighten packaging truth by curating Enterprise entitlements (avoid `set(FeatureFlag)` as packaging truth).
3. Add feature maturity metadata (`GA` / `Beta` / `Preview`) to reduce over-promise risk.
4. Introduce explicit tier flags for enforcement control-plane capabilities so "economic control plane" is a deliberate paid step.
5. Execute the planned permissive external surfaces (public SDK/spec helper repos) to improve ecosystem adoption without exposing core moat logic.

## Tiering critique coverage (requested checklist)

This section covers the full tiering feedback list and marks each point with repository-backed status.

### What is good (fact-backed)

1. Obvious progression (Free -> Starter -> Growth -> Pro -> Enterprise) with feature unlocks + limits.
   - Status: Verified.
   - Evidence: `app/shared/core/pricing.py` (`PricingTier`, `TIER_CONFIG`).
2. Retention scaling `30 -> 90 -> 365 -> 730`.
   - Status: Verified.
   - Evidence: `app/shared/core/pricing.py` (`retention_days` in Free/Starter/Growth/Pro limits).
3. Multi-cloud unlock at Growth.
   - Status: Verified.
   - Evidence: `FeatureFlag.MULTI_CLOUD` in Growth features in `app/shared/core/pricing.py`.
4. SCIM reserved for Enterprise.
   - Status: Verified at runtime gating layer.
   - Evidence: SCIM feature checks in `app/modules/governance/api/v1/settings/identity.py` and `app/modules/governance/api/v1/scim.py`.

### What is risky and how to fix (fact-backed + action)

1. Capability names may imply maturity not yet contract-safe (`auto_remediation`, `gitops_remediation`, `incident_integrations`, `reconciliation`, `carbon_assurance`).
   - Status: Partially validated risk.
   - Fact basis:
     - Several are runtime-gated and used in live paths.
     - Some flags appear packaging-heavy or under-specified in maturity contract (for example no global GA/Beta metadata model).
   - Action:
     1. Add per-feature maturity metadata (`GA|Beta|Preview`) in tier config source of truth.
     2. Surface maturity in billing/plans API response and pricing UI copy.
     3. Rename high-risk labels where needed (`assisted_remediation` vs fully autonomous wording).

2. Growth/Pro boundary is overloaded and can blur Enterprise procurement story.
   - Status: Verified as a packaging risk.
   - Fact basis:
     - Pro includes broad control/integration feature set in `TIER_CONFIG`.
   - Action:
     1. Define explicit Pro vs Enterprise procurement triggers.
     2. Decide intentional placement for `SSO`, `AUDIT_LOGS`, `COMPLIANCE_EXPORTS`, `DEDICATED_SUPPORT`.
     3. Encode final boundary in `TIER_CONFIG` and docs.

3. `Enterprise = set(FeatureFlag)` is contract-risky.
   - Status: Verified.
   - Fact basis:
     - Enterprise currently maps to `features: set(FeatureFlag)` in `app/shared/core/pricing.py`.
   - Action:
     1. Replace with curated enterprise entitlement set.
     2. Treat flags as capability switches, not packaging truth.
     3. Add test that Enterprise only exposes curated explicit list.
   - Release-hard requirement:
     1. Do not ship control-plane GA packaging while `Enterprise = set(FeatureFlag)` remains in `TIER_CONFIG`.
     2. Close `PKG-007` before any "enterprise control-plane" commercial claim.

4. Free/Starter clarity risk (feature richness and ambiguous value messaging).
   - Status: Verified as packaging/copy risk.
   - Fact basis:
     - Free includes `llm_analysis`, `zombie_scan`, `unit_economics` with low but non-zero LLM limits.
     - Starter includes `ai_insights`, `ingestion_sla`, `multi_region`.
   - Action:
     1. Rework tier narratives in pricing copy (evaluation vs team vs adoption vs platform-grade vs enterprise controls).
     2. Keep limits but simplify headline value statements to reduce confusion.
     3. Confirm unit economics/margin impact for free-tier LLM allowance.

5. Economic control-plane differentiator is not yet represented as paid packaging step.
   - Status: Verified.
   - Fact basis:
     - No explicit enforcement feature flags in `FeatureFlag`.
     - Enforcement endpoints are role-gated; no tier feature gate in enforcement routes.
   - Action:
     1. Add enforcement feature flags (for example `ENFORCEMENT_GATE`, `ENFORCEMENT_HITL`, `ENFORCEMENT_CREDITS`, `ENFORCEMENT_POLICY_AS_CODE`).
     2. Gate `/api/v1/enforcement/*` capabilities by tier+role where intended.
     3. Align pricing pages and `/billing/features` output with those new flags.

### Practical tier-adjustment model (candidate packaging)

Use as a target model for pricing committee review before code changes.

1. Free (evaluation):
   - 1 AWS connection, core dashboards/cost tracking, basic alerts/zombie scan, 30-day retention, minimal or no LLM.
2. Starter (team):
   - 5 AWS connections, stronger alerting/reporting, 90-day retention, lightweight unit economics.
3. Growth (FinOps adoption):
   - Multi-cloud, chargeback/attribution, anomaly detection, remediation approval workflows, 365-day retention.
4. Pro (platform-grade):
   - API access, Slack/incident integrations, controlled automation hooks, optional audit logs boundary, 730-day retention.
5. Enterprise (org-scale control plane):
   - SCIM, advanced approver groups/RBAC, policy-as-code + gate enforcement, SLA/support/residency/custom controls.

### Packaging action backlog (track separately from ECP)

Track these as `PKG-*` items in addition to `ECP-*`:

1. `PKG-001` Curate Enterprise entitlements (remove `set(FeatureFlag)` behavior).
2. `PKG-002` Add feature maturity metadata (`GA|Beta|Preview`) and expose in API/UI/docs.
3. `PKG-003` Introduce enforcement feature flags and apply tier gates to enforcement APIs.
4. `PKG-004` Rebalance Growth/Pro/Enterprise boundary for procurement clarity.
5. `PKG-005` Simplify Free/Starter value messaging and validate margin impact of free-tier LLM limits.
6. `PKG-006` Add an enforceability matrix test so each paid capability is either runtime-gated or explicitly marked catalog-only.
7. `PKG-007` Replace `Enterprise = set(FeatureFlag)` with curated explicit entitlement list + regression guard.
8. `PKG-008` Add per-feature maturity metadata (`GA|Beta|Preview`) in pricing source-of-truth and plan payloads.
9. `PKG-009` Define enterprise pricing policy + floor model (flat/spend/hybrid), publish internal quote rules.
10. `PKG-010` Add free-tier compute guardrails and margin telemetry for LLM-enabled capabilities.
11. `PKG-011` Add a qualitative AI capability ladder by tier (teaser vs operational AI outcomes), not only request-count scaling.
12. `PKG-012` Recalibrate Starter generosity (limits + feature narrative) using conversion/expansion telemetry, with explicit decision on `max_aws_accounts` (for example 5 -> 3 or keep 5 with stricter guardrails).
13. `PKG-013` Split remediation packaging semantics into explicit capabilities (HITL workflow vs autonomous execution) and align naming/contracts.
14. `PKG-014` Add runtime gating (or remove marketing claims) for flags that currently behave catalog-only in this context (notably `API_ACCESS`, `POLICY_CONFIGURATION`).
15. `PKG-015` Define B-launch readiness gate criteria and block control-plane positioning until required enforcement/package items are complete.
16. `PKG-016` Introduce explicit control-plane package/tier entitlements (pricing + limits + feature boundaries).
17. `PKG-017` Define messaging transition criteria (`analytics-led` -> `economic-control-plane`) tied to readiness gate.
18. `PKG-018` Define customer migration plan for pricing/packaging transition (grandfathering + contract updates).
19. `PKG-019` Record explicit GTM strategy choice (`B-first` vs `Hybrid`) with launch criteria, owner, and date.

### Suggested PR order

1. PR-1: `ECP-003` approver boundary + SCIM approver-group contract.
2. PR-2: `ECP-004` credit lifecycle.
3. PR-3: `ECP-012` concurrency serialization.
4. PR-4: `ECP-002` waterfall stage model.
5. PR-5: `ECP-005` environment fail-mode matrix.
6. PR-6: `ECP-010` token claims.
7. PR-7: `ECP-008` ledger linkage.
8. PR-8: `ECP-001` computed decision context.
9. PR-9: `ECP-006` AdmissionReview endpoint.
10. PR-10: `ECP-007`, `ECP-014`, `ECP-009` contract surfaces.
11. PR-11: `ECP-011` actions orchestrator skeleton.
12. PR-12: `ECP-013` policy-as-code formalization.

## Execution tracking template

Use this row format in PRs/issues:

`[ECP-XXX] <title> | owner=<name> | status=<OPEN/IN_PROGRESS/BLOCKED/DONE> | target=<YYYY-MM-DD> | evidence=<tests/docs path>`

Minimum done criteria per item:
1. Code merged.
2. Tests added/updated and passing.
3. API/docs updated.
4. Runbook/ops notes updated where operational behavior changed.

## Deep technical necessity filter (2026-02-24 addendum)

This addendum is a strict pass over what is truly needed now versus later.
It is based on repository code inspection only (no external market research in this pass).

### Additional fact checks run in this pass

1. Verified enforcement API/service/model paths and role checks.
2. Verified pricing/tier configuration behavior.
3. Verified SCIM/identity approval-permission linkage.
4. Ran static usage scan of `FeatureFlag.*` references outside pricing config.

Command used for feature-flag runtime signal:
- `rg -o --no-filename 'FeatureFlag\\.[A-Z0-9_]+' app/shared/core/pricing.py | ...`

### Strict necessity matrix (must/should/later)

| Topic | Current fact in code | Need level | Why |
|---|---|---|---|
| Real-time gate endpoints (Terraform, K8s) | Implemented in `app/modules/enforcement/api/v1/enforcement.py` | Keep | Baseline exists; not a gap. |
| Deterministic decision + policy version + immutable ledger | Implemented (`policy_version`, append-only ledger) | Keep | Baseline exists; not a gap. |
| Idempotency for duplicate gate requests | Implemented via unique key on `(tenant_id, source, idempotency_key)` | Keep | Handles same-key replay. |
| Concurrency safety across distinct idempotency keys | Not serialized around shared headroom read/reserve | Must | Money correctness risk (over-reserve race). |
| Credit grant decrement lifecycle | `remaining_amount_usd` is read for headroom; no clear decrement on reconcile/release | Must | Headroom can drift from real consumption. |
| Terraform preflight gate | Implemented (`POST /gate/terraform`) | Keep | Baseline exists. |
| K8s native AdmissionReview contract | Current endpoint accepts generic `GateRequest` | Should | Needed for drop-in webhook compatibility. |
| Signed approval tokens + replay protection | Implemented (hash binding + one-time consume) | Keep | Baseline exists. |
| Token claim completeness (`project_id`, explicit cost bound policy) | Missing/partial in JWT claims | Should | Strengthens anti-replay and contract clarity. |
| Approval routing + role boundary hardening | Endpoint role is `member`; service uses remediation permissions | Must | Enterprise HITL boundary must be explicit and auditable. |
| Two-person rule for prod | Not implemented | Must (if prod destructive actions in scope) | Common control expectation for high-risk changes. |
| Fail-open/fail-closed per environment | Mode is source-level (`terraform_mode`, `k8s_admission_mode`) | Should | Needed for prod vs nonprod policy control. |
| Entitlement waterfall stage completeness (plan/project/reserved/emergency/ceiling) | Partial; current flow is allocation + credits | Must | Needed to make decisions contract-true and deterministic. |
| Budget dimensions (`project/team/env`) as first-class fields | Current model uses generic `scope_key` | Should | Improves policy clarity and routing/reporting. |
| Cloud-event gate endpoint | `CLOUD_EVENT` enum exists, route absent | Later/Optional | Useful for post-provision controls, not core MVP. |
| Separate `actions` subdomain folder | Not present | Later | Structural nicety; not a functional blocker. |
| Policy-as-code engine (formal DSL/runtime) | Not formalized; logic lives in service code + DB fields | Should | Important for enterprise reviewability, not first blocking fix. |

### Packaging and licensing reality check (fact-based)

1. BSL + public repo posture is explicitly documented and consistent:
   - `README.md` (BSL 1.1 + change date)
   - `docs/licensing.md`
   - `docs/open_core_boundary.md`
2. Enterprise tier currently uses `features: set(FeatureFlag)` in `app/shared/core/pricing.py`.
3. Enforcement APIs are role-gated but not tier/feature-gated (no `requires_feature` in enforcement routes).
4. SCIM is feature-gated and wired as enterprise identity control (`FeatureFlag.SCIM` checks in identity/SCIM APIs).

Conclusion for packaging:
1. Keep BSL + public repo now.
2. Curate enterprise entitlements explicitly (do not expose all flags by default).
3. Add enforcement feature flags and tier-gate enforcement capabilities where packaging requires it.

### Feature-flag runtime signal (outside pricing config)

Flags with zero non-test references outside `app/shared/core/pricing.py` in this scan:
1. `AI_ANALYSIS_DETAILED`
2. `AI_INSIGHTS`
3. `API_ACCESS`
4. `CARBON_TRACKING`
5. `DASHBOARDS`
6. `DEDICATED_SUPPORT`
7. `DOMAIN_DISCOVERY`
8. `HOURLY_SCANS`
9. `MULTI_REGION`
10. `POLICY_CONFIGURATION`
11. `ZOMBIE_SCAN`

Interpretation:
1. Some tier flags are currently packaging/catalog markers rather than hard runtime switches.
2. This increases risk of plan-copy drift versus enforceable backend behavior.
3. Track this under packaging hardening (`PKG-003` + `PKG-004` + `PKG-005`).

### What to implement first (tight, credible sequence)

Mandatory first wave (`Must`):
1. `ECP-003` approval boundary hardening + SCIM approver-group contract + optional two-person prod rule.
2. `ECP-004` credit decrement lifecycle.
3. `ECP-012` reservation concurrency serialization under distinct idempotency keys.
4. `ECP-002` full entitlement waterfall stages.

Second wave (`Should`):
1. `ECP-005` per-environment mode controls.
2. `ECP-010` token claim completeness (`project_id`, explicit cost bounds).
3. `ECP-006` AdmissionReview compatibility adapter.
4. `ECP-013` policy-as-code formalization.

Later wave (`Optional/Later`):
1. `ECP-009` cloud-event gate endpoint.
2. `ECP-011` actions subdomain extraction.

### New tracking items added from this pass

1. `PKG-006` Build enforcement matrix test proving every marketed paid capability has an API/runtime gate (or explicit “catalog-only” annotation).
2. `PKG-007` Replace `Enterprise = set(FeatureFlag)` with curated explicit list + regression test.
3. `PKG-008` Add per-feature maturity metadata (`GA|Beta|Preview`) to pricing source-of-truth and expose in plan payloads.

## Operator review of new pricing feedback (2026-02-24)

This section evaluates the newly provided pricing feedback with two evidence types only:
1. Codebase facts (current Valdrix implementation).
2. Public pricing evidence from primary vendor pages / AWS Marketplace.

### Codebase facts verified

1. Tier prices are currently:
   - Starter: `$29 monthly / $290 annual`
   - Growth: `$79 monthly / $790 annual`
   - Pro: `$199 monthly / $1990 annual`
   - Enterprise: `price_usd=None` (not explicitly priced)
   - Evidence: `app/shared/core/pricing.py`

2. Annual pricing is exactly "10 months billed for 12" for Starter/Growth/Pro.
   - Evidence: `app/shared/core/pricing.py` monthly vs annual values.

3. Free tier includes cost-sensitive features (`LLM_ANALYSIS`, `ZOMBIE_SCAN`, `UNIT_ECONOMICS`, `CARBON_TRACKING`) with non-zero usage limits.
   - Evidence: `app/shared/core/pricing.py` Free features + limits.

4. Pro tier includes many advanced/enterprise-like flags (for example `API_ACCESS`, `AUDIT_LOGS`, `COMPLIANCE_EXPORTS`, `GITOPS_REMEDIATION`, `INCIDENT_INTEGRATIONS`, `DEDICATED_SUPPORT`, `SSO`).
   - Evidence: `app/shared/core/pricing.py` Pro features.

5. Enterprise tier currently exposes `features: set(FeatureFlag)`.
   - Evidence: `app/shared/core/pricing.py`.

6. Enforcement APIs are role-gated but not tier/feature-gated in route dependencies.
   - Evidence: enforcement routes in `app/modules/enforcement/api/v1/*.py` use role dependencies and do not apply `requires_feature`.

7. SCIM/SSO are already tier-feature-gated in governance identity surfaces.
   - Evidence: `app/modules/governance/api/v1/settings/identity.py`, `app/modules/governance/api/v1/scim.py`.

### External pricing evidence snapshot (public pages)

1. Vantage public pricing shows:
   - Pro plan at `$30/month`
   - Business plan at `$200/month`
   - Enterprise as custom
   - Source: https://www.vantage.sh/pricing

2. CloudZero pricing is request-based (non-self-serve public number).
   - Source: https://www.cloudzero.com/pricing/

3. Finout pricing is quote-based with fixed-fee positioning (non-self-serve public number).
   - Source: https://www.finout.io/lp/pricing_request

4. AWS Marketplace enterprise FinOps-style contract examples (annual):
   - IBM Cloudability: `$30,000/year` for up to `$1M annual cloud spend` dimension.
     - Source: https://aws.amazon.com/marketplace/pp/prodview-h77jedsmpzs4k
   - CloudHealth: `$45,000/year` entry dimension for up to `$150K monthly AWS spend`.
     - Source: https://aws.amazon.com/marketplace/pp/prodview-btyciyjmdewhm
   - Flexera Cloud Cost Optimization: `$50,000/year` dimension for up to `$1M yearly cloud spend`.
     - Source: https://aws.amazon.com/marketplace/pp/prodview-c6teorsdi64jq

5. OpenCost provides a free/open-source lower-bound alternative for Kubernetes cost visibility.
   - Source: https://opencost.io/docs/FAQ
   - Source: https://www.cncf.io/projects/opencost/

### Feedback verdict table (operator lens)

| Feedback claim | Verdict | Evidence-backed note |
|---|---|---|
| Ladder `29 -> 79 -> 199` is reasonable for SMB/mid-market | Supported | Internal ladder is real; external comp signals include `$30` and `$200` public points (Vantage). |
| Enterprise should not remain undefined | Supported (high priority) | `price_usd=None` today leaves packaging ambiguity and sales friction. |
| Pro may be underpriced if enforcement control plane becomes real | Directionally supported | Current code already trends toward enterprise-grade controls; once hardened, value likely exceeds analytics-only price anchors. |
| Free may be too generous (margin risk) | Supported risk hypothesis | Free includes LLM and multiple advanced signals with non-zero limits; cost containment policy is not formalized in pricing artifacts. |
| Enterprise must be identity + governance + enforcement differentiated | Strongly supported | SCIM is gated today; enforcement tier gates are not yet formalized, so differentiation is not contract-clean yet. |
| Annual discount at ~16.7% is reasonable | Directionally supported | Sits inside common B2B SaaS discount practice bands; keep unless conversion data says otherwise. |

### What is truly needed now (pricing/package track)

Mandatory now:
1. `PKG-007` remove `Enterprise = set(FeatureFlag)` and define curated enterprise entitlements.
2. `PKG-003` add explicit enforcement-related feature flags and gate enforcement APIs by tier where intended.
3. `PKG-006` enforceability matrix test: every marketed paid capability must map to runtime gate or catalog-only marker.
4. Define an explicit enterprise pricing policy artifact (`floor + metric + packaging terms`) instead of `TBD`.

Next:
1. `PKG-008` add per-feature maturity metadata (`GA|Beta|Preview`) across pricing payload/docs.
2. Rebalance Growth/Pro/Enterprise boundaries after enforcement hardening milestones (`ECP` P0/P1) to avoid over-promising.
3. Evaluate free-tier LLM allowance with measured COGS and conversion telemetry before changing numbers.

### New pricing tracking IDs (added)

1. `PKG-009` Define enterprise pricing policy and floor model (flat minimum vs spend-based vs hybrid), with documented approval rules for discounting.
2. `PKG-010` Add free-tier compute guardrails for LLM-heavy paths (caps, fail-safe behavior, and budget telemetry), with margin impact dashboard.

## Pricing committee stress-test addendum (2026-02-24, latest feedback)

This addendum evaluates the latest tier-by-tier pricing feedback against repository implementation.

### Fact checks from code (tier contract)

1. Starter (`$29`) includes:
   - Features: dashboards, cost tracking, alerts, zombie scan, AI insights, LLM analysis, domain discovery, multi-region, carbon tracking/greenops, unit economics, ingestion SLA.
   - Limits: `max_aws_accounts=5`, `llm_analyses_per_day=5`, `llm_analyses_per_user_per_day=2`, `retention_days=90`.
   - Evidence: `app/shared/core/pricing.py`.

2. Growth (`$79`) includes:
   - Features: multi-cloud, anomaly detection, auto remediation, chargeback, commitment optimization, escalation workflow, policy preview, owner attribution.
   - Limits include `retention_days=365`.
   - Evidence: `app/shared/core/pricing.py`.

3. Pro (`$199`) includes:
   - Features: API access, SSO, audit logs, GitOps remediation, incident integrations, reconciliation, close workflow, savings proof, policy configuration, hourly scans, dedicated support.
   - Limits include `retention_days=730`, `llm_analyses_per_day=100`.
   - Evidence: `app/shared/core/pricing.py`.

### Fact checks from code (remediation semantics)

1. User-facing remediation flow is explicitly request -> approve -> execute.
   - `approve_request` states "Does NOT execute yet - that's a separate step for safety."
   - Execution requires `APPROVED` or `SCHEDULED` status.
   - Evidence: `app/modules/optimization/domain/remediation_workflow.py`, `app/modules/optimization/domain/remediation_execute.py`.

2. Endpoints for creating/executing remediation are feature-gated by `AUTO_REMEDIATION`.
   - Evidence: `app/modules/optimization/api/v1/zombies.py`.

3. Autonomous execution paths exist in scheduler code:
   - `SavingsProcessor` can auto-approve and execute high-confidence safe actions.
   - `AutonomousRemediationEngine` has autopilot mode, but defaults to dry-run in current handler path (`auto_pilot_enabled=False` unless explicitly set).
   - Evidence: `app/modules/governance/domain/scheduler/processors.py`, `app/shared/remediation/autonomous.py`, `app/modules/governance/domain/jobs/handlers/remediation.py`.

### Verdict on latest feedback (strict)

1. "Starter may be too generous at $29" -> `Supported`.
   - Starter currently combines broad visibility + AI + hygiene + 5 AWS accounts + 90-day retention.
   - This can reduce expansion pressure to Growth unless differentiated by governance depth.

2. "Growth at $79 is strong but auto-remediation wording is risky" -> `Supported with nuance`.
   - Product contract is mostly HITL for user flow.
   - Separate autonomous execution code paths exist, so naming must distinguish "approval workflow" versus "autonomous execution."

3. "Pro at $199 is justified when workflow/integration power is real" -> `Mostly supported`.
   - SSO/audit/reconciliation/close workflow/incident surfaces are real in code.
   - But some listed Pro flags remain weakly enforced as runtime boundaries in this context (`API_ACCESS`, `POLICY_CONFIGURATION`), which can blur value proof.

4. "B/control-plane ambition should reshape ladder later" -> `Supported`.
   - Enforcement surfaces exist but are not yet tier-feature gated; packaging cannot yet cleanly claim control-plane step functions by plan.

### New actions from this feedback

1. `PKG-012` Decide Starter generosity strategy with telemetry-backed threshold (connection cap + feature granularity) and implement accordingly.
2. `PKG-013` Split and rename remediation capabilities for contract truth:
   - `approval_workflow` (HITL)
   - `autonomous_execution` (autopilot/system-driven)
3. `PKG-014` Add runtime enforcement or reduce claim scope for Pro differentiators currently not hard-gated.

## B-first launch recalibration addendum (2026-02-24, latest feedback)

This section evaluates the claim that pricing/positioning must shift immediately if Valdrix launches as an economic control plane.

### Codebase facts that constrain launch positioning

1. Current public tier ladder in code is still analytics-era:
   - Starter `$29`, Growth `$79`, Pro `$199`, Enterprise `None/custom`.
   - Evidence: `app/shared/core/pricing.py`.

2. Enforcement routes are present but currently role-gated (not tier/feature-gated):
   - Gate endpoints: `POST /gate/terraform`, `POST /gate/k8s/admission`.
   - Route dependencies use role checks; no `requires_feature(...)` guard on enforcement routes.
   - Evidence: `app/modules/enforcement/api/v1/enforcement.py` and sibling enforcement routers.

3. Enterprise-control-plane correctness work is still open in tracked gaps:
   - P0 items include `ECP-001`, `ECP-002`, `ECP-003`, `ECP-004`, `ECP-005`, `ECP-012`.
   - These cover decision context completeness, entitlement waterfall, approval boundary hardening, credit lifecycle, fail-mode granularity, and concurrency safety.
   - Evidence: this register's tracking board.

### External market signals (updated references)

1. IaC/policy-control vendors already anchor higher than SMB dashboard pricing:
   - Spacelift self-serve Starter is listed at `$399/month`; enterprise is custom.
   - Source: https://spacelift.io/pricing

2. env0 self-serve baseline appears at `$2,500/year` with enterprise custom.
   - Source: https://www.env0.com/pricing

3. HCP Terraform positions on usage-based economics (resources under management), reinforcing infrastructure-control pricing psychology rather than dashboard-seat pricing.
   - Source: https://developer.hashicorp.com/terraform/cloud-docs/architectural-details/estimate-cost

4. FinOps analytics vendors still commonly present quote/custom plans at higher maturity tiers (CloudZero, Finout).
   - Sources: https://www.cloudzero.com/pricing/ and https://www.finout.io/lp/pricing_request

### Verdict on this feedback (strict)

1. "If B is core at launch, current ladder is under-anchored" -> `Supported`.
   - `29/79/199` communicates SMB analytics SaaS more than control-plane infrastructure.

2. "Immediate positioning change is required if B is launch promise" -> `Conditionally supported`.
   - Supported only if P0 enforcement correctness gaps are closed.
   - Without that, repositioning to full control-plane marketing creates over-claim risk.

3. "Enterprise must be materially stronger and explicitly priced/policy-defined" -> `Supported`.
   - `price_usd=None` + `Enterprise=set(FeatureFlag)` is not procurement-ready for control-plane sales motion.

### Recommended decision gate (before pricing reset)

Treat B-first launch as blocked unless all are complete:
1. `ECP-003`, `ECP-004`, `ECP-012` (approval boundary, credit correctness, concurrency safety).
2. `ECP-002`, `ECP-005` (entitlement waterfall and fail-mode controls).
3. `PKG-003`, `PKG-006`, `PKG-007` (enforcement feature gates + enforceability matrix + curated enterprise entitlements).

### New tracked actions from this feedback

1. `PKG-015` Define "B launch gate" criteria and block control-plane marketing until required `ECP/PKG` items are DONE.
2. `PKG-016` Add a first-class `control_plane` commercial tier (or equivalent package) with explicit enforcement entitlements and limits.
3. `PKG-017` Publish position-switch rules:
   - `analytics-led` messaging before B gate
   - `economic-control-plane` messaging only after B gate
4. `PKG-018` Create price-transition plan for existing cohorts (grandfathering, migration offers, and contract language updates).

### Tier model options to decide now

1. `B-first model` (control-plane launch posture):
   - Visibility tier (lead-gen only), Governance tier, Control-Plane tier, Enterprise.
   - Pricing anchors should move upward for enforcement-bearing tiers.
   - Use only after B-launch gate (`PKG-015`) is satisfied.

2. `Hybrid model` (safer transition posture):
   - Keep SMB analytics entry ladder, but add explicit control-plane tier above Pro.
   - Clearly distinguish "preview governance" from "runtime enforcement".
   - Allows earlier revenue while closing P0 enforcement correctness gaps.

3. Decision rule:
   - If P0 enforcement items are not DONE, default to `Hybrid`.
   - If P0 enforcement items are DONE and gated in runtime entitlements, `B-first` is viable.

## Unit economics simulation addendum (2026-02-24)

This section evaluates the latest revenue/COGS simulation assumptions for `29/79/199/499`.

### What is factual from code

1. Tier prices currently implemented:
   - Starter `$29`, Growth `$79`, Pro `$199`, Enterprise `price_usd=None`.
   - Evidence: `app/shared/core/pricing.py`.

2. Annual pricing for Starter/Growth/Pro is configured as 10 months billed for 12 months.
   - Evidence: `app/shared/core/pricing.py` (`monthly` vs `annual` values).

3. LLM usage limits are tier-defined and non-trivial at higher tiers:
   - Starter `5/day`, Growth `20/day`, Pro `100/day`, Enterprise `2000/day`.
   - Evidence: `app/shared/core/pricing.py`.

### Simulation math check (your provided model)

1. Scenario-2 MRR arithmetic is correct:
   - `20*29 + 50*79 + 25*199 + 5*499 = 12,000`.

2. 70% annual mix effect is correct under 16.7% annual discount:
   - Effective MRR factor `= 0.3 + 0.7*(10/12) = 0.8833`.
   - `12,000 * 0.8833 ~= 10,600`.
   - Overall revenue reduction ~= `11.7%`.

3. 1,000-customer scaled revenue arithmetic is correct:
   - `120,000 MRR` and `~1.44M ARR` (monthly run-rate basis).

### Critical caveats (must model before using as board target)

1. Enterprise `$499` is currently a planning assumption, not configured product pricing.
2. LLM COGS assumptions here are average-case; worst-case consumption could be much higher given tier call caps.
3. COGS sensitivity should be tracked with at least:
   - base-case (observed p50),
   - stress-case (p95 usage),
   - abuse-case (near-cap usage before guardrails trigger).
4. Gross-margin projections are likely valid directionally, but they are not launch-safe until usage telemetry is measured in production-like shadow/beta cohorts.

### Finance tracking additions from this feedback

1. `FIN-001` Build monthly unit-economics dashboard by tier:
   - MRR, effective MRR after annual discounts, LLM COGS, infra COGS, support load proxy, gross margin.
2. `FIN-002` Add COGS stress-test model tied to actual tier limits and observed percentile usage (p50/p95/p99).
3. `FIN-003` Require quarterly re-pricing check when Enterprise adoption or enforcement usage crosses threshold bands.
4. `FIN-004` Tie `PKG-016` control-plane tier pricing decision to measured beta cost + value evidence, not assumption-only modeling.

### Strategic lever confirmation

1. Primary growth lever is up-tier conversion, not Starter volume.
   - In the provided 1,000-customer scenario, Enterprise penetration shifts have outsized ARR impact versus low-tier growth.
2. Add conversion KPIs as launch finance gates:
   - Growth -> Pro conversion rate
   - Pro -> Enterprise conversion rate
   - Net Revenue Retention (NRR)
3. Track as `FIN-005`: tier-migration funnel dashboard with monthly cohort progression and expansion contribution.

### Launch finance gate (operational)

Use this gate alongside technical launch gates (`ECP-*`, `BSAFE-*`):

1. `FIN-GATE-1` Gross margin floor:
   - Shadow/beta observed blended gross margin must stay `>= 80%` for two consecutive monthly closes.
2. `FIN-GATE-2` LLM COGS containment:
   - p95 tenant LLM COGS must remain within planned tier envelope; any sustained breach opens pricing/limit review.
3. `FIN-GATE-3` Annual billing impact control:
   - Effective MRR reduction from annual mix must stay within planned discount tolerance bands and be offset by retention/churn improvements.
4. `FIN-GATE-4` Expansion signal:
   - Growth -> Pro and Pro -> Enterprise conversion must show positive month-over-month trend before broad GA pricing reset.
5. `FIN-GATE-5` Scenario stress resilience:
   - Base + stress scenario (`~2x infra COGS`) must keep projected gross margin above `75%`.

If any `FIN-GATE-*` fails, hold pricing/positioning escalation and run corrective plan (`FIN-001..FIN-005`).

## AI acceleration vs control-plane risk addendum (2026-02-24)

This section evaluates the latest point that AI can accelerate delivery but does not remove systemic enforcement risk.

### Fact checks from code

1. No LLM provider usage is present in enforcement runtime module paths.
   - Repo scan over `app/modules/enforcement` and `app/models/enforcement.py` returned no `llm/groq/openai/anthropic/gemini` references.

2. Runtime gate has explicit timeout handling and fail-safe fallback path.
   - `asyncio.wait_for(...)` is used around gate evaluation.
   - Timeout/error paths call `resolve_fail_safe_gate(...)`.
   - Evidence: `app/modules/enforcement/api/v1/enforcement.py`.

3. Fail behavior is deterministic and mode-based (`SHADOW/SOFT/HARD`).
   - Mode maps to `ALLOW/REQUIRE_APPROVAL/DENY` and fail-safe reason codes.
   - Evidence: `app/modules/enforcement/domain/service.py`, `app/models/enforcement.py`.

4. Determinism/audit primitives exist:
   - idempotency key handling and unique-constraint model support,
   - append-only immutable decision ledger,
   - approval token replay protection with one-time consume semantics.
   - Evidence: `app/models/enforcement.py`, `app/modules/enforcement/domain/service.py`.

5. Observability exists for enforcement path:
   - gate decision/failure/latency metrics,
   - reservation reconciliation metrics.
   - Evidence: `app/shared/core/ops_metrics.py`, enforcement API/service modules.

6. Gaps that reinforce your warning still exist:
   - concurrency correctness under distinct idempotency keys (`ECP-012`),
   - credit decrement lifecycle completeness (`ECP-004`),
   - per-environment fail-mode policy (`ECP-005`),
   - missing explicit replay/simulation engine for enforcement decisions.

### Verdict on this feedback (strict)

1. "AI speeds coding but does not remove distributed-systems risk" -> `Supported`.
2. "LLM should not be in allow/deny runtime path" -> `Already aligned in current enforcement code`.
3. "Phased rollout (shadow -> soft -> hard) is required for safe B adoption" -> `Supported and partially implemented`.
   - Mode primitives exist, but there is no formal promotion gate framework tied to measured false-positive/blast-radius thresholds.

### New safety tracking IDs (engineering)

1. `BSAFE-001` Add an invariant test/guardrail that enforcement decision path remains LLM-free (static import + runtime dependency checks).
2. `BSAFE-002` Build enforcement replay/simulation runner for historical traffic with outputs: `would_allow`, `would_require_approval`, `would_deny`, false-positive estimates.
3. `BSAFE-003` Define and enforce rollout promotion gates (`shadow -> soft -> hard`) with explicit SLO/quality thresholds and sign-off owners.
4. `BSAFE-004` Add failure-injection test matrix for gate timeout, DB unavailability, token replay races, and reservation contention.
5. `BSAFE-005` Add operator-facing explanation contract for blocked decisions (deterministic reason + remediation suggestion), with strict separation from decision logic.

## Release gating discipline addendum (2026-02-24, CTRL snapshot mapping)

The external `CTRL-*` snapshot (`PASS/IN_PROGRESS/PENDING`) is not currently represented as native IDs in this repo tracker.
This section maps those controls to repository evidence and current readiness interpretation.

### Control mapping (fact-based)

| External control | Repo-backed status | Evidence | Readiness impact |
|---|---|---|---|
| `CTRL-003` Ledger immutability | Implemented baseline; proof can be strengthened | DB trigger/function in migration + ORM update/delete guards + unit tests | Beta-ready; keep as GA evidence item |
| `CTRL-009` Cross-tenant abuse guard | Implemented baseline | Enforcement gate endpoints now have tenant-aware limits and an explicit global cross-tenant throttle (`global_rate_limit`) with configurable cap (`ENFORCEMENT_GLOBAL_GATE_PER_MINUTE_CAP`) and tests proving shared-budget throttling | Keep threshold tuning + operational evidence for GA packet |
| `CTRL-011` Tier token ceilings enforcement | Implemented baseline | Tier token ceilings and daily quotas exist; actor propagation/fallback hardening (`LLM-001..005`) is closed with regression coverage across analyzers/jobs and tier-aware fallback policy tests | Keep threshold tuning + cost telemetry as ops follow-on |
| `CTRL-020` Export parity/integrity pack | Implemented baseline | `/exports/parity` + hash/count parity logic + targeted API tests | Beta-ready; strengthen for procurement-grade evidence |

### Mapped evidence references

1. Ledger immutability:
   - Migration-level immutable trigger/function: `migrations/versions/c3f8d9e4a1b2_add_enforcement_decision_ledger_immutable.py`
   - ORM guards: `app/models/enforcement.py`
   - Tests: `tests/unit/enforcement/test_enforcement_service.py` (immutable ledger append/update/delete checks)
2. Abuse guards:
   - Tenant-aware limiter keying: `app/shared/core/rate_limit.py`
   - Enforcement endpoint limits: `app/modules/enforcement/api/v1/enforcement.py`, `app/modules/enforcement/api/v1/approvals.py`
3. Token ceilings:
   - Tier ceilings in pricing: `app/shared/core/pricing.py`
   - Ceiling enforcement path: `app/shared/llm/analyzer.py`, `app/shared/llm/zombie_analyzer.py`, `app/shared/llm/budget_fair_use.py`
4. Export integrity:
   - Parity/hash bundle builder: `app/modules/enforcement/domain/service.py`
   - Export parity/archive APIs: `app/modules/enforcement/api/v1/exports.py`
   - API tests: `tests/unit/enforcement/test_enforcement_api.py`

### External CTRL arithmetic normalization (feedback reconciliation)

1. The external statement "4 pending controls" conflicts with the listed pending set when `CTRL-019` is included (that would be 5 pending items, not 4).
2. Repository evidence for debated controls:

| External control | Current evidence in repo | Normalized interpretation |
|---|---|---|
| `CTRL-010` Bot friction | Turnstile server-side validation and route dependencies exist (`app/shared/core/turnstile.py`, governance public/onboard endpoints) | Implemented baseline |
| `CTRL-016` Supply-chain provenance | SBOM + lock verification + attestation workflow exists (`.github/workflows/sbom.yml`) and workflow tests assert wiring (`tests/unit/supply_chain/test_supply_chain_provenance_workflow.py`) | Implemented baseline |
| `CTRL-017` Key rotation drill evidence | Rotation-compatible enforcement token verification tests exist (`tests/unit/enforcement/test_enforcement_service.py`), emergency rotation runbook exists (`docs/runbooks/secret_rotation_emergency.md`), staged drill artifact exists (`docs/ops/key-rotation-drill-2026-02-27.md`), and release-gate validator enforces freshness/rollback markers (`scripts/verify_key_rotation_drill_evidence.py`) | Implemented baseline |
| `CTRL-018` Dashboards/alerts evidence pack | Metrics instrumentation + artifactized rules/dashboard/evidence exist (`app/shared/core/ops_metrics.py`, `ops/alerts/enforcement_control_plane_rules.yml`, `ops/dashboards/enforcement_control_plane_overview.json`, `docs/ops/alert-evidence-2026-02-25.md`) | Implemented baseline |
| `CTRL-019` Incident runbook/drills | Enforcement incident runbook + drill artifacts exist (`docs/runbooks/enforcement_incident_response.md`, `docs/ops/drills/enforcement_incident_drill_2026-02-23.md`) | Implemented baseline |
| `CTRL-021` Program CI quality gate | Dedicated release-blocking gate job exists (`.github/workflows/ci.yml`, `scripts/run_enterprise_tdd_gate.py`) | Implemented baseline |
| `CTRL-022` No-placeholder CI scan | CI invokes strict placeholder guard (`scripts/verify_enterprise_placeholder_guards.py`) | Implemented baseline |

3. Tracker rule for consistency:
   - If `CTRL-019` is treated as pending, pending count must include it explicitly.
   - If runbook+drill artifacts are accepted, mark `CTRL-019` as implemented baseline and keep pending counts aligned to the remaining controls only.

### Updated release interpretation

1. Private beta with controlled tenants and progressive enforcement modes: `viable`.
2. Public GA control-plane launch: `not yet`.
3. Highest-priority closures before GA:
   - `ECP-012` reservation concurrency serialization
   - `ECP-004` credit lifecycle correctness
   - `ECP-005` per-environment fail policy
   - `LLM-001..004` token-ceiling/fair-use hardening
   - `BSAFE-002..004` replay, rollout gates, and failure injection coverage

### Additional tracking IDs from this mapping

1. `BSAFE-006` Add global enforcement abuse/fairness guard beyond per-tenant limiter (global throttle + saturation policy + observability). Status update (2026-02-25): `DONE` baseline.
2. `BSAFE-007` Add procurement-grade export integrity pack (signed manifest + reproducibility checks + parity regression suite). Status update (2026-02-25): `DONE` baseline.
3. `BSAFE-008` Minimum viable enforcement operations evidence pack (alerts/dashboard artifacts + validation tests). Status update (2026-02-25): `DONE` baseline.

#### BSAFE-006 closure evidence (2026-02-25)

1. Global cross-tenant limiter primitive added:
   - `app/shared/core/rate_limit.py` (`global_limit_key`, `global_rate_limit`).
2. Enforcement gate endpoints now enforce global shared throttle namespace:
   - `app/modules/enforcement/api/v1/enforcement.py` (`@global_rate_limit(..., namespace="enforcement_gate")` on gate routes).
3. Configurable guardrails and validation:
   - `app/shared/core/config.py`
   - `ENFORCEMENT_GLOBAL_ABUSE_GUARD_ENABLED`
   - `ENFORCEMENT_GLOBAL_GATE_PER_MINUTE_CAP`
4. Test coverage:
   - `tests/unit/core/test_rate_limit.py` (`test_global_rate_limit_throttles_cross_tenant_requests`)
   - `tests/unit/core/test_config_validation.py` (global cap validation tests)
   - `tests/unit/enforcement/test_enforcement_api.py` (gate global limit contract helper tests)
5. Validation runs:
   - `uv run pytest --no-cov -q tests/unit/core/test_rate_limit.py tests/unit/core/test_config_validation.py tests/unit/enforcement/test_enforcement_api.py`
   - Result: `77 passed`
   - `uv run pytest --no-cov -q tests/unit/enforcement`
   - Result: `130 passed`

#### BSAFE-007 closure evidence (2026-02-25)

1. Signed export manifest contract added:
   - `app/modules/enforcement/domain/service.py` (`build_signed_export_manifest`, canonical manifest hashing, HMAC signature generation).
2. Archive now ships signed manifest artifacts:
   - `manifest.json`
   - `manifest.canonical.json`
   - `manifest.sha256`
   - `manifest.sig`
   - Evidence: `app/modules/enforcement/api/v1/exports.py`.
3. Parity API response now includes signed-manifest fields:
   - `manifest_content_sha256`
   - `manifest_signature`
   - `manifest_signature_algorithm`
   - `manifest_signature_key_id`
   - Evidence: `app/modules/enforcement/api/v1/schemas.py`, `app/modules/enforcement/api/v1/exports.py`.
4. Signing guardrails and config bounds:
   - `ENFORCEMENT_EXPORT_SIGNING_SECRET`
   - `ENFORCEMENT_EXPORT_SIGNING_KID`
   - Evidence: `app/shared/core/config.py`.
5. Regression tests:
   - `tests/unit/enforcement/test_enforcement_api.py`
   - `tests/unit/enforcement/test_enforcement_service.py`
   - `tests/unit/core/test_config_validation.py`
6. External standards/reference basis:
   - HMAC construction reference: RFC 2104 (`https://www.rfc-editor.org/rfc/rfc2104`)
   - Rationale: deterministic, tamper-evident manifest signing for archive integrity assertions.

#### BSAFE-008 closure evidence (2026-02-25)

1. Alert rules pack:
   - `ops/alerts/enforcement_control_plane_rules.yml`
2. Dashboard pack:
   - `ops/dashboards/enforcement_control_plane_overview.json`
3. Evidence document:
   - `docs/ops/alert-evidence-2026-02-25.md`
4. Validation tests:
   - `tests/unit/ops/test_enforcement_observability_pack.py`
5. New queue backlog metric:
   - `valdrix_ops_enforcement_approval_queue_backlog`
   - Evidence: `app/shared/core/ops_metrics.py`, `app/modules/enforcement/api/v1/approvals.py`.
6. External standards/reference basis:
   - Prometheus alerting rule specification: `https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/`
   - Prometheus HTTP API (alerts/rules observability): `https://prometheus.io/docs/prometheus/latest/querying/api/`

### Tuesday hardening sprint plan (execution mode)

This plan operationalizes the latest release-hardening feedback.

Date clarity:
1. If deadline means `Tuesday, February 24, 2026` (today), only limited closure is realistic.
2. If deadline means `Tuesday, March 3, 2026` (next Tuesday), full critical-path closure below is feasible with parallel owners.

Critical path mapping (`external CTRL-*` -> repo IDs):
1. `CTRL-003` Ledger immutability -> implemented baseline; keep evidence hardening under `BSAFE-007`.
2. `CTRL-009` Cross-tenant abuse guard -> `BSAFE-006` implemented baseline (keep threshold tuning + operational evidence).
3. `CTRL-011` Tier token ceiling proof -> `LLM-001`, `LLM-003`, `LLM-004` (GA blocker).
4. `CTRL-020` Export parity/integrity -> implemented baseline; procurement-grade evidence under `BSAFE-007`.
5. `CTRL-018` Counters + dashboards/alerts evidence -> `BSAFE-008` implemented baseline.

Parallel work lanes:
1. Lane A (platform safety): `BSAFE-006` regression watch + threshold tuning.
2. Lane B (margin and quota safety): `LLM-001`, `LLM-003`, `LLM-004`.
3. Lane C (audit/export evidence): `BSAFE-007` regression watch.
4. Lane D (operational evidence): `BSAFE-008` regression watch.

Definition of done for Tuesday sprint:
1. All critical path items have merged code/tests/docs evidence.
2. CI contains regression tests for abuse guard, token ceiling enforcement, and export parity.
3. Release packet contains:
   - immutable-ledger proof references,
   - abuse-guard behavior and thresholds,
   - token ceiling pass/fail tests,
   - counters/alerts evidence snapshot.

Closure note:
1. `BSAFE-008` Minimum viable enforcement operations evidence pack is implemented with:
   - counters exposed,
   - alert thresholds defined,
   - sample alert/log evidence for gate failures, rate-limit hits, token-ceiling denials, approval backlog.

### Evidence pack manifest (release-gate artifacts)

Use this manifest so `PASS` remains binary and auditable.

| Artifact | Path (repo) | Current signal |
|---|---|---|
| Immutable ledger enforcement proof | `migrations/versions/c3f8d9e4a1b2_add_enforcement_decision_ledger_immutable.py` + `tests/unit/enforcement/test_enforcement_service.py` | Present |
| Export parity/integrity regression | `tests/unit/enforcement/test_enforcement_api.py` | Present |
| Program CI hard gate definition | `.github/workflows/ci.yml` + `scripts/run_enterprise_tdd_gate.py` | Present |
| Placeholder/legacy guard definition | `scripts/verify_enterprise_placeholder_guards.py` + `scripts/placeholder_guard_allowlist_full.txt` | Present |
| Supply-chain SBOM + provenance attestation | `.github/workflows/sbom.yml` + `scripts/generate_provenance_manifest.py` | Present |
| Incident runbook + drill records | `docs/runbooks/enforcement_incident_response.md` + `docs/ops/drills/enforcement_incident_drill_2026-02-23.md` | Present |
| Key rotation drill report | `docs/ops/key-rotation-drill-2026-02-27.md` + `scripts/verify_key_rotation_drill_evidence.py` | Present |
| Alerts/dashboard evidence packet | `docs/ops/alert-evidence-2026-02-25.md` + `ops/alerts/*` + `ops/dashboards/*` | Present |
| CI green-run capture for release packet | `docs/evidence/ci-green-YYYY-MM-DD.md` (`docs/evidence/ci-green-template.md` for baseline format) | Template present; staged run artifact still required for promotion packets |

### Binary Artifact Closure Checklist (release packet)

Treat this checklist as release-blocking closure evidence. Completion is binary (`PASS` only when all are satisfied).

1. Staged stress evidence JSON captured and committed:
   - `docs/ops/evidence/enforcement_stress_artifact_YYYY-MM-DD.json`
2. Staged failure-injection evidence JSON captured and committed:
   - `docs/ops/evidence/enforcement_failure_injection_YYYY-MM-DD.json`
3. CI green-run release packet captured and committed:
   - `docs/evidence/ci-green-YYYY-MM-DD.md`
4. One-pass release evidence gate executed against staged artifacts:
   - `uv run python3 scripts/run_enforcement_release_evidence_gate.py --stress-evidence-path docs/ops/evidence/enforcement_stress_artifact_YYYY-MM-DD.json --failure-evidence-path docs/ops/evidence/enforcement_failure_injection_YYYY-MM-DD.json --stress-max-age-hours 24 --failure-max-age-hours 48 --stress-min-duration-seconds 30 --stress-min-concurrent-users 10`
5. Post-closure sanity validator confirms artifact checklist contract:
   - `uv run python3 scripts/verify_enforcement_post_closure_sanity.py --doc-path docs/ops/enforcement_post_closure_sanity_2026-02-26.md --gap-register docs/ops/enforcement_control_plane_gap_register_2026-02-23.md`

## LLM free-tier feedback audit (2026-02-24, operator pass)

This section evaluates the latest "Free LLM via Groq" feedback against implementation reality.

### Fact checks from code

1. Default provider is Groq:
   - `LLM_PROVIDER="groq"` in config.
   - Default LLM budget bootstrap also sets `preferred_provider="groq"`.
   - Evidence: `app/shared/core/config.py`, `app/shared/llm/budget_execution.py`.

2. Model fallback can switch away from Groq on primary failure:
   - Fallback order is `Groq -> Google -> OpenAI`.
   - Evidence: `app/shared/llm/analyzer.py`.

3. Per-tenant and per-user daily limits exist:
   - Tenant limit (`llm_analyses_per_day`) is always enforced.
   - User limit (`llm_analyses_per_user_per_day`) is enforced only when `user_id` is provided.
   - Evidence: `app/shared/llm/budget_fair_use.py`.

4. Free plan currently sets:
   - `llm_analyses_per_day = 1`
   - `llm_analyses_per_user_per_day = 1`
   - `llm_output_max_tokens = 512`
   - Evidence: `app/shared/core/pricing.py`.

5. Authenticated LLM analysis endpoint has tier-aware rate limiting:
   - Free `1/hour`, Starter `2/hour`, Growth `10/hour`, Pro `50/hour`, Enterprise `200/hour`.
   - Evidence: `app/shared/core/rate_limit.py`, `app/modules/reporting/api/v1/costs.py`.

6. Global anti-abuse throttle exists:
   - Enabled by default (`LLM_GLOBAL_ABUSE_GUARDS_ENABLED=True`) with global RPM/tenant thresholds and kill-switch support.
   - Evidence: `app/shared/core/config.py`, `app/shared/llm/budget_fair_use.py`.

7. Additional fair-use guards (soft daily, per-minute, concurrency) are disabled by default and only applied for Pro/Enterprise tiers:
   - `LLM_FAIR_USE_GUARDS_ENABLED=False`
   - `fair_use_tier_allowed()` returns only Pro/Enterprise.
   - Evidence: `app/shared/core/config.py`, `app/shared/llm/budget_fair_use.py`.

Guard-scope clarity for this tracker:
1. Global anti-abuse guard (`LLM_GLOBAL_ABUSE_*`) is cross-tier and applies regardless of paid tier when enabled.
2. Additional fair-use guard set (`LLM_FAIR_USE_*`) is currently Pro/Enterprise-only by policy.
3. Therefore, statements like "fair-use guards are Pro/Enterprise-only" refer to the additional fair-use layer, not the global abuse layer.

8. Some user-triggered LLM paths do not pass `user_id`, so per-user caps are skipped there:
   - Zombie scan endpoint triggers analysis workflow without actor propagation.
   - Job handler calls analyzer without `user_id`.
   - Zombie analyzer reserves budget without `user_id`.
   - Evidence: `app/modules/optimization/api/v1/zombies.py`, `app/modules/optimization/domain/service.py`, `app/modules/governance/domain/jobs/handlers/analysis.py`, `app/shared/llm/zombie_analyzer.py`.

9. Public/onboarding bot friction exists via Turnstile + rate limits:
   - Turnstile enforced for `public_assessment`, `sso_discovery`, and `onboard` surfaces.
   - Evidence: `app/shared/core/turnstile.py`, `app/modules/governance/api/v1/public.py`, `app/modules/governance/api/v1/settings/onboard.py`.

### External references (for pricing/rate-limit context)

1. Groq pricing page publishes token pricing and "start for free" messaging:
   - https://groq.com/pricing
2. Groq rate-limit docs explicitly state limits are organization-level and include Free/Developer tiers:
   - https://console.groq.com/docs/rate-limits
3. Groq billing FAQ states Free vs Developer behavior and pay-as-you-go upgrade path:
   - https://console.groq.com/docs/billing-faqs
4. OWASP API Security Top 10 `API4: Unrestricted Resource Consumption`:
   - https://owasp.org/API-Security/editions/2023/en/0x11-t10/
5. Google SRE alerting guidance for error budget/burn-rate policy:
   - https://sre.google/workbook/alerting-on-slos/

### Verdict on the new feedback

1. "Per-user cap exists" -> `Partially true`.
   - True for flows that pass `user_id`.
   - Not universally true across all LLM entry paths.

2. "Need per-user + per-tenant + global abuse guard" -> `Supported and mostly implemented`.
   - Core primitives exist.
   - Actor propagation inconsistency is the main gap.

3. "Abuse prevention should include rate limiting + signup friction" -> `Supported`.
   - Implemented on key surfaces, but no dedicated IP-only LLM throttle for authenticated traffic.

4. "Free LLM should be teaser, higher tiers operational AI" -> `Not fully encoded in backend contract`.
   - Limits exist, but capability-shape differences are still mostly quantitative, not strongly qualitative.

5. "Groq lowers cost risk" -> `Directionally true`.
   - But fallback to Google/OpenAI can raise marginal cost unless constrained by policy.

### Necessity decision for this feedback (strict)

1. Keep LLM in Free tier -> `Can keep`, but only with hard controls.
   - Current evidence already includes tenant daily cap, per-user cap (when actor present), token ceilings, and endpoint rate limits.
2. Add per-tenant cap -> `Already present`.
   - Current free tier is `llm_analyses_per_day=1`, which already blocks "many users in one free tenant" cost explosion.
3. Enforce per-user caps universally -> `Needed now`.
   - Actor propagation gaps mean some user-triggered async flows bypass per-user enforcement.
4. Add abuse controls beyond plan quotas -> `Needed now`.
   - Rate limits and Turnstile exist, but authenticated LLM paths still need stronger abuse telemetry/risk scoring.
5. Make Free AI "teaser" and paid tiers "operational AI" -> `Needed now`.
   - Current contract is mostly quantitative limits; qualitative capability boundaries are not explicit in runtime gates.
6. Keep AI as additive positioning, not core moat claim -> `Needed (packaging governance)`.
   - Enforcement/economic control-plane capability is the durable differentiation in current roadmap.

### LLM gap tracker additions

1. `LLM-001` Propagate `user_id` across all user-triggered LLM execution paths (especially zombie analysis async flow) so per-user quotas are consistently enforceable.
2. `LLM-002` Add explicit actor classification (`user` vs `system`) in LLM usage records and quota policy; prevent system jobs from silently bypassing intended user fairness controls.
3. `LLM-003` Add tier-aware analysis-shape limits (max date range / max records / prompt token ceiling per request) to prevent heavy free-tier queries.
4. `LLM-004` Add provider fallback policy by tier (for example restrict Free fallback to low-cost providers unless explicit override) to protect COGS.
5. `LLM-005` Add authenticated endpoint abuse telemetry with optional IP dimension/risk scoring for anomaly detection beyond tenant-key rate limits.

### LLM closure pass (2026-02-25)

Status updates for the `CTRL-011` blocker set:

1. `LLM-001` -> `Done` (user actor propagation end-to-end for zombie flow and job handlers).
   - API/background payload propagation:
     - `app/modules/optimization/api/v1/zombies.py`
     - `app/modules/optimization/domain/service.py`
     - `app/modules/governance/domain/jobs/handlers/zombie.py`
     - `app/modules/governance/domain/jobs/handlers/analysis.py`
   - Analyzer metering propagation:
     - `app/shared/llm/zombie_analyzer.py`
   - Validation evidence:
     - `tests/unit/zombies/test_zombies_api_branches.py`
     - `tests/unit/services/jobs/test_job_handlers.py`
     - `tests/unit/llm/test_zombie_analyzer_exhaustive.py`

2. `LLM-003` -> `Done` (tier-aware request-shape controls).
   - Added deterministic limits to tier config:
     - `llm_analysis_max_records`
     - `llm_analysis_max_window_days`
     - `llm_prompt_max_input_tokens`
     - Evidence: `app/shared/core/pricing.py`
   - Enforced in analyzers before prompt construction:
     - `app/shared/llm/analyzer.py`
     - `app/shared/llm/zombie_analyzer.py`
   - Validation evidence:
     - `tests/unit/llm/test_analyzer_exhaustive.py`
     - `tests/unit/llm/test_zombie_analyzer_exhaustive.py`

3. `LLM-004` -> `Done` (tier-aware fallback policy in runtime invocation).
   - Fallback chain now tier-scoped:
     - Free/Starter/Growth -> low-cost fallbacks only (`groq`, `google`)
     - Pro -> low-cost + `openai`
     - Enterprise -> low-cost + `openai` + `anthropic`
     - BYOK requests disable cross-provider fallback.
   - Evidence: `app/shared/llm/analyzer.py`
   - Validation evidence: `tests/unit/llm/test_analyzer_exhaustive.py`

4. `LLM-002` -> `Done` (explicit actor classification + quota policy).
   - Added actor-aware quota enforcement:
     - user actor requests require user context
     - system actor requests enforce `llm_system_analyses_per_day`
   - Metered usage now stores explicit actor prefix in `request_type` (`user:*` / `system:*`) for downstream auditing.
   - Evidence:
     - `app/shared/llm/budget_fair_use.py`
     - `app/shared/llm/budget_execution.py`
     - `app/shared/core/pricing.py`
   - Validation evidence:
     - `tests/unit/shared/llm/test_budget_fair_use_branches.py`
     - `tests/unit/llm/test_usage_tracker.py`

5. `LLM-005` -> `Done` (authenticated abuse telemetry baseline with IP risk signal).
   - Added authenticated abuse signal metrics:
     - `valdrix_ops_llm_auth_abuse_signals_total`
     - `valdrix_ops_llm_auth_ip_risk_score`
   - Added optional client IP propagation from authenticated API/job surfaces into LLM pre-auth guardrails.
   - Added client IP bucket/risk classification with high-risk audit events.
   - Evidence:
     - `app/shared/core/ops_metrics.py`
     - `app/shared/llm/budget_fair_use.py`
     - `app/modules/reporting/api/v1/costs.py`
     - `app/modules/optimization/api/v1/zombies.py`
     - `app/modules/optimization/domain/service.py`
     - `app/modules/governance/domain/jobs/handlers/{zombie,analysis,finops}.py`
   - Validation evidence:
     - `tests/unit/api/v1/test_costs_endpoints.py`
     - `tests/unit/services/jobs/test_job_handlers.py`
     - `tests/unit/zombies/test_zombies_api_branches.py`

### LLM implementation order (tight)

1. `P0` `LLM-001` + `LLM-003` + `LLM-004` (cost and fairness correctness first).
2. `P1` `LLM-002` + `LLM-005` (now closed baseline; continue tuning thresholds/alerting policy).
3. `P1` `PKG-011` (encode qualitative AI value ladder in pricing/entitlement contract).

### Validation run for LLM-002 + LLM-005 closure (2026-02-25)

- Commands:
  - `uv run ruff check app/shared/core/ops_metrics.py app/shared/llm/budget_manager.py app/shared/llm/budget_execution.py app/shared/llm/budget_fair_use.py app/shared/llm/analyzer.py app/shared/llm/zombie_analyzer.py app/shared/llm/usage_tracker.py app/shared/core/pricing.py app/modules/reporting/api/v1/costs.py app/modules/optimization/api/v1/zombies.py app/modules/optimization/domain/service.py app/modules/governance/domain/jobs/handlers/zombie.py app/modules/governance/domain/jobs/handlers/analysis.py app/modules/governance/domain/jobs/handlers/finops.py tests/unit/shared/llm/test_budget_fair_use_branches.py tests/unit/llm/test_usage_tracker.py tests/unit/llm/test_analyzer_exhaustive.py tests/unit/llm/test_zombie_analyzer_exhaustive.py tests/unit/services/jobs/test_job_handlers.py tests/unit/zombies/test_zombies_api_branches.py tests/unit/api/v1/test_costs_endpoints.py`
  - `uv run mypy app/shared/llm/budget_manager.py app/shared/llm/budget_execution.py app/shared/llm/budget_fair_use.py app/shared/llm/analyzer.py app/shared/llm/zombie_analyzer.py app/shared/llm/usage_tracker.py app/modules/governance/domain/jobs/handlers/analysis.py app/modules/governance/domain/jobs/handlers/finops.py app/modules/governance/domain/jobs/handlers/zombie.py app/modules/optimization/domain/service.py app/modules/reporting/api/v1/costs.py`
  - `uv run pytest --no-cov -q tests/unit/shared/llm/test_budget_fair_use_branches.py tests/unit/llm/test_budget_manager.py tests/unit/llm/test_budget_manager_exhaustive.py tests/unit/llm/test_usage_tracker.py tests/unit/llm/test_usage_tracker_audit.py tests/unit/llm/test_analyzer_exhaustive.py tests/unit/llm/test_zombie_analyzer_exhaustive.py tests/unit/services/jobs/test_job_handlers.py tests/unit/zombies/test_zombies_api_branches.py tests/unit/api/v1/test_costs_endpoints.py`
- Results:
  - `ruff: All checks passed`
  - `mypy: Success, no issues found in 11 source files`
  - `pytest: 169 passed in 68.05s`

### Validation run for this pass

- Command:
  - `uv run pytest --no-cov -q tests/unit/shared/llm/test_budget_fair_use_branches.py tests/unit/core/test_rate_limit_expanded.py tests/security/test_multi_tenant_safety.py`
- Result:
  - `43 passed in 7.20s`

### Validation run for this closure pass (ECP-008 + ECP-010)

- Commands:
  - `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_api.py`
  - `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_property_and_concurrency.py`
  - `uv run ruff check app/models/enforcement.py app/modules/enforcement/domain/service.py app/modules/enforcement/api/v1/schemas.py app/modules/enforcement/api/v1/approvals.py app/modules/enforcement/api/v1/ledger.py tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_api.py migrations/versions/j6k7l8m9n0p1_add_enforcement_ledger_approval_linkage_fields.py`
  - `uv run mypy app/modules/enforcement/domain/service.py app/modules/enforcement/api/v1/schemas.py app/modules/enforcement/api/v1/approvals.py app/modules/enforcement/api/v1/ledger.py app/models/enforcement.py`
- Results:
  - `84 passed in 320.55s` (service + API suite)
  - `5 passed in 8.49s` (property/concurrency suite)
  - `ruff: All checks passed`
  - `mypy: Success, no issues found in 5 source files`

### Validation run for this closure pass (ECP-006 + ECP-007)

- Commands:
  - `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_api.py tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_property_and_concurrency.py`
  - `uv run ruff check app/modules/enforcement/api/v1/enforcement.py app/modules/enforcement/api/v1/schemas.py app/modules/enforcement/domain/service.py tests/unit/enforcement/test_enforcement_api.py`
  - `uv run mypy app/modules/enforcement/api/v1/enforcement.py app/modules/enforcement/api/v1/schemas.py app/modules/enforcement/domain/service.py`
- Results:
  - `95 passed in 622.57s` (API + service + property/concurrency suites)
  - `ruff: All checks passed`
  - `mypy: Success, no issues found in 3 source files`

### Validation run for this closure pass (ECP-009 + ECP-014)

- Commands:
  - `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_api.py tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_property_and_concurrency.py`
  - `uv run ruff check app/modules/enforcement/api/v1/enforcement.py app/modules/enforcement/api/v1/schemas.py app/modules/enforcement/domain/service.py tests/unit/enforcement/test_enforcement_api.py`
  - `uv run mypy app/modules/enforcement/api/v1/enforcement.py app/modules/enforcement/api/v1/schemas.py app/modules/enforcement/domain/service.py`
- Results:
  - `98 passed in 187.04s` (API + service + property/concurrency suites)
  - `ruff: All checks passed`
  - `mypy: Success, no issues found in 3 source files`

## Pricing feedback addendum (2026-02-24, market-verified B-tier positioning)

This section applies the latest pricing feedback to repository reality and externally verifiable market anchors.

### External pricing anchors (verified)

1. Vantage public pricing:
   - Pro `$30/month`, Business `$200/month`, Enterprise custom.
   - Source: https://www.vantage.sh/pricing
2. Holori public pricing:
   - Pro `$49/month`, Business `$199/month`.
   - Source: https://holori.com/pricing/
3. Cloudchipr public pricing:
   - Basic `$49/month`, Advanced `$189/month`, Pro `$445/month`.
   - Source: https://cloudchipr.com/pricing
4. Ternary public pricing:
   - "Pricing starts at $25K annually."
   - Source: https://ternary.app/pricing/
5. IBM Kubecost marketplace pricing (primary seller channel):
   - IBM Kubecost Cloud: 12-month contract dimension listed at `$7,950`.
   - IBM Kubecost Enterprise: 12-month contract dimension listed at `$15,000`.
   - IBM Kubecost EKS cost-monitoring listing: available free (bundle listing) with additional infra costs possible.
   - Sources:
     - https://aws.amazon.com/marketplace/pp/prodview-qnvpdqk2wrsui
     - https://aws.amazon.com/marketplace/pp/prodview-zdyeh4lqc5jaw
     - https://aws.amazon.com/marketplace/pp/prodview-asiz4x22pm2n2

Pricing evidence quality note:
1. Some third-party pages still cite Kubecost "Business $449/month".
2. For this tracker, primary vendor pages/marketplace listings are treated as highest-confidence sources.
3. Third-party pricing cards are treated as secondary references unless confirmed by first-party pages.

### Codebase alignment with the feedback

1. Current plan ladder in code is still `Starter 29 / Growth 79 / Pro 199 / Enterprise custom`.
   - Evidence: `app/shared/core/pricing.py`
2. Enterprise entitlement is still `features: set(FeatureFlag)` (packaging risk still open).
   - Evidence: `app/shared/core/pricing.py`
3. Enforcement gate APIs are role-gated but not tier-feature gated.
   - Evidence: `app/modules/enforcement/api/v1/enforcement.py`
4. Pro already carries many integration/governance flags; clear runtime-enforced control-plane boundary is not yet formalized.
   - Evidence: `app/shared/core/pricing.py`, enforcement route dependencies.

### Verdict on the latest feedback (strict)

1. Keeping `$29/$79/$199` is viable for now.
2. For B-level positioning, viability depends on strict feature allocation and runtime enforcement of tier boundaries.
3. The safest contract shape with current code:
   - Starter/Growth: visibility + governance preview/manual controls.
   - Pro+: enforcement/gating entry point only after runtime tier gates are implemented.
4. "Disruptive pricing" claim is credible only when packaging truth is fixed (`PKG-007`) and enforcement entitlements are runtime-gated (`PKG-003`/`PKG-006`).

### Actions added from this feedback

1. `PKG-020` Add a pricing benchmark evidence register (source URL, source class, crawl date, confidence) and require periodic refresh before pricing updates.
2. `PKG-021` Define and implement explicit control-plane tier boundary in runtime:
   - gate APIs, approval token consume/issue surfaces, budget/credit enforcement controls.
3. `PKG-022` Add tier-allocation contract tests:
   - Starter/Growth cannot access enforcement endpoints when control-plane gating is set to Pro/Enterprise.
4. `PKG-023` Add GTM regional pricing policy artifact:
   - keep global USD list pricing baseline;
   - define when/where local-currency or regional discount programs apply;
   - include margin guardrails and FX review cadence.

## Executive feedback reconciliation (2026-02-24, control-plane maturity + pricing)

This section evaluates the latest executive-style feedback in three layers:
1. Control-plane technical reality.
2. Program contract risk (18-22 working day completion claim).
3. Pricing/positioning implication for B-tier credibility.

### 1) Control-plane technical reality check (fact-based)

What is already true in repository evidence:
1. Deterministic gate path with idempotency and policy-versioned decisions exists.
   - Evidence: `app/modules/enforcement/domain/service.py`, `app/models/enforcement.py`.
2. Immutable append-only decision ledger controls exist (DB migration + model guards).
   - Evidence: `migrations/versions/c3f8d9e4a1b2_add_enforcement_decision_ledger_immutable.py`, `app/models/enforcement.py`.
3. Approval-token signing/consume/replay-defense exists.
   - Evidence: `app/modules/enforcement/domain/service.py`, `app/modules/enforcement/api/v1/approvals.py`.
4. Fail-safe runtime modes and timeout fallback exist (`shadow/soft/hard`).
   - Evidence: `app/modules/enforcement/api/v1/enforcement.py`, `app/models/enforcement.py`.
5. Supply-chain evidence gates and release-blocking quality gate exist in CI.
   - Evidence: `.github/workflows/sbom.yml`, `.github/workflows/ci.yml`, `scripts/run_enterprise_tdd_gate.py`, `scripts/verify_enterprise_placeholder_guards.py`.

Verdict:
1. The architecture is no longer "analytics-only SaaS"; it is control-plane-grade in structure.
2. This does not yet imply full public GA readiness because unresolved correctness/operational controls remain in this register (`ECP-*`, `BSAFE-*`).

### 2) Program contract risk check (18-22 day claim)

Fact reconciliation:
1. The companion hardening snapshot reports `22/22 PASS (slice)`.
   - Evidence: `docs/ops/enterprise_hardening_and_llm_tier_strategy_2026-02-22.md`.
2. This register still tracks unresolved GA blockers/open items, especially:
   - `ECP-001..005`, `ECP-012` (decision/waterfall/routing/credit/concurrency),
   - `BSAFE-002..004`, `BSAFE-006..008` (replay/promotion gates/failure injection/global abuse/evidence pack).

Risk interpretation:
1. "PASS (slice)" should be treated as component-level completion, not end-to-end production validation.
2. Remaining risk is primarily operational proof under stress:
   - sustained multi-tenant load,
   - failure-injection/chaos matrix evidence,
   - staged key-rotation drill evidence,
   - alert/dashboards evidence artifacts.

### 3) Pricing + positioning implication (B-tier credibility)

External market anchors (primary public pages):
1. Vantage: `$30` Pro, `$200` Business.
2. Holori: `$49` Pro, `$199` Business.
3. Cloudchipr: `$49/$189/$445`.
4. Ternary: starts at `$25K/year`.
5. IBM Kubecost marketplace listings: contract dimensions in high-hundreds/low-thousands annualized monthly equivalents.

Current code reality:
1. Existing ladder remains `29/79/199` with Enterprise custom.
2. Enterprise entitlement still uses `set(FeatureFlag)`.
3. Enforcement is role-gated, not yet packaged by tier-gates.

Pricing implication:
1. Keeping `29/79/199` is still viable.
2. B-tier credibility requires enforcement to be a clearly higher-order commercial boundary (tier or add-on) with runtime gating.
3. Pricing too low for enforcement-bearing tiers can dilute trust signal; pricing must reflect outage/liability surface of real-time gates.

### Added actions from this feedback

1. `BSAFE-009` Create enforcement stress-evidence pack:
   - sustained multi-tenant load replay,
   - concurrency contention outcomes,
   - SLO pass/fail records.
2. `BSAFE-010` Add failure-injection/chaos evidence suite for gate timeouts, DB degradation, token replay races, and limiter saturation.
3. `BSAFE-011` Produce staged key-rotation drill artifact with rollback validation (`docs/ops/key-rotation-drill-YYYY-MM-DD.md`). Status update (2026-02-27): `DONE`.
4. `PKG-024` Decide and implement control-plane packaging strategy:
   - `Pro+ add-on` vs `new control-plane tier`,
   - explicit runtime feature gates and migration rules.
5. `FIN-006` Model price sensitivity for enforcement packaging bands (for example `199` vs `249/299`) with conversion and margin impact.

## Structural audit addendum (2026-02-24, product coherence + plan integrity)

This section reconciles the latest structural feedback in four lenses.

### 1) Product coherence (one product vs many products)

Fact pattern in code:
1. Pricing feature matrix spans analytics, remediation, commitment optimization, chargeback, close/reconciliation, carbon, identity, and governance/export surfaces.
   - Evidence: `app/shared/core/pricing.py`.
2. Enforcement control-plane module is present with dedicated gate/approval/ledger/budget-credit APIs.
   - Evidence: `app/modules/enforcement/api/v1/*`.
3. Identity/SCIM integration is first-class and enterprise-gated.
   - Evidence: `app/modules/governance/api/v1/settings/identity.py`, `app/modules/governance/api/v1/scim.py`.

Interpretation:
1. The product is coherent as a "cloud economics operating system" architecture.
2. GTM narrative still has a dual-core tension:
   - post-provision optimization/finance workflows,
   - pre-provision enforcement/gating workflows.

### 2) Plan integrity (tier logic cleanliness)

Fact pattern:
1. Free and Starter include non-trivial capability sets (LLM, zombie scan, unit economics, carbon, domain discovery).
   - Evidence: `app/shared/core/pricing.py`.
2. Growth includes high-value governance/automation signals (multi-cloud, anomaly detection, auto remediation, chargeback, commitment optimization).
   - Evidence: `app/shared/core/pricing.py`.
3. Pro includes identity/integration/audit/compliance and workflow-heavy features.
   - Evidence: `app/shared/core/pricing.py`.
4. Enterprise is currently "custom + all flags + high limits" rather than explicitly curated capability boundaries.
   - Evidence: `app/shared/core/pricing.py` (`features: set(FeatureFlag)`).

Interpretation:
1. Tier progression is logically increasing.
2. Tension points remain:
   - Growth may be very feature-dense for current price,
   - Enterprise looks partially limit-based instead of capability-differentiated,
   - enforcement/control-plane capability is not yet explicit as a commercial boundary.

### 3) Role model soundness

Fact pattern:
1. Core role hierarchy is explicit: `owner > admin > member`.
   - Evidence: `app/shared/core/auth.py`, `app/models/tenant.py`.
2. Enforcement APIs consistently use role dependencies (`member` for gate/approvals, `admin` for ledger/exports/reservations/policy writes).
   - Evidence: `app/modules/enforcement/api/v1/*.py`.
3. SCIM group mappings augment permission scope while preserving role model.
   - Evidence: `app/shared/core/approval_permissions.py`, `app/modules/governance/api/v1/settings/identity.py`.

Interpretation:
1. Role model is structurally sound.
2. Remaining hardening need is policy/routing strictness for high-risk approvals (`ECP-003`) rather than fundamental RBAC redesign.

### 4) Commercial signal vs operational complexity

Fact pattern:
1. Enforcement surface carries infrastructure-grade responsibility (pre-provision gates, fail-safe decisions, token security, immutable audit, export parity, abuse controls).
2. This register still marks unresolved GA blockers (`ECP-001..005`, `ECP-012`, plus `BSAFE-*` evidence hardening items).
3. Current public plan ladder is still SMB/mid-market signaling (`29/79/199`, Enterprise custom).

Interpretation:
1. Architecture maturity currently signals higher responsibility than pricing/package boundaries.
2. Commercial packaging should explicitly reflect liability surface when enforcement is enabled.

### Strategic model options (decision framing)

1. `Model-A` volume-first mid-market:
   - keep current ladder and defer hard control-plane monetization.
2. `Model-B` dual-core ladder:
   - keep analytics-led entry tiers,
   - make Pro/Enterprise explicit control-plane boundary.
3. `Model-C` enforcement add-on:
   - keep base tiers,
   - charge separate control-plane add-on tied to runtime gating entitlement.

Current architecture fit:
1. Best fit is `Model-B` or `Model-C` (given operational risk surface of enforcement).

### Added actions from this feedback

1. `PKG-025` Publish single-line product core narrative and dual-core boundary:
   - "post-provision optimization" vs "pre-provision enforcement" ownership model.
2. `PKG-026` Define explicit enforcement commercial boundary:
   - which tiers can call `/api/v1/enforcement/*`,
   - and whether enforcement is base-tier or add-on.
3. `PKG-027` Replace limit-led Enterprise differentiation with capability-led contract set:
   - multi-org controls, residency/compliance controls, SLA/support class, custom policy controls.
4. `PKG-028` Add free/growth anti-cannibalization checks:
   - enforce operational deltas so low tiers cannot emulate control-plane outcomes in practice.
5. `FIN-007` Run GTM economics comparison:
   - `high-volume low-ARPU` vs `lower-volume control-plane ARPU` scenarios with support/ops load assumptions.
6. `BSAFE-012` Add enforcement liability readiness gate:
   - explicit SLOs, rollback standards, incident ownership, and customer-facing operational commitments before GA enforcement marketing.

## BSL commercial model addendum (2026-02-24, source-available strategy)

This section evaluates the latest BSL feedback against repository license terms and market licensing patterns.

### Repository facts (legal/commercial posture)

1. Valdrix is licensed under BSL 1.1 with source availability, not OSI open-source licensing today.
   - Evidence: `LICENSE`, `README.md`, `docs/licensing.md`.
2. Change terms are explicit:
   - Change Date: `2029-01-12`.
   - Change License: Apache 2.0.
   - Evidence: `LICENSE`, `docs/licensing.md`.
3. Default BSL terms allow internal self-hosting but prohibit third-party competing hosted service without commercial exception.
   - Evidence: `docs/licensing.md`, `COMMERCIAL_LICENSE.md`.
4. Commercial exceptions are explicitly offered (hosted exception/OEM/partner agreements).
   - Evidence: `COMMERCIAL_LICENSE.md`.
5. Open-core boundary policy in this repo keeps control-plane logic/UI/connectors under BSL, with planned permissive SDK/spec helper repos.
   - Evidence: `docs/open_core_boundary.md`.

### External analogy fact-check (licensing model precision)

The feedback named several companies as "similar positioning." Reality is mixed:
1. HashiCorp: adopted BSL/BUSL for future releases in 2023.
   - Source: https://www.hashicorp.com/en/blog/hashicorp-adopts-business-source-license
2. Sentry: current self-hosted licensing guidance references Functional Source License for newer downloads and BSL for older versions.
   - Source: https://sentry.zendesk.com/hc/en-us/articles/33679582040219-What-terms-govern-my-use-of-Sentry
3. Elastic: licensing is not BSL; free source code portions are under SSPL/ELv2 with AGPL option.
   - Source: https://www.elastic.co/pricing/faq/licensing
4. Temporal: core server repository is MIT-licensed (not BSL/source-available restrictive).
   - Source: https://github.com/temporalio/temporal
5. CockroachDB: historical BSL usage existed, but current licensing model has changed for newer releases.
   - Source: https://www.cockroachlabs.com/docs/releases

Conclusion:
1. The strategic comparison is useful directionally.
2. Licensing analogs must be treated as category-adjacent, not all "BSL peers."

### Commercial implication for Valdrix (strict)

1. Under BSL + public repo, monetization strength comes from operated service value:
   - reliability/SLOs,
   - enterprise support/response class,
   - compliance/attestation operations,
   - contractual guarantees,
   - managed scale/security posture.
2. Pricing can remain competitive without racing to the bottom if hosted operational differentiation is explicit.
3. Current ladder (`29/79/199`) is defensible only if control-plane packaging boundaries become explicit and enforceable in runtime (`PKG-026`).
4. Enterprise differentiation should move from mostly limit-led to capability + operating-model-led (`PKG-027`).

### Recommended additions from this feedback

1. `PKG-029` Publish "Hosted vs self-hosted value matrix" tied to BSL terms:
   - what customers get only in official hosted service (SLA, managed operations, compliance evidence cadence, response-time guarantees).
2. `FIN-008` Build self-host vs hosted TCO model:
   - staffing, on-call, security/compliance maintenance, incident response, key rotation, provenance pipeline upkeep.
3. `PKG-030` Define enterprise contract pack baseline:
   - SLA tiers, support response matrix, compliance evidence scope, residency/deployment options, escalation commitments.
4. `PKG-031` Add pricing guardrail policy for early market phase:
   - avoid premature `999+` enterprise anchor until reference customers + operational proof gates are met.
5. `PKG-032` Add licensing clarity page in commercial docs:
   - "source-available under BSL" vs "open source" terminology guard to reduce procurement confusion.

## World benchmark addendum (2026-02-24, external engineering standards)

This section checks the program against current external engineering standards and platform contracts (as of 2026-02-24).

Method:
1. Primary sources only (official specs/docs/RFCs).
2. Map each benchmark to current repository status and a concrete tracking action.

### External benchmark map (2026 baseline)

| Benchmark | Primary source | Current repo status | Gap/Action |
|---|---|---|---|
| Kubernetes dynamic admission contract (`AdmissionReview` request/response, `uid` echo, webhook failure policy behavior) | https://kubernetes.io/docs/reference/access-authn-authz/extensible-admission-controllers/ | Implemented baseline (`/gate/k8s/admission/review` with native AdmissionReview schema + conformance tests) | `ECP-006` closed; keep production-hardening checks in `BSAFE-012` |
| Kubernetes admission webhook production guidance (low timeout, HA, request filtering, dependency-loop avoidance, fail-open mutate + validate final state) | https://kubernetes.io/docs/concepts/cluster-administration/admission-webhooks-good-practices/ | Partial | `ECP-006` + `BSAFE-012` should include these operational constraints explicitly |
| Built-in CEL admission policy path (ValidatingAdmissionPolicy stable in v1.30; MutatingAdmissionPolicy beta in v1.34) | https://kubernetes.io/docs/reference/access-authn-authz/validating-admission-policy/ and https://kubernetes.io/docs/reference/access-authn-authz/mutating-admission-policy/ | Partial (policy-as-code not formalized) | Keep `ECP-013`; add CEL compatibility profile for Kubernetes-native deployment path |
| Terraform run-task style preflight contract (stage payloads, callback URL, `200 OK` trigger behavior, HMAC signature header) | https://developer.hashicorp.com/terraform/enterprise/api-docs/run-tasks/run-tasks-integration | Implemented baseline preflight contract (`/gate/terraform/preflight`) with deterministic fingerprint retry semantics and continuation bindings | `ECP-007` closed; optional future hardening: native run-task callback + signature verification profile |
| Policy enforcement ordering in HCP Terraform (run tasks + Sentinel/OPA stages) | https://developer.hashicorp.com/terraform/cloud-docs/policy-enforcement/view-results | Partial-to-strong (stage-aware preflight contract added; full run-task ordering profile still doc-level) | Keep as documentation hardening item, not blocking gap |
| JWT BCP for token hardening (algorithm verification, issuer/audience validation, explicit typing, confusion-attack mitigations) | RFC 8725: https://www.rfc-editor.org/rfc/rfc8725 | Implemented baseline (explicit checklist + validator + gate wiring) | `BSAFE-013` closed with machine-verifiable checklist evidence |
| Supply-chain security benchmark (SLSA v1.2 + provenance attestations) | https://slsa.dev/spec/v1.2/ and https://slsa.dev/spec/v1.1/provenance | Implemented baseline | `BSAFE-014` closed with deploy-time attestation verification gate |
| Sigstore/cosign verification path (verify/verify-attestation with identity constraints) | https://docs.sigstore.dev/cosign/verifying/verify/ | Implemented baseline | `BSAFE-014` closed with release/deploy verification policy |
| NIST SSDF baseline for secure software development lifecycle | NIST SP 800-218: https://csrc.nist.gov/pubs/sp/800/218/final | Implemented baseline | `BSAFE-015` closed with SSDF traceability matrix + validator |
| SRE error-budget/burn-rate alerting discipline | https://sre.google/workbook/alerting-on-slos/ | Implemented baseline | `BSAFE-016` closed with burn-rate alerts + release hold policy |
| Workload identity for service-to-service auth using short-lived workload credentials (SPIFFE/SVID model) | https://spiffe.io/docs/latest/spiffe-about/overview/ | Future-looking (not explicit in enforcement path today) | Add optional future track (`BSAFE-017`) for zero-trust workload identity |

### New benchmark tracking IDs

1. `BSAFE-013` JWT BCP conformance checklist for approval/enforcement tokens:
   - algorithm allow-list pinning evidence,
   - issuer/audience/type validation matrix,
   - confusion-attack test coverage.
2. `BSAFE-014` Attestation verification gate:
   - require signature/provenance verification (`verify-attestation`) before promotion.
3. `BSAFE-015` SSDF traceability map:
   - map implemented controls/tests/docs to SP 800-218 practices.
4. `BSAFE-016` SLO burn-rate gate:
   - codify multi-window burn-rate alerts and release hold criteria.
5. `BSAFE-017` (future track) workload identity hardening:
   - evaluate SPIFFE/SVID for inter-service trust in enforcement-critical paths.

### World-class target framing (2026 now vs 2027+)

Immediate (2026 launch-hardening):
1. Close `ECP-006`, `ECP-007`, `ECP-003` (with `ECP-012` and `ECP-004` already closed).
2. Close `BSAFE-013..016` for standards-backed production confidence.
3. Keep `PKG-026` and `PKG-027` aligned so commercial boundary matches runtime guarantees.

Beyond (2027+):
1. Advance `ECP-013` to support Kubernetes-native CEL policy deployment patterns.
2. Evaluate `BSAFE-017` workload identity adoption for stronger zero-trust posture.
3. Expand external evidence cadence (quarterly standards refresh) under `PKG-020`.

## Execution mode kickoff (starting 2026-02-24)

This section defines how to run delivery now as an execution program, not as a planning thread.

### Scope lock for execution mode

Execution scope is locked to release-critical controls first.

1. P0 engineering blockers:
   - `ECP-001`, `ECP-002`, `ECP-003`, `ECP-005`.
   - `ECP-012` and `ECP-004` are closed (`DONE`, 2026-02-24) and remain under regression watch.
2. GA safety/evidence blockers:
   - `BSAFE-006`, `BSAFE-007`, `BSAFE-008`.
   - `LLM-001`, `LLM-003`, `LLM-004`.
3. New benchmark hardening items:
   - `BSAFE-013`, `BSAFE-014`, `BSAFE-015`, `BSAFE-016`.
4. Non-critical items (`P1/P2`) remain open unless they directly block one of the above.

### Workstream lanes and owner model

Run work in parallel lanes with one accountable owner per ID.

1. Lane A (`Decision/Policy`): `ECP-001`, `ECP-002`, `ECP-005`, `ECP-013`.
2. Lane B (`Approvals/Concurrency/Credits`): `ECP-003` (`ECP-004` is regression-watch only).
3. Lane C (`Safety/Evidence`): `BSAFE-006`, `BSAFE-007`, `BSAFE-008`, `BSAFE-013..016`.
4. Lane D (`LLM margin controls`): `LLM-001`, `LLM-003`, `LLM-004`.
5. Lane E (`Commercial boundary sync`): `PKG-026`, `PKG-027` (kept aligned to runtime truth, no blocking feature work).

### PR and closure protocol (binary, non-negotiable)

Each control closes only when all conditions are met.

1. One PR per control ID (or tightly-coupled pair only).
2. Mandatory tests added/updated in same PR.
3. Evidence artifact path updated in this document.
4. CI passes on required gates (`ci.yml`, TDD gate, placeholder guard, relevant unit/integration tests).
5. Tracker status updated in this file from `OPEN` to `DONE` with merge date.

### Daily operating cadence (UTC)

1. `09:00` Program standup:
   - yesterday merged controls,
   - today target controls,
   - blockers with named owner.
2. `14:00` Midday checkpoint:
   - PR readiness and test status,
   - reassign blockers older than 4 hours.
3. `18:00` Release-gate review:
   - update control board,
   - attach evidence links,
   - decide next-day critical path.

### Week-1 execution sequence (2026-02-24 to 2026-03-02)

1. Day 1-2 (`Feb 24-25`):
   - verify `ECP-004` regression coverage stays green while shipping adjacent changes,
   - verify `ECP-012` regression coverage stays green while shipping adjacent changes,
   - close `LLM-001`, `LLM-003`, `LLM-004`.
2. Day 3-4 (`Feb 26-27`):
   - close `ECP-003` and `ECP-005`,
   - close `BSAFE-006`.
3. Day 5-6 (`Feb 28-Mar 01`):
   - close `ECP-001` and `ECP-002`,
   - close `BSAFE-007`.
4. Day 7 (`Mar 02`):
   - close `BSAFE-008`,
   - close `BSAFE-013..016` where implementation already exists and only checklist/evidence formalization is required,
   - publish release evidence packet.

### Go/No-Go criteria

1. Beta Go:
   - all P0 `ECP-*` controls are `DONE`,
   - `BSAFE-006` and `LLM-001/003/004` are `DONE`,
   - evidence packet has no missing critical artifact.
2. Public GA Go:
   - Beta Go criteria plus `BSAFE-007`, `BSAFE-008`, `BSAFE-013..016` are `DONE`,
   - commercial claims remain aligned to runtime gates (`PKG-026`, `PKG-027`).

## Execution update (2026-02-25): reservation reconciliation idempotency hardening

Objective:
1. Make manual reservation reconciliation safe for retrying callers (network retries, client retries) without double-settlement side effects.
2. Keep strict conflict semantics when the same idempotency key is replayed with a different payload.

Implemented:
1. Added `idempotency_key` to manual reservation reconcile request schema.
   - `app/modules/enforcement/api/v1/schemas.py` (`ReservationReconcileRequest`).
2. Added API-level idempotency key resolution for manual reconcile (`Idempotency-Key` header takes precedence over body key) with strict length validation.
   - `app/modules/enforcement/api/v1/reservations.py` (`_resolve_idempotency_key`).
3. Added service-level idempotent replay path for completed reconciliations:
   - if reservation is already inactive and the same idempotency key is replayed with matching payload, return prior reconciliation result (`200` path) instead of `409`.
   - if same key is replayed with mismatched payload (`actual_monthly_delta_usd` or `notes`), reject with `409`.
   - persist `idempotency_key` inside `reservation_reconciliation` payload for deterministic replay binding.
   - `app/modules/enforcement/domain/service.py` (`_build_reservation_reconciliation_idempotent_replay`, `reconcile_reservation`).

Test coverage added:
1. Service tests:
   - `test_reconcile_reservation_idempotent_replay_with_same_key`
   - `test_reconcile_reservation_idempotent_replay_rejects_payload_mismatch`
   - File: `tests/unit/enforcement/test_enforcement_service.py`.
2. API tests:
   - `test_reconcile_reservation_endpoint_idempotent_replay_header`
   - `test_reconcile_reservation_rejects_invalid_idempotency_key_header`
   - File: `tests/unit/enforcement/test_enforcement_api.py`.

Validation:
1. `uv run ruff check app/modules/enforcement/api/v1/reservations.py app/modules/enforcement/api/v1/schemas.py app/modules/enforcement/domain/service.py tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_api.py` -> pass.
2. `uv run mypy app/modules/enforcement/api/v1/reservations.py app/modules/enforcement/api/v1/schemas.py app/modules/enforcement/domain/service.py tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_api.py` -> pass.
3. `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_api.py -k "reconcile_reservation or reconcile_overdue or reconciliation_exceptions"` -> `17 passed, 86 deselected`.

## Execution update (2026-02-25): reconciliation concurrency race hardening

Objective:
1. Prove and harden reconciliation behavior under parallel retries from separate DB sessions.
2. Ensure no double-settlement of credit allocations under concurrent reconcile attempts.

Implemented:
1. Added atomic reservation claim in manual reconcile path:
   - `UPDATE ... WHERE reservation_active = true` guard before settlement.
   - on claim miss, execute replay path (same key + same payload) or return conflict.
   - file: `app/modules/enforcement/domain/service.py` (`reconcile_reservation`).
2. Added API edge coverage for idempotency contract:
   - body-only idempotent replay.
   - header key precedence over body key.
   - file: `tests/unit/enforcement/test_enforcement_api.py`.
3. Added multi-session concurrency tests for reconcile race conditions:
   - same key + same payload -> single effective settlement, stable replay.
   - same key + mismatched payload -> one success + one `409` conflict.
   - explicit credit allocation/grant balance assertions ensure no double consumption/release.
   - file: `tests/unit/enforcement/test_enforcement_property_and_concurrency.py`.

Validation:
1. `uv run ruff check app/modules/enforcement/domain/service.py tests/unit/enforcement/test_enforcement_property_and_concurrency.py tests/unit/enforcement/test_enforcement_api.py tests/unit/enforcement/test_enforcement_service.py` -> pass.
2. `uv run mypy app/modules/enforcement/domain/service.py tests/unit/enforcement/test_enforcement_property_and_concurrency.py tests/unit/enforcement/test_enforcement_api.py tests/unit/enforcement/test_enforcement_service.py` -> pass.
3. `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_property_and_concurrency.py tests/unit/enforcement/test_enforcement_api.py -k "concurrency_reconcile_same_idempotency_key or reconcile_reservation_endpoint_idempotent_replay_body_key or reconcile_reservation_header_idempotency_key_precedence"` -> `4 passed`.
4. `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_api.py tests/unit/enforcement/test_enforcement_property_and_concurrency.py tests/unit/enforcement/test_reconciliation_worker.py` -> `115 passed`.

## Execution update (2026-02-25): ledger coverage for reconciliation + overdue claim serialization

Objective:
1. Ensure reconciliation state transitions are auditable in the immutable decision ledger.
2. Harden overdue reconciliation against concurrent worker double-processing.

Implemented:
1. Manual reconcile now appends a decision ledger snapshot (with approval linkage when present):
   - `app/modules/enforcement/domain/service.py` (`reconcile_reservation`).
2. Overdue reconcile now:
   - atomically claims each reservation row (`UPDATE ... WHERE reservation_active = true`) before settlement,
   - skips rows not claimed by current worker,
   - appends ledger snapshots for processed decisions with approval linkage,
   - reports metrics/counts based on actually processed decisions.
   - `app/modules/enforcement/domain/service.py` (`reconcile_overdue_reservations`).
3. Added service-level assertions for ledger snapshots after reconciliation:
   - `tests/unit/enforcement/test_enforcement_service.py`.
4. Added concurrency property test for overdue reconciliation claim correctness:
   - parallel overdue reconciliation calls process a reservation once (single released count and amount),
   - no duplicate decision IDs in summaries.
   - `tests/unit/enforcement/test_enforcement_property_and_concurrency.py`.

Validation:
1. `uv run ruff check app/modules/enforcement/domain/service.py tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_property_and_concurrency.py` -> pass.
2. `uv run mypy app/modules/enforcement/domain/service.py tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_property_and_concurrency.py` -> pass.
3. `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_property_and_concurrency.py -k "reconcile_reservation_releases_and_records_drift or reconcile_overdue_reservations_releases_only_stale or concurrency_reconcile_overdue_claims_each_reservation_once or concurrency_reconcile_same_idempotency_key"` -> `5 passed`.
4. `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_api.py tests/unit/enforcement/test_enforcement_property_and_concurrency.py tests/unit/enforcement/test_reconciliation_worker.py` -> `116 passed`.

## Execution update (2026-02-25): overdue reconciliation queue semantics + replay audit assertions

Objective:
1. Improve overdue reconciliation throughput under parallel workers by avoiding lock-wait contention.
2. Strengthen audit assurances: idempotent replay must not create duplicate ledger snapshots.

Implemented:
1. Updated overdue reservation selection to use non-blocking lock semantics:
   - `.with_for_update(skip_locked=True)` for queue-like worker behavior.
   - `app/modules/enforcement/domain/service.py` (`reconcile_overdue_reservations`).
2. Added test asserting idempotent manual replay does not append extra ledger rows:
   - `tests/unit/enforcement/test_enforcement_service.py` (`test_reconcile_reservation_idempotent_replay_with_same_key`).
3. Added metric correctness test for overdue reconciliation processed count:
   - ensures `ENFORCEMENT_RESERVATION_RECONCILIATIONS_TOTAL(trigger=auto,status=auto_release)` increments by processed rows.
   - `tests/unit/enforcement/test_enforcement_service.py` (`test_reconcile_overdue_reservations_records_processed_count_metric`).
4. Extended overdue concurrency test to assert single overdue ledger append across parallel runners:
   - `tests/unit/enforcement/test_enforcement_property_and_concurrency.py` (`test_concurrency_reconcile_overdue_claims_each_reservation_once`).

Validation:
1. `uv run ruff check app/modules/enforcement/domain/service.py tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_property_and_concurrency.py` -> pass.
2. `uv run mypy app/modules/enforcement/domain/service.py tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_property_and_concurrency.py` -> pass.
3. `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_property_and_concurrency.py -k "reconcile_reservation_idempotent_replay_with_same_key or reconcile_overdue_reservations_records_processed_count_metric or concurrency_reconcile_overdue_claims_each_reservation_once"` -> `3 passed`.
4. `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_api.py tests/unit/enforcement/test_enforcement_property_and_concurrency.py tests/unit/enforcement/test_reconciliation_worker.py` -> `117 passed`.

## Execution update (2026-02-25): explicit rollback safety on reconciliation failure paths

Objective:
1. Ensure no partial in-transaction mutation leaks when credit settlement fails during manual/overdue reconciliation.
2. Keep session state clean and deterministic for callers after reconciliation exceptions.

Implemented:
1. Added explicit rollback wrappers in reconciliation execution paths:
   - `reconcile_reservation`: wraps settlement + payload + ledger append + commit in `try/except` and calls `await self.db.rollback()` on failure.
   - `reconcile_overdue_reservations`: wraps per-decision processing + ledger append with rollback on failure.
   - file: `app/modules/enforcement/domain/service.py`.
2. Added failure-path tests that intentionally remove credit reservation allocation rows before reconcile to force settlement failure (`409`) and assert state remains unchanged:
   - manual reconcile rollback test,
   - overdue reconcile rollback test.
   - file: `tests/unit/enforcement/test_enforcement_service.py`.

Validation:
1. `uv run ruff check app/modules/enforcement/domain/service.py tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_property_and_concurrency.py` -> pass.
2. `uv run mypy app/modules/enforcement/domain/service.py tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_property_and_concurrency.py` -> pass.
3. `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_service.py -k "rolls_back_on_credit_settlement_failure or reconcile_reservation_idempotent_replay_with_same_key or reconcile_overdue_reservations_records_processed_count_metric"` -> `4 passed`.
4. `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_api.py tests/unit/enforcement/test_enforcement_property_and_concurrency.py tests/unit/enforcement/test_reconciliation_worker.py` -> `119 passed`.

## Feedback sanity-check closure (2026-02-25)

Source feedback items reviewed:
1. lock contention observability + reason-code clarity
2. computed-context snapshot consistency
3. AdmissionReview failure-policy alignment
4. policy-document migration/export consistency
5. end-to-end Terraform preflight/consume documentation

### Fact-based disposition

| Item | Need? | Status | Evidence | Action |
|---|---|---|---|---|
| Lock contention behavior + observability (`gate_lock_contended` / `gate_lock_timeout`) | Yes | Addressed (code + tests) | `app/shared/core/ops_metrics.py`, `app/modules/enforcement/domain/service.py`, `app/modules/enforcement/api/v1/enforcement.py`, `tests/unit/enforcement/test_enforcement_service_helpers.py`, `tests/unit/enforcement/test_enforcement_api.py` | Closed for this sanity check; monitor reason/metric distribution in staging. |
| Computed-context snapshot metadata stability across runs | Yes | Addressed (test added) | `tests/unit/enforcement/test_enforcement_service.py` (`test_evaluate_gate_computed_context_snapshot_metadata_stable_across_runs`) | Closed for this sanity check. |
| AdmissionReview failure policy alignment (cluster webhook `failurePolicy`) | Yes | Partial (documentation-level complete, deployment template still open) | `docs/runbooks/enforcement_preprovision_integrations.md` (explicit `failurePolicy` guidance + webhook example) | Add deployable `ValidatingWebhookConfiguration` templates and environment defaults (`ECP-016`). |
| Policy-document migration completeness in export story | Yes | Partial (policy contract/hash authoritative in service/API; export lineage still incomplete) | `app/modules/enforcement/domain/service.py` (materialize + canonical hash), policy tests in `tests/unit/enforcement/test_enforcement_service.py` and `tests/unit/enforcement/test_enforcement_api.py` | Add policy-hash lineage to export evidence (`ECP-015`) so exported decisions can be tied to policy hash at decision time. |
| End-to-end docs for Terraform preflight -> approval -> consume | Yes | Addressed (runbook added) | `docs/runbooks/enforcement_preprovision_integrations.md` | Keep examples synced with API contract changes. |

### New follow-up gaps opened

1. `ECP-015` (P1): Policy hash lineage in export artifacts.
   - Requirement: export evidence must bind decision records to effective policy hash (not only policy version).
   - Current gap: exports include decisions/approvals parity but do not include policy-hash lineage per decision window.
2. `ECP-016` (P1): K8s webhook deployment contract pack.
   - Requirement: publish production-ready `ValidatingWebhookConfiguration` templates with explicit `failurePolicy`, timeout, and rollout mode guidance per environment.
   - Current gap: API supports AdmissionReview; repo lacks deployment manifests/templates for cluster operators.

Validation for this sanity-check closure:
1. `uv run ruff check app/modules/enforcement/api/v1/enforcement.py app/modules/enforcement/domain/service.py app/shared/core/ops_metrics.py tests/unit/enforcement/test_enforcement_api.py tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_service_helpers.py` -> pass.
2. `uv run mypy app/modules/enforcement/api/v1/enforcement.py app/modules/enforcement/domain/service.py tests/unit/enforcement/test_enforcement_api.py tests/unit/enforcement/test_enforcement_service_helpers.py` -> pass.
3. `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_service_helpers.py tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_api.py -k "acquire_gate_evaluation_lock or computed_context_snapshot_metadata_stable_across_runs or lock_failures_route_to_failsafe_with_lock_reason_codes"` -> `5 passed`.
4. `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_api.py tests/unit/enforcement/test_enforcement_property_and_concurrency.py tests/unit/enforcement/test_reconciliation_worker.py` -> `122 passed`.

## Execution update (2026-02-25): policy-hash export lineage and webhook deployment profiles

Objective:
1. Close `ECP-015` by binding export evidence to decision-time policy hash lineage.
2. Close `ECP-016` by shipping deployable webhook configuration profiles with explicit failure-policy controls.

Implemented:
1. Added decision-time policy lineage fields on decision + immutable ledger rows:
   - `policy_document_schema_version`
   - `policy_document_sha256`
   - Files:
     - `app/models/enforcement.py`
     - `app/modules/enforcement/domain/service.py` (gate + fail-safe creation paths and ledger append path)
     - `migrations/versions/m9n0p1q2r3s4_add_enforcement_policy_hash_lineage_fields.py`
2. Extended export pipeline with policy lineage integrity:
   - export bundle now computes deterministic `policy_lineage` and `policy_lineage_sha256`,
   - signed manifest includes policy lineage payload and hash,
   - parity response includes policy lineage summary (`policy_lineage_sha256`, `policy_lineage_entries`),
   - decisions CSV includes policy lineage columns.
   - Files:
     - `app/modules/enforcement/domain/service.py`
     - `app/modules/enforcement/api/v1/schemas.py`
     - `app/modules/enforcement/api/v1/exports.py`
3. Extended ledger API response with policy lineage fields:
   - `policy_document_schema_version`
   - `policy_document_sha256`
   - File: `app/modules/enforcement/api/v1/ledger.py`
4. Added deployable helm template for Kubernetes validating webhook with explicit failure policy profile:
   - File: `helm/valdrix/templates/enforcement-validating-webhook.yaml`
   - Values contract: `helm/valdrix/values.yaml` (`enforcementWebhook.*`)
   - Operational runbook updated:
     - `docs/runbooks/enforcement_preprovision_integrations.md`

Status closure:
1. `ECP-015`: `DONE` (policy-hash lineage persisted at decision time and included in export parity/manifest evidence).
2. `ECP-016`: `DONE` (deployable webhook template + explicit failure-policy profiles via chart values and runbook contract).

Validation:
1. `uv run ruff check app/models/enforcement.py app/modules/enforcement/domain/service.py app/modules/enforcement/api/v1/schemas.py app/modules/enforcement/api/v1/exports.py app/modules/enforcement/api/v1/ledger.py tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_api.py`
2. `uv run mypy app/modules/enforcement/domain/service.py app/modules/enforcement/api/v1/schemas.py app/modules/enforcement/api/v1/exports.py app/modules/enforcement/api/v1/ledger.py`
3. `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_api.py -k "build_export_bundle_reconciles_counts_and_is_deterministic or enforcement_export_parity_and_archive_endpoints or decision_ledger_endpoint_admin or evaluate_gate_computed_context_populates_decision_and_ledger"`
4. `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_api.py tests/unit/enforcement/test_enforcement_property_and_concurrency.py tests/unit/enforcement/test_reconciliation_worker.py`

External standard alignment used for implementation choices:
1. Kubernetes admission webhook contract and failure policy semantics (`Ignore` vs `Fail`):
   - https://kubernetes.io/docs/reference/access-authn-authz/extensible-admission-controllers/
   - https://kubernetes.io/docs/concepts/cluster-administration/admission-webhooks-good-practices/
2. Policy decision logging lineage concept (policy bundle/revision provenance in decision logs):
   - https://www.openpolicyagent.org/docs/latest/management-decision-logs/

## Execution update (2026-02-25): feedback sanity-check hardening closeout

Objective:
1. Convert remaining feedback-only concerns into binary evidence artifacts.
2. Ensure operators can distinguish policy denials from infrastructure lock/contention problems.
3. Prove policy hash lineage consistency across policy evolution and exports.

Implemented:
1. Added lock contention alerting and dashboard coverage:
   - Alert: `ValdrixEnforcementGateLockContentionSpike` (contention/timeout/not-acquired lock events).
   - Dashboard panel: `Gate Lock Contention Events (10m increase)`.
   - Files:
     - `ops/alerts/enforcement_control_plane_rules.yml`
     - `ops/dashboards/enforcement_control_plane_overview.json`
     - `tests/unit/ops/test_enforcement_observability_pack.py`
     - `docs/ops/alert-evidence-2026-02-25.md`
2. Added service-level lock-contention reason-code test on rowcount=0 lock path:
   - verifies `409` + `gate_lock_contended` + lock event telemetry (`acquired`, `not_acquired`).
   - File: `tests/unit/enforcement/test_enforcement_service_helpers.py`
3. Added policy-lineage consistency test across multiple policy updates:
   - verifies policy-document remains authoritative,
   - verifies decisions preserve decision-time policy hash/version,
   - verifies export lineage includes both hashes with exact counts.
   - File: `tests/unit/enforcement/test_enforcement_service.py`
4. Updated pre-provision runbook operator checks with explicit lock contention metric and policy-lineage export verification:
   - File: `docs/runbooks/enforcement_preprovision_integrations.md`

Status closure:
1. Feedback item “lock contention behavior + observability” -> fully evidenced (metrics, reason codes, alert rule, dashboard, tests).
2. Feedback item “policy document migration completeness/export consistency” -> fully evidenced for multi-update lineage and export binding.
3. Feedback item “AdmissionReview failure-policy alignment” -> deployment template + runbook profile guidance already in place (`ECP-016`), now paired with operator checklist.

Validation:
1. `uv run ruff check tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_service_helpers.py tests/unit/ops/test_enforcement_observability_pack.py`
2. `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_service_helpers.py tests/unit/ops/test_enforcement_observability_pack.py -k "export_policy_lineage_remains_consistent_across_policy_updates or acquire_gate_evaluation_lock_rowcount_zero_raises_contended_reason or enforcement_alert_rules_pack_exists_and_covers_required_signals or enforcement_dashboard_pack_is_valid_json_and_references_required_metrics or enforcement_observability_evidence_doc_exists"`

## Execution update (2026-02-25): computed-context lineage export hardening

Objective:
1. Make computed decision snapshot boundaries first-class in export evidence, not only embedded in response payload JSON.
2. Add parity-level integrity signals for computed-context lineage.

Implemented:
1. Extended export bundle and signed manifest with deterministic computed-context lineage:
   - `computed_context_lineage_sha256`
   - `computed_context_lineage` (context window/signature grouping + decision counts)
   - Files:
     - `app/modules/enforcement/domain/service.py`
2. Extended export parity API response:
   - `computed_context_lineage_sha256`
   - `computed_context_lineage_entries`
   - Files:
     - `app/modules/enforcement/api/v1/schemas.py`
     - `app/modules/enforcement/api/v1/exports.py`
3. Extended decisions CSV with explicit computed-context snapshot columns:
   - `computed_context_version`
   - `computed_context_generated_at`
   - `computed_context_month_start`
   - `computed_context_month_end`
   - `computed_context_month_elapsed_days`
   - `computed_context_month_total_days`
   - `computed_context_observed_cost_days`
   - `computed_context_latest_cost_date`
   - `computed_context_data_source_mode`
4. Added/updated tests for deterministic lineage and API/archive contract:
   - `tests/unit/enforcement/test_enforcement_service.py`
   - `tests/unit/enforcement/test_enforcement_api.py`

Validation:
1. `uv run ruff check app/modules/enforcement/domain/service.py app/modules/enforcement/api/v1/schemas.py app/modules/enforcement/api/v1/exports.py tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_api.py`
2. `uv run mypy app/modules/enforcement/domain/service.py app/modules/enforcement/api/v1/schemas.py app/modules/enforcement/api/v1/exports.py`
3. `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_service.py tests/unit/enforcement/test_enforcement_api.py -k "build_export_bundle_reconciles_counts_and_is_deterministic or export_policy_lineage_remains_consistent_across_policy_updates or enforcement_export_parity_and_archive_endpoints"`

## Execution update (2026-02-25): Helm webhook deployment contract hardening

Objective:
1. Make Kubernetes webhook rollout safety rules non-bypassable at chart validation/render time.
2. Add automated tests for schema and rendered webhook contract.

Implemented:
1. Added strict Helm values schema for `enforcementWebhook`:
   - validates allowed enums and structural fields,
   - enforces `admissionReviewVersions` contains `v1`,
   - enforces `failurePolicy=Fail -> timeoutSeconds <= 5`,
   - enforces cert-manager injector secret requirement,
   - disallows mixed CA sources (`certManager.enabled` + `caBundle`).
   - File: `helm/valdrix/values.schema.json`
2. Hardened webhook template with explicit render-time guardrails (`fail`):
   - cert-manager secret required when enabled,
   - CA source conflict detection,
   - fail-closed timeout guard.
   - File: `helm/valdrix/templates/enforcement-validating-webhook.yaml`
3. Hardened default selector posture:
   - default namespace exclusion for control-plane namespaces.
   - File: `helm/valdrix/values.yaml`
4. Added chart-level tests (schema + helm render contract/failure paths):
   - File: `tests/unit/ops/test_enforcement_webhook_helm_contract.py`
5. Updated integration runbook with enforced chart guardrails.
   - File: `docs/runbooks/enforcement_preprovision_integrations.md`

Validation:
1. `helm lint helm/valdrix`
2. `helm template valdrix-dev helm/valdrix`
3. `uv run ruff check tests/unit/ops/test_enforcement_webhook_helm_contract.py`
4. `uv run pytest --no-cov -q tests/unit/ops/test_enforcement_webhook_helm_contract.py`

## Execution update (2026-02-25): fail-closed webhook HA gate + selector schema hardening

Objective:
1. Prevent unsafe fail-closed admission deployments that run with single API replica.
2. Enforce valid label-selector semantics in webhook selector contracts.

Implemented:
1. Added fail-closed HA guardrails in webhook template:
   - `failurePolicy=Fail` now requires:
     - `autoscaling.enabled=true` with `autoscaling.minReplicas >= 2`, or
     - `autoscaling.enabled=false` with `replicaCount >= 2`.
   - File: `helm/valdrix/templates/enforcement-validating-webhook.yaml`
2. Extended Helm values schema with root-level HA constraints:
   - cross-field validation for fail-closed + replica policy,
   - `replicaCount` and `autoscaling.minReplicas` minimums.
   - File: `helm/valdrix/values.schema.json`
3. Tightened `LabelSelectorRequirement` schema semantics:
   - `operator in {In, NotIn}` requires non-empty `values`,
   - `operator in {Exists, DoesNotExist}` disallows non-empty `values`.
   - File: `helm/valdrix/values.schema.json`
4. Expanded webhook chart tests for fail-closed HA pass/fail paths:
   - fail when fail-closed runs with single replica and autoscaling disabled,
   - pass when fail-closed runs with manual `replicaCount>=2`,
   - pass when fail-closed runs with HPA `minReplicas>=2`.
   - File: `tests/unit/ops/test_enforcement_webhook_helm_contract.py`
5. Updated chart/runbook comments to surface HA requirement explicitly.
   - Files:
     - `helm/valdrix/values.yaml`
     - `docs/runbooks/enforcement_preprovision_integrations.md`

Validation:
1. `helm lint helm/valdrix`
2. `helm template valdrix-dev helm/valdrix`
3. `uv run ruff check tests/unit/ops/test_enforcement_webhook_helm_contract.py`
4. `uv run pytest --no-cov -q tests/unit/ops/test_enforcement_webhook_helm_contract.py`
5. `uv run pytest --no-cov -q tests/unit/ops`

## Execution update (2026-03-01): VAL-ADAPT-002+ breaking wrapper-seam cleanup completed

Objective:
1. Close the remaining compatibility seam in the license adapter decomposition track.
2. Remove legacy private wrapper indirection and switch to direct dispatch/runtime interfaces.

Implemented:
1. Removed compatibility mixin layer:
   - deleted `app/shared/adapters/license_native_compat.py`.
   - dropped `LicenseNativeCompatMixin` inheritance from `app/shared/adapters/license.py`.
2. Removed legacy private wrapper method seam from `LicenseAdapter`:
   - verify wrappers (`_verify_*`, `_verify_native_vendor`),
   - stream wrappers (`_stream_google_workspace_license_costs`, `_stream_microsoft_365_license_costs`),
   - revoke wrappers (`_revoke_*`),
   - activity wrappers (`_list_*_activity`).
3. Upgraded native dispatch to direct function maps:
   - `app/shared/adapters/license_native_dispatch.py` now maps native vendors directly to vendor-op functions.
   - removed method-name string dispatch and runtime `getattr` indirection.
4. Updated all impacted tests to assert direct dispatch behavior and vendor-op integration.
5. This update supersedes earlier interim notes that wrappers were temporarily preserved during staged decomposition.

Validation:
1. `uv run ruff check app/shared/adapters/license.py app/shared/adapters/license_native_dispatch.py tests/unit/shared/adapters/test_license_native_dispatch.py tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/services/adapters/test_license_verification_stream_branches.py tests/unit/services/adapters/test_cloud_plus_adapters.py`
2. `uv run mypy app/shared/adapters/license.py app/shared/adapters/license_native_dispatch.py --hide-error-context --no-error-summary`
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/shared/adapters/test_license_native_dispatch.py tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/services/adapters/test_license_verification_stream_branches.py tests/unit/services/adapters/test_cloud_plus_adapters.py tests/unit/shared/adapters/test_google_workspace.py`
4. `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py` -> `883 passed`; all preflight/sanity gates and coverage thresholds satisfied.

Post-closure sanity (mandatory release checks):
1. Concurrency: dispatch tables are immutable module-level mappings; no mutable wrapper state remains.
2. Observability: error/warning paths and `last_error` propagation remain intact on public adapter flows.
3. Deterministic replay: native vendor routing is table-driven and deterministic.
4. Snapshot stability/export integrity: public adapter output schemas are unchanged; only internal call topology changed.
5. Failure modes/misconfiguration: unsupported vendor/revoke paths remain explicit fail-closed behavior.

## Execution update (2026-03-01): Cloud+ native-dispatch hardening follow-up (SaaS/Platform/Hybrid)

Objective:
1. Remove remaining branch-heavy native vendor verify/stream routing patterns from Cloud+ adapters.
2. Keep runtime behavior unchanged while reducing adapter control-flow concentration risk.

Implemented:
1. Refactored `app/shared/adapters/saas.py` to table-driven native handler resolution:
   - `_resolve_native_verify_handler()`
   - `_resolve_native_stream_handler()`
2. Refactored `app/shared/adapters/platform.py` to table-driven native handler resolution:
   - `_resolve_native_verify_handler()`
   - `_resolve_native_stream_handler()`
3. Refactored `app/shared/adapters/hybrid.py` to table-driven native handler resolution:
   - `_resolve_native_verify_handler()`
   - `_resolve_native_stream_handler()`
4. Added/expanded branch tests for handler-map contracts and fallback behavior:
   - `tests/unit/shared/adapters/test_saas_adapter_branch_paths.py`
   - `tests/unit/services/adapters/test_adapter_helper_branches.py`
   - existing Cloud+ regression coverage in `tests/unit/services/adapters/test_cloud_plus_adapters.py`.
5. Removed stub-grade discovery behavior for Cloud+ adapters:
   - added deterministic projection utility `discover_resources_from_cost_rows()` in `app/shared/adapters/resource_usage_projection.py`,
   - wired `discover_resources()` in SaaS/Platform/Hybrid adapters to recent cost-row projection with fail-closed error handling.
6. Added discovery projection tests:
   - `tests/unit/shared/adapters/test_resource_usage_projection.py`,
   - expanded `tests/unit/services/adapters/test_cloud_plus_adapters.py`.

Validation:
1. `uv run ruff check app/shared/adapters/saas.py app/shared/adapters/platform.py app/shared/adapters/hybrid.py app/shared/adapters/resource_usage_projection.py tests/unit/shared/adapters/test_saas_adapter_branch_paths.py tests/unit/services/adapters/test_adapter_helper_branches.py tests/unit/services/adapters/test_cloud_plus_adapters.py tests/unit/shared/adapters/test_resource_usage_projection.py`
2. `uv run mypy app/shared/adapters/saas.py app/shared/adapters/platform.py app/shared/adapters/hybrid.py app/shared/adapters/resource_usage_projection.py --hide-error-context --no-error-summary`
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/shared/adapters/test_resource_usage_projection.py tests/unit/shared/adapters/test_saas_adapter_branch_paths.py tests/unit/services/adapters/test_adapter_helper_branches.py tests/unit/services/adapters/test_cloud_plus_adapters.py` -> `88 passed`.
4. `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py` -> `883 passed`; all preflight/sanity gates and coverage thresholds satisfied.

Post-closure sanity (mandatory release checks):
1. Concurrency: no shared mutable dispatch state introduced; handler maps are local immutable dictionaries.
2. Observability: native verify/stream failures still emit structured vendor/error logs and preserve `last_error`.
3. Deterministic replay: vendor-path selection is now table-driven for SaaS/Platform/Hybrid native connectors.
4. Snapshot stability/export integrity: discovery payload shape is deterministic/sorted and cost row payload contracts remain unchanged; fallback-to-feed behavior preserved.
5. Failure modes/misconfiguration: unsupported vendor/auth mode checks remain explicit fail-closed behavior.

## Execution update (2026-02-28): VAL-ADAPT-002+ vendor-module split hardening pass

Objective:
1. Continue architecture hardening by reducing adapter concentration risk in license vendor operations.
2. Preserve existing runtime behavior while making vendor logic easier to test, reason about, and secure.

Implemented:
1. Split vendor operation logic into dedicated modules:
   - `app/shared/adapters/license_vendor_verify.py`
   - `app/shared/adapters/license_vendor_google.py`
   - `app/shared/adapters/license_vendor_microsoft.py`
   - `app/shared/adapters/license_vendor_github.py`
   - `app/shared/adapters/license_vendor_zoom.py`
   - `app/shared/adapters/license_vendor_slack.py`
   - `app/shared/adapters/license_vendor_salesforce.py`
2. Added shared runtime typing contract:
   - `app/shared/adapters/license_vendor_types.py`
3. Kept `app/shared/adapters/license_vendor_ops.py` as compatibility facade and made its public API explicit with `__all__` so static typing enforces exported symbols.
4. Kept `license.py` behavior and wrapper seams intact while continuing decomposition.

Validation:
1. `uv run ruff check app/shared/adapters/license.py app/shared/adapters/license_feed_ops.py app/shared/adapters/license_vendor_registry.py app/shared/adapters/license_vendor_ops.py app/shared/adapters/license_vendor_types.py app/shared/adapters/license_vendor_verify.py app/shared/adapters/license_vendor_google.py app/shared/adapters/license_vendor_microsoft.py app/shared/adapters/license_vendor_github.py app/shared/adapters/license_vendor_zoom.py app/shared/adapters/license_vendor_slack.py app/shared/adapters/license_vendor_salesforce.py tests/unit/shared/adapters/test_license_feed_ops.py tests/unit/shared/adapters/test_license_vendor_registry.py`
2. `uv run mypy app/shared/adapters/license.py app/shared/adapters/license_feed_ops.py app/shared/adapters/license_vendor_registry.py app/shared/adapters/license_vendor_ops.py app/shared/adapters/license_vendor_types.py app/shared/adapters/license_vendor_verify.py app/shared/adapters/license_vendor_google.py app/shared/adapters/license_vendor_microsoft.py app/shared/adapters/license_vendor_github.py app/shared/adapters/license_vendor_zoom.py app/shared/adapters/license_vendor_slack.py app/shared/adapters/license_vendor_salesforce.py --hide-error-context --no-error-summary`
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/shared/adapters/test_license_feed_ops.py tests/unit/shared/adapters/test_license_vendor_registry.py tests/unit/services/adapters/test_adapter_helper_branches.py tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/services/adapters/test_license_verification_stream_branches.py tests/unit/services/adapters/test_cloud_plus_adapters.py tests/unit/shared/adapters/test_google_workspace.py`
4. Result: `123 passed in 8.03s`.

Post-closure sanity (mandatory release checks):
1. Concurrency: no shared mutable state introduced; dispatch remains module-level immutable mappings.
2. Observability: error semantics preserved through existing adapter exception paths.
3. Deterministic replay: extracted helper behavior remains deterministic and test-covered.
4. Snapshot stability/export integrity: stream/revoke/activity contracts unchanged at consumer boundaries.
5. Failure modes/misconfiguration: unsupported vendor selection remains explicit fail-closed behavior.

## Execution update (2026-02-28): full enterprise gate rerun after VAL-ADAPT-002+ split

Validation:
1. `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py`
2. Result: passed (`876 passed`, no runtime warnings, no gate failure).
3. Coverage gates remained satisfied:
   - enforcement subset `99%` (threshold `>=95%`),
   - LLM budget/provider subset `100%` (threshold `>=90%`),
   - analytics subset (`analyzer.py` + `costs.py`) `100%` (threshold `>=99%`).

## Execution update (2026-02-28): VAL-ADAPT-002+ license resource-surface hardening

Objective:
1. Remove remaining stub-grade behavior from license adapter resource surfaces.
2. Make discovery/usage behavior deterministic, testable, and fail-closed under connector errors/misconfiguration.

Implemented:
1. Added `app/shared/adapters/license_resource_ops.py`:
   - resource/service alias contracts,
   - deterministic identity normalization and ordered output shaping,
   - explicit usage row construction from activity records.
2. Upgraded `app/shared/adapters/license.py`:
   - `discover_resources()` now returns license-seat resources for supported aliases from `list_users_activity()`.
   - `get_resource_usage()` now returns normalized seat usage rows with safe default-price/currency handling.
   - connector/activity failures now log context and fail closed with empty results + `last_error`.
3. Added comprehensive branch coverage:
   - `tests/unit/shared/adapters/test_license_resource_ops.py`
   - expanded `tests/unit/services/adapters/test_license_activity_and_revoke.py`.

Validation:
1. `uv run ruff check app/shared/adapters/license.py app/shared/adapters/license_resource_ops.py tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/shared/adapters/test_license_resource_ops.py`
2. `uv run mypy app/shared/adapters/license.py app/shared/adapters/license_resource_ops.py --hide-error-context --no-error-summary`
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/shared/adapters/test_license_resource_ops.py tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/services/adapters/test_cloud_plus_adapters.py tests/unit/shared/adapters/test_license_feed_ops.py tests/unit/shared/adapters/test_license_vendor_registry.py`
4. Result: `69 passed`.
5. `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py` -> `876 passed` with all gate thresholds satisfied.

Post-closure sanity (mandatory release checks):
1. Concurrency: no mutable shared state introduced; shaping logic is stateless/pure.
2. Observability: failure paths now emit structured warning logs and preserve `last_error`.
3. Deterministic replay: outputs are canonicalized and sorted by resource identity.
4. Snapshot stability/export integrity: usage row schema is explicit and stable.
5. Failure modes/misconfiguration: unsupported services/types fail closed; negative configured seat prices are clamped.

## Execution update (2026-02-27): binary release-artifact checklist hardening

Objective:
1. Remove remaining ambiguity in release evidence artifacts by making template + checklist contract machine-verifiable.
2. Ensure post-closure sanity validation fails when artifact-template baseline or checklist wiring drifts.
3. Keep one-pass gate execution deterministic with explicit artifact paths and capture format.

Implemented:
1. Added release artifact template pack:
   - `docs/ops/evidence/README.md`
   - `docs/ops/evidence/enforcement_stress_artifact_TEMPLATE.json`
   - `docs/ops/evidence/enforcement_failure_injection_TEMPLATE.json`
   - `docs/evidence/ci-green-template.md`
2. Hardened post-closure sanity validator to enforce artifact-template + checklist contract:
   - validator now requires template files/tokens and gap-register checklist tokens:
     - `Binary Artifact Closure Checklist (release packet)`
     - `docs/ops/evidence/enforcement_stress_artifact_YYYY-MM-DD.json`
     - `docs/ops/evidence/enforcement_failure_injection_YYYY-MM-DD.json`
     - `docs/evidence/ci-green-YYYY-MM-DD.md`
   - file: `scripts/verify_enforcement_post_closure_sanity.py`
3. Expanded post-closure sanity tests for the artifact-template contract:
   - file: `tests/unit/ops/test_verify_enforcement_post_closure_sanity.py`
4. Added dedicated template-pack tests and wired them into enterprise gate target set:
   - file: `tests/unit/ops/test_release_artifact_templates_pack.py`
   - gate target wiring: `scripts/run_enterprise_tdd_gate.py`
5. Updated evidence protocol docs to reference template seeds:
   - `docs/ops/enforcement_stress_evidence_2026-02-25.md`
   - `docs/ops/enforcement_failure_injection_matrix_2026-02-25.md`
6. Added explicit binary checklist section in this register:
   - `Binary Artifact Closure Checklist (release packet)` under evidence manifest.

Result:
1. Artifact baseline is now binary and test-backed (no narrative-only closure for release packet templates/checklist).
2. Enterprise gate remains green with this stricter contract:
   - `793 passed in 548.37s`
   - enforcement subset coverage: `99%` (service/actions at `100%`)
   - LLM guardrail subset coverage: `99%`
   - analytics visibility subset coverage: `99%`
3. Remaining execution blockers are unchanged and explicit:
   - `BSAFE-009` real staged stress artifact capture/attachment.
   - staged CI release packet capture (`docs/evidence/ci-green-YYYY-MM-DD.md`) for promotion runs.

Validation:
1. `DEBUG=false uv run ruff check scripts/verify_enforcement_post_closure_sanity.py scripts/run_enterprise_tdd_gate.py tests/unit/ops/test_verify_enforcement_post_closure_sanity.py tests/unit/ops/test_enforcement_stress_evidence_pack.py tests/unit/ops/test_enforcement_failure_injection_pack.py tests/unit/ops/test_release_artifact_templates_pack.py`
2. `DEBUG=false uv run pytest --no-cov -q tests/unit/ops/test_verify_enforcement_post_closure_sanity.py tests/unit/ops/test_enforcement_stress_evidence_pack.py tests/unit/ops/test_enforcement_failure_injection_pack.py tests/unit/ops/test_release_artifact_templates_pack.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
3. `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py`

## Execution update (2026-02-27): BSAFE-013 JWT BCP checklist gate + token-type binding

Objective:
1. Close `BSAFE-013` with machine-verifiable JWT BCP evidence (not narrative-only status).
2. Enforce explicit approval-token typing in runtime decode path to reduce token-confusion risk.
3. Keep the release gate binary and non-bypassable.

Implemented:
1. Hardened approval-token contract in enforcement service:
   - issue path now includes explicit claim: `token_type=enforcement_approval`,
   - decode path now requires `token_type` claim and rejects non-matching values.
   - File: `app/modules/enforcement/domain/service.py`
2. Added JWT BCP checklist artifact:
   - `docs/security/jwt_bcp_checklist_2026-02-27.json`
   - includes required controls for algorithm allow-list, issuer/audience binding, explicit token typing, temporal claims, binding claims, replay safety, and rotation-compatible verification.
3. Added checklist validator script:
   - `scripts/verify_jwt_bcp_checklist.py`
   - enforces RFC 8725 source linkage, required control IDs, status/schema validity, and evidence-path existence.
4. Wired JWT checklist validator into release gate:
   - `scripts/run_enterprise_tdd_gate.py` now runs `verify_jwt_bcp_checklist.py` before pytest/coverage stages.
5. Added/updated regression tests:
   - `tests/unit/supply_chain/test_verify_jwt_bcp_checklist.py`
   - `tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
   - `tests/unit/enforcement/test_enforcement_service_helpers.py`
   - `tests/unit/enforcement/test_enforcement_service.py`

Result:
1. `BSAFE-013`: `DONE` (artifact + validator + gate wiring + runtime type-binding enforcement).
2. `CTRL-011`: moved to implemented baseline in this tracker snapshot (`LLM-001..005` closure plus quota/fallback propagation evidence already present).
3. Latest full enterprise gate evidence:
   - `769 passed in 379.24s`
   - enforcement subset coverage: `99%` aggregate (`service.py` at `100%`)
   - LLM guardrail subset coverage: `96%`
   - analytics visibility subset coverage: `99%`
4. Remaining hard blockers in this lane stay explicit:
   - `BSAFE-009` (real staged stress artifact capture),
   - `BSAFE-010` (real staged failure-injection artifact capture under verifier/gate contract),
   - packaging/commercial boundary backlog (`PKG-*`).

Validation:
1. `DEBUG=false uv run ruff check app/modules/enforcement/domain/service.py scripts/verify_jwt_bcp_checklist.py scripts/verify_enforcement_post_closure_sanity.py tests/unit/enforcement/test_enforcement_service_helpers.py tests/unit/enforcement/test_enforcement_service.py tests/unit/supply_chain/test_verify_jwt_bcp_checklist.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py tests/unit/ops/test_verify_enforcement_post_closure_sanity.py`
2. `DEBUG=false uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_service_helpers.py -k "decode_and_extract_approval_token_error_branches or build_approval_token_requires_secret_and_includes_kid or decode_approval_token_deduplicates_candidate_secrets"`
3. `DEBUG=false uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_service.py -k "approval_token_claims_include_project_and_hourly_cost_binding or consume_approval_token_rejects_project_claim_mismatch or consume_approval_token_rejects_hourly_cost_claim_mismatch"`
4. `DEBUG=false uv run pytest --no-cov -q tests/unit/supply_chain/test_verify_jwt_bcp_checklist.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py tests/unit/ops/test_verify_enforcement_post_closure_sanity.py`
5. `DEBUG=false uv run python3 scripts/verify_jwt_bcp_checklist.py --checklist-path docs/security/jwt_bcp_checklist_2026-02-27.json`
6. `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py`

## Execution update (2026-02-27): BSAFE-010 staged failure-injection evidence verifier + gate

Objective:
1. Move `BSAFE-010` from matrix-only baseline to staged-evidence contract parity with stress evidence.
2. Make staged failure-injection evidence machine-verifiable and release-gate enforceable.
3. Keep separation-of-duties and freshness controls explicit for operational proof quality.

Implemented:
1. Added staged failure-injection evidence validator:
   - `scripts/verify_enforcement_failure_injection_evidence.py`
   - enforces:
     - `profile=enforcement_failure_injection`
     - `runner=staged_failure_injection`
     - `execution_class=staged`
     - timezone-aware `captured_at`
     - separation-of-duties (`executed_by != approved_by`)
     - full scenario coverage (`FI-001..FI-005`) with duplicate/missing/unknown rejection
     - per-scenario contract (`status`, `duration_seconds>0`, non-empty `checks`, non-empty `evidence_refs`)
     - summary anti-tamper integrity (`total`, `passed`, `failed`, `overall_passed`)
     - optional freshness bound (`--max-artifact-age-hours`)
2. Added comprehensive validator tests:
   - `tests/unit/ops/test_verify_enforcement_failure_injection_evidence.py`
3. Wired validator into enterprise gate with optional/required artifact semantics:
   - `scripts/run_enterprise_tdd_gate.py`
   - env contract:
     - `ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_PATH`
     - `ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_MAX_AGE_HOURS`
     - `ENFORCEMENT_FAILURE_INJECTION_EVIDENCE_REQUIRED=true` (fail-fast when path missing)
4. Added gate-runner tests for new failure-injection command wiring/fail-fast behavior:
   - `tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
5. Extended failure-injection evidence documentation with staged artifact contract and gate integration:
   - `docs/ops/enforcement_failure_injection_matrix_2026-02-25.md`
   - `tests/unit/ops/test_enforcement_failure_injection_pack.py` updated for contract tokens.

Result:
1. `BSAFE-010` closure posture upgraded:
   - baseline deterministic matrix/tests remain `DONE`,
   - staged artifact verification and gate wiring are now implemented,
   - remaining item is operational artifact capture/attachment (execution evidence), not contract/tooling gaps.
2. This aligns `BSAFE-010` with the same release-discipline model used by `BSAFE-009`.
3. Latest full enterprise gate evidence after this change:
   - `783 passed in 386.17s`
   - enforcement subset coverage: `99%` aggregate (`service.py` at `100%`)
   - LLM guardrail subset coverage: `99%`
   - analytics visibility subset coverage: `99%`

Validation:
1. `DEBUG=false uv run ruff check scripts/verify_enforcement_failure_injection_evidence.py scripts/run_enterprise_tdd_gate.py tests/unit/ops/test_verify_enforcement_failure_injection_evidence.py tests/unit/ops/test_enforcement_failure_injection_pack.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
2. `DEBUG=false uv run pytest --no-cov -q tests/unit/ops/test_verify_enforcement_failure_injection_evidence.py tests/unit/ops/test_enforcement_failure_injection_pack.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
3. `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py`

## Execution update (2026-02-27): single-command staged evidence gate wrapper

Objective:
1. Remove manual stop/start env orchestration when running release gate with staged stress + failure-injection artifacts.
2. Provide one deterministic command that enforces both artifact requirements and executes enterprise gate in one pass.

Implemented:
1. Added wrapper script:
   - `scripts/run_enforcement_release_evidence_gate.py`
   - validates artifact files and required thresholds before launching gate,
   - sets required env contract automatically:
     - stress: path/required/freshness/workload floor,
     - failure injection: path/required/freshness.
2. Added comprehensive tests:
   - `tests/unit/supply_chain/test_run_enforcement_release_evidence_gate.py`
   - coverage includes env wiring, missing artifact rejection, non-positive threshold rejection, and gate invocation contract.
3. Added wrapper test into enterprise gate target set:
   - `scripts/run_enterprise_tdd_gate.py` now includes `tests/unit/supply_chain/test_run_enforcement_release_evidence_gate.py`.
4. Updated staged evidence docs with single-command release invocation:
   - `docs/ops/enforcement_stress_evidence_2026-02-25.md`
   - `docs/ops/enforcement_failure_injection_matrix_2026-02-25.md`
   - corresponding pack tests updated:
     - `tests/unit/ops/test_enforcement_stress_evidence_pack.py`
     - `tests/unit/ops/test_enforcement_failure_injection_pack.py`

Result:
1. Staged evidence gate execution is now one command once real artifacts exist:
   - `uv run python3 scripts/run_enforcement_release_evidence_gate.py --stress-evidence-path ... --failure-evidence-path ...`
2. Latest full enterprise gate evidence after wrapper integration:
   - `788 passed in 382.38s`
   - enforcement subset coverage: `99%` aggregate (`service.py` at `100%`)
   - LLM guardrail subset coverage: `99%`
   - analytics visibility subset coverage: `99%`
3. Remaining blockers are now execution/business, not local hardening mechanics:
   - `BSAFE-009` real staged stress artifact capture/attachment,
   - `BSAFE-010` real staged failure-injection artifact capture/attachment,
   - `PKG-*` packaging/commercial boundary decisions.

Validation:
1. `DEBUG=false uv run ruff check scripts/run_enforcement_release_evidence_gate.py scripts/run_enterprise_tdd_gate.py tests/unit/supply_chain/test_run_enforcement_release_evidence_gate.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py tests/unit/ops/test_enforcement_stress_evidence_pack.py tests/unit/ops/test_enforcement_failure_injection_pack.py`
2. `DEBUG=false uv run pytest --no-cov -q tests/unit/supply_chain/test_run_enforcement_release_evidence_gate.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py tests/unit/ops/test_enforcement_stress_evidence_pack.py tests/unit/ops/test_enforcement_failure_injection_pack.py tests/unit/ops/test_verify_enforcement_failure_injection_evidence.py`
3. `DEBUG=false uv run python3 scripts/run_enforcement_release_evidence_gate.py --stress-evidence-path docs/ops/enforcement_stress_evidence_2026-02-25.md --failure-evidence-path docs/ops/enforcement_failure_injection_matrix_2026-02-25.md --dry-run`
4. `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py`

## Execution update (2026-02-27): register recovery + defensive branch closure + current backlog snapshot

Objective:
1. Recover missing enforcement gap register/evidence docs without discarding prior closure history.
2. Close remaining defensive service/actions branch gaps identified in latest pass.
3. Reconfirm release-gate health and publish explicit remaining backlog status.

Implemented:
1. Recovered `docs/ops/enforcement_control_plane_gap_register_2026-02-23.md` from local editor logs after accidental truncation.
2. Restored missing release-critical evidence docs required by enterprise gate contracts:
   - `docs/ops/enforcement_post_closure_sanity_2026-02-26.md`
   - `docs/ops/enforcement_failure_injection_matrix_2026-02-25.md`
   - `docs/ops/enforcement_stress_evidence_2026-02-25.md`
3. Added explicit defensive-invariant comments in enforcement service guard paths:
   - negative entitlement threshold fail-safes (`auto_approve`, `plan_ceiling`, `enterprise_ceiling`)
   - reserve-amount quantization fail-safe in grant allocation.
4. Added TDD coverage for previously defensive/unreachable branches:
   - forced quantization-regression tests to prove defensive threshold guards execute safely,
   - forced zero-reserve quantization regression to execute reserve-allocation defensive continue path.
   - File: `tests/unit/enforcement/test_enforcement_service_helpers.py`
5. Closed remaining targeted `actions.py` branch paths from prior pass:
   - integrity-error/no-dedupe re-raise branch,
   - list filter false branch (`status is None`),
   - lease loop no-candidate return path.
   - File: `tests/unit/enforcement/test_enforcement_actions_service.py`

Result:
1. Enterprise gate run is green after recovery and branch-closure work.
2. Latest gate evidence:
   - `504 passed`
   - enforcement subset coverage: `99%` aggregate, `service.py` now `100%`, `actions.py` `100%`
   - LLM guardrail subset coverage: `96%` (`>=90%`)
   - analytics visibility subset coverage: `99%` (`>=99%`)
3. Post-closure sanity validator passes with all seven release-critical dimensions.

Current backlog snapshot (explicit):
1. `BSAFE-009`: `DONE` (staged stress artifact captured, PostgreSQL backend verified, and release-gate evidence run completed).
2. `CTRL-011`: `DONE` baseline (tier token ceilings + actor propagation/fallback hardening + regression evidence are now closed).
3. `CTRL-017`: `DONE` baseline (staged artifact + verifier + gate wiring present).
4. External benchmark rows previously marked `Partial`:
   - Kubernetes webhook operational hardening: `Partial-to-strong` (fail-closed HA/PDB/anti-affinity contracts implemented; keep staged operational proof open).
   - CEL policy portability: `Partial` (keep as forward roadmap under policy portability).
   - Terraform ordering profile docs: `Partial-to-strong` (preflight contract is implemented; full ordering profile remains documentation hardening).
   - JWT BCP checklist (`BSAFE-013`): `DONE` (checklist artifact + validator + release-gate wiring).
   - Supply-chain verification (`BSAFE-014`): `DONE` (verification gate implemented in workflow).
   - SSDF traceability (`BSAFE-015`): `DONE` (matrix + validator + gate wiring).
   - Burn-rate release gate (`BSAFE-016`): `DONE` (policy + evidence + gate checks).
5. `PKG-*` backlog (`PKG-001..PKG-019`): still actionable work overall; this pass closes `PKG-003` and `PKG-014` baseline runtime gating while pricing/policy decision items remain open.

Validation:
1. `DEBUG=false .venv/bin/ruff check tests/unit/enforcement/test_enforcement_service_helpers.py`
2. `DEBUG=false .venv/bin/pytest --no-cov -q tests/unit/enforcement/test_enforcement_service_helpers.py -k "defensive_threshold_guards_on_quantize_regression or defensive_zero_reserve_amount_guard or policy_entitlement_matrix_prevalidates_negative_thresholds or reserve_amount_quantization_invariant_proves_defensive_guard"`
3. `DEBUG=false .venv/bin/pytest --no-cov -q tests/unit/enforcement/test_enforcement_actions_service.py -k "action_orchestrator_create_auto_idempotency_and_integrity_dedup_paths or action_orchestrator_get_list_lease_and_cancel_missing_branches"`
4. `DEBUG=false .venv/bin/pytest --no-cov -q tests/unit/ops/test_enforcement_failure_injection_pack.py tests/unit/ops/test_enforcement_stress_evidence_pack.py tests/unit/ops/test_verify_enforcement_post_closure_sanity.py`
5. `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py`

## Execution update (2026-02-27): BSAFE-009 stress-evidence contract hardening pass

Objective:
1. Remove protocol drift between stress-evidence docs and actual CLI contracts.
2. Harden stress evidence verification against malformed or internally inconsistent payloads.
3. Reconfirm release-gate integrity after stress-evidence contract tightening.

Implemented:
1. Fixed stress protocol documentation to match real runner/verifier flags:
   - capture uses `--out` (not `--output`)
   - verification uses `--evidence-path` (not `--artifact`)
   - added explicit `--enforce-thresholds` guidance for release evidence runs.
   - file: `docs/ops/enforcement_stress_evidence_2026-02-25.md`
2. Added stricter evidence contract checks in verifier:
   - require `runner == scripts/load_test_api.py`,
   - require timezone-aware ISO timestamp for `captured_at`,
   - require `runs` count to align with declared `rounds`,
   - require `preflight.failures` empty when preflight is marked passed,
   - require `results.successful_requests == total_requests - failed_requests`,
   - require `results.throughput_rps > 0`,
   - require `evaluation.overall_meets_targets` consistency with all `evaluation.rounds[*].meets_targets`,
   - require payload-level `meets_targets` consistency when present.
   - file: `scripts/verify_enforcement_stress_evidence.py`
3. Expanded validator/pack tests for edge-case contract enforcement:
   - runner/timestamp contract rejection,
   - round-alignment and success-count drift rejection,
   - evaluation consistency rejection,
   - doc snippet assertions updated to the real CLI contract.
   - files:
     - `tests/unit/ops/test_verify_enforcement_stress_evidence.py`
     - `tests/unit/ops/test_enforcement_stress_evidence_pack.py`

Result:
1. Enterprise gate remains green after the stress-evidence hardening pass.
2. Latest gate evidence:
   - `507 passed`
   - enforcement subset coverage: `99%` aggregate (`service.py`/`actions.py` at `100%`)
   - LLM guardrail subset coverage: `96%`
   - analytics visibility subset coverage: `99%`
3. Historical status at this checkpoint was `IN_PROGRESS`:
   - protocol and verifier had already reached production-grade hardening.
   - superseded by the 2026-02-27 staged artifact closure listed in the canonical status section.

External benchmark revalidation (online):
1. Google SRE Workbook burn-rate alerting guidance:
   - https://sre.google/workbook/alerting-on-slos/
2. Grafana k6 threshold pass/fail automation guidance:
   - https://grafana.com/docs/k6/latest/using-k6/thresholds/

Validation:
1. `DEBUG=false .venv/bin/ruff check scripts/verify_enforcement_stress_evidence.py tests/unit/ops/test_verify_enforcement_stress_evidence.py tests/unit/ops/test_enforcement_stress_evidence_pack.py`
2. `DEBUG=false .venv/bin/pytest --no-cov -q tests/unit/ops/test_verify_enforcement_stress_evidence.py tests/unit/ops/test_enforcement_stress_evidence_pack.py`
3. `DEBUG=false .venv/bin/pytest --no-cov -q tests/unit/core/test_load_test_api_script.py`
4. `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py`

## Execution update (2026-02-27): BSAFE-009 optional CI artifact gate + freshness hardening

Objective:
1. Make stress evidence release-blocking in CI when a real staged artifact path is supplied.
2. Strengthen stale-artifact rejection and evidence consistency checks.
3. Keep local/dev gate workflow deterministic when no staged artifact is supplied.

Implemented:
1. Added optional stress artifact verification command wiring in enterprise gate:
   - when `ENFORCEMENT_STRESS_EVIDENCE_PATH` is set, `run_enterprise_tdd_gate.py` appends:
     - `scripts/verify_enforcement_stress_evidence.py --evidence-path <path>`
   - when `ENFORCEMENT_STRESS_EVIDENCE_MAX_AGE_HOURS` is also set, gate enforces freshness bound.
   - file: `scripts/run_enterprise_tdd_gate.py`
2. Extended stress evidence verifier with freshness and integrity controls:
   - optional `--max-artifact-age-hours`,
   - strict `captured_at` timezone-aware parsing,
   - strict run/evaluation consistency checks.
   - file: `scripts/verify_enforcement_stress_evidence.py`
3. Added comprehensive gate/validator tests:
   - verify optional stress verifier command inclusion/exclusion in gate command plan,
   - verify stale artifact rejection and invalid freshness bound handling,
   - preserve existing edge-path checks.
   - files:
     - `tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
     - `tests/unit/ops/test_verify_enforcement_stress_evidence.py`
4. Updated stress evidence protocol doc with CI integration contract env vars.
   - file: `docs/ops/enforcement_stress_evidence_2026-02-25.md`

Result:
1. Enterprise gate remains green after integration hardening.
2. Latest full gate evidence:
   - `509 passed`
   - enforcement subset coverage: `99%`
   - LLM guardrail subset coverage: `96%`
   - analytics visibility subset coverage: `99%`
3. Historical status at this checkpoint was `IN_PROGRESS` pending staged artifact execution.
   - superseded by the 2026-02-27 staged artifact closure listed in the canonical status section.

Validation:
1. `DEBUG=false .venv/bin/ruff check scripts/run_enterprise_tdd_gate.py scripts/verify_enforcement_stress_evidence.py tests/unit/ops/test_verify_enforcement_stress_evidence.py tests/unit/ops/test_enforcement_stress_evidence_pack.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
2. `DEBUG=false .venv/bin/pytest --no-cov -q tests/unit/ops/test_verify_enforcement_stress_evidence.py tests/unit/ops/test_enforcement_stress_evidence_pack.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py tests/unit/core/test_load_test_api_script.py`
3. `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py`

## Execution update (2026-02-27): BSAFE-009 run-level aggregate anti-tamper hardening

Objective:
1. Close the remaining integrity gap where top-level stress metrics could diverge from run-level evidence while still looking plausible.
2. Convert those aggregate invariants into enforced validation logic plus explicit tests.
3. Re-run full enterprise gate and preserve release-blocking posture.

Implemented:
1. Extended `scripts/verify_enforcement_stress_evidence.py` with deterministic run-level aggregate checks:
   - each run must provide `run_index`, timezone-aware `captured_at`, and `results`,
   - run-level arithmetic integrity:
     - `successful_requests == total_requests - failed_requests`,
   - top-level aggregate integrity:
     - totals/success/failure sums must match all runs,
     - top-level p95/p99 must equal max run p95/p99,
     - `min_throughput_rps` must equal min run throughput,
     - top-level `results.throughput_rps` must equal average run throughput.
2. Updated stress verifier unit tests to use mathematically consistent run-level fixtures and cover tamper/error paths under the new invariants.
   - file: `tests/unit/ops/test_verify_enforcement_stress_evidence.py`
3. Updated stress protocol documentation to reflect the strengthened run/aggregate contract.
   - file: `docs/ops/enforcement_stress_evidence_2026-02-25.md`

Result:
1. Enterprise gate remains green after aggregate anti-tamper hardening.
2. Latest full gate evidence:
   - `510 passed`
   - enforcement subset coverage: `99%` aggregate (`service.py` and `actions.py` at `100%`)
   - LLM guardrail subset coverage: `96%`
   - analytics visibility subset coverage: `99%`
3. Historical status at this checkpoint was `IN_PROGRESS` until a staged artifact was captured.
   - superseded by the 2026-02-27 staged artifact closure listed in the canonical status section.

Validation:
1. `DEBUG=false .venv/bin/ruff check scripts/verify_enforcement_stress_evidence.py tests/unit/ops/test_verify_enforcement_stress_evidence.py`
2. `DEBUG=false .venv/bin/pytest --no-cov -q tests/unit/ops/test_verify_enforcement_stress_evidence.py`
3. `DEBUG=false .venv/bin/pytest --no-cov -q tests/unit/ops/test_enforcement_stress_evidence_pack.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py tests/unit/core/test_load_test_api_script.py`
4. `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py`

## Execution update (2026-02-27): BSAFE-009 release workload floor + endpoint contract hardening

Objective:
1. Prevent trivially weak stress artifacts (too short / too few users / incomplete endpoint surface) from being accepted as release evidence.
2. Keep `BSAFE-009` focused on the final remaining closure item: staged artifact capture, not verifier-contract gaps.

Implemented:
1. Hardened stress verifier contract in `scripts/verify_enforcement_stress_evidence.py`:
   - minimum workload checks:
     - `duration_seconds >= min_duration_seconds` (default `30`)
     - `concurrent_users >= min_concurrent_users` (default `10`)
   - required enforcement endpoint set checks:
     - `/api/v1/enforcement/policies`
     - `/api/v1/enforcement/ledger?limit=50`
     - `/api/v1/enforcement/exports/parity?limit=50`
2. Added comprehensive TDD coverage for the new failure modes:
   - `tests/unit/ops/test_verify_enforcement_stress_evidence.py` now validates:
     - duration floor rejection,
     - concurrent-user floor rejection,
     - required endpoint omission rejection,
     - existing tamper/evaluation/freshness constraints,
     - threshold contract mismatch rejection,
     - evaluation aggregate consistency rejection (`worst_p95` / `min_throughput` / round-count).
3. Updated stress evidence protocol doc and pack assertions:
   - `docs/ops/enforcement_stress_evidence_2026-02-25.md`
   - `tests/unit/ops/test_enforcement_stress_evidence_pack.py`
4. Updated enterprise gate stress verifier wiring to support explicit workload-floor env overrides when staged artifacts are validated:
   - `ENFORCEMENT_STRESS_EVIDENCE_MIN_DURATION_SECONDS` (default `30`)
   - `ENFORCEMENT_STRESS_EVIDENCE_MIN_CONCURRENT_USERS` (default `10`)
   - file: `scripts/run_enterprise_tdd_gate.py`
   - tests: `tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
5. Extended stress protocol doc and pack to include:
   - CI env overrides for minimum workload floor,
   - thresholds/evaluation consistency contract clauses.
   - files:
     - `docs/ops/enforcement_stress_evidence_2026-02-25.md`
     - `tests/unit/ops/test_enforcement_stress_evidence_pack.py`

Result:
1. Enterprise gate remains green with the stricter stress evidence contract.
2. Latest full gate evidence:
   - `758 passed`
   - enforcement subset coverage: `99%` aggregate (`service.py` and `actions.py` at `100%`)
   - LLM guardrail subset coverage: `96%`
   - analytics visibility subset coverage: `99%`
3. Historical status at this checkpoint was `IN_PROGRESS` only for staged artifact execution/attachment.
   - superseded by the 2026-02-27 staged artifact closure listed in the canonical status section.

Validation:
1. `DEBUG=false .venv/bin/ruff check scripts/verify_enforcement_stress_evidence.py scripts/run_enterprise_tdd_gate.py tests/unit/ops/test_verify_enforcement_stress_evidence.py tests/unit/ops/test_enforcement_stress_evidence_pack.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
2. `DEBUG=false .venv/bin/pytest --no-cov -q tests/unit/ops/test_verify_enforcement_stress_evidence.py tests/unit/ops/test_enforcement_stress_evidence_pack.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py tests/unit/core/test_load_test_api_script.py`
3. `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py`

## Execution update (2026-02-27): BSAFE-011 key-rotation drill evidence gate

Objective:
1. Close `CTRL-017` / `BSAFE-011` by replacing narrative-only status with explicit staged drill evidence and release-gate validation.
2. Enforce separation-of-duties, rollback proof, replay-safety, and drill freshness in CI.

Implemented:
1. Added staged drill artifact:
   - `docs/ops/key-rotation-drill-2026-02-27.md`
   - includes deterministic key/value evidence markers:
     - `owner` vs `approver` (must differ),
     - fallback/rollback/replay outcomes,
     - `post_drill_status: PASS`,
     - `next_drill_due_on`.
2. Added machine validator:
   - `scripts/verify_key_rotation_drill_evidence.py`
   - enforces:
     - required evidence fields present,
     - all critical boolean outcomes are `true`,
     - owner/approver are distinct,
     - execution timestamp sanity,
     - maximum drill age bound (`--max-drill-age-days`).
3. Wired validator into enterprise release gate:
   - `scripts/run_enterprise_tdd_gate.py` now always runs drill evidence validation with defaults:
     - `docs/ops/key-rotation-drill-2026-02-27.md`
     - max age `120` days
   - env overrides supported:
     - `ENFORCEMENT_KEY_ROTATION_DRILL_PATH`
     - `ENFORCEMENT_KEY_ROTATION_DRILL_MAX_AGE_DAYS`
4. Added comprehensive tests:
   - `tests/unit/ops/test_verify_key_rotation_drill_evidence.py`
   - `tests/unit/ops/test_key_rotation_drill_evidence_pack.py`
   - updated `tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
   - updated `tests/unit/ops/test_verify_enforcement_post_closure_sanity.py` and `scripts/verify_enforcement_post_closure_sanity.py` to include rotation-drill evidence token checks.

Result:
1. `BSAFE-011`: `DONE` (artifact + validator + gate + tests).
2. `CTRL-017`: upgraded from `Partial` to `Implemented baseline`.
3. Enterprise gate remains green with this additional release-blocking control.
4. Latest full gate evidence:
   - `723 passed`
   - enforcement subset coverage: `99%` aggregate (`service.py` and `actions.py` at `100%`)
   - LLM guardrail subset coverage: `96%`
   - analytics visibility subset coverage: `99%`

Validation:
1. `DEBUG=false .venv/bin/ruff check scripts/verify_key_rotation_drill_evidence.py scripts/verify_enforcement_post_closure_sanity.py scripts/run_enterprise_tdd_gate.py tests/unit/ops/test_verify_key_rotation_drill_evidence.py tests/unit/ops/test_key_rotation_drill_evidence_pack.py tests/unit/ops/test_verify_enforcement_post_closure_sanity.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
2. `DEBUG=false .venv/bin/pytest --no-cov -q tests/unit/ops/test_verify_key_rotation_drill_evidence.py tests/unit/ops/test_key_rotation_drill_evidence_pack.py tests/unit/ops/test_verify_enforcement_post_closure_sanity.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
3. `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py`

## Execution update (2026-02-26): defensive analyzer branch rationale + invariant tests

Objective:
1. Prevent future churn on `analyzer.py` defensive branch misses in the analytics visibility gate (`99%` target).
2. Encode the control-flow invariants as executable tests and code comments instead of leaving them implicit.

Implemented:
1. Added explicit defensive-invariant comments in `app/shared/llm/analyzer.py` at the two residual analytics branch guards:
   - unexpected budget-check exception handler tenant gate (anonymous path cannot enter reservation block)
   - metered usage record tenant guard (reservation is only created in tenant-scoped flow)
2. Added gate-counted invariant test in `tests/unit/llm/test_analyzer_branch_edges.py`:
   - proves anonymous `analyze()` skips:
     - tenant tier lookup,
     - tier limit reads,
     - `LLMBudgetManager.check_and_reserve`,
     - `LLMBudgetManager.record_usage`
   - while still completing analysis successfully via mocked LLM/process path.

Why this matters:
1. The analytics gate now stays at `99%` without pressure to force impossible branch coverage.
2. If future refactors accidentally make the anonymous path touch tenant reservation/metering code, the invariant test fails immediately.

Authoritative validation:
1. `uv run python3 scripts/run_enterprise_tdd_gate.py` ✅
   - `473 passed`
   - Enforcement coverage subset: `96%` (`>=95%`)
   - LLM guardrail coverage subset: `96%` (`>=90%`)
   - Analytics visibility subset (`analyzer.py` + `costs.py`): `99%` (`>=99%`)
2. Residual `analyzer.py` misses remain defensive-only after comment insertion (line numbers shifted):
   - `412->418`
   - `472`

Validation:
1. `uv run ruff check app/shared/llm/analyzer.py tests/unit/llm/test_analyzer_branch_edges.py`
2. `uv run pytest --no-cov -q tests/unit/llm/test_analyzer_branch_edges.py`
3. `uv run python3 scripts/run_enterprise_tdd_gate.py`

## Execution update (2026-02-26): service.py helper branch closure batch (credit headroom + approval token guards)

Objective:
1. Raise coverage on `app/modules/enforcement/domain/service.py` (largest remaining enforcement surface under the enterprise gate) using helper-level tests with high branch density.
2. Close specific uncovered/partial clusters in the credit headroom + approval token helper paths.

Implemented (helper tests in `tests/unit/enforcement/test_enforcement_service_helpers.py`):
1. Credit headroom legacy-adjustment branch coverage:
   - `_get_credit_headrooms()` now exercised for:
     - legacy uncovered reservation spillover into emergency headroom,
     - legacy uncovered reservation fully absorbed by reserved headroom,
     - zero uncovered legacy reservation (bypass legacy reduction branch).
   - This closes/strengthens the previously uncovered branch cluster around `4072–4083`.
2. Active credit headroom aggregation + credit reservation helper branch coverage:
   - `_get_active_credit_headroom()` quantized sum path (`4100`, `4105`),
   - `_reserve_credit_for_decision()` branch matrix:
     - reserved+emergency targets,
     - emergency-only,
     - reserved-only,
   - closes branch halves around `4121` and `4132`.
3. Approval token candidate-secret dedupe branch coverage:
   - `_decode_approval_token()` with duplicate fallback secrets verifies unique candidate iteration only.
   - closes branch at `4687`.
4. Approval token decimal-claim validation branch coverage:
   - `_extract_token_context()` invalid decimal claim (`Infinity`) now provably hits the `InvalidOperation` rejection path.
   - closes error path lines `4767–4768`.

Focused evidence (targeted helper probe):
1. `service.py` targeted line/branch hits confirmed from `/tmp/service-helper-coverage.xml`:
   - `4072` branch `100% (2/2)`
   - `4082` branch `100% (2/2)`
   - `4100`, `4105` hit
   - `4121` branch `100% (2/2)`
   - `4132` branch `100% (2/2)`
   - `4687` branch `100% (2/2)`
   - `4767`, `4768` hit

Authoritative gate result:
1. `uv run python3 scripts/run_enterprise_tdd_gate.py` ✅
   - `477 passed`
   - Enforcement coverage subset: `96%` (`>=95%`)
   - `app/modules/enforcement/domain/service.py`: `94%` (up from `93%` in prior gate run)
   - LLM guardrail coverage subset: `96%` (`>=90%`)
   - Analytics visibility subset (`analyzer.py` + `costs.py`): `99%` (`>=99%`)

Validation:
1. `uv run ruff check tests/unit/enforcement/test_enforcement_service_helpers.py`
2. `uv run pytest --no-cov -q tests/unit/enforcement/test_enforcement_service_helpers.py -k "credit_headroom_helpers_cover_legacy_uncovered_and_spillover_paths or active_headroom_and_reserve_credit_for_decision_helper_branches or decode_approval_token_deduplicates_candidate_secrets or extract_token_context_rejects_invalid_decimal_claims"`
3. `uv run pytest -q -o addopts= tests/unit/enforcement/test_enforcement_service_helpers.py -k "credit_headroom_helpers_cover_legacy_uncovered_and_spillover_paths or active_headroom_and_reserve_credit_for_decision_helper_branches or decode_approval_token_deduplicates_candidate_secrets or extract_token_context_rejects_invalid_decimal_claims" --cov=app/modules/enforcement --cov-report=xml:/tmp/service-helper-coverage.xml`
4. XML spot-check for targeted `service.py` lines/branches (`4072,4082,4100,4105,4121,4132,4687,4767,4768`)
5. `uv run python3 scripts/run_enterprise_tdd_gate.py`

## Execution update (2026-02-26): analytics visibility gate hardening to 98% + edge-case coverage expansion

Objective:
1. Increase confidence in LLM analytics + reporting analytics surfaces (`analyzer.py`, `costs.py`) with gate-counted edge-case tests.
2. Ratchet the analytics visibility coverage floor above `95%` using measured evidence.
3. Preserve release-gate discipline by re-running the full enterprise gate and post-closure sanity checks.

Implemented:
1. Expanded gate-counted analytics edge-case coverage in `tests/unit/api/v1/test_costs_acceptance_payload_branches.py`:
   - `get_costs` small-dataset direct summary branch (non-async/offload path),
   - `get_canonical_quality` notify-disabled skip-alert branch,
   - `get_cost_anomalies` alert-disabled skip-dispatch branch with non-empty anomalies,
   - `get_unit_economics` anomaly-present + `alert_on_anomaly=False` skip-alert branch.
2. Expanded gate-counted analytics edge-case coverage in `tests/unit/llm/test_analyzer_branch_edges.py`:
   - prompt registry fallback when `prompts.yaml` is present but missing `finops_analysis`,
   - `_setup_client_and_usage` hard-limit branch (gate-counted suite now covers `BudgetExceededError` path),
   - provider-specific soft-limit degradation branches (Groq and Google),
   - invalid-provider fallback to configured default provider/model,
   - `_invoke_llm` BYOK + non-default provider + `max_output_tokens` factory branch,
   - enterprise-tier `_invoke_llm` fallback policy branch selection,
   - tenant-scoped Slack lookup branch with no configured Slack service,
   - `analyze()` shape-limit logging + invocation-failure logging path,
   - `analyze()` defensive tenant-tier re-fetch branch when initial tier lookup returns `None`.
3. Ratcheted enterprise gate analytics visibility floor:
   - `ANALYTICS_VISIBILITY_COVERAGE_FAIL_UNDER: 95 -> 98`
   - File: `scripts/run_enterprise_tdd_gate.py`

Measured evidence (gate-counted analytics slice):
1. Corrected focused analytics probe (including `tests/unit/api/v1/test_reconciliation_endpoints.py` to match enterprise gate coverage shape):
   - `app/modules/reporting/api/v1/costs.py`: `100%`
   - `app/shared/llm/analyzer.py`: `99%`
   - subset report (`coverage report --include=app/shared/llm/analyzer.py,app/modules/reporting/api/v1/costs.py`): `99%`
2. Remaining `analyzer.py` misses after this pass are narrow defensive branches:
   - `408->414` (budget error + anonymous path),
   - `465` (tenant-id required during metered usage record; effectively unreachable under normal reserve flow),
   - `532`,
   - `652`,
   - `655->658`.

Authoritative gate result:
1. `uv run python3 scripts/run_enterprise_tdd_gate.py` ✅
   - `470 passed`
   - Enforcement coverage subset: `96%` (`>=95%`)
   - LLM guardrail coverage subset: `96%` (`>=90%`)
   - Analytics visibility subset (`analyzer.py` + `costs.py`): `99%` (`>=98%`)

Validation:
1. `uv run ruff check tests/unit/llm/test_analyzer_branch_edges.py tests/unit/api/v1/test_costs_acceptance_payload_branches.py`
2. `uv run pytest --no-cov -q tests/unit/llm/test_analyzer_branch_edges.py tests/unit/api/v1/test_costs_acceptance_payload_branches.py`
3. `uv run pytest -q -o addopts= tests/unit/llm/test_analyzer_exhaustive.py tests/unit/llm/test_analyzer_branch_edges.py tests/unit/api/v1/test_costs_endpoints.py tests/unit/api/v1/test_costs_acceptance_payload_branches.py tests/unit/api/v1/test_reconciliation_endpoints.py --cov=app/shared/llm --cov=app/modules/reporting/api/v1 --cov-report=term-missing --cov-report=xml:/tmp/analytics-coverage.xml`
4. `uv run coverage report --include=app/shared/llm/analyzer.py,app/modules/reporting/api/v1/costs.py`
5. `uv run ruff check scripts/run_enterprise_tdd_gate.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
6. `uv run pytest --no-cov -q tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
7. `uv run python3 scripts/run_enterprise_tdd_gate.py`

## Execution update (2026-02-26): analytics visibility gate ratchet to 99% (reachable analyzer misses closed)

Objective:
1. Close remaining reachable `app/shared/llm/analyzer.py` misses in the gate-counted analytics slice.
2. Reclassify residual misses as defensive/unreachable where applicable and ratchet analytics visibility floor from `98%` to `99%`.
3. Revalidate with full enterprise gate + post-closure sanity after evidence update.

Implemented:
1. Expanded `tests/unit/llm/test_analyzer_branch_edges.py` to cover the remaining reachable analyzer branches:
   - `_check_cache_and_delta` `date` (not `datetime`) record parsing path (`line 532` previously uncovered) using a valid dict-backed `CostRecord` shape.
   - `_setup_client_and_usage` soft-limit OpenAI degradation branch (`gpt-4o -> gpt-4o-mini`).
   - `_setup_client_and_usage` soft-limit Azure no-degradation branch to drive the `elif ... ANTHROPIC` false path into provider validation (`655->658` branch).
2. Ratcheted enterprise gate analytics visibility threshold:
   - `ANALYTICS_VISIBILITY_COVERAGE_FAIL_UNDER: 98 -> 99`
   - File: `scripts/run_enterprise_tdd_gate.py`

Measured analytics slice (gate-counted test set):
1. Focused analytics probe (same suite composition as enterprise gate analytics surfaces):
   - `app/modules/reporting/api/v1/costs.py`: `100%`
   - `app/shared/llm/analyzer.py`: `99%`
   - Remaining analyzer misses reduced to defensive-only paths:
     - `408->414` (anonymous/fail-open side of unexpected budget-check exception path; effectively unreachable under current control flow because no budget-check work executes without tenant context)
     - `465` (tenant-id-required metered usage record guard; effectively unreachable because `reserved_amount` is only assigned inside the tenant-scoped reservation branch)
2. Exact analytics subset report:
   - `uv run coverage report --include=app/shared/llm/analyzer.py,app/modules/reporting/api/v1/costs.py`
   - Result: `99%`

Authoritative gate result:
1. `uv run python3 scripts/run_enterprise_tdd_gate.py` ✅
   - `472 passed`
   - Enforcement coverage subset: `96%` (`>=95%`)
   - LLM guardrail coverage subset: `96%` (`>=90%`)
   - Analytics visibility subset (`analyzer.py` + `costs.py`): `99%` (`>=99%`)

Validation:
1. `uv run ruff check tests/unit/llm/test_analyzer_branch_edges.py`
2. `uv run pytest --no-cov -q tests/unit/llm/test_analyzer_branch_edges.py`
3. `uv run pytest -q -o addopts= tests/unit/llm/test_analyzer_exhaustive.py tests/unit/llm/test_analyzer_branch_edges.py tests/unit/api/v1/test_costs_endpoints.py tests/unit/api/v1/test_costs_acceptance_payload_branches.py tests/unit/api/v1/test_reconciliation_endpoints.py --cov=app/shared/llm --cov=app/modules/reporting/api/v1 --cov-report=term-missing --cov-report=xml:/tmp/analytics-coverage.xml`
4. `uv run coverage report --include=app/shared/llm/analyzer.py,app/modules/reporting/api/v1/costs.py`
5. `uv run ruff check scripts/run_enterprise_tdd_gate.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py tests/unit/llm/test_analyzer_branch_edges.py`
6. `uv run pytest --no-cov -q tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
7. `uv run python3 scripts/run_enterprise_tdd_gate.py`

## Execution update (2026-02-26): post-closure sanity validator tightening + enterprise LLM guardrail gate realignment

Objective:
1. Convert latest operator feedback into non-bypassable post-closure sanity evidence checks (not just narrative guidance).
2. Restore enterprise gate correctness after LLM coverage scope drift caused a false release blocker on broad analytics surfaces.
3. Keep the 90% LLM threshold strict by measuring the release-critical LLM guardrail control surface and adding missing guardrail test suites.

Implemented:
1. Tightened `scripts/verify_enforcement_post_closure_sanity.py` evidence contract:
   - added explicit observability evidence for lock contention/timeout operator clarity:
     - `test_gate_lock_failures_route_to_failsafe_with_lock_reason_codes`
     - `valdrix_ops_enforcement_gate_lock_events_total`
   - added explicit snapshot/export stability evidence:
     - deterministic export bundle test (`test_build_export_bundle_reconciles_counts_and_is_deterministic`)
     - exported snapshot metadata fields (`computed_context_month_start`, `computed_context_data_source_mode`)
2. Added unit contract coverage for the above validator tokens:
   - File: `tests/unit/ops/test_verify_enforcement_post_closure_sanity.py`
3. Expanded endpoint wrapper branch coverage for enforcement API release surfaces:
   - added wrapper tests covering:
     - `gate_k8s_admission`
     - `gate_terraform_preflight` continuation/binding + optional metadata branches
     - `gate_k8s_admission_review` deny/allow-with-credits AdmissionReview shaping
   - File: `tests/unit/enforcement/test_enforcement_endpoint_wrapper_coverage.py`
4. Realigned enterprise gate LLM coverage threshold to the release-critical LLM guardrail slice and expanded guardrail test targets:
   - added missing gate targets:
     - `tests/unit/shared/llm/test_budget_execution_branches.py`
     - `tests/unit/shared/llm/test_budget_scheduler.py`
     - `tests/unit/core/test_budget_manager_audit.py`
     - `tests/unit/llm/test_usage_tracker.py`
     - `tests/unit/llm/test_usage_tracker_audit.py`
   - scoped 90% LLM threshold include list to:
     - `budget_fair_use.py`
     - `budget_execution.py`
     - `budget_manager.py`
     - `usage_tracker.py`
     - `factory.py`
     - provider adapters (`openai/anthropic/google/groq`)
   - broad analytics surfaces (`analyzer.py`, `reporting/api/v1/costs.py`) remain in the gate test run but are not part of the 90% guardrail threshold.
   - Files:
     - `scripts/run_enterprise_tdd_gate.py`
     - `tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
5. Updated post-closure sanity policy doc with explicit guidance for:
   - lock contention reason/metric separation,
   - snapshot metadata persistence/export,
   - Kubernetes `failurePolicy` alignment and HA prerequisites.
   - File: `docs/ops/enforcement_post_closure_sanity_2026-02-26.md`

Result:
1. Post-closure sanity validator now enforces the feedback-driven operator checks as binary evidence requirements.
2. Enterprise gate passes end-to-end after scope/test-target correction.
3. Enforcement coverage threshold passes at `96%`.
4. LLM guardrail coverage threshold passes at `91%` (fail-under remains `90%`).

Validation:
1. `uv run ruff check scripts/verify_enforcement_post_closure_sanity.py tests/unit/ops/test_verify_enforcement_post_closure_sanity.py tests/unit/enforcement/test_enforcement_endpoint_wrapper_coverage.py scripts/run_enterprise_tdd_gate.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
2. `uv run pytest --no-cov -q tests/unit/ops/test_verify_enforcement_post_closure_sanity.py tests/unit/enforcement/test_enforcement_endpoint_wrapper_coverage.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
3. `uv run python scripts/verify_enforcement_post_closure_sanity.py --doc-path docs/ops/enforcement_post_closure_sanity_2026-02-26.md --gap-register docs/ops/enforcement_control_plane_gap_register_2026-02-23.md`
4. `uv run python scripts/run_enterprise_tdd_gate.py` (`402 passed`)

## Execution update (2026-02-26): LLM guardrail coverage margin lift + XML threshold fallback for enterprise gate

Objective:
1. Increase confidence margin on release-critical LLM guardrail modules (`budget_execution`, `budget_manager`) beyond the `90%` threshold.
2. Eliminate enterprise-gate fragility when `pytest-cov` writes XML output but does not persist a `.coverage` data file for follow-up `coverage report` commands.

Root cause (observed):
1. Enterprise gate pytest step produced `coverage-enterprise-gate.xml` and term coverage output, but in some runs left no `.coverage` data file.
2. The subsequent `uv run coverage report ...` threshold commands then failed with `No data to report.` despite valid coverage data existing in the XML artifact.

Implemented:
1. Added targeted edge-path TDD coverage for LLM budget control surfaces:
   - `tests/unit/shared/llm/test_budget_execution_branches.py`
     - auto-bootstrap tier defaults (`FREE/GROWTH/PRO` paths)
     - actor normalization for authenticated users
     - month reset branch
     - slot-release behavior on budget exceed + unexpected errors
     - awaitable `scalar_one_or_none()` accessors
     - rollback-failure warning path
     - invalid-limit alert-check early return
     - helper default/fallback branches
   - `tests/unit/llm/test_budget_manager_exhaustive.py`
     - `_to_decimal(None)` + invalid conversion warning path
     - global pricing fallback path in `estimate_cost`
     - fair-use delegator wrapper methods (`*_fair_use_*`, request counting, slot acquire/release)
2. Hardened `scripts/run_enterprise_tdd_gate.py` coverage threshold execution:
   - retained existing `coverage report` commands for normal path compatibility;
   - added XML subset coverage parser/fallback (`coverage-enterprise-gate.xml`) for threshold verification when `coverage report` fails due missing `.coverage`;
   - computes subset coverage from XML line + branch counts (same weighted logic class/file aggregation uses for threshold intent).
3. Added gate-runner tests for the new fallback behavior and XML subset parser:
   - `tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
     - XML line/branch subset aggregation test
     - `coverage report` failure -> XML fallback threshold verification path

Result:
1. `budget_manager.py` guardrail coverage increased to `100%`.
2. `budget_execution.py` guardrail coverage increased to `99%`.
3. LLM guardrail subset threshold margin increased from `91%` to `96%`.
4. Enterprise gate remains release-blocking and now tolerates `.coverage` persistence flaps without lowering thresholds.

Validation:
1. `uv run ruff check scripts/run_enterprise_tdd_gate.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py tests/unit/llm/test_budget_manager_exhaustive.py tests/unit/shared/llm/test_budget_execution_branches.py`
2. `uv run pytest --no-cov -q tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py tests/unit/llm/test_budget_manager_exhaustive.py tests/unit/shared/llm/test_budget_execution_branches.py`
3. Focused guardrail coverage probe:
   - `budget_execution.py`: `99%`
   - `budget_manager.py`: `100%`
   - guardrail subset total: `95%`
4. `uv run python scripts/run_enterprise_tdd_gate.py` (`415 passed`, enforcement `96%`, LLM guardrail subset `96%`)

## Execution update (2026-02-25): BSAFE-015 SSDF traceability matrix gate

Objective:
1. Close `BSAFE-015` by creating a standards-backed, machine-verifiable SSDF traceability artifact.
2. Make SSDF matrix integrity a release-blocking gate (non-bypassable via enterprise TDD runner).

Implemented:
1. Added machine-readable SSDF matrix:
   - file: `docs/security/ssdf_traceability_matrix_2026-02-25.json`
   - includes all required SSDF practices (`PO.1..PO.5`, `PS.1..PS.3`, `PW.1/PW.2/PW.4..PW.9`, `RV.1..RV.3`)
   - maps each practice to concrete repository evidence paths and conservative status (`implemented_baseline|partial|planned`).
2. Added human-readable companion doc:
   - file: `docs/security/ssdf_traceability_matrix_2026-02-25.md`
3. Added validator script:
   - file: `scripts/verify_ssdf_traceability_matrix.py`
   - enforces:
     - required practice coverage,
     - duplicate/invalid status detection,
     - required NIST source URL presence,
     - evidence-path existence checks.
4. Wired SSDF validator into release-blocking enterprise gate:
   - file: `scripts/run_enterprise_tdd_gate.py`
   - command now runs before placeholder and coverage checks.
5. Added tests:
   - `tests/unit/supply_chain/test_verify_ssdf_traceability_matrix.py`
   - `tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py` (updated for SSDF gate command).

Status closure:
1. `BSAFE-015`: `DONE` (traceability matrix + validator + release-gate wiring + tests).

Validation:
1. `uv run ruff check scripts/verify_ssdf_traceability_matrix.py tests/unit/supply_chain/test_verify_ssdf_traceability_matrix.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
2. `uv run mypy scripts/verify_ssdf_traceability_matrix.py`
3. `uv run pytest --no-cov -q tests/unit/supply_chain/test_verify_ssdf_traceability_matrix.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
4. `uv run python scripts/verify_ssdf_traceability_matrix.py --matrix-path docs/security/ssdf_traceability_matrix_2026-02-25.json`

Primary sources (NIST):
1. NIST SSDF final publication page:
   - https://csrc.nist.gov/pubs/sp/800/218/final
2. DOI for SP 800-218:
   - https://doi.org/10.6028/NIST.SP.800-218
3. NIST SP 800-218 Rev.1 v1.2 IPD (forward watch):
   - https://csrc.nist.gov/pubs/sp/800/218/r1/ipd

## Execution update (2026-02-25): BSAFE-010 failure-injection evidence suite baseline

Objective:
1. Convert failure-injection expectations into a deterministic, test-backed evidence matrix.
2. Make failure-injection evidence part of enterprise release-gate test targets.

Implemented:
1. Added failure-injection matrix artifact:
   - file: `docs/ops/enforcement_failure_injection_matrix_2026-02-25.md`
   - scenarios:
     - `FI-001` gate timeout fallback,
     - `FI-002` lock contention/timeout fail-safe routing,
     - `FI-003` approval token replay/tamper rejection,
     - `FI-004` reservation reconciliation contention handling,
     - `FI-005` cross-tenant limiter saturation.
2. Added validation test for the matrix:
   - file: `tests/unit/ops/test_enforcement_failure_injection_pack.py`
   - verifies required scenario IDs and references to concrete test cases/files.
3. Added failure-injection pack test to enterprise gate targets:
   - file: `scripts/run_enterprise_tdd_gate.py`
   - target added: `tests/unit/ops/test_enforcement_failure_injection_pack.py`.

Status update:
1. `BSAFE-010`: `DONE` (baseline evidence suite + release-gate wiring for deterministic scenarios).
2. `BSAFE-009` (stress load evidence with measured SLO records) is now closed with staged PostgreSQL-backed evidence.

Validation:
1. `uv run ruff check tests/unit/ops/test_enforcement_failure_injection_pack.py scripts/run_enterprise_tdd_gate.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
2. `uv run pytest --no-cov -q tests/unit/ops/test_enforcement_failure_injection_pack.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
3. `uv run python scripts/run_enterprise_tdd_gate.py --dry-run`

## Execution update (2026-02-25): BSAFE-016 burn-rate SLO release/ops gate

Objective:
1. Close benchmark gap `BSAFE-016` with explicit multi-window burn-rate policy and binary evidence artifacts.
2. Convert burn-rate guidance into actionable release-hold criteria for enforcement promotions.

Implemented:
1. Added enforcement burn-rate recording rules:
   - `valdrix:enforcement_gate_error_ratio_5m`
   - `valdrix:enforcement_gate_error_ratio_30m`
   - `valdrix:enforcement_gate_error_ratio_1h`
   - `valdrix:enforcement_gate_error_ratio_6h`
   - File: `ops/alerts/enforcement_control_plane_rules.yml`
2. Added multi-window burn-rate alerts for 99.9% SLO:
   - `ValdrixEnforcementErrorBudgetBurnFast` (1h + 5m, `14.4x`, critical)
   - `ValdrixEnforcementErrorBudgetBurnSlow` (6h + 30m, `6x`, warning)
   - includes low-traffic eligibility guards to reduce false positives.
   - File: `ops/alerts/enforcement_control_plane_rules.yml`
3. Added dashboard visibility for burn-rate ratios:
   - panel: `Gate Error-Budget Burn Ratio`
   - expressions include 5m/30m/1h/6h recording rules.
   - File: `ops/dashboards/enforcement_control_plane_overview.json`
4. Added explicit release-hold policy and operator workflow:
   - runbook section `SLO Burn-Rate Policy (BSAFE-016)`
   - release promotion blocked while burn-rate alert is firing.
   - File: `docs/runbooks/enforcement_incident_response.md`
5. Updated evidence pack with burn-rate trigger methods and release-hold criteria:
   - File: `docs/ops/alert-evidence-2026-02-25.md`
6. Added test coverage:
   - observability pack test now validates burn-rate recording/alert coverage and dashboard expressions.
   - runbook test validates SLO policy and release-block semantics.
   - Files:
     - `tests/unit/ops/test_enforcement_observability_pack.py`
     - `tests/unit/ops/test_enforcement_slo_runbook.py`

Status closure:
1. `BSAFE-016`: `DONE` (baseline implemented + test-backed evidence).

Validation:
1. `uv run ruff check tests/unit/ops/test_enforcement_observability_pack.py tests/unit/ops/test_enforcement_slo_runbook.py`
2. `uv run pytest --no-cov -q tests/unit/ops/test_enforcement_observability_pack.py tests/unit/ops/test_enforcement_slo_runbook.py`
3. `uv run pytest --no-cov -q tests/unit/ops`

External reference used:
1. Google SRE Workbook burn-rate alerting guidance:
   - https://sre.google/workbook/alerting-on-slos/

## Feedback reconciliation (2026-02-25): walkthrough.md.resolved sanity check

Reviewed feedback source:
1. `/home/daretechie/.gemini/antigravity/brain/67b6d1aa-6d00-445d-883b-96f0564522a5/walkthrough.md.resolved`

### Reconciliation outcomes

1. Webhook HA gap (`Advice 2`) -> `Addressed`.
   - Evidence:
     - `helm/valdrix/templates/enforcement-validating-webhook.yaml` (fail-closed guardrails for timeout, replicas/HPA, PDB, rollout strategy, anti-affinity)
     - `helm/valdrix/templates/enforcement-webhook-pdb.yaml`
     - `helm/valdrix/values.schema.json` (non-bypassable fail-closed constraints)
     - `tests/unit/ops/test_enforcement_webhook_helm_contract.py` (pass/fail contract coverage)
2. Terraform preflight run-task terminology alignment (`Advice 3`) -> `Partial`.
   - Baseline contract is implemented (`ECP-007` done), but explicit advisory/soft/hard mapping to Terraform nomenclature remains mostly doc-level and can be expanded.
3. Policy-as-code portability to CEL/OPA (`Advice 1`) -> `Partial`.
   - `ECP-013` is closed for internal policy engine formalization.
   - CEL compatibility profile remains future hardening (tracked in benchmark map).
4. Fallback COGS monitoring (`Advice 4`) -> `Partial`.
   - Tier-aware fallback policy is implemented.
   - Explicit fallback-rate cost telemetry by tier is still a tracking item (`FIN-*` follow-on).
5. LLM output disclosure controls (`Advice 5`) -> `Partial`.
   - Input sanitization/guardrails and token ceilings exist.
   - Dedicated output PII/disclosure filter path is not yet formalized as a distinct release gate.
6. Enterprise packaging truth (`Advice 6/7`) -> `Open`.
   - Current code still has:
     - `app/shared/core/pricing.py`: `price_usd=None` for Enterprise
     - `app/shared/core/pricing.py`: `features: set(FeatureFlag)` for Enterprise
   - Existing trackers remain active: `PKG-007`, `PKG-009`.
7. Attestation verification before promotion (`Advice 8`) -> `Addressed`.
   - SBOM/provenance generation + attestations exist in `.github/workflows/sbom.yml`.
   - Deploy/release verification gate is implemented and test-backed (`BSAFE-014`).
8. Stress/chaos + burn-rate operational proof (`Advice 9`) -> `Partial`.
   - Alert pack and staged-evidence validators exist, but execution artifacts remain tracked:
     - `BSAFE-009` stress evidence,
     - `BSAFE-010` staged failure-injection execution evidence,
     - staged operational capture continuity.

### Net decision from this feedback

1. No rollback needed: current implementation direction remains correct.
2. Remaining launch-hardening focus stays on:
   - `BSAFE-009`, `BSAFE-010`,
   - `PKG-007`, `PKG-009`.

## Execution update (2026-02-25): BSAFE-009 stress evidence protocol + validator

Objective:
1. Move `BSAFE-009` from abstract requirement to executable, test-backed stress evidence protocol.
2. Ensure enforcement-specific stress evidence has deterministic acceptance criteria.

Implemented:
1. Added enforcement load profile in stress runner:
   - file: `scripts/load_test_api.py`
   - profile: `enforcement`
   - endpoint set includes:
     - `/api/v1/enforcement/policies`
     - `/api/v1/enforcement/budgets`
     - `/api/v1/enforcement/credits`
     - `/api/v1/enforcement/approvals/queue`
     - `/api/v1/enforcement/ledger`
     - `/api/v1/enforcement/exports/parity`
   - profile thresholds:
     - `max_p95_seconds=2.0`
     - `max_error_rate_percent=1.0`
     - `min_throughput_rps=0.5`
2. Added stress evidence validator:
   - file: `scripts/verify_enforcement_stress_evidence.py`
   - validates:
     - expected profile,
     - preflight pass,
     - minimum rounds,
     - enforcement endpoint presence,
     - p95/error-rate/throughput thresholds,
     - `evaluation.overall_meets_targets=true`.
3. Added stress evidence protocol doc:
   - file: `docs/ops/enforcement_stress_evidence_2026-02-25.md`
   - includes capture command + validator command + release blocking rule.
4. Added tests:
   - `tests/unit/core/test_load_test_api_script.py` (enforcement profile endpoint coverage),
   - `tests/unit/ops/test_verify_enforcement_stress_evidence.py` (validator pass/fail matrix),
   - `tests/unit/ops/test_enforcement_stress_evidence_pack.py` (doc/gate protocol assertions).
5. Added stress evidence tests to release-gate target list:
   - file: `scripts/run_enterprise_tdd_gate.py`.

Status update:
1. Historical status at this checkpoint was `IN_PROGRESS` (protocol + validator + TDD gate wiring complete).
2. Closure requirement listed here has since been completed via staged artifact capture and verifier pass on PostgreSQL.

## Execution update (2026-02-27): Release-gate determinism + PostgreSQL staged evidence reconfirmed

Objective:
1. Eliminate release-gate flakiness caused by non-boolean ambient `DEBUG` values.
2. Reconfirm `BSAFE-009`/`EVID-DB-001` style staged evidence closure on PostgreSQL backend under full release-gate execution.

Implemented:
1. Hardened gate runner environment handling:
   - forced deterministic `DEBUG=false` inside `scripts/run_enterprise_tdd_gate.py` command environment.
   - added regression test:
     - `tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py::test_run_gate_forces_debug_false_in_command_environment`
2. Re-ran full enforcement release evidence gate with PostgreSQL requirement:
   - command:
     - `uv run python3 scripts/run_enforcement_release_evidence_gate.py --stress-evidence-path docs/ops/evidence/enforcement_stress_artifact_2026-02-27.json --failure-evidence-path docs/ops/evidence/enforcement_failure_injection_2026-02-27.json --stress-required-database-engine postgresql`
   - stress verifier confirmed:
     - `database_engine=postgresql`
     - measured thresholds passed (`p95=0.0644s`, `error_rate=0.0000%`, throughput above floor).

Result:
1. Full release evidence gate passed end-to-end.
2. Test/coverage evidence:
   - `808 passed`
   - enforcement subset: `100%`
   - LLM guardrail subset: `100%`
   - analytics visibility subset: `100%`
3. Canonical status unchanged: `BSAFE-009`, `BSAFE-010`, `CI-EVID-001`, and `BENCH-DOC-001` are `DONE`; remaining open buckets stay `PKG-*` and `FIN-*`.

Validation:
1. `DEBUG=false uv run pytest --no-cov -q tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py tests/unit/supply_chain/test_run_enforcement_release_evidence_gate.py`
2. `uv run python3 scripts/run_enforcement_release_evidence_gate.py --stress-evidence-path docs/ops/evidence/enforcement_stress_artifact_2026-02-27.json --failure-evidence-path docs/ops/evidence/enforcement_failure_injection_2026-02-27.json --stress-required-database-engine postgresql`

Validation:
1. `uv run ruff check scripts/load_test_api.py scripts/verify_enforcement_stress_evidence.py tests/unit/core/test_load_test_api_script.py tests/unit/ops/test_verify_enforcement_stress_evidence.py tests/unit/ops/test_enforcement_stress_evidence_pack.py scripts/run_enterprise_tdd_gate.py`
2. `uv run mypy scripts/verify_enforcement_stress_evidence.py scripts/run_enterprise_tdd_gate.py`
3. `uv run pytest --no-cov -q tests/unit/core/test_load_test_api_script.py tests/unit/ops/test_verify_enforcement_stress_evidence.py tests/unit/ops/test_enforcement_stress_evidence_pack.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
4. `uv run python scripts/run_enterprise_tdd_gate.py --dry-run`

External references used:
1. Google SRE workbook (SLO and error-budget operations):
   - https://sre.google/workbook/alerting-on-slos/
2. Grafana k6 thresholds (performance pass/fail gating model):
   - https://grafana.com/docs/k6/latest/using-k6/thresholds/

## Execution update (2026-02-26): post-closure sanity check gate

Objective:
1. Enforce a mandatory post-closure sanity check whenever a control is marked `DONE`.
2. Treat sanity dimensions as release-critical evidence, not optional follow-up.

Implemented:
1. Added explicit post-closure sanity policy document:
   - file: `docs/ops/enforcement_post_closure_sanity_2026-02-26.md`
   - dimensions:
     - concurrency
     - observability
     - deterministic replay
     - snapshot stability
     - export integrity
     - failure modes
     - operational misconfiguration risks
2. Added validator script:
   - file: `scripts/verify_enforcement_post_closure_sanity.py`
   - validates dimension evidence across code/tests/docs and checks register/doc contract presence.
3. Wired validator into enterprise release gate:
   - file: `scripts/run_enterprise_tdd_gate.py`
4. Added tests:
   - `tests/unit/ops/test_verify_enforcement_post_closure_sanity.py`
   - `tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py` (command wiring assertion).

Sanity check coverage bound to closed controls:
1. `BSAFE-010` failure-injection evidence suite.
2. `BSAFE-015` SSDF traceability gate.
3. `BSAFE-016` burn-rate SLO release gate.

Status update:
1. Post-closure sanity automation: `DONE` (policy + validator + release-gate wiring + tests).

Validation:
1. `uv run ruff check scripts/verify_enforcement_post_closure_sanity.py tests/unit/ops/test_verify_enforcement_post_closure_sanity.py scripts/run_enterprise_tdd_gate.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
2. `uv run mypy scripts/verify_enforcement_post_closure_sanity.py scripts/run_enterprise_tdd_gate.py`
3. `uv run pytest --no-cov -q tests/unit/ops/test_verify_enforcement_post_closure_sanity.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
4. `uv run python scripts/verify_enforcement_post_closure_sanity.py --doc-path docs/ops/enforcement_post_closure_sanity_2026-02-26.md --gap-register docs/ops/enforcement_control_plane_gap_register_2026-02-23.md`

## Execution update (2026-02-26): enterprise gate LLM coverage target normalization

Objective:
1. Fix release-gate correctness for LLM/cost coverage threshold enforcement.
2. Eliminate false failures from `pytest-cov` source targeting and `coverage report` no-data behavior.

Root cause (observed):
1. `--cov` arguments using file-path strings (for example `app/shared/llm/analyzer.py`) were treated as module identifiers by `pytest-cov`, producing `module-not-imported` warnings and no coverage data for the LLM threshold step.
2. Switching to dotted module targets caused eager import of `app.shared.llm.analyzer` at pytest startup, which pulled `pandas/numpy` too early and triggered an environment-specific numpy re-import/internal initialization failure during test bootstrap.

Implemented:
1. Updated `scripts/run_enterprise_tdd_gate.py` coverage source collection to use path-based package/directory targets:
   - `app/modules/enforcement`
   - `app/shared/llm`
   - `app/modules/reporting/api/v1`
2. Kept the LLM threshold scoped to the intended release-critical subset by using an explicit `coverage report --include=...` list for:
   - `budget_fair_use.py`
   - `budget_execution.py`
   - `analyzer.py`
   - `factory.py`
   - provider adapters (`openai/anthropic/google/groq`)
   - `app/modules/reporting/api/v1/costs.py`
3. Updated `tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py` to assert the normalized include-pattern command shape.

Result:
1. Enterprise gate executes without startup import/internal errors.
2. Enforcement coverage threshold passes at `95%`.
3. Targeted LLM/costs coverage threshold passes at `93%`.

Validation:
1. `uv run ruff check scripts/run_enterprise_tdd_gate.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
2. `uv run pytest --no-cov -q tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
3. `uv run python scripts/run_enterprise_tdd_gate.py`

## Execution update (2026-02-26): analytics visibility coverage floor split from guardrail gate

Objective:
1. Separate release-critical LLM budget/enforcement guardrail coverage from analytics/reporting coverage so threshold intent is explicit.
2. Add a minimum visibility/analytics coverage floor without weakening guardrail enforcement thresholds.

Implemented:
1. Added a distinct analytics visibility coverage threshold to `scripts/run_enterprise_tdd_gate.py`:
   - `ANALYTICS_VISIBILITY_COVERAGE_FAIL_UNDER = 60`
2. Added a dedicated analytics visibility include list:
   - `app/shared/llm/analyzer.py`
   - `app/modules/reporting/api/v1/costs.py`
3. Added a third coverage report step in the enterprise gate:
   - `uv run coverage report --include=app/shared/llm/analyzer.py,app/modules/reporting/api/v1/costs.py --fail-under=60`
4. Reused the existing XML fallback path for reliability when `.coverage` is absent after the pytest stage (same threshold, no relaxation).
5. Extended `tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py` to assert:
   - the analytics coverage command is present,
   - analytics include paths are separate from the LLM guardrail subset,
   - the analytics threshold uses the dedicated constant.

Baseline and threshold rationale:
1. Measured analytics subset baseline from enterprise-gate XML before wiring the new check:
   - combined coverage (`analyzer.py` + `costs.py`) = `62.65%`
2. Set initial floor to `60%` to create a non-bypassable visibility guardrail while preserving headroom for ongoing branch hardening.
3. Guardrail subset threshold remains unchanged and separate:
   - LLM budget/enforcement guardrail subset `>= 90%`

Result:
1. Full enterprise gate passes with the new split thresholds.
2. Enterprise gate run result:
   - `415 passed`
   - enforcement coverage = `96%` (`>=95%`)
   - LLM guardrail subset coverage = `96%` (`>=90%`)
   - analytics visibility subset coverage = `63%` (`>=60%`)

Validation:
1. `uv run ruff check scripts/run_enterprise_tdd_gate.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
2. `uv run pytest --no-cov -q tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
3. `uv run python scripts/run_enterprise_tdd_gate.py --dry-run`
4. `uv run python scripts/run_enterprise_tdd_gate.py`

## Execution update (2026-02-26): analytics coverage ratchet to 85% + gate target expansion

Objective:
1. Raise analytics visibility subset coverage materially (not just by lowering/holding thresholds).
2. Tighten the analytics coverage floor from the initial `60%` bootstrap level using measured evidence.
3. Ensure branch-heavy `analyzer.py` and `costs.py` tests are part of the non-bypassable enterprise gate.

Implemented:
1. Expanded `ENTERPRISE_GATE_TEST_TARGETS` in `scripts/run_enterprise_tdd_gate.py` to include existing branch-heavy analytics suites that were already present in the repo but not counted by the enterprise gate:
   - `tests/unit/llm/test_analyzer_branch_edges.py`
   - `tests/unit/api/v1/test_costs_acceptance_payload_branches.py`
   - `tests/unit/api/v1/test_reconciliation_endpoints.py`
2. Raised analytics visibility threshold:
   - `ANALYTICS_VISIBILITY_COVERAGE_FAIL_UNDER`: `60` -> `85`
3. Kept analytics subset scope unchanged (still explicitly limited to):
   - `app/shared/llm/analyzer.py`
   - `app/modules/reporting/api/v1/costs.py`
4. Preserved all existing release-gate protections:
   - enforcement coverage floor (`95%`)
   - LLM guardrail subset floor (`90%`)
   - XML fallback threshold verification path (no threshold relaxation)

Evidence and rationale:
1. Focused analytics coverage probe (existing gate analyzer/costs tests + the three branch-heavy suites above) produced:
   - analytics subset = `90.78%` (branch-weighted)
   - lines = `812/869`
   - branches = `182/226`
2. Probe file-level analytics surfaces:
   - `app/modules/reporting/api/v1/costs.py` = `95%`
   - `app/shared/llm/analyzer.py` = `87%`
3. Based on the `90.78%` probe result, the analytics floor was ratcheted to `85%` to maintain meaningful enforcement with operational headroom.

Result (full enterprise gate):
1. Enterprise gate passes with expanded analytics branch suites and raised analytics threshold.
2. Enterprise gate run result:
   - `446 passed`
   - enforcement coverage = `96%` (`>=95%`)
   - LLM guardrail subset coverage = `96%` (`>=90%`)
   - analytics visibility subset coverage = `91%` (`>=85%`)
3. Analytics visibility floor improvement relative to initial split-gate baseline:
   - `63%` -> `91%` (same scoped subset, stronger test coverage)

Validation:
1. `uv run pytest --no-cov -q tests/unit/llm/test_analyzer_branch_edges.py`
2. `uv run pytest --no-cov -q tests/unit/api/v1/test_costs_acceptance_payload_branches.py`
3. `uv run pytest --no-cov -q tests/unit/api/v1/test_reconciliation_endpoints.py`
4. `uv run pytest -q -o addopts= tests/unit/llm/test_analyzer_exhaustive.py tests/unit/llm/test_analyzer_branch_edges.py tests/unit/api/v1/test_costs_endpoints.py tests/unit/api/v1/test_costs_acceptance_payload_branches.py tests/unit/api/v1/test_reconciliation_endpoints.py --cov=app/shared/llm --cov=app/modules/reporting/api/v1 --cov-report=xml:/tmp/analytics-coverage.xml --cov-report=term-missing`
5. `uv run python3 -c "... compute_coverage_subset_from_xml(... analyzer.py,costs.py ...)"`
6. `uv run ruff check scripts/run_enterprise_tdd_gate.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
7. `uv run pytest --no-cov -q tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
8. `uv run python scripts/run_enterprise_tdd_gate.py --dry-run`
9. `uv run python scripts/run_enterprise_tdd_gate.py`

## Execution update (2026-02-26): analytics edge-case test expansion + 95% floor ratchet + gate integrity fix

Objective:
1. Add real branch/edge-case test coverage for analytics surfaces (`analyzer.py` and `costs.py`) beyond gate-target expansion.
2. Ratchet analytics visibility coverage floor again using measured evidence.
3. Fix a release-gate integrity defect where XML fallback could false-pass if no subset rows matched.

Implemented (analytics tests):
1. Expanded `tests/unit/llm/test_analyzer_branch_edges.py` with additional helper/edge-path coverage for:
   - cached prompt short-circuit (`_get_prompt` cached path),
   - prompt YAML load executor exception fallback,
   - `_resolve_positive_limit` invalid/below-min/cap paths,
   - `_record_to_date` dict/object/invalid-string branches,
   - `_apply_tier_analysis_shape_limits` no-limit path and deterministic truncation path,
   - `_bind_output_token_ceiling` double-`TypeError` terminal return path.
2. Expanded `tests/unit/api/v1/test_costs_acceptance_payload_branches.py` with direct `costs.py` wrapper and endpoint branch coverage for:
   - wrapper delegates (`_is_connection_active`, `_build_provider_recency_summary`, async delegate wrappers),
   - provider-filter blank + invalid branches,
   - direct endpoint date-window validation branches (`attribution/coverage`, `canonical/quality`, `reconciliation/restatements`),
   - canonical-quality alert failure branch (`alert_error`/`alert_triggered=False`),
   - acceptance KPI JSON return path,
   - `_compute_acceptance_kpis_payload` invalid-window rejection and low-tier unavailable feature KPI branches.

Implemented (gate integrity hardening):
1. Hardened `scripts/run_enterprise_tdd_gate.py` XML fallback verifier:
   - now fails if a coverage subset matches zero measurable lines/branches (prevents false-pass on empty subset matches).
2. Isolated enterprise gate coverage data file:
   - `run_gate()` now runs all commands with `COVERAGE_FILE=.coverage.enterprise-gate`
   - prevents collisions/corruption from shared `.coverage` state during local/dev concurrent coverage runs.
3. Extended gate-runner tests:
   - assert `subprocess.run(..., env=...)` carries isolated coverage file,
   - assert XML fallback raises on zero-match subsets.

Evidence and rationale:
1. Focused analytics coverage probe after new tests (same scoped subset):
   - analytics subset = `96.07%` (branch-weighted)
   - lines = `848/869`
   - branches = `204/226`
2. Focused probe file-level analytics surfaces:
   - `app/modules/reporting/api/v1/costs.py` = `99%`
   - `app/shared/llm/analyzer.py` = `93%`
3. Based on the `96.07%` probe result, analytics visibility floor was ratcheted:
   - `ANALYTICS_VISIBILITY_COVERAGE_FAIL_UNDER`: `85` -> `95`

Result (full enterprise gate, after gate-integrity fix):
1. Enterprise gate passes under the raised analytics threshold and isolated coverage-data path.
2. Enterprise gate run result:
   - `456 passed`
   - enforcement coverage = `96%` (`>=95%`)
   - LLM guardrail subset coverage = `96%` (`>=90%`)
   - analytics visibility subset coverage = `96%` (`>=95%`)
3. False-pass condition removed:
   - no fallback success on zero-match XML subsets,
   - no shared `.coverage` corruption warnings affecting gate threshold checks.

Validation:
1. `uv run ruff check tests/unit/llm/test_analyzer_branch_edges.py tests/unit/api/v1/test_costs_acceptance_payload_branches.py`
2. `uv run pytest --no-cov -q tests/unit/llm/test_analyzer_branch_edges.py tests/unit/api/v1/test_costs_acceptance_payload_branches.py`
3. `uv run pytest -q -o addopts= tests/unit/llm/test_analyzer_exhaustive.py tests/unit/llm/test_analyzer_branch_edges.py tests/unit/api/v1/test_costs_endpoints.py tests/unit/api/v1/test_costs_acceptance_payload_branches.py tests/unit/api/v1/test_reconciliation_endpoints.py --cov=app/shared/llm --cov=app/modules/reporting/api/v1 --cov-report=xml:/tmp/analytics-coverage.xml --cov-report=term-missing`
4. `uv run python3 -c "... compute_coverage_subset_from_xml(... analyzer.py,costs.py ...)"`
5. `uv run ruff check scripts/run_enterprise_tdd_gate.py tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
6. `uv run pytest --no-cov -q tests/unit/supply_chain/test_enterprise_tdd_gate_runner.py`
7. `uv run python scripts/run_enterprise_tdd_gate.py --dry-run`
8. `uv run python scripts/run_enterprise_tdd_gate.py`

## Execution update (2026-02-25): BSAFE-014 attestation verification gate

Objective:
1. Enforce deploy/release-time verification of generated SBOM/provenance attestations.
2. Fail the workflow if attestation verification output is absent/invalid.

Implemented:
1. Added dedicated attestation verification script:
   - validates GitHub CLI version baseline for safe verification semantics (`>= 2.67.0`),
   - runs `gh attestation verify` for each artifact with explicit signer workflow constraint,
   - requires parseable non-empty JSON verification output for each subject.
   - File: `scripts/verify_supply_chain_attestations.py`
2. Wired non-bypassable verification step into SBOM workflow:
   - verifies attestation for:
     - `./sbom/valdrix-python-sbom.json`
     - `./sbom/valdrix-container-sbom.json`
     - `./provenance/supply-chain-manifest.json`
   - enforces signer workflow binding: `.github/workflows/sbom.yml`.
   - File: `.github/workflows/sbom.yml`
3. Added script-level and workflow-level tests:
   - `tests/unit/supply_chain/test_verify_supply_chain_attestations.py`
   - `tests/unit/supply_chain/test_supply_chain_provenance_workflow.py` (verification step wiring assertions)

Validation:
1. `uv run ruff check scripts/verify_supply_chain_attestations.py tests/unit/supply_chain/test_verify_supply_chain_attestations.py tests/unit/supply_chain/test_supply_chain_provenance_workflow.py`
2. `uv run mypy scripts/verify_supply_chain_attestations.py`
3. `uv run pytest --no-cov -q tests/unit/supply_chain/test_verify_supply_chain_attestations.py tests/unit/supply_chain/test_supply_chain_provenance_workflow.py tests/unit/supply_chain/test_supply_chain_provenance.py`

## Execution update (2026-02-25): fail-closed rollout strategy + anti-affinity hardening

Objective:
1. Prevent unsafe API rollout behavior while admission webhook runs in fail-closed mode.
2. Make node-level separation an explicit fail-closed precondition.

Implemented:
1. Added explicit API deployment strategy values:
   - `deploymentStrategy.type`
   - `deploymentStrategy.rollingUpdate.maxUnavailable`
   - `deploymentStrategy.rollingUpdate.maxSurge`
   - File: `helm/valdrix/values.yaml`
2. Wired deployment template to render explicit strategy:
   - File: `helm/valdrix/templates/deployment.yaml`
3. Added fail-closed guardrails in webhook template:
   - reject non-`RollingUpdate` strategy,
   - reject `maxUnavailable != 0`,
   - reject `maxSurge < 1`,
   - reject missing hard anti-affinity requirements,
   - reject anti-affinity not anchored to `kubernetes.io/hostname`.
   - File: `helm/valdrix/templates/enforcement-validating-webhook.yaml`
4. Extended values schema for non-bypassable validation:
   - root `deploymentStrategy` contract,
   - root `affinity.podAntiAffinity.requiredDuringSchedulingIgnoredDuringExecution`,
   - fail-closed conditional checks for rollout strategy and host anti-affinity.
   - File: `helm/valdrix/values.schema.json`
5. Strengthened defaults for hard anti-affinity in values:
   - `affinity.podAntiAffinity.requiredDuringSchedulingIgnoredDuringExecution`.
   - File: `helm/valdrix/values.yaml`
6. Expanded helm contract tests:
   - reject fail-closed with `Recreate` strategy,
   - reject fail-closed without host-level hard anti-affinity,
   - keep pass paths for fail-closed manual/HPA HA.
   - File: `tests/unit/ops/test_enforcement_webhook_helm_contract.py`
7. Updated pre-provision runbook guardrail checklist for rollout strategy and anti-affinity.
   - File: `docs/runbooks/enforcement_preprovision_integrations.md`

Validation:
1. `helm lint helm/valdrix`
2. `helm template valdrix-dev helm/valdrix`
3. `uv run ruff check tests/unit/ops/test_enforcement_webhook_helm_contract.py`
4. `uv run pytest --no-cov -q tests/unit/ops/test_enforcement_webhook_helm_contract.py`
5. `uv run pytest --no-cov -q tests/unit/ops`

## Execution update (2026-02-25): fail-closed webhook disruption-budget hardening

Objective:
1. Ensure fail-closed admission mode remains available during node drain/voluntary disruptions.
2. Make disruption-budget posture a chart-level, test-backed contract.

Implemented:
1. Added webhook-adjacent API PodDisruptionBudget template:
   - renders when `enforcementWebhook.enabled=true` and `enforcementWebhook.podDisruptionBudget.enabled=true`.
   - targets API pods (`app.kubernetes.io/component=api`) with configured `maxUnavailable`.
   - File: `helm/valdrix/templates/enforcement-webhook-pdb.yaml`
2. Added values contract for disruption budget:
   - `enforcementWebhook.podDisruptionBudget.enabled`
   - `enforcementWebhook.podDisruptionBudget.maxUnavailable`
   - File: `helm/valdrix/values.yaml`
3. Extended schema and guardrails for fail-closed mode:
   - `failurePolicy=Fail` now requires `podDisruptionBudget.enabled=true`,
   - `failurePolicy=Fail` now requires `podDisruptionBudget.maxUnavailable <= 1`.
   - File: `helm/valdrix/values.schema.json`
4. Added render-time template assertions for same constraints:
   - explicit `fail` on unsafe fail-closed PDB configuration.
   - File: `helm/valdrix/templates/enforcement-validating-webhook.yaml`
5. Expanded ops tests for PDB rendering and rejection paths:
   - verifies PDB resource renders in fail-closed contract,
   - verifies fail-open profile does not render PDB by default,
   - verifies schema rejects fail-closed with `maxUnavailable > 1`,
   - verifies schema rejects fail-closed with PDB disabled.
   - File: `tests/unit/ops/test_enforcement_webhook_helm_contract.py`
6. Updated runbook rollout profile and guardrail list for PDB requirements:
   - File: `docs/runbooks/enforcement_preprovision_integrations.md`

Validation:
1. `helm lint helm/valdrix`
2. `helm template valdrix-dev helm/valdrix`
3. `uv run ruff check tests/unit/ops/test_enforcement_webhook_helm_contract.py`
4. `uv run pytest --no-cov -q tests/unit/ops/test_enforcement_webhook_helm_contract.py`
5. `uv run pytest --no-cov -q tests/unit/ops`

## Execution update (2026-03-01): VAL-ADAPT-002+ no-compat dispatch cleanup and CUR discovery evidence refresh

Implemented:
1. Removed production compatibility facade for license native vendor ops:
   - deleted `app/shared/adapters/license_vendor_ops.py`.
2. Rewired native vendor dispatch to direct vendor modules:
   - `app/shared/adapters/license_native_dispatch.py` now binds directly to:
     - `license_vendor_verify.py`
     - `license_vendor_google.py`
     - `license_vendor_microsoft.py`
     - `license_vendor_github.py`
     - `license_vendor_slack.py`
     - `license_vendor_zoom.py`
     - `license_vendor_salesforce.py`
   - stream/activity wrappers preserve deterministic normalization contracts (`feed_utils.as_float`, `feed_utils.parse_timestamp`).
3. Removed compatibility-facade callsites from adapter tests:
   - `tests/unit/services/adapters/test_cloud_plus_adapters.py`
   - `tests/unit/services/adapters/test_license_activity_and_revoke.py`
   - `tests/unit/services/adapters/test_license_verification_stream_branches.py`
4. Refreshed same-pass evidence for Cloud+ CUR resource-discovery hardening:
   - `app/shared/adapters/aws_cur.py::discover_resources` projection path and fail-closed error handling remain green.

Validation:
1. `uv run ruff check app/shared/adapters/license_native_dispatch.py tests/unit/services/adapters/test_cloud_plus_adapters.py tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/services/adapters/test_license_verification_stream_branches.py tests/unit/shared/adapters/test_license_native_dispatch.py`
2. `uv run mypy app/shared/adapters/license_native_dispatch.py --hide-error-context --no-error-summary`
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/shared/adapters/test_license_native_dispatch.py tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/services/adapters/test_license_verification_stream_branches.py tests/unit/services/adapters/test_cloud_plus_adapters.py` -> `97 passed`
4. `uv run ruff check app/shared/adapters/aws_cur.py tests/unit/shared/adapters/test_aws_cur.py`
5. `uv run mypy app/shared/adapters/aws_cur.py --hide-error-context --no-error-summary`
6. `DEBUG=false uv run pytest -q --no-cov tests/unit/shared/adapters/test_aws_cur.py` -> `28 passed`
7. `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py` -> `883 passed`

Post-closure sanity (release-critical):
1. Concurrency: immutable dispatch maps; no mutable compatibility seam state.
2. Observability: structured native-dispatch and discovery error logs unchanged and still emitted.
3. Deterministic replay: table-driven vendor routing; deterministic wrapper bindings for parse/float normalization.
4. Snapshot stability: no outward API schema changes.
5. Export integrity: cost/resource usage payload fields unchanged.
6. Failure modes: unsupported vendor paths remain explicit fail-closed.
7. Operational misconfiguration: native-auth/vendor and connector-config guardrails remain enforced.

## Execution update (2026-03-01): adapter error-state consistency hardening + stale trace cleanup

Implemented:
1. Standardized adapter operation lifecycle for discovery/usage across cloud and Cloud+ adapters:
   - `discover_resources` and `get_resource_usage` now clear stale `last_error` at operation start.
2. Hardened fail-closed error visibility in AWS multitenant discovery:
   - unsupported-region and plugin-not-found branches now set explicit `last_error` messages before returning `[]`.
3. Ensured discovery exception paths set sanitized adapter errors consistently:
   - Azure and GCP `discover_resources` now set contextual `last_error` on failures.
4. Removed stale architecture trace reference to deleted compatibility module:
   - updated landing capability backend trace doc to point at `license_native_dispatch.py` and `license_vendor_*.py`.

Validation:
1. `uv run ruff check app/shared/adapters/aws_cur.py app/shared/adapters/aws_multitenant.py app/shared/adapters/azure.py app/shared/adapters/gcp.py app/shared/adapters/saas.py app/shared/adapters/platform.py app/shared/adapters/hybrid.py app/shared/adapters/license.py tests/unit/shared/adapters/test_aws_cur.py tests/unit/shared/adapters/test_aws_multitenant_branch_paths.py tests/unit/shared/adapters/test_azure_adapter.py tests/unit/shared/adapters/test_gcp_adapter.py tests/unit/services/adapters/test_cloud_plus_adapters.py tests/unit/services/adapters/test_license_activity_and_revoke.py`
2. `uv run mypy app/shared/adapters/aws_cur.py app/shared/adapters/aws_multitenant.py app/shared/adapters/azure.py app/shared/adapters/gcp.py app/shared/adapters/saas.py app/shared/adapters/platform.py app/shared/adapters/hybrid.py app/shared/adapters/license.py --hide-error-context --no-error-summary`
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/shared/adapters/test_aws_cur.py tests/unit/shared/adapters/test_aws_multitenant_branch_paths.py tests/unit/shared/adapters/test_azure_adapter.py tests/unit/shared/adapters/test_gcp_adapter.py tests/unit/services/adapters/test_cloud_plus_adapters.py tests/unit/services/adapters/test_license_activity_and_revoke.py` -> `128 passed`
4. `DEBUG=false uv run python3 scripts/run_enterprise_tdd_gate.py` -> `883 passed`

Post-closure sanity (release-critical):
1. Concurrency: stale adapter error state is reset at operation entry across adapter discovery/usage surfaces.
2. Observability: discovery and fail-closed branches emit deterministic structured logs plus sanitized operator-facing `last_error`.
3. Deterministic replay: operation state transitions are explicit and consistent (`clear -> execute -> set on failure`).
4. Snapshot stability: no endpoint response-schema drift introduced.
5. Export integrity: usage/cost/export payload structure unchanged.
6. Failure modes: previously silent empty-return branches now include explicit error context where applicable.
7. Operational misconfiguration: unsupported AWS region/plugin mapping now produces actionable operator errors.

## Execution update (2026-03-01): stream seam cleanup + sitemap determinism hardening

Implemented:
1. Removed remaining private stream-wrapper seams from cloud and Cloud+ adapters:
   - deleted `_stream_cost_and_usage_impl` method usage from:
     - `app/shared/adapters/azure.py`
     - `app/shared/adapters/gcp.py`
     - `app/shared/adapters/license.py`
   - streaming now flows only through public `stream_cost_and_usage(...)` contracts.
2. Updated adapter coverage to lock public-stream behavior:
   - `tests/unit/services/adapters/test_license_verification_stream_branches.py` migrated from private method probing to public streaming APIs.
3. Hardened sitemap route for deterministic replay and snapshot stability:
   - `dashboard/src/routes/sitemap.xml/+server.ts` no longer emits request-time dynamic `lastmod`.
   - `<lastmod>` now emits only when explicitly configured via valid env (`PUBLIC_SITEMAP_LASTMOD` or `SITEMAP_LASTMOD`).
4. Added explicit deterministic sitemap tests:
   - `dashboard/src/routes/sitemap.xml/sitemap.server.test.ts` verifies unset/valid/invalid lastmod configuration branches.

Validation:
1. `uv run ruff check app/shared/adapters/azure.py app/shared/adapters/gcp.py app/shared/adapters/license.py tests/unit/services/adapters/test_license_verification_stream_branches.py`
2. `uv run mypy app/shared/adapters/azure.py app/shared/adapters/gcp.py app/shared/adapters/license.py --hide-error-context --no-error-summary`
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/services/adapters/test_license_verification_stream_branches.py tests/unit/shared/adapters/test_azure_adapter.py tests/unit/shared/adapters/test_gcp_adapter.py tests/unit/shared/adapters/test_aws_multitenant_branch_paths.py tests/unit/shared/adapters/test_aws_cur.py tests/unit/services/adapters/test_cloud_plus_adapters.py tests/unit/services/adapters/test_license_activity_and_revoke.py` -> `156 passed`
4. `cd dashboard && npm run test:unit -- --run` -> includes `src/routes/sitemap.xml/sitemap.server.test.ts` pass.
5. `DEBUG=false uv run python scripts/run_enterprise_tdd_gate.py` -> `883 passed`

Post-closure sanity (release-critical):
1. Concurrency: stream invocation paths are now consolidated on public interfaces, reducing seam-level race/error leakage risk.
2. Observability: adapter stream fallback/error logging and `last_error` propagation remain intact.
3. Deterministic replay: sitemap output is deterministic by default (no request-time clock writes).
4. Snapshot stability: sitemap snapshots are stable across replays unless explicitly versioned by operator-configured `lastmod`.
5. Export integrity: XML and adapter payload contracts remain compatible; this pass changed execution topology, not schema.
6. Failure modes: invalid `lastmod` values are safely ignored, preventing malformed metadata export.
7. Operational misconfiguration: lastmod is now explicit configuration rather than implicit runtime behavior.

## Execution update (2026-03-01): license unsupported-native fail-closed hardening + Playwright backend env guard

Implemented:
1. Hardened `LicenseAdapter` native-auth behavior for unsupported vendors:
   - `app/shared/adapters/license.py`
   - `list_users_activity()` now fail-closes (sets `last_error`, returns `[]`) when `auth_method=api_key|oauth` and vendor is not supported for native auth.
   - `stream_cost_and_usage()` now fail-closes in the same condition and no longer silently falls back to manual feed rows.
   - extracted `_unsupported_native_vendor_message()` to keep verify/activity/stream messaging consistent.
2. Added regression coverage for unsupported-native fail-closed behavior:
   - `tests/unit/services/adapters/test_license_activity_and_revoke.py`
   - `tests/unit/services/adapters/test_license_verification_stream_branches.py`
3. Hardened dashboard e2e backend startup command:
   - `dashboard/playwright.config.ts` backend `webServer` command now enforces `DEBUG=false` to avoid invalid boolean env parsing from inherited shell values.

Validation:
1. `uv run ruff check app/shared/adapters/license.py tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/services/adapters/test_license_verification_stream_branches.py`
2. `uv run mypy app/shared/adapters/license.py --hide-error-context --no-error-summary`
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/services/adapters/test_license_activity_and_revoke.py tests/unit/services/adapters/test_license_verification_stream_branches.py` -> `49 passed`
4. `cd dashboard && npx playwright test --list` -> passed
5. `cd dashboard && npm run test:e2e -- e2e/critical-paths.spec.ts --grep "robots.txt references sitemap"` -> `1 passed`
6. `DEBUG=false uv run python scripts/run_enterprise_tdd_gate.py` -> `883 passed`

Post-closure sanity (release-critical):
1. Concurrency: unsupported-native branches now terminate deterministically without manual-feed fallback races.
2. Observability: unsupported-native auth paths emit explicit warnings and operator-facing `last_error` context.
3. Deterministic replay: native-auth mismatch behavior is now deterministic across verify/activity/stream flows.
4. Snapshot stability: no payload schema changes; behavior hardening only.
5. Export integrity: existing adapter/export contracts remain unchanged.
6. Failure modes: unsupported native-auth vendors can no longer silently execute feed fallback in stream paths.
7. Operational misconfiguration: Playwright backend startup now tolerates inherited non-boolean `DEBUG` env values.

## Execution update (2026-03-01): pricing-tier runtime cache hardening + DB dependency no-compat cleanup

Implemented:
1. Completed `VAL-CORE-003` performance hardening with explicit runtime cache controls:
   - `app/shared/core/pricing.py`
   - added bounded tenant-tier runtime cache (`TTL=60s`, `max_entries=4096`) for `get_tenant_tier(...)`,
   - added `clear_tenant_tier_cache()` for deterministic invalidation and test/runtime control.
2. Enforced plan-sync cache coherency:
   - `app/modules/billing/domain/billing/entitlement_policy.py`
   - `sync_tenant_plan(...)` now invalidates tenant tier runtime cache immediately after successful plan update.
3. Removed remaining DB dependency compatibility indirection seams:
   - `app/shared/db/session.py`
   - removed `_get_db_impl_ref` and `_get_system_db_impl_ref` alias proxies,
   - `get_db()` / `get_system_db()` now delegate directly to concrete implementation generators.
4. Updated unit tests to patch direct DB implementation seams and codified cache behavior:
   - `tests/unit/db/test_session_branch_paths_2.py`
   - `tests/unit/core/test_pricing_deep.py`
   - `tests/unit/services/billing/test_entitlement_policy.py`

Validation:
1. `uv run ruff check app/shared/core/pricing.py app/modules/billing/domain/billing/entitlement_policy.py tests/unit/core/test_pricing_deep.py tests/unit/services/billing/test_entitlement_policy.py`
2. `uv run mypy app/shared/core/pricing.py app/modules/billing/domain/billing/entitlement_policy.py --hide-error-context --no-error-summary`
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/core/test_pricing_deep.py tests/unit/services/billing/test_entitlement_policy.py` -> `26 passed`
4. `uv run ruff check app/shared/db/session.py tests/unit/db/test_session_branch_paths_2.py`
5. `uv run mypy app/shared/db/session.py --hide-error-context --no-error-summary`
6. `DEBUG=false uv run pytest -q --no-cov tests/unit/db/test_session_branch_paths_2.py tests/unit/db/test_session.py tests/unit/core/test_session.py tests/security/test_rls_security.py` -> `34 passed`
7. `DEBUG=false uv run python scripts/run_enterprise_tdd_gate.py` -> `883 passed`

Post-closure sanity (release-critical):
1. Concurrency: tenant-tier runtime cache writes/evictions are lock-guarded; direct DB dependency delegation removes mutable alias seam risk.
2. Observability: cache and DB session failure/edge logs remain explicit; no silent branch introduced.
3. Deterministic replay: cache invalidation is explicit and deterministic (`clear_tenant_tier_cache` + post-plan-sync invalidation).
4. Snapshot stability: no endpoint/export schema changes; runtime behavior hardening only.
5. Export integrity: report/enforcement export contracts unchanged.
6. Failure modes: stale-tier risk reduced through bounded TTL + explicit invalidation; DB dependency behavior remains fail-closed where required.
7. Operational misconfiguration: removal of compatibility alias indirection reduces override drift and hidden dependency-hooking mismatches.

## Execution update (2026-03-01): webhook proxy trust fail-closed hardening + DB session lifecycle cleanup

Implemented:
1. Hardened webhook source-IP extraction against proxy-hop/XFF misconfiguration drift:
   - `app/modules/billing/api/v1/billing.py`
   - `_extract_client_ip()` now accepts XFF only when:
     - proxy headers are explicitly enabled,
     - request peer is inside configured trusted proxy CIDRs,
     - valid forwarded chain is present.
2. Added explicit trusted-proxy CIDR policy controls in runtime configuration:
   - `app/shared/core/config.py`
   - introduced `TRUSTED_PROXY_CIDRS`,
   - environment safety validation now rejects invalid CIDRs and requires explicit CIDR allowlist when `TRUST_PROXY_HEADERS=true` in staging/production.
3. Removed redundant manual DB session close paths:
   - `app/shared/db/session.py`
   - `_get_db_impl()` and `_get_system_db_impl()` now rely solely on `async with` lifecycle management (no duplicate manual `session.close()` in `finally`).
4. Updated tests for security and lifecycle behavior:
   - `tests/unit/api/v1/test_billing.py`
   - `tests/unit/reporting/test_billing_api.py`
   - `tests/unit/core/test_config_branch_paths.py`
   - `tests/unit/db/test_session.py`

Validation:
1. `uv run ruff check app/shared/core/config.py app/modules/billing/api/v1/billing.py app/shared/db/session.py tests/unit/core/test_config_branch_paths.py tests/unit/api/v1/test_billing.py tests/unit/reporting/test_billing_api.py tests/unit/db/test_session.py`
2. `uv run mypy app/shared/core/config.py app/modules/billing/api/v1/billing.py app/shared/db/session.py --hide-error-context --no-error-summary`
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/core/test_config_branch_paths.py tests/unit/api/v1/test_billing.py tests/unit/reporting/test_billing_api.py tests/unit/db/test_session.py tests/unit/db/test_session_branch_paths_2.py tests/unit/shared/db/test_session_coverage.py tests/security/test_rls_security.py` -> `105 passed`
4. `DEBUG=false uv run python scripts/run_enterprise_tdd_gate.py` -> `883 passed`

Post-closure sanity (release-critical):
1. Concurrency: session lifecycle now has a single owner (`async with`) and avoids redundant close-path races.
2. Observability: invalid CIDR and proxy trust branches emit explicit warning/error telemetry.
3. Deterministic replay: client-IP attribution behavior is now policy-driven and deterministic under explicit trusted-proxy CIDRs.
4. Snapshot stability: no response schema changes; only security/lifecycle behavior tightened.
5. Export integrity: enforcement/reporting export contracts unchanged.
6. Failure modes: misconfigured proxy trust now fails closed for XFF consumption.
7. Operational misconfiguration: staging/production with proxy-header trust now requires explicit trusted CIDRs.

## Execution update (2026-03-01): pricing scalar-contract cleanup + Paystack IP allowlist config hardening

Implemented:
1. Removed legacy async-scalar compatibility branch in tenant-tier lookup:
   - `app/shared/core/pricing.py`
   - `get_tenant_tier(...)` now enforces a single scalar contract path,
   - invalid scalar result types fail closed to `FREE` with explicit telemetry.
2. Made webhook source allowlist fully config-governed:
   - `app/shared/core/config.py`
   - introduced/validated `PAYSTACK_WEBHOOK_ALLOWED_IPS` (non-empty, valid IPs).
3. Removed hardcoded Paystack webhook IP constants from runtime webhook handler path:
   - `app/modules/billing/api/v1/billing_ops.py`
   - origin authorization now uses validated runtime config.
4. Updated and tightened test coverage:
   - `tests/unit/core/test_pricing_deep.py`
   - `tests/unit/core/test_config_branch_paths.py`
   - `tests/unit/reporting/test_billing_api.py`
   - `tests/unit/api/v1/test_billing.py`

Validation:
1. `uv run ruff check app/shared/core/pricing.py app/shared/core/config.py app/modules/billing/api/v1/billing_ops.py tests/unit/core/test_pricing_deep.py tests/unit/core/test_config_branch_paths.py tests/unit/reporting/test_billing_api.py`
2. `uv run mypy app/shared/core/pricing.py app/shared/core/config.py app/modules/billing/api/v1/billing_ops.py --hide-error-context --no-error-summary`
3. `DEBUG=false uv run pytest -q --no-cov tests/unit/core/test_pricing_deep.py tests/unit/core/test_config_branch_paths.py tests/unit/reporting/test_billing_api.py tests/unit/api/v1/test_billing.py` -> `91 passed`
4. `DEBUG=false uv run python scripts/run_enterprise_tdd_gate.py` -> passed (exit `0`)

Post-closure sanity (release-critical):
1. Concurrency: no new shared mutable state or race-prone compatibility seams introduced.
2. Observability: invalid scalar and webhook allowlist misconfiguration paths now produce explicit operator-facing telemetry.
3. Deterministic replay: pricing tier resolution now follows a single deterministic scalar contract.
4. Snapshot stability: no schema or payload format changes.
5. Export integrity: enforcement/reporting export contracts remain unchanged.
6. Failure modes: malformed paystack allowlists and invalid tier lookup result shapes fail closed.
7. Operational misconfiguration: webhook origin policy is now centralized in validated settings.

## Execution update (2026-03-01): canonical closure sync for VAL-ADAPT-002/002+ and VAL-FE-*

Implemented:
1. Added canonical status disposition for adapter decomposition track:
   - `VAL-ADAPT-002`: `CLOSED`.
   - `VAL-ADAPT-002+`: `CLOSED`.
2. Explicitly superseded earlier staged notes that marked `VAL-ADAPT-002+` as open maintainability backlog during intermediate decomposition batches.
3. Added validated frontend issue dispositions from `VALDRX_CODEBASE_AUDIT_2026-02-28.md.resolved`:
   - `VAL-FE-001` (mobile horizontal overflow): `CLOSED`.
   - `VAL-FE-002` (`sr-only` clipping/layout break): `CLOSED`.
   - `VAL-FE-003` (off-screen mobile header action): `CLOSED`.
   - `VAL-FE-004` (hero toggle clipping): `CLOSED`.
4. Bound frontend closure to machine-checkable regression tests:
   - `dashboard/e2e/landing-layout-audit.spec.ts`.

Validation:
1. `cd dashboard && npm run test:e2e -- e2e/landing-layout-audit.spec.ts`
2. Result: `2 passed` (`horizontal overflow + sr-only clipping` and `mobile header action on-screen` checks green).

Post-closure sanity (release-critical):
1. Concurrency: no new mutable runtime state introduced by this disposition sync.
2. Observability: `VAL-FE-*` layout regressions remain machine-detected by dedicated Playwright checks.
3. Deterministic replay: viewport-specific landing-layout assertions are deterministic.
4. Snapshot stability: no backend/API contract changes in this batch.
5. Export integrity: enforcement/reporting/export payload schemas remain unchanged.
6. Failure modes: overflow/sr-only/off-screen/toggle clipping regressions fail fast in CI.
7. Operational misconfiguration: no new configuration knobs introduced in this pass.
