import type { RequestHandler } from './$types';

const ONE_PAGER = `# Valdrics Executive One-Pager

## Positioning
Valdrics is the economic control plane for cloud and software spend.

## What Teams Get
- Unified visibility for cloud, SaaS, and ITAM/license movement.
- Deterministic owner routing and approval-driven execution.
- Audit-ready decision history and measurable savings proof.

## Typical Rollout
- Week 1: connect spend sources and baseline owner mapping.
- Week 2: run first controlled remediation cycle with finance + engineering.

## Commercial Model
- Free tier for initial workflow validation.
- Paid tiers for advanced automation, API depth, and enterprise support.

## Ideal Buyer Motion
- Engineering + FinOps + Finance leadership alignment.
- Procurement path with security/compliance review.
- ROI model with subscription + implementation effort assumptions.
`;

export const GET: RequestHandler = () => {
	return new Response(ONE_PAGER, {
		headers: {
			'Content-Type': 'text/markdown; charset=utf-8',
			'Content-Disposition': 'attachment; filename="valdrics-enterprise-one-pager.md"',
			'Cache-Control': 'public, max-age=3600'
		}
	});
};
