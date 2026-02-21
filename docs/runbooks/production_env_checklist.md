# Production Environment Checklist (SaaS Mode)

Use this checklist before every production rollout.

## 1. Ownership model (who sets what)

- Platform operator (you/Valdrix team) sets infrastructure env vars and deploys backend/frontend.
- Tenant users configure integrations in product UI under `/settings/notifications`.
- Tenant users do **not** set backend process env vars.

## 2. Required operator env vars

Set these in production runtime (Koyeb/Kubernetes/etc):

- `ENVIRONMENT=production`
- `DATABASE_URL=...`
- `SUPABASE_JWT_SECRET=...`
- `ENCRYPTION_KEY=...`
- `KDF_SALT=...`
- `CSRF_SECRET_KEY=...`
- `ADMIN_API_KEY=...`
- `LLM_PROVIDER=...`
- Provider key for selected LLM (`GROQ_API_KEY` or `OPENAI_API_KEY` or `CLAUDE_API_KEY` or `GOOGLE_API_KEY`)
- `PAYSTACK_SECRET_KEY=sk_live_...`
- `PAYSTACK_PUBLIC_KEY=pk_live_...`
- `CORS_ORIGINS=[\"https://<your-frontend-domain>\"]`
- `SAAS_STRICT_INTEGRATIONS=true`
- If `prophet` is not bundled, set all break-glass vars:
  - `FORECASTER_ALLOW_HOLT_WINTERS_FALLBACK=true`
  - `FORECASTER_BREAK_GLASS_REASON=<incident/ticket reference>`
  - `FORECASTER_BREAK_GLASS_EXPIRES_AT=<ISO-8601 UTC future timestamp>`

## 3. Strict SaaS integration rules

When `SAAS_STRICT_INTEGRATIONS=true`:

- Allowed:
  - `SLACK_BOT_TOKEN` (shared bot token used with tenant channel settings)
- Must be unset/empty in production:
  - `SLACK_CHANNEL_ID`
  - `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY`
  - `GITHUB_ACTIONS_*`
  - `GITLAB_CI_*`
  - `GENERIC_CI_WEBHOOK_*`

If disallowed vars are set in production, startup fails by design.

## 4. Tenant onboarding requirements

Each tenant should configure (UI):

- Slack channel override (if Slack alerts enabled)
- Jira settings (if Jira enabled)
- Workflow automation target(s): GitHub/GitLab/webhook

All tokens/secrets are stored in tenant notification settings.

## 5. Deployment sequence

1. Deploy backend image/code.
2. Run migrations: `uv run alembic upgrade head`
3. Validate runtime contract: `uv run python scripts/validate_runtime_env.py --environment production`
4. Apply env vars above and restart app.
5. Deploy frontend.
6. Validate health and notification paths.

## 6. Smoke tests after deploy

- `GET /health` returns healthy.
- From UI/API, run:
  - `POST /api/v1/settings/notifications/test-jira`
  - `POST /api/v1/settings/notifications/test-workflow`
- Capture and persist audit-grade acceptance evidence:
  - `POST /api/v1/settings/notifications/acceptance-evidence/capture`
  - `GET /api/v1/settings/notifications/acceptance-evidence`
- Export the tenant compliance pack ZIP (owner-only, Pro+):
  - `GET /api/v1/audit/compliance-pack?include_focus_export=true&include_savings_proof=true&include_realized_savings=true&include_close_package=true`
- Trigger one policy event (`block` or `escalate`) and confirm downstream notifications.

## 7. Change management rule

Whenever config behavior changes:

1. Update this file.
2. Update `.env.example`.
3. Update `docs/integrations/workflow_automation.md`.
4. Add/adjust tests for config validation where applicable.
