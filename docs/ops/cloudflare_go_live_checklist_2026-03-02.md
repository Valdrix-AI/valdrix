# Cloudflare Go-Live Checklist (valdrics.com) - 2026-03-02

Purpose: one pass, operator-ready checklist for production readiness of `valdrics.com` on Cloudflare Pages + Koyeb API.

Scope:
- Frontend: Cloudflare Pages (`valdrics.pages.dev`, custom domains `valdrics.com` and `www.valdrics.com`)
- Backend/API: Koyeb (recommended behind custom domain like `api.valdrics.com`)
- DNS/SSL/Security/Bot/Notifications/Access preview protection

## 0) Baseline assumptions

- Zone is active in Cloudflare and nameservers are delegated to Cloudflare.
- Pages production deployment is successful.
- `dashboard/wrangler.toml` is committed with:
  - `pages_build_output_dir = ".svelte-kit/cloudflare"`
  - `compatibility_flags = ["nodejs_compat"]`

---

## 1) P0 (must complete before public launch)

### 1.1 DNS records for apex + www

Dashboard path: `Cloudflare -> DNS -> Records`

Set:
- `CNAME` `@` -> `valdrics.pages.dev` (`Proxied`, TTL `Auto`)
- `CNAME` `www` -> `@` (`Proxied`, TTL `Auto`) or `valdrics.pages.dev`

Cross-check:
- [ ] `dig +short A valdrics.com` returns Cloudflare IPs (not empty)
- [ ] `dig +short A www.valdrics.com` returns Cloudflare IPs

### 1.2 Pages custom domains attached

Dashboard path: `Workers & Pages -> <project> -> Custom domains`

Set:
- Add `valdrics.com`
- Add `www.valdrics.com`
- Wait for status `Active`

Cross-check:
- [ ] Both domains show `Active`

### 1.3 Canonical host redirect (single direction)

Choose one canonical host:
- Recommended: apex canonical (`valdrics.com`)

Set:
- Redirect `www` -> `https://valdrics.com` (301)

Cross-check:
- [ ] `curl -I https://www.valdrics.com` returns `301` with `Location: https://valdrics.com/...`
- [ ] `curl -I https://valdrics.com` returns `200` (or app-level redirect you intended)

### 1.4 Pages environment variables (Production + Preview)

Dashboard path: `Workers & Pages -> <project> -> Settings -> Environment variables`

Set all in both environments (unless intentionally different):
- `PUBLIC_SUPABASE_URL`
- `PUBLIC_SUPABASE_ANON_KEY`
- `PUBLIC_API_URL` (for example `https://api.valdrics.com/api/v1`)
- `PRIVATE_API_ORIGIN` (for example `https://api.valdrics.com`)
- `PUBLIC_TURNSTILE_SITE_KEY` (if Turnstile enabled)

Notes:
- Missing Supabase vars no longer crash public routes, but protected auth flows require them.
- `PRIVATE_API_ORIGIN` should be treated as required for edge proxy correctness.

Cross-check:
- [ ] `/auth/login` loads without runtime config error
- [ ] authenticated pages work after login
- [ ] API proxy calls from UI succeed

### 1.5 Node compatibility at runtime

Set/verify:
- `nodejs_compat` active through `dashboard/wrangler.toml`
- compatibility date current (already set in `dashboard/wrangler.toml`)

Cross-check:
- [ ] New deploy logs do not show unresolved runtime breakage for `node:*` imports

### 1.6 DNSSEC consistency

Dashboard path:
- Zone: `DNS -> Settings -> DNSSEC`
- Registrar: DS record view

Set:
- DNSSEC enabled on Cloudflare zone
- DS at registrar matches Cloudflare-provided DS

Cross-check:
- [ ] `dig +short DS valdrics.com` returns DS record
- [ ] No resolver validation failures (`SERVFAIL`) on public resolvers

---

## 2) P1 (strongly recommended right after go-live)

### 2.1 SSL/TLS hardening

Dashboard path: `SSL/TLS -> Edge Certificates` and `SSL/TLS -> Overview`

Set:
- `Always Use HTTPS` = ON
- `Automatic HTTPS Rewrites` = ON
- `TLS 1.3` = ON
- `Minimum TLS Version` = `1.2`
- If proxying API origin via Cloudflare: encryption mode `Full (strict)`

Cross-check:
- [ ] `http://valdrics.com` redirects to HTTPS
- [ ] no major mixed-content warnings on landing/auth pages

### 2.2 HSTS staged rollout (avoid lockout)

Dashboard path: `SSL/TLS -> Edge Certificates -> HTTP Strict Transport Security (HSTS)`

Stage 1 (now):
- Enable HSTS = ON
- `max-age` = 1 month
- `includeSubDomains` = OFF
- `preload` = OFF
- `No-Sniff` = ON

Stage 2 (after all subdomains are HTTPS-only):
- `max-age` = 12 months
- `includeSubDomains` = ON
- `preload` = OFF

Stage 3 (only when fully confident):
- `preload` = ON and submit to preload list

Cross-check:
- [ ] response headers include expected HSTS policy

### 2.3 WAF + bot baseline

Dashboard path:
- `Security -> WAF`
- `Security -> Settings` (Bot traffic section)

Set:
- Enable Cloudflare Managed Ruleset (default scope first)
- Enable Bot Fight Mode (or Super Bot Fight Mode per plan)
- Add at least one rate limiting rule for abuse-prone endpoints
  - `/api/marketing/subscribe`
  - `/auth/*` paths
  - any public write endpoints

Cross-check:
- [ ] Security events show WAF/bot actions
- [ ] legitimate user traffic is not blocked unexpectedly

### 2.4 Notifications

Dashboard path: `Notifications`

