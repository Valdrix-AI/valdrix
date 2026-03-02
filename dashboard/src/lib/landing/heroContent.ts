import type { BuyerPersona } from '$lib/landing/landingExperiment';

export const HERO_ROLE_CONTEXT: Record<
	BuyerPersona,
	{
		controlTitle: string;
		metricsTitle: string;
		subtitle: string;
		quantPromise: string;
		primaryIntent: string;
	}
> = Object.freeze({
	cto: {
		controlTitle: 'Stop cloud and software waste before it slows your roadmap.',
		metricsTitle: 'From cost dashboards to fast, owner-led engineering action.',
		subtitle:
			'Give engineering a faster path from spend signal to safe execution with clear ownership.',
		quantPromise: 'Target 10-18% controllable spend recovery opportunity in the first 90 days.',
		primaryIntent: 'engineering_control'
	},
	finops: {
		controlTitle: 'Control every dollar with accountable ownership and faster decisions.',
		metricsTitle: 'From visibility reporting to faster financial action.',
		subtitle:
			'Detect spend movement earlier, route accountable owners immediately, and close actions before month-end pressure.',
		quantPromise:
			'Target 30-50% fewer late-cycle escalations by formalizing ownership and action paths.',
		primaryIntent: 'finops_governance'
	},
	security: {
		controlTitle: 'Reduce spend and change risk without becoming a delivery bottleneck.',
		metricsTitle: 'From anomalies to safe, reviewable remediation.',
		subtitle:
			'Keep execution guarded by approvals and pre-change checks while engineering keeps shipping.',
		quantPromise:
			'Target measurable reduction in risky manual changes by enforcing pre-change checks.',
		primaryIntent: 'security_governance'
	},
	cfo: {
		controlTitle: 'Control cloud margin risk before it reaches the boardroom.',
		metricsTitle: 'From spend metrics to board-ready economic control.',
		subtitle:
			'Tie spend movement to accountable owners so margin conversations shift from surprise to strategy.',
		quantPromise:
			'Target stronger forecast confidence with one decision loop across engineering and finance.',
		primaryIntent: 'executive_briefing'
	}
});

export const HERO_PROOF_POINTS = Object.freeze([
	{
		title: 'One Economic Truth',
		detail: 'Cloud, SaaS, and license decisions share one operating view.'
	},
	{
		title: 'Execution With Guardrails',
		detail: 'Owners, approvals, and safety checks are built into every action path.'
	},
	{
		title: 'Board-Ready Narrative',
		detail: 'You can explain spend movement, actions, and outcomes in minutes.'
	}
]);

export const HERO_OUTCOME_CHIPS = Object.freeze([
	{
		label: 'Signal-to-owner handoff',
		value: '< 1 business day target'
	},
	{
		label: 'Controllable waste opportunity',
		value: '10-18% target range'
	},
	{
		label: 'Operating model',
		value: 'Visibility + ownership + action'
	}
]);

export const ABOVE_FOLD_TRUST_BADGES = Object.freeze([
	'SOC 2 program alignment',
	'GDPR data-rights support',
	'SSO + SCIM access controls',
	'Tenant-isolated workspaces'
]);

export const SIGNAL_VALUE_CARDS = Object.freeze([
	{
		label: 'Clarity',
		value: 'See what changed and why',
		hint: 'Cloud spend, anomaly, and workload signals in one operational view.'
	},
	{
		label: 'Ownership',
		value: 'Know who decides next',
		hint: 'Clear responsibility across platform, finance, and leadership.'
	},
	{
		label: 'Confidence',
		value: 'Explain decisions quickly',
		hint: 'Teams stay aligned during finance and leadership reviews.'
	}
]);

export const MICRO_DEMO_STEPS = Object.freeze([
	{
		id: 'detect',
		title: 'Detect',
		detail: 'Realtime cloud anomaly is detected and scoped to impacted workloads.'
	},
	{
		id: 'govern',
		title: 'Assess',
		detail: 'Risk checks and entitlement context evaluate blast radius before execution.'
	},
	{
		id: 'approve',
		title: 'Approve',
		detail: 'Accountable owner approves with explicit decision context and clear impact.'
	},
	{
		id: 'prove',
		title: 'Confirm',
		detail: 'Outcomes are captured so finance and engineering can measure impact quickly.'
	}
]);

