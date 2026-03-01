# Workflow Automation Integrations

Valdrics can trigger external automation workflows on remediation policy and execution events.

## Supported targets

- GitHub Actions (`workflow_dispatch`)
- GitLab CI (`trigger/pipeline`)
- Generic CI webhook (`POST` JSON)

## Event model

Valdrics emits deterministic events:

- `policy.block`
- `policy.escalate`
- `policy.warn`
- `policy.allow`
- `remediation.completed`

Each payload includes tenant context, remediation context, and evidence links (for example `policy_preview_api`, `remediation_plan_api`, and `execute_api`).

## Configuration model

Primary (SaaS multi-tenant):

- Configure per-tenant integrations in **Settings -> Slack Notifications -> Workflow Automation**
- Secrets are stored encrypted in tenant notification settings.
- Validate connectivity from **Settings -> Send Test Workflow Event** (calls `POST /api/v1/settings/notifications/test-workflow`).
- Capture acceptance evidence for audits/sign-off with:
  - `POST /api/v1/settings/notifications/acceptance-evidence/capture`
  - `GET /api/v1/settings/notifications/acceptance-evidence`
- Ops Center supports the same capture flow with per-run controls:
  - Include channels: Slack/Jira/Teams/Workflow
  - `fail_fast` toggle for stop-on-first-failure behavior
  - Run-level status summary and channel outcomes in **Ops Center -> Integration Acceptance Runs**

Fallback (self-host/operator-level):

- Environment variables are used only for operator/non-tenant flows.
- Tenant-scoped execution paths require tenant settings and do not fallback to env.

Strict SaaS mode:

- Set `SAAS_STRICT_INTEGRATIONS=true` to disable env-based Slack/Jira/workflow dispatchers at runtime.
- In production, startup validation fails if env integration secrets are set while strict mode is enabled.
- Shared `SLACK_BOT_TOKEN` is still allowed for tenant-scoped Slack delivery; env channel routing (`SLACK_CHANNEL_ID`) is blocked.
- Use this mode for pure multi-tenant SaaS deployments where all integrations must be tenant-scoped.

## Environment variables (fallback)

Shared:

- `WORKFLOW_DISPATCH_TIMEOUT_SECONDS` (default: `10.0`)
- `WORKFLOW_EVIDENCE_BASE_URL` (optional; defaults to `API_URL`)

GitHub Actions:

- `GITHUB_ACTIONS_ENABLED`
- `GITHUB_ACTIONS_OWNER`
- `GITHUB_ACTIONS_REPO`
- `GITHUB_ACTIONS_WORKFLOW_ID`
- `GITHUB_ACTIONS_REF`
- `GITHUB_ACTIONS_TOKEN`

GitLab CI:

- `GITLAB_CI_ENABLED`
- `GITLAB_CI_BASE_URL` (default: `https://gitlab.com`)
- `GITLAB_CI_PROJECT_ID`
- `GITLAB_CI_REF`
- `GITLAB_CI_TRIGGER_TOKEN`

Generic CI webhook:

- `GENERIC_CI_WEBHOOK_ENABLED`
- `GENERIC_CI_WEBHOOK_URL`
- `GENERIC_CI_WEBHOOK_BEARER_TOKEN` (optional)

Security:

- Generic webhook dispatch honors existing webhook controls:
  - `WEBHOOK_ALLOWED_DOMAINS`
  - `WEBHOOK_REQUIRE_HTTPS`
  - `WEBHOOK_BLOCK_PRIVATE_IPS`
