# Competitive Parity Evidence Register (2026-02-19)

This register tracks which product/marketing claims are currently evidence-backed in the repository.

## Rules for external messaging
- Only publish claims marked `evidence-backed`.
- Claims marked `partial` require qualifiers in copy.
- Claims marked `unverified` must not be used in public comparisons.

## Claim Register

| Claim | Status | Evidence (Code) | Evidence (Tests / Checks) | Notes |
|---|---|---|---|---|
| AWS Cost Explorer API calls are disabled in platform paths | evidence-backed | `app/shared/adapters/factory.py`, `cloudformation/valdrix-role.yaml` | `tests/unit/core/test_competitive_guardrails.py::test_no_cost_explorer_client_usage_in_app_code`, `tests/unit/core/test_competitive_guardrails.py::test_aws_role_template_excludes_cost_explorer_actions` | CE is blocked by design; CUR is required for ingestion. |
| AWS customer IAM template excludes `ce:*` permissions | evidence-backed | `cloudformation/valdrix-role.yaml` | `tests/unit/core/test_competitive_guardrails.py::test_aws_role_template_excludes_cost_explorer_actions` | Template comments also document this guardrail. |
| GPU-aware idle instance detection is implemented | evidence-backed | `app/modules/optimization/adapters/aws/plugins/compute.py` | `tests/unit/core/test_competitive_guardrails.py::test_gpu_idle_detection_families_include_high_cost_gpu_lines` | Guardrail asserts required GPU family coverage remains present. |
| Stage A domain discovery is broadly available | evidence-backed | `app/shared/core/pricing.py` | `tests/unit/core/test_competitive_guardrails.py::test_discovery_tier_guardrail_stage_a_vs_stage_b`, `tests/unit/core/test_pricing_deep.py::test_discovery_feature_split_by_tier` | Stage A should remain a prefill flow. |
| Stage B IdP deep scan is Pro+ only | evidence-backed | `app/shared/core/pricing.py`, `app/modules/governance/api/v1/settings/connections.py` | `tests/unit/core/test_competitive_guardrails.py::test_discovery_tier_guardrail_stage_a_vs_stage_b`, `tests/unit/governance/test_connections_discovery_api.py::test_deep_scan_requires_cloud_plus_tier` | Hard tier gate enforced in API path. |
| Discovery wizard is prefill guidance, not guaranteed full inventory | evidence-backed | `app/shared/connections/discovery.py`, `docs/architecture/discovery_wizard.md` | Manual product copy review | UI and docs should use “likely/best-effort/prefill” wording. |
| BYOK is enabled on all tiers | evidence-backed | `app/shared/core/pricing.py` (`limits.byok_enabled`) | `tests/unit/core/test_pricing_deep.py` and tier config assertions | Fair-use and daily limits still apply by tier. |
| “Zero hidden cloud API costs” | partial | CE disabled and CUR path are enforced | No end-to-end metered cost benchmark in repo | Market as “cost-minimized architecture” unless measured customer-side cost telemetry is published. |
| “Detects 11+ zombie categories” | partial | Plugin registry and provider plugin modules exist | Existing plugin tests cover subsets, not a single canonical category count assertion | Keep wording as “broad multi-category detection” unless count guardrail is added. |
| Competitor dollar/feature comparisons | unverified | N/A (external data) | N/A | Requires dated third-party sources and methodology before publishing. |

## Operational checklist before publishing claims
1. Re-run guardrail suite:
   - `uv run pytest -q --no-cov tests/unit/core/test_competitive_guardrails.py`
2. Re-run discovery/tiering regression:
   - `uv run pytest -q --no-cov tests/unit/core/test_pricing_deep.py tests/unit/governance/test_connections_discovery_api.py`
3. Ensure UI copy uses qualified language for `partial` claims.

## Open gaps
- SOC2 claim can only be upgraded to evidence-backed after audit completion artifacts are available.
- Auto-scaling and deep Kubernetes parity remain roadmap items, not parity claims.
- Competitor comparisons require external, timestamped references.

Execution roadmap for these gap tracks:
- `docs/ops/gap_tracks_roadmap_2026-02-19.md`