export const CLOUD_HOOK_STATES = Object.freeze([
	{
		id: 'without',
		title: 'Without Valdrics',
		subtitle: 'Reactive cloud cost operations',
		ahaMoment: 'Anomalies surface late, ownership is unclear, and teams react under pressure.',
		points: [
			'Spend spikes are discovered after the billing cycle.',
			'Remediation ownership is ambiguous across teams.',
			'Cost actions execute ad hoc, and outcomes are hard to track.'
		],
		metrics: [
			{ label: 'Signal Lag', value: 'After invoice close' },
			{ label: 'Decision Owner', value: 'Unclear' },
			{ label: 'Execution Safety', value: 'Inconsistent' }
		]
	},
	{
		id: 'with',
		title: 'With Valdrics',
		subtitle: 'Controlled cloud economics',
		ahaMoment: 'Anomaly detected, owner assigned, risk checked, and action approved in one flow.',
		points: [
			'Realtime anomalies route to a named accountable owner.',
			'Safety checks run before every change.',
			'Decision history is easy to share with finance and leadership.'
		],
		metrics: [
			{ label: 'Signal Lag', value: 'Realtime' },
			{ label: 'Decision Owner', value: 'Explicit' },
			{ label: 'Execution Safety', value: 'Guardrailed' }
		]
	}
]);

export const EXECUTIVE_CONFIDENCE_POINTS = Object.freeze([
	{
		kicker: 'Decision Quality',
		title: 'Teams decide faster with less friction',
		detail: 'Economic controls are clear, reviewable, and consistently applied across teams.'
	},
	{
		kicker: 'Execution',
		title: 'Actions stay safe and accountable',
		detail: 'Change flows remain safe with clear ownership and explicit approvals.'
	},
	{
		kicker: 'Leadership',
		title: 'Reviews stay focused on outcomes',
		detail: 'Leadership gets a clear narrative from signal to action without noise.'
	}
]);

export const TRUST_ECOSYSTEM_BADGES = Object.freeze([
	'AWS',
	'Azure',
	'GCP',
	'Microsoft 365',
	'Salesforce',
	'Datadog',
	'Kubernetes'
]);

export const TRUST_BENCHMARK_OUTCOMES = Object.freeze([
	{
		title: 'Faster economic decisions',
		detail:
			'High-growth teams target a tighter detect-to-decision cycle by unifying ownership and execution context.',
		benchmark: 'Target benchmark: 15-25% faster decision cycles'
	},
	{
		title: 'Fewer finance escalations',
		detail:
			'When ownership and approvals are explicit, month-end surprise escalations can be reduced materially.',
		benchmark: 'Target benchmark: 30-50% fewer late escalations'
	},
	{
		title: 'Clear accountability',
		detail:
			'Teams can move from ambiguous remediation ownership to explicit, role-based accountability across functions.',
		benchmark: 'Target benchmark: owner assigned on every material anomaly'
	}
]);

export const BUYER_ROLE_VIEWS = Object.freeze([
	{
		id: 'cto' as const,
		label: 'Engineering',
		headline: 'Keep roadmap velocity while controlling cloud and software spend',
		detail:
			'Engineering ships faster when spend risk is managed inside delivery workflows, not escalated after the close.',
		signals: ['Roadmap stability', 'Controlled velocity', 'Fewer escalation loops'],
		thirtyDayOutcomes: [
			'Top spend regressions mapped to accountable owners.',
			'High-risk actions routed through explicit owner sign-off.',
			'Weekly engineering reviews include cost + risk with clear next actions.'
		]
	},
	{
		id: 'finops' as const,
		label: 'FinOps',
		headline: 'Move from reporting to faster financial action',
		detail:
			'Use one operating loop to attribute spend movement, assign ownership, and route remediation clearly.',
		signals: ['Forecast confidence', 'Ownership clarity', 'Faster remediation cycle'],
		thirtyDayOutcomes: [
			'Material anomalies triaged with ownership and deadlines.',
			'Escalation volume reduced through earlier owner-led decisions.',
			'Finance and platform teams review one shared operating narrative.'
		]
	},
	{
		id: 'security' as const,
		label: 'Security',
		headline: 'Reduce risk without becoming a delivery bottleneck',
		detail:
			'Run risk checks before execution with explicit ownership and a clear change history.',
		signals: ['Control adherence', 'Risk visibility', 'Decision traceability'],
		thirtyDayOutcomes: [
			'Risk checks applied before cost-impacting actions.',
			'Approval lineage made explicit for sensitive changes.',
			'Security and platform teams share one review trail.'
		]
	},
	{
		id: 'cfo' as const,
		label: 'CFO',
		headline: 'Protect gross margin with predictable spend decisions',
		detail:
			'Tie cloud actions to financial impact and ownership so executive decisions rely on controlled, trusted signals.',
		signals: ['Margin protection', 'Investment confidence', 'Board-level explainability'],
		thirtyDayOutcomes: [
			'Top margin risks linked to named owners and action dates.',
			'Forecast conversations shift from variance explanation to decision planning.',
			'Board updates include a concise signal-to-action narrative.'
		]
	}
]);

