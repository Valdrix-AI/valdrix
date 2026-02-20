# ADR-0004: Supabase JWT Verification with HS256

- Date: 2026-02-20
- Status: Accepted Risk

## Context

Auth verification in `app/shared/core/auth.py` validates Supabase-issued JWTs
with HS256 and the shared `SUPABASE_JWT_SECRET`.

## Decision

Keep HS256 for Supabase compatibility, with strict verification controls:

- Explicit algorithm pinning: `algorithms=["HS256"]`
- Audience validation: `audience="authenticated"`
- Expiration validation via PyJWT default behavior

## Consequences

- Backend compromise would expose signing capability.
- This is acceptable under current Supabase architecture and compensating controls.

## Follow-up

- If auth ownership moves from Supabase-managed to self-managed,
  migrate to asymmetric signing (RS256/ES256) with public-key verification.
