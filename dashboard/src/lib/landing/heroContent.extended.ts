import { getPublicCustomerCommentsFeed } from '$lib/landing/customerCommentsFeed';

export const CUSTOMER_QUOTES = Object.freeze(
	getPublicCustomerCommentsFeed().map((record) => ({
		quote: record.quote,
		attribution: record.attribution
	}))
);

export const COMPLIANCE_FOUNDATION_BADGES = Object.freeze([
	'ISO 27001 readiness alignment',
	'DORA operational resilience',
	'SOC 2 program alignment',
	'GDPR data-rights support',
	'Single sign-on (SAML)',
	'SCIM user provisioning',
	'Role-based approvals',
	'Decision history logs',
	'DPA and BAA review support',
	'Export-ready records',
	'Tenant isolation'
]);

export const PLAN_COMPARE_CARDS = Object.freeze([
	{
		id: 'starter',
		name: 'Starter',
		price: 'From $49/mo',
		kicker: 'For focused cloud teams',
		detail: 'Best for a single-provider start when one team needs owner-routed spend control.',
		priceNote: 'Monthly starting price. Best fit for a single-provider operating scope.',
		features: ['Single cloud provider (AWS)', 'Budgets + owner-routed alerts', 'Baseline owner action workflows']
	},
	{
		id: 'growth',
		name: 'Growth',
		price: 'From $149/mo',
		kicker: 'For cross-functional FinOps',
		detail: 'Best for multi-cloud teams that need approval routing, GreenOps visibility, and guided execution.',
		priceNote: 'Monthly starting price. Built for broader provider coverage and team governance.',
		features: ['AWS + Azure + GCP coverage', 'Approval workflows + GreenOps', 'Non-production auto-remediation']
	},
	{
		id: 'pro',
		name: 'Pro',
		price: 'From $299/mo',
		kicker: 'For enterprise teams',
		detail:
			'Best for teams that want broader automation, API-first operations, and expanded commercial support.',
		priceNote: 'Monthly starting price. Adds deeper automation, API access, and priority support.',
		features: ['Automated remediation tracks', 'Priority support + full API access', 'Expanded governance support']
	}
]);

export const PLANS_PRICING_EXPLANATION =
	'Starting prices shown here are monthly entry points. Plan fit changes with provider coverage, workflow automation depth, and support needs.';

export const FREE_TIER_HIGHLIGHTS = Object.freeze([
	'One owner-routed savings workflow on the free tier',
	'Cloud and software signal map access',
	'Baseline owner routing and approval workflow',
	'BYOK supported in the current lineup; daily AI limits still apply by tier'
]);

export const FREE_TIER_LIMIT_NOTE =
	'Free is best for proving one workflow. Upgrade when you need multi-cloud coverage, more automation, or expanded governance support.';

export const IMPLEMENTATION_COST_FACTS = Object.freeze([
	'Typical rollout: 3-10 business days for first production workflow.',
	'Common team footprint: one engineering owner + one finance/FinOps owner.',
	'No mandatory professional-services retainer for core onboarding.',
	'Implementation effort is visible upfront in the ROI planner assumptions.'
]);

export const CROSS_SURFACE_COVERAGE = Object.freeze([
	{
		title: 'Catch waste before close',
		detail:
			'Spot cloud and software cost movement earlier and route it before month-end pressure turns it into escalation.'
	},
	{
		title: 'Give every issue an owner',
		detail:
			'Every material anomaly lands with a named owner, a decision path, and a deadline instead of another thread.'
	},
	{
		title: 'Review one shared control loop',
		detail:
			'Cloud, SaaS, license, and carbon decisions stay in one operating narrative leadership can review quickly.'
	}
]);

export const DECISION_LEDGER_SUMMARY = Object.freeze([
	{ label: 'Scope', value: 'Cloud + software + carbon' },
	{ label: 'Control loop', value: 'Owner, approval, proof' },
	{ label: 'Review rhythm', value: 'Weekly finance + engineering' }
]);

export const DECISION_LEDGER_STEPS = Object.freeze([
	{
		step: '01',
		kicker: 'Signal scoped',
		title: 'The issue lands with owner and context',
		detail:
			'Valdrics ties spend movement to the affected workload, team, and decision path instead of leaving another chart for someone to interpret.',
		meta: 'Workload tagged. Owner queue opened.'
	},
	{
		step: '02',
		kicker: 'Guardrails applied',
		title: 'Approval happens with the right checks',
		detail:
			'Risk checks, role boundaries, and approval routes stay attached before action moves forward, so teams do not trade speed for control.',
		meta: 'Pre-change checks passed. Approval path visible.'
	},
	{
		step: '03',
		kicker: 'Outcome recorded',
		title: 'Leadership gets a reviewable decision trail',
		detail:
			'Every finished action keeps its rationale, owner, and savings proof so finance, engineering, and security can review one clean record.',
		meta: 'Decision saved. Export-ready record available.'
	}
]);

export const BACKEND_CAPABILITY_PILLARS = Object.freeze([
	{
		title: 'Cost Intelligence and Forecasting',
		detail:
			'Track spend, attribution, anomalies, and forecast movement before variance turns into escalation.'
	},
	{
		title: 'GreenOps Execution',
		detail:
			'Manage carbon budgets, regional intensity, and greener workload scheduling in the same workflow as cost.'
	},
	{
		title: 'Cloud Hygiene and Remediation',
		detail:
			'Detect idle resources, route owner actions, and execute approved remediation with built-in safety checks.'
	},
	{
		title: 'SaaS and ITAM License Control',
		detail:
			'Bring SaaS usage and license posture into one view so reclamation and renewal decisions stay measurable.'
	},
	{
		title: 'Financial Guardrails',
		detail:
			'Apply budgets, credits, reservations, and approval flows so high-impact spend actions stay controlled.'
	},
	{
		title: 'Savings Proof for Leadership',
		detail:
			'Show realized savings events, leaderboard movement, and executive-ready operating outcomes.'
	},
	{
		title: 'Operational Integrations',
		detail:
			'Connect Slack, Teams, Jira, and workflow alerts so decisions move into the channels teams already use.'
	},
	{
		title: 'Security and Identity',
		detail:
			'Support SSO, SCIM provisioning, role-scoped approvals, and audit-ready decision history.'
	}
]);