export const CUSTOMER_PROOF_STORIES = Object.freeze([
	{
		title: 'Growth B2B SaaS Platform',
		before: 'Monthly spikes were discovered late and routed through ad-hoc escalation threads.',
		after: 'Ownership and approvals moved into weekly operating reviews with named decision owners.',
		impact:
			'Design-partner pattern: double-digit controllable spend opportunity surfaced before month-end close.'
	},
	{
		title: 'Digital Commerce Group',
		before: 'Finance and engineering escalations clustered around month-end close.',
		after: 'Spend issues were triaged weekly with clear owners and explicit action deadlines.',
		impact: 'Design-partner pattern: fewer late-cycle escalations and faster owner handoffs.'
	},
	{
		title: 'Multi-Region Platform Team',
		before: 'Cloud and SaaS actions were tracked in disconnected channels and ticket queues.',
		after: 'Cloud+, SaaS, and license decisions ran in one shared operating loop across teams.',
		impact: 'Design-partner pattern: unified signal-to-action narrative for leadership reviews.'
	}
]);

export const CUSTOMER_QUOTES = Object.freeze([
	{
		quote:
			'We stopped debating whose queue a cost issue belongs to. Ownership is now explicit in the workflow.',
		attribution: 'Head of FinOps, Growth-stage SaaS'
	},
	{
		quote:
			'The value is not another dashboard. It is moving from signal to controlled action without drama.',
		attribution: 'VP Engineering, Multi-cloud Platform'
	},
	{
		quote:
			'Leadership reviews got shorter because the economic story is consistent from platform to finance.',
		attribution: 'CFO, Digital Services Organization'
	}
]);

export const COMPLIANCE_FOUNDATION_BADGES = Object.freeze([
	'Single sign-on (SAML)',
	'SCIM user provisioning',
	'Role-based approvals',
	'Decision history logs',
	'Export-ready records',
	'Tenant isolation'
]);

export const PLAN_COMPARE_CARDS = Object.freeze([
	{
		id: 'starter',
		name: 'Starter',
		price: 'From $49/mo',
		kicker: 'For focused cloud teams',
		detail: 'Move from static dashboards to owner-routed spend control in one workspace.',
		features: ['Single-cloud start', 'Budgets + anomaly routing', 'Owner action workflows']
	},
	{
		id: 'growth',
		name: 'Growth',
		price: 'From $149/mo',
		kicker: 'For cross-functional FinOps',
		detail: 'Unify cloud, SaaS, and operational ownership with guided execution loops.',
		features: ['Multi-cloud + Cloud+ signals', 'Approval workflows', 'AI-assisted prioritization']
	},
	{
		id: 'pro',
		name: 'Pro',
		price: 'From $299/mo',
		kicker: 'For enterprise teams',
		detail:
			'Scale shared execution across engineering, finance, and leadership with API-first operations.',
		features: ['Automated remediation tracks', 'Expanded API access', 'Priority support']
	}
]);

export const FREE_TIER_HIGHLIGHTS = Object.freeze([
	'Permanent free tier with usage limits',
	'Cloud and software signal map access',
	'Owner routing and baseline action workflows',
	'BYOK available with tier limits'
]);

export const IMPLEMENTATION_COST_FACTS = Object.freeze([
	'Typical rollout: 3-10 business days for first production workflow.',
	'Common team footprint: one engineering owner + one finance/FinOps owner.',
	'No mandatory professional-services retainer for core onboarding.',
	'Implementation effort is visible upfront in the ROI planner assumptions.'
]);

export const CROSS_SURFACE_COVERAGE = Object.freeze([
	{
		title: 'Cloud Infrastructure',
		detail:
			'AWS, Azure, and GCP spend signals are attributed to accountable teams before they become month-end surprises.'
	},
	{
		title: 'GreenOps and Carbon',
		detail:
			'Carbon intensity, budget thresholds, and cleaner-runtime opportunities are tracked alongside cost decisions.'
	},
	{
		title: 'SaaS Spend',
		detail:
			'Vendor usage and expansion pressure are surfaced with ownership context so renewals become controlled decisions.'
	},
	{
		title: 'ITAM and License',
		detail: 'Entitlement and license posture are reviewed in the same workflow as cloud spend.'
	},
	{
		title: 'Platform Tooling',
		detail:
			'Observability and platform service costs are tied to operating owners and financial outcomes.'
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
