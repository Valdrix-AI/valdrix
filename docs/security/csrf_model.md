# CSRF Enforcement Model

## Scope

CSRF protections apply to cookie-authenticated browser workflows where the browser can attach credentials implicitly.

## Explicit Exception: `/api/v1/public/*`

`/api/v1/public/*` endpoints are intentionally excluded from CSRF checks because they are designed for unauthenticated, third-party initiated onboarding and discovery flows (for example public forms and pre-auth SSO discovery).

## Why this is acceptable

- Public endpoints do not rely on ambient browser cookies for privileged actions.
- Sensitive actions remain protected by authentication/authorization and tenant scoping.
- CSRF checks remain active for authenticated cookie/session flows.
- Additional controls (input validation, rate limiting, audit logging) are enforced at the API layer.

## Code references

- CSRF middleware and public-path bypass: `app/main.py`
- Public API routes: `app/modules/governance/api/v1/public.py`

