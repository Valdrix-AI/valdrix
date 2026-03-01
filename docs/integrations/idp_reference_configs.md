# IdP Reference Configs (SCIM + SSO Enforcement)

This doc provides **reference configuration values** for common IdPs when integrating with Valdrics.

Goal: reduce “tribal knowledge” during enterprise onboarding by documenting the **exact fields** Valdrics expects.

Note: IdP admin UIs change often. This guide focuses on stable inputs (URLs, auth, attribute mappings) rather than click-path screenshots.

## SCIM (Enterprise)

### Valdrics SCIM Base URL

Your SCIM base URL is:

`https://<your-valdrix-host>/scim/v2`

Authentication:

- `Authorization: Bearer <tenant-scoped scim token>`

Generate the tenant SCIM token:

1. Dashboard: `Settings -> Identity -> SCIM provisioning -> Rotate SCIM token`
2. Store the token in your IdP secrets vault

### Required User Attributes (Minimum)

Valdrics requires:

- `userName` (email)

Recommended:

- `active` (boolean)
- `groups` (list of group refs) and/or `/Groups` provisioning (see `docs/integrations/scim.md`)

### Group Mappings (Recommended)

In Valdrics:

- `Settings -> Identity -> SCIM group mappings`
- Map IdP group name -> `role` (`admin|member`) and optional default `persona`

This is the cleanest way to keep “who owns what” aligned with how your org already operates.

## Okta (SCIM)

Reference values:

- SCIM connector base URL: `https://<your-valdrix-host>/scim/v2`
- Auth mode: `HTTP Header`
- Token: `Bearer <SCIM_TOKEN>`
- Unique identifier: `userName` (email)

Recommended provisioning scope:

- Users: create + update + deactivate
- Groups: create/update + membership push (if your Okta setup supports Group Push)

Attribute mapping guidance:

- `userName` <- Okta user email
- `active` <- Okta active status

If you use groups:

- Ensure groups are pushed and names match the Valdrics SCIM group mappings (case-insensitive).

## Microsoft Entra ID (Azure AD) (SCIM)

Reference values (Provisioning):

- Tenant URL: `https://<your-valdrix-host>/scim/v2`
- Secret token: `<SCIM_TOKEN>` (Valdrics tenant SCIM token)

Recommended provisioning scope:

- “Sync only assigned users and groups”

Attribute mapping guidance:

- `userName` <- `userPrincipalName` (or `mail`, depending on your directory)
- `active` <- account enabled status

Group provisioning:

- Enable group provisioning if you want membership-driven entitlements (recommended for Enterprise).

## Google Workspace / Cloud Identity (SCIM)

Google-native admin tooling often does not expose a generic SCIM app-provisioning flow equivalent to Okta/Entra for third-party SaaS.

Recommended production pattern:

- Keep Google Workspace/Cloud Identity as source directory.
- Use an IdP/broker layer that supports generic SCIM push to Valdrics (for example Okta Workforce Identity, Entra ID, or a directory broker).

Reference values (via broker):

- SCIM connector base URL: `https://<your-valdrix-host>/scim/v2`
- Auth mode: `Authorization: Bearer <SCIM_TOKEN>`
- Unique identifier: `userName` (email)
- Group mapping: broker group names should match Valdrics SCIM group mappings.

Operational guidance:

- Run `scripts/smoke_test_scim_idp.py` in staging before production cutover.
- Enable group sync after role/persona mappings are configured in Valdrics.
- Rotate SCIM token after onboarding and store it in your secret manager.

## SSO Federation + Enforcement (Pro+)

Valdrics supports:
- federated login bootstrap (`domain` or `provider_id` mode via Supabase SSO),
- plus email-domain allowlist enforcement.

Reference values:

- Allowed domains: your corporate domains (example: `example.com`)
- Federation mode:
  - `domain` (recommended) when your IdP is configured in Supabase for domain discovery
  - `provider_id` when you need explicit provider routing
- Guardrail: Valdrics prevents lockout by requiring current admin domain in allowlist when enabling enforcement.

See:

- `docs/integrations/sso.md`
- `GET /api/v1/settings/identity/diagnostics`

## Operator Smoke Test (Recommended)

For a production-grade onboarding, run an operator smoke test against your environment:

- Read-only: validates SCIM discovery endpoints (`ServiceProviderConfig`, `Schemas`, `ResourceTypes`)
- Write-mode (recommended on a staging tenant): creates a test user + group, verifies membership, then cleans up

Script:

`scripts/smoke_test_scim_idp.py`
