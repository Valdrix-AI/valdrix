# SCIM 2.0 Provisioning (Enterprise)

Valdrics supports **tenant-scoped SCIM 2.0 provisioning** for **Users** and (optionally) **Groups** via a dedicated SCIM bearer token.

## Availability
- Tier: **Enterprise**
- Resource types: **Users**, **Groups**
- Auth: **Bearer token** (tenant-scoped SCIM token)

## Base URL
Your SCIM base URL is:
`https://<your-valdrics-host>/scim/v2`

Examples:
- `GET /scim/v2/ServiceProviderConfig`
- `GET /scim/v2/Users`

## How To Enable
1. In Valdrics, go to **Settings** -> **Identity**.
2. Toggle **SCIM provisioning** on.
3. Click **Rotate SCIM token** (this returns a new token once).
4. Store the token in your IdP as a secret.

## Diagnostics and Token Test (Recommended)
Use diagnostics to confirm SCIM readiness and rotation hygiene:
- UI: **Settings -> Identity -> Onboarding Diagnostics**
- API: `GET /api/v1/settings/identity/diagnostics` (admin-only)

If your IdP provisioning calls return `401` unexpectedly, validate whether you are using the latest token:
- UI: **Settings -> Identity -> SCIM Provisioning -> Test Token**
- API: `POST /api/v1/settings/identity/scim/test-token` with JSON:
  - `{ "scim_token": "<token from your IdP>" }`

This endpoint never returns the stored token. It only confirms whether the submitted token matches.

## IdP Configuration (Generic)
Set the following:
- SCIM Base URL: `https://<your-valdrics-host>/scim/v2`
- Authentication: Bearer Token
- Token: the SCIM token you generated in Valdrics

## Supported Operations
- `GET /ServiceProviderConfig`
- `GET /Schemas`
- `GET /ResourceTypes`
- `GET /Users`
  - Supports filter: `userName eq "email@domain.com"`
- `POST /Users` (create)
- `PUT /Users/{id}` (replace)
- `PATCH /Users/{id}` (partial update; supports `active`, `userName`, and `groups`)
- `GET /Groups`
  - Supports filter: `displayName eq "Group Name"` and `externalId eq "idp-external-id"`
- `POST /Groups` (create)
- `GET /Groups/{id}` (read)
- `PUT /Groups/{id}` (replace)
- `PATCH /Groups/{id}` (partial update; supports `displayName`, `externalId`, and `members`)
- `DELETE /Groups/{id}` (delete)

## Compatibility Notes
For the exact set of supported payload variants (IdP interoperability checklist), see:
- `docs/integrations/scim_compatibility.md`

## IdP Reference Configs (Recommended)
For stable “reference values” (URLs, auth mode, attribute mapping guidance) for common IdPs, see:
- `docs/integrations/idp_reference_configs.md`

## SCIM Group Mappings (Recommended)
Valdrics supports **tenant-configurable group mappings** that assign:
- `role`: `admin` or `member`
- `persona` (optional UX default): `engineering | finance | platform | leadership`

Configure:
1. **Settings -> Identity -> SCIM group mappings**
2. Add one or more mappings (group name is case-insensitive).

Provisioning behavior:
- If your IdP includes `groups` on `POST/PUT/PATCH /Users`, Valdrics applies mappings to set `role` and optional `persona`.
- If your IdP provisions Group objects and manages membership via `POST/PUT/PATCH /Groups`, Valdrics stores group membership and recomputes entitlements for affected users based on your mappings.
- If `groups` is **omitted** on `PUT`, entitlements are treated as **no change**.
- If `groups` is **present** (even an empty list) on `PUT`, it is treated as **authoritative** for `role`:
  - No matching mapping => `member`
  - Owner users are never demoted by SCIM (guardrail)
- Persona is UX-only: it is only set when a mapping provides it and is not reset when groups are removed.

## Common Errors
- `401 Unauthorized`
  - Missing/invalid Authorization header, token not recognized, or token was rotated.
- `403 Forbidden`
  - SCIM is disabled for the tenant, or tenant tier is not Enterprise.
- `400 Bad Request`
  - Unsupported filter expression or invalid SCIM payload.

## Security Notes
- SCIM tokens are **tenant-scoped** and encrypted at rest.
- Treat the token like a password: store it in a secret manager, rotate it on compromise, and remove it when offboarding.
