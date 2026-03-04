# Valdrics Email Auth DNS Baseline (Cloudflare) - 2026-03-04

Purpose: copy/paste baseline for `valdrics.com` email routing and sender authentication.

Scope:
- Cloudflare Email Routing (inbound aliases)
- DMARC correction and enforcement
- `security.txt` publication

## 1) Copy/Paste DNS records (Cloudflare DNS)

Set these records in `Cloudflare -> DNS -> Records`.

### 1.1 MX (Email Routing inbound)

| Type | Name | Priority | Content | Proxy |
|---|---|---:|---|---|
| MX | `@` | 7 | `route2.mx.cloudflare.net` | DNS only |
| MX | `@` | 26 | `route3.mx.cloudflare.net` | DNS only |
| MX | `@` | 77 | `route1.mx.cloudflare.net` | DNS only |

### 1.2 SPF (domain TXT)

| Type | Name | Content | Proxy |
|---|---|---|---|
| TXT | `@` | `v=spf1 include:_spf.mx.cloudflare.net ~all` | DNS only |

### 1.3 DMARC (domain policy TXT) - corrected

Replace any malformed value such as `p=quarantine/reject`.

| Type | Name | Content | Proxy |
|---|---|---|---|
| TXT | `_dmarc` | `v=DMARC1; p=quarantine; adkim=s; aspf=s; fo=1; rua=mailto:a0b11df6b98a4e32ae13dc4c1f2b3c97@dmarc-reports.cloudflare.net` | DNS only |

Recommended phase-up:
1. Keep `p=quarantine` for 2-4 weeks while watching aggregate reports.
2. Move to `p=reject` after false-positive review is clean.

## 2) DKIM note (important)

DKIM is **outbound-provider specific**.

- If you only use Cloudflare inbound forwarding and do not send from `@valdrics.com`, no extra DKIM record is needed for forwarding itself.
- If you send outbound mail as `sales@valdrics.com`/`support@valdrics.com`, configure DKIM in that sender provider and publish the exact selector records they generate.

Do not invent DKIM selectors manually; use provider-generated values.

## 3) security.txt publication

Public security disclosure file is now routed at:

- `https://valdrics.com/.well-known/security.txt`

Minimum fields:
- `Contact: mailto:security@valdrics.com`
- `Contact: mailto:privacy@valdrics.com`
- `Policy: https://valdrics.com/privacy`

## 4) Verification commands

Run after DNS propagation:

```bash
dig +short MX valdrics.com
dig +short TXT valdrics.com
dig +short TXT _dmarc.valdrics.com
curl -sI https://valdrics.com/.well-known/security.txt
curl -s https://valdrics.com/.well-known/security.txt
```

Pass criteria:
1. MX shows the three `route*.mx.cloudflare.net` records.
2. SPF TXT includes `_spf.mx.cloudflare.net`.
3. DMARC contains a single valid `p=` policy value.
4. `security.txt` returns `200` and `Content-Type: text/plain`.

## 5) Function-based routing and SLA labels (where to configure)

Cloudflare handles alias forwarding; triage workflow lives in destination inbox tooling.

### 5.1 Cloudflare (alias -> destination)

`Cloudflare -> Email -> Email Routing -> Routing rules`

Create/maintain aliases:
- `sales@` -> GTM inbox
- `support@` -> support inbox
- `security@` -> security inbox
- `billing@` -> finance inbox
- `privacy@` -> privacy inbox

### 5.2 Destination inbox (labels/SLAs)

If destination is Gmail:
1. `Gmail -> Settings -> Filters and Blocked Addresses -> Create filter`
2. Filter by `To:` alias (for example `to:support@valdrics.com`)
3. Apply label (for example `Support/P1`, `Sales/New`, `Security/Incident`)
4. Add color + inbox section priorities

SLA baseline:
1. Sales: first response < 4 business hours
2. Support: first response < 8 business hours
3. Security/privacy: acknowledgement < 24 hours
