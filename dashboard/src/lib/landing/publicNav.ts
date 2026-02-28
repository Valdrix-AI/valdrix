export interface PublicNavLink {
	href: string;
	label: string;
	external?: boolean;
}

export const PUBLIC_PRIMARY_LINKS: readonly PublicNavLink[] = Object.freeze([
	{ href: '/#benefits', label: 'Features' },
	{ href: '/#personas', label: "Who It's For" },
	{ href: '/#workflow', label: 'How It Works' },
	{ href: '/docs', label: 'Docs' },
	{ href: '/pricing', label: 'Pricing' }
]);

export const PUBLIC_SECONDARY_LINKS: readonly PublicNavLink[] = Object.freeze([
	{ href: '/#trust', label: 'Why Trust It' },
	{ href: '/pricing', label: 'Pricing' }
]);

export const PUBLIC_MOBILE_LINKS: readonly PublicNavLink[] = Object.freeze([
	{ href: '/#benefits', label: 'Features' },
	{ href: '/#personas', label: "Who It's For" },
	{ href: '/#workflow', label: 'How It Works' },
	{ href: '/#trust', label: 'Why Trust It' },
	{ href: '/docs', label: 'Docs' },
	{ href: '/pricing', label: 'Pricing' }
]);

export const PUBLIC_FOOTER_LINKS: readonly PublicNavLink[] = Object.freeze([
	{ href: '/docs', label: 'Documentation' },
	{ href: '/docs/api', label: 'API Reference' },
	{ href: '/pricing', label: 'Pricing' },
	{ href: '/#trust', label: 'Trust' },
	{ href: '/privacy', label: 'Privacy' },
	{ href: '/terms', label: 'Terms' },
	{ href: 'https://github.com/Valdrix-AI/valdrix', label: 'GitHub', external: true },
	{ href: '/status', label: 'Status' }
]);

export const PUBLIC_SIGNAL_STRIP: readonly string[] = Object.freeze([
	'Catch waste before invoice shock',
	'Align finance and engineering fast',
	'Act with confidence, not fire drills'
]);

export const PUBLIC_FOOTER_BADGES: readonly string[] = Object.freeze([
	'Svelte 5',
	'FastAPI 0.128+',
	'Policy-Governed Actions',
	'Cloud + SaaS + ITAM',
	'Executive Decision Ready',
	'License: BSL 1.1'
]);

export const PUBLIC_FOOTER_SUBTITLE =
	'The economic control plane for cloud and software spend with deterministic governance and policy-driven execution.';

export const PUBLIC_FOOTER_CAPTION =
	'Designed for teams that need fast cost control, clear ownership, and reliable outcomes.';
