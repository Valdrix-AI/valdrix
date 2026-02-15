# Personas (Product Defaults)

Valdrix is used by different roles with different success metrics. Persona is a **UX default** that controls:

- which navigation items are emphasized
- which home widgets load first
- which “next actions” are suggested

Persona is **not** a permission boundary. Access is enforced by RBAC + pricing tier gates.

## Supported Personas

1. Engineering
- Primary goal: identify and remediate waste safely.
- Default focus: zombie findings, remediation policy preview, approval flow, auditability.

2. Finance
- Primary goal: accountability and decision support for spend.
- Default focus: allocation coverage, unit economics, anomalies, reconciliation/close outputs, savings proof.

3. Platform
- Primary goal: reliability and guardrails.
- Default focus: ingestion recency/completeness, job SLOs, safety fuses, policy enforcement and escalation queues.

4. Leadership
- Primary goal: high-level cost drivers and proof of impact.
- Default focus: top drivers, carbon, savings realized vs opportunity, leaderboards.

## Default Navigation (v1)

Navigation is curated per persona to reduce clutter. Deep-links still work; persona only changes defaults.

- Engineering: Dashboard, Ops Center, Connections, GreenOps, LLM Usage, Audit Logs, Settings
- Finance: Dashboard, Leaderboards, Savings Proof, Billing, Connections, GreenOps, Audit Logs, Settings
- Platform: Ops Center, Connections, Audit Logs, Settings (Admin Health if admin/owner)
- Leadership: Dashboard, Leaderboards, Savings Proof, GreenOps, Audit Logs, Settings

## Cross-Persona Handoff Workflow (Detect -> Assign -> Act -> Verify)

1. Detect
- Deterministic engines produce findings: anomalies, zombies, waste/rightsizing, architectural inefficiency, policy violations.

2. Assign
- Findings can be routed into integrations (Slack/Jira/CI workflows) and recorded with audit evidence.
- Ownership is explicit: a finding must have a next responsible actor (team/user) or it is operationally “dead”.

3. Act
- Actions are executed through remediation requests with policy preview and approval workflow.
- Safety fuses (circuit breaker, daily savings limits) prevent runaway automation.

4. Verify
- Savings proof and reconciliation outputs validate impact and prevent “phantom savings”.
- Audit logs provide traceability for compliance and finance-grade month-end close.

## Where To Configure Persona

Settings -> **Default Persona**

Backend API:
- `GET /api/v1/settings/profile`
- `PUT /api/v1/settings/profile` (body: `{ "persona": "engineering|finance|platform|leadership" }`)

