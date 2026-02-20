# Valdrix Roadmap Progress Snapshot

Date: **2026-02-20**

This is a progress archive (what shipped + evidence pointers). For the previous snapshot, see:
- `reports/roadmap/ROADMAP_PROGRESS_2026-02-15.md`

## Completed Since 2026-02-15

### 1) Acceptance Evidence Capture Closure (Production Sign-off Bundle)
Acceptance capture was re-run against the live API and completed with a full pass.

- Run:
  - `scripts/capture_acceptance_evidence.py --url "http://127.0.0.1:8000" --token "$VALDRIX_TOKEN"`
- Result:
  - `26/26 ok`
- Evidence bundle:
  - `reports/acceptance/20260220T160636Z/`
- Primary manifest:
  - `reports/acceptance/20260220T160636Z/manifest.json`

### 2) SSO Federation Operator Smoke + Publish Validation
SSO federation smoke validation was executed successfully after tier-aligned sign-off configuration.

- Run:
  - `scripts/smoke_test_sso_federation.py --url "http://127.0.0.1:8000" --token "$VALDRIX_TOKEN" --email "admin@yourcompany.com" --publish --timeout 60`
- Result:
  - `passed: true`
  - `public.sso_discovery: 200`
  - `admin.sso_validation: 200`
  - Publish succeeded (no API publish error returned)
- Validation notes:
  - Discovery currently returns `available=false` / `reason=sso_not_configured_for_domain` for `yourcompany.com`, which is expected when federation is disabled and no active domain mapping exists.

### 3) Operator Reliability Hardening (Already Landed, Re-validated)
The following runtime hardening previously added for operator workflows was re-validated during this sign-off cycle:

- SSO smoke script resilience:
  - `scripts/smoke_test_sso_federation.py`
  - Adds base URL preflight handling, cleaner connectivity error exits, and configurable `--timeout`.
- Public discovery timeout/error fail-safe:
  - `app/modules/governance/api/v1/public.py`
  - `POST /api/v1/public/sso/discovery` now fails closed with deterministic reasons:
    - `sso_discovery_backend_timeout`
    - `sso_discovery_backend_error`
- Tests:
  - `tests/unit/governance/api/test_public.py`
  - Includes timeout and backend error path coverage for SSO discovery.

## Sign-off Summary
- Acceptance bundle capture: **PASS (26/26)**
- SSO federation smoke + publish: **PASS**
- Roadmap status remains: SSO federation v2 hardening and acceptance evidence closure are implemented and operationally validated.
