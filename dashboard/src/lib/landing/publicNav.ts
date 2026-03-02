export interface PublicNavLink {
	href: string;
	label: string;
	external?: boolean;
}

export const PUBLIC_PRIMARY_LINKS: readonly PublicNavLink[] = Object.freeze([
	{ href: '/#benefits', label: 'Outcomes' },
	{ href: '/#workflow', label: 'How It Works' },
	{ href: '/#personas', label: "Who It's For" },
	{ href: '/#trust', label: 'Proof' },
	{ href: '/resources', label: 'Resources' },
	{ href: '/pricing', label: 'Pricing' }
]);

export const PUBLIC_SECONDARY_LINKS: readonly PublicNavLink[] = Object.freeze([
	{ href: '/talk-to-sales', label: 'Talk to Sales' },
	{ href: '/insights', label: 'Insights' },
	{ href: '/docs', label: 'Docs' }
]);

export const PUBLIC_MOBILE_LINKS: readonly PublicNavLink[] = Object.freeze([
	{ href: '/#benefits', label: 'Outcomes' },
	{ href: '/#workflow', label: 'How It Works' },
	{ href: '/#personas', label: "Who It's For" },
	{ href: '/#trust', label: 'Proof' },
	{ href: '/resources', label: 'Resources' },
	{ href: '/insights', label: 'Insights' },
	{ href: '/talk-to-sales', label: 'Talk to Sales' },
	{ href: '/docs', label: 'Docs' },
	{ href: '/pricing', label: 'Pricing' }
]);

export const PUBLIC_FOOTER_LINKS: readonly PublicNavLink[] = Object.freeze([
	{ href: '/docs', label: 'Documentation' },
	{ href: '/docs/api', label: 'API Reference' },
	{ href: '/resources', label: 'Resources' },
	{ href: '/insights', label: 'Insights' },
	{ href: '/talk-to-sales', label: 'Talk to Sales' },
	{ href: '/pricing', label: 'Pricing' },
	{ href: '/#trust', label: 'Trust' },
	{ href: '/privacy', label: 'Privacy' },
	{ href: '/terms', label: 'Terms' },
	{ href: 'https://github.com/Valdrics-AI/valdrics', label: 'GitHub', external: true },
	{ href: '/status', label: 'Status' }
]);

export const PUBLIC_SIGNAL_STRIP: readonly string[] = Object.freeze([
	'Catch waste before invoice shock',
	'Align finance and engineering fast',
	'Act with confidence, not fire drills'
]);

export const PUBLIC_FOOTER_BADGES: readonly string[] = Object.freeze([
	'Start Free at $0',
	'Owner-assigned actions',
	'Safe approvals',
	'Cloud + SaaS + ITAM',
	'Enterprise-ready security',
	'Usage-based scaling'
]);

export const PUBLIC_FOOTER_SUBTITLE =
	'The spend control platform for cloud and software teams that need clear ownership, faster action, and measurable savings.';

export const PUBLIC_FOOTER_CAPTION =
	'Built for finance, engineering, and operations teams that want less waste and faster decisions.';
