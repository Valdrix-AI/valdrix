# Sidebar Latency Audit (February 13, 2026)

## Scope
- Routes reviewed: `/`, `/ops`, `/onboarding`, `/audit`, `/connections`, `/greenops`, `/llm`, `/billing`, `/leaderboards`, `/settings`, `/admin/health`.
- Method: code-path audit of first-load request chains, timeout coverage, and blocking behavior.

## High-Latency Findings
1. `dashboard/src/routes/+page.ts`
- Risk before fix: high.
- Cause: server-side `Promise.all` on dashboard widgets with no per-request timeout. One slow endpoint blocked full route data.

2. `dashboard/src/routes/connections/+page.svelte`
- Risk before fix: high.
- Cause: five provider requests executed sequentially through retrying `api.get` calls, amplifying worst-case latency.

3. `dashboard/src/routes/settings/+page.svelte`
- Risk before fix: high.
- Cause: first render gated by notifications settings call; no timeout wrapper for read paths.

## Remediations Applied
1. Dashboard route loading hardened
- Added per-request timeout + `Promise.allSettled` fallback behavior.
- Partial widget data now renders if one or more endpoints are slow/unavailable.

2. Connections route loading hardened
- Converted provider loads to parallel `Promise.allSettled`.
- Added timeout wrapper around `api.get` responses.
- Each provider section now resolves independently instead of being blocked by earlier requests.

3. Settings route loading hardened
- Added timeout wrapper for settings fetches (`notifications`, `carbon`, `llm`, `activeops`, `safety`, `llm/models`).
- Switched initial hydration trigger to `onMount` and preserved section-level loading states.
- Defaults render immediately while backend data hydrates in background.

4. Sidebar interaction preloading
- Enabled route preloading on sidebar links via `data-sveltekit-preload-data="hover"` and `data-sveltekit-preload-code="hover"`.

## Remaining Work (Backend Coordination)
1. Collect live p95/p99 latency per endpoint under real tenant load (APM traces) for:
- `/costs`, `/carbon`, `/zombies`, `/settings/connections/*`, `/settings/notifications`, `/admin/health-dashboard`.
2. Optimize the slowest backend handlers only after roadmap/backend branch coordination to avoid merge conflicts.
