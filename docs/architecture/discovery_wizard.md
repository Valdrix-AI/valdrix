# Discovery Wizard (Prefill-Only)

## Goal

Improve onboarding speed without weakening security guarantees.

- Connector onboarding remains the source of truth.
- Discovery provides probable candidates that users explicitly accept or ignore.

## Stages

1. Stage A (`/api/v1/settings/connections/discovery/stage-a`)
   - Input: user email.
   - Process: domain normalization + DNS signals (MX/TXT + selected CNAME probes).
   - Output: candidate providers/connectors with confidence and evidence.

2. Stage B (`/api/v1/settings/connections/discovery/deep-scan`)
   - Input: domain + primary IdP provider.
   - Requires: active native License connector token + `idp_deep_scan` entitlement (Pro+).
   - Process:
     - Microsoft 365: Graph service principals (best effort).
     - Google Workspace: user token sampling (best effort).
   - Output: stronger-confidence candidates enriched from app inventory.

3. Stage C (selection)
   - Candidate statuses: `pending`, `accepted`, `ignored`, `connected`.
   - Endpoints:
     - `POST .../candidates/{id}/accept`
     - `POST .../candidates/{id}/ignore`
     - `POST .../candidates/{id}/connected`

## Security + Reliability

- No secrets are discovered from DNS; DNS is used only for non-sensitive inference.
- Deep scan is gated behind authenticated tenant context + plan checks.
- API calls are best effort with bounded retries and warning surfacing.
- User intent is preserved: ignored candidates are not auto-connected.

## UX Messaging

Use: “Fast discovery + one-click setup guidance”

Avoid: “100% automatic account detection from email.”