Set:
- Add notifications for:
  - Domain/certificate issues
  - Security events / DDoS / WAF triggers
  - Origin/API availability issues (where available)

Cross-check:
- [ ] Send test notifications and verify delivery

### 2.5 Preview deployment protection

Dashboard path:
- `Workers & Pages -> <project> -> Settings -> General -> Enable access policy`
- then manage Access application

Set:
- Require auth for preview URLs
- Optional: protect `*.pages.dev` as well (Cloudflare known-issues guidance)

Cross-check:
- [ ] preview URL requires Access authentication

### 2.6 Account security + token hygiene

Dashboard path:
- `My Profile -> Authentication`
- `My Profile -> API Tokens`

Set:
- Enable 2FA (prefer security key + backup method)
- Enforce 2FA for account members (if multi-user account)
- Use least-privilege API tokens (zone/account scoped, minimal permissions)
- Add token restrictions (IP allowlist and/or TTL) where possible
- Roll/revoke stale tokens

Cross-check:
- [ ] all active tokens mapped to owner + purpose + expiry policy

---

## 3) Email section decision tree

Reference baseline:
- `docs/ops/email_auth_dns_baseline_2026-03-04.md` (copy/paste MX/SPF/DMARC + verification commands)

If you do not need domain email now:
- [ ] Do nothing in Email Routing yet
- [ ] Do not add conflicting MX/TXT records

If you want forwarding now:
- Dashboard path: `Email -> Email Routing`
- [ ] Enable Email Routing (wizard adds required MX/TXT)
- [ ] Create custom address -> destination address
- [ ] Verify destination address
- [ ] Lock DNS records for Email Routing once stable
- [ ] Ensure DMARC record is valid (`p=quarantine` or `p=reject`, never `p=quarantine/reject`)

If you use external email provider:
- [ ] Keep provider MX records only
- [ ] Add SPF/DKIM/DMARC per provider
- [ ] Keep mail records DNS-only (not proxied)

---

## 4) Operational smoke tests (run after each major DNS/Pages change)

Run:

```bash
dig +short NS valdrics.com
dig +short A valdrics.com
dig +short A www.valdrics.com
dig +short DS valdrics.com
curl -I https://valdrics.com
curl -I https://www.valdrics.com
```

Expected:
- NS points to Cloudflare nameservers
- apex and www resolve
- DS present if DNSSEC enabled
- canonical redirect works as configured
- site returns 200/301 as designed (not DNS resolution failure)

---

## 5) Final sign-off matrix

- [ ] DNS records correct and resolving globally
- [ ] Pages custom domains active
- [ ] Canonical redirect intentional and verified
- [ ] Required runtime vars present in Production + Preview
- [ ] SSL/TLS baseline set (HTTPS, TLS1.3, min TLS1.2)
- [ ] HSTS stage applied (safe stage)
- [ ] WAF/bot/rate-limit baseline enabled
- [ ] Notifications configured and tested
- [ ] Preview access restricted
- [ ] 2FA + token least privilege enforced
- [ ] Email path explicitly chosen (routing vs external provider vs deferred)

---

## Sources (Cloudflare primary docs)

- Custom domains (Pages): https://developers.cloudflare.com/pages/configuration/custom-domains/
- Redirect `www` to apex (Pages): https://developers.cloudflare.com/pages/how-to/www-redirect/
- Build config / env vars (Pages): https://developers.cloudflare.com/pages/configuration/build-configuration/
- SvelteKit on Pages: https://developers.cloudflare.com/pages/framework-guides/deploy-a-svelte-kit-site/
- Monorepos (Pages root/build settings): https://developers.cloudflare.com/pages/configuration/monorepos/
- Compatibility flags (`nodejs_compat`): https://developers.cloudflare.com/workers/configuration/compatibility-flags/
- DNS proxy status: https://developers.cloudflare.com/dns/manage-dns-records/reference/proxied-dns-records/
- CNAME flattening: https://developers.cloudflare.com/dns/cname-flattening/
- DNSSEC: https://developers.cloudflare.com/dns/dnssec/
- Always Use HTTPS: https://developers.cloudflare.com/ssl/edge-certificates/additional-options/always-use-https/
- Automatic HTTPS Rewrites: https://developers.cloudflare.com/ssl/edge-certificates/additional-options/automatic-https-rewrites/
- TLS 1.3: https://developers.cloudflare.com/ssl/edge-certificates/additional-options/tls-13/
- Minimum TLS Version: https://developers.cloudflare.com/ssl/edge-certificates/additional-options/minimum-tls/
- Full (strict) mode: https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/
- HSTS: https://developers.cloudflare.com/ssl/edge-certificates/additional-options/http-strict-transport-security/
- WAF getting started: https://developers.cloudflare.com/waf/get-started/
- Cloudflare Managed Ruleset: https://developers.cloudflare.com/waf/managed-rules/reference/cloudflare-managed-ruleset/
- WAF rate limiting rules: https://developers.cloudflare.com/waf/rate-limiting-rules/
- Bot Fight Mode: https://developers.cloudflare.com/bots/get-started/bot-fight-mode/
- Security settings (new dashboard): https://developers.cloudflare.com/security/settings/
- Notifications setup: https://developers.cloudflare.com/notifications/get-started/
- Account 2FA: https://developers.cloudflare.com/fundamentals/account/account-security/2fa/
- API token permissions: https://developers.cloudflare.com/fundamentals/api/reference/permissions/
- Restrict API tokens (IP/TTL): https://developers.cloudflare.com/fundamentals/api/how-to/restrict-tokens/
- Email Routing enable: https://developers.cloudflare.com/email-routing/get-started/enable-email-routing/
- Email Routing DNS records: https://developers.cloudflare.com/email-routing/setup/email-routing-dns-records/
