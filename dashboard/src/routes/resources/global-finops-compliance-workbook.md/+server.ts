import type { RequestHandler } from './$types';

const WORKBOOK = `# Valdrics Access Control and Compliance Checklist

## Purpose
Support enterprise security, risk, finance, and procurement reviews with a structured validation baseline.

## 1) Governance and Decision Controls
- Document ownership model across cloud, SaaS, and ITAM/license domains.
- Define approval routing for high-impact spend actions and exceptions.
- Confirm decision evidence retention, export format, and review cadence.

## 2) Identity and Access Posture
- Confirm SSO strategy (SAML/OIDC) and identity provider integration plan.
- Confirm SCIM provisioning/deprovisioning model and ownership.
- Validate RBAC matrix, least-privilege coverage, and periodic access reviews.

## 3) Financial Governance Controls
- Define budget thresholds, policy gates, and escalation paths.
- Define exception handling workflow with approval traceability.
- Define KPI and savings reporting cadence for executive oversight.

## 4) Rollout Risk and Operating Model
- Scope first integrations and pilot boundary.
- Assign rollout owners across platform engineering and finance/FinOps.
- Define day-30 validation milestones and go-live readiness criteria.

## 5) Due-Diligence and Contract Readiness
- Assign owner for security questionnaire and control evidence responses.
- Assign owner for DPA/BAA and legal review workflows.
- Attach ROI assumptions workbook for commercial diligence.

## Assistance
enterprise@valdrics.com (fallback: sales@valdrics.com)
`;

export const GET: RequestHandler = () => {
	return new Response(WORKBOOK, {
		headers: {
			'Content-Type': 'text/markdown; charset=utf-8',
			'Content-Disposition':
				'attachment; filename="global-finops-compliance-workbook.md"',
			'Cache-Control': 'public, max-age=3600'
		}
	});
};
