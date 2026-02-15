# Microsoft Teams Integration (Pro+)

Valdrix supports tenant-scoped Microsoft Teams notifications using incoming webhook URLs.

## Availability
- Tier: **Pro**, **Enterprise**
- Feature flag: `incident_integrations`

## What It Does
- Sends policy and remediation incident notifications to Teams.
- Includes actionable evidence links (ops dashboard, policy preview, approve/execute endpoints) on policy events.
- Stores webhook URL encrypted at rest in tenant notification settings.

## Configure
1. In Valdrix, open **Settings -> Notifications**.
2. Enable **Teams policy notifications**.
3. Paste your Teams incoming webhook URL.
4. Save settings.
5. Run **Send Test Teams Notification**.

## API Endpoints
- `POST /api/v1/settings/notifications/test-teams`
- `POST /api/v1/settings/notifications/acceptance-evidence/capture`
  - Include Teams check with `include_teams=true`.

## Security Controls
- HTTPS-only webhook validation.
- Host allowlist enforcement.
- Local/private network targets blocked.
- Webhook URL is treated as secret and encrypted at rest.

## Notes
- Scheduled acceptance suite runs use passive Teams validation only (no message dispatch) to avoid noisy automation.
