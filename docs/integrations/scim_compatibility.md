# SCIM Compatibility Matrix (Valdrix)

This document is an internal, source-controlled checklist for SCIM IdP interoperability.
It describes what Valdrix **supports today** (endpoints + payload variants), so we can
validate compatibility without relying on tribal knowledge.

It does **not** claim vendor certification unless explicitly stated elsewhere.

## Service Provider Capabilities
- Auth: `Authorization: Bearer <tenant-scoped token>`
- Bulk: not supported
- ETag: not supported
- Sorting: not supported
- Filtering: supported (limited, see below)

## Resource Types
- Users: supported
- Groups: supported (optional IdP path for membership management)

## Filters Supported
- Users:
  - `userName eq "email@domain.com"`
- Groups:
  - `displayName eq "Group Name"`
  - `externalId eq "idp-external-id"`

## PATCH Payload Variants Supported

### Users
- `PATCH /Users/{id}`
  - `active` replace/remove
  - `userName` replace
  - `groups` add/replace/remove (list of `{ value?, display? }`)

### Groups
- `PATCH /Groups/{id}`
  - `displayName` replace
  - `externalId` replace/remove
  - `members` add/replace/remove (list of `{ value?, display? }`)
  - Member remove path-filter form:
    - `members[value eq "uuid"]`
  - No-path replace form:
    - `{ "op": "replace", "value": { "displayName": "...", "members": [...] } }`

## Entitlement Semantics
- Group mappings are configured per tenant:
  - `role`: `admin | member`
  - `persona`: `engineering | finance | platform | leadership` (UX default)
- Entitlements can be driven by:
  - `groups` field on the SCIM User payloads, and/or
  - `/Groups` membership changes (server recomputes entitlements for impacted users).
- Guardrail: Owner users are never demoted by SCIM.

