# Valdrics Roadmap Progress Snapshot

Date: **2026-02-15**

This is a progress archive (what shipped + evidence pointers). For the previous snapshot, see:
- `reports/roadmap/ROADMAP_PROGRESS_2026-02-14.md`

## Completed Since 2026-02-14

### 1) Cloud+ Vendor-Native Connectors v2 (Platform + Hybrid)
Adds true vendor-native pull connectors beyond `ledger_http` for Platform/Hybrid sources, including tenant-scoped secret handling, config validation, UI support, and tests.

- DB:
  - Adds encrypted second secret (`api_secret`) to Platform/Hybrid connection tables.
  - Migration: `migrations/versions/cd8320390f08_add_api_secret_to_platform_and_hybrid_.py`
- API + schema hardening:
  - Connector vendor allowlists + vendor-specific required config validation: `app/schemas/connections.py`
  - Create endpoints persist `api_secret` for platform/hybrid: `app/modules/governance/api/v1/settings/connections.py`
- Adapters:
  - Platform native pulls: `app/shared/adapters/platform.py` (Datadog, New Relic)
  - Hybrid native pulls: `app/shared/adapters/hybrid.py` (OpenStack/CloudKitty, VMware vCenter)
- Dashboard:
  - Platform/Hybrid second secret fields and vendor-specific validation UX: `dashboard/src/routes/connections/+page.svelte`
- Tests:
  - `tests/unit/services/adapters/test_cloud_plus_adapters.py`

### 2) Performance Gate v1 (Manual GitHub Action)
Adds a manual, threshold-enforced performance gate workflow for staging/prod sign-off evidence.

- Workflow:
  - `.github/workflows/performance-gate.yml`
- Runner:
  - `scripts/load_test_api.py` (`--enforce-thresholds`)
- Evidence artifact:
  - `reports/performance/perf_gate_<run_id>.json` (uploaded as an Actions artifact)

### 3) Procurement Bundle Docs Alignment (Compliance Pack v3)
Keeps procurement/runbooks aligned as evidence artifacts evolve.

- New/updated docs:
  - `docs/compliance/compliance_pack.md`
  - `docs/ops/acceptance_evidence_capture.md` (documents the Actions performance gate workflow)
  - `docs/runbooks/production_env_checklist.md` (adds compliance pack export step)
- Compliance pack export includes the compliance-pack doc:
  - `app/modules/governance/api/v1/audit.py` now bundles `docs/compliance/compliance_pack.md`
- Tests:
  - `tests/unit/api/v1/test_audit_compliance_pack.py`

### 4) Workflow Integrations v2 (Microsoft Teams, Tenant-Scoped)
Adds Teams as a first-class incident channel with tenant-scoped configuration, secure webhook handling, acceptance evidence capture, and dashboard controls.

- DB + model:
  - Migration: `migrations/versions/ab12cd34ef56_add_tenant_teams_notification_settings.py`
  - Model fields: `app/models/notification_settings.py` (`teams_enabled`, encrypted `teams_webhook_url`)
- Notifications domain:
  - Teams service and passive health check: `app/modules/notifications/domain/teams.py`
  - Dispatcher integration for alerts/policy events: `app/shared/core/notifications.py`
- Settings API:
  - Teams settings read/write + tier gating + test endpoint:
    - `GET/PUT /api/v1/settings/notifications`
    - `POST /api/v1/settings/notifications/test-teams`
  - Acceptance evidence capture/list includes Teams:
    - `POST /api/v1/settings/notifications/acceptance-evidence/capture`
    - `GET /api/v1/settings/notifications/acceptance-evidence`
- Scheduled passive evidence:
  - Acceptance suite handler includes Teams passive URL validation:
    - `app/modules/governance/domain/jobs/handlers/acceptance.py`
- Compliance pack:
  - Notification snapshot includes `teams_enabled` and `has_teams_webhook_url`.
  - Integration evidence includes `integration_test.teams`.
- Dashboard:
  - Settings UI: Teams enable/rotate/clear/test controls in `dashboard/src/routes/settings/+page.svelte`
- Docs:
  - `docs/integrations/microsoft_teams.md`
  - `docs/integrations/idp_reference_configs.md` (adds Google Workspace/Cloud Identity SCIM guidance)
  - `docs/integrations/sso.md` (SSO scope and operating model)

### 5) Real SSO Federation v1 (Tenant-Scoped OIDC/SAML Bootstrap)
Implements real login federation bootstrap using Supabase SSO while retaining tenant allowlist enforcement.

- DB + model:
  - Migration: `migrations/versions/e9f0a1b2c3d4_add_sso_federation_fields_to_identity.py`
  - Model fields: `app/models/tenant_identity_settings.py`
    - `sso_federation_enabled`, `sso_federation_mode`, `sso_federation_provider_id`
- Identity settings API:
  - `GET/PUT /api/v1/settings/identity` now includes federation config.
  - `GET /api/v1/settings/identity/diagnostics` adds federation readiness signals.
  - File: `app/modules/governance/api/v1/settings/identity.py`
- Public discovery API:
  - `POST /api/v1/public/sso/discovery` resolves domain/provider bootstrap mode by tenant-domain mapping.
  - File: `app/modules/governance/api/v1/public.py`
- Dashboard auth flow:
  - Login page adds `Continue with SSO` and discovery call:
    - `dashboard/src/routes/auth/login/+page.svelte`
  - Auth callback exchanges code for session:
    - `dashboard/src/routes/auth/callback/+server.ts`
- Dashboard identity settings:
  - Adds federation controls (enable + mode + provider_id):
    - `dashboard/src/lib/components/IdentitySettingsCard.svelte`
- Tests:
  - Backend:
    - `tests/unit/governance/settings/test_identity_settings.py`
    - `tests/unit/governance/api/test_public.py`
  - Frontend:
    - `dashboard/src/lib/components/IdentitySettingsCard.svelte.test.ts`
