# SSO (Federation + Enforcement) (Pro+)

Valdrix supports two complementary layers:

1. **Federated login bootstrap** (OIDC/SAML through Supabase SSO)
2. **Tenant-scoped domain allowlisting enforcement**

## Current Scope (Important)
- Implemented:
  - Domain allowlist enforcement after authentication.
  - Federated login initiation from login page (`Continue with SSO`) using tenant-scoped discovery.
- Not managed by Valdrix (still configured in Supabase):
  - IdP/provider creation, certificates, and metadata lifecycle (SAML/OIDC provider setup remains in Supabase).

## Availability
- Tier: **Pro**, **Enterprise**

## How It Works
When configured:
- login page calls `POST /api/v1/public/sso/discovery` with user email.
- Valdrix resolves tenant federation mode from domain allowlist + tenant identity settings.
- browser starts Supabase SSO flow (`domain` or `provider_id` mode).
- callback completes session at `/auth/callback`.
- API still enforces allowlist after authentication as a second-layer policy.

## Configure
1. In Valdrix, go to **Settings** -> **Identity**.
2. Enable **SSO enforcement**.
3. Add one or more allowed domains (example: `example.com`).
4. Enable **Federated SSO login**.
5. Choose mode:
   - `domain` (recommended): Supabase resolves provider by domain.
   - `provider_id`: explicitly set Supabase SSO provider id.

## Diagnostics (Recommended)
After configuration, use the built-in diagnostics to confirm you will not lock out admins:
- UI: **Settings -> Identity -> Onboarding Diagnostics**
- API: `GET /api/v1/settings/identity/diagnostics` (admin-only)
  - SSO operator validation: `GET /api/v1/settings/identity/sso/validation` (admin-only)

Operator smoke test (publishes audit-grade evidence when you have Compliance Exports enabled):
- `uv run python scripts/smoke_test_sso_federation.py --email admin@example.com --publish`

Key signals:
- `enforcement_active` should be true when SSO is enabled and the allowlist is non-empty.
- `current_admin_domain_allowed` should be true to avoid lockout risk.
- `federation_ready` should be true when federated login is enabled.

## Self-Lockout Guardrail
Valdrix prevents accidental lockout:
- when enabling enforcement, the API requires your current admin email domain to be included in the allowlist.

## Notes
- Keep allowlisting enabled even when federation is enabled; federation handles login, allowlisting enforces tenant boundary.

## IdP-Initiated Flow (Optional)
Valdrix’s supported flow is **SP-initiated** (user clicks `Continue with SSO` on the Valdrix login page).

If your IdP strongly prefers IdP-initiated patterns, keep the federation flow **anchored in Supabase SSO** and
still rely on Valdrix allowlist enforcement to bind users to the correct tenant. IdP-initiated flows are easy to
misconfigure (and can bypass tenant discovery if you’re not careful), so treat them as an enterprise-only operator
option and validate with `/api/v1/settings/identity/sso/validation` before rollout.
