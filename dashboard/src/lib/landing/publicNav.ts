export interface PublicNavLink {
	href: string;
	label: string;
	external?: boolean;
}

export interface PublicContactChannel {
	label: string;
	email: string;
	href: string;
}

export const PUBLIC_PRIMARY_LINKS: readonly PublicNavLink[] = Object.freeze([
	{ href: '/#product', label: 'Product' },
	{ href: '/#signal-map', label: 'Live Demo' },
	{ href: '/#simulator', label: 'ROI' },
	{ href: '/pricing', label: 'Pricing' },
	{ href: '/enterprise', label: 'Enterprise' },
	{ href: '/resources', label: 'Resources' }
]);

export const PUBLIC_RESOURCES_DROPDOWN_LINKS: readonly PublicNavLink[] = Object.freeze([
	{ href: '/resources', label: 'Resource Hub' },
	{ href: '/#trust', label: 'Proof' },
	{ href: '/docs', label: 'Docs' },
	{ href: '/blog', label: 'Blog' },
	{ href: '/insights', label: 'Insights' }
]);

export const PUBLIC_SECONDARY_LINKS: readonly PublicNavLink[] = Object.freeze([
	{ href: '/docs', label: 'Docs' },
	{ href: '/insights', label: 'Insights' },
	{ href: '/talk-to-sales', label: 'Talk to Sales' }
]);

export const PUBLIC_MOBILE_LINKS: readonly PublicNavLink[] = Object.freeze([
	{ href: '/#product', label: 'Product' },
	{ href: '/#signal-map', label: 'Live Demo' },
	{ href: '/#simulator', label: 'ROI' },
	{ href: '/pricing', label: 'Pricing' },
	{ href: '/enterprise', label: 'Enterprise' },
	{ href: '/resources', label: 'Resources' }
]);

export const PUBLIC_FOOTER_LINKS: readonly PublicNavLink[] = Object.freeze([
	{ href: '/docs', label: 'Documentation' },
	{ href: '/docs/api', label: 'API Reference' },
	{ href: '/resources', label: 'Resources' },
	{ href: '/enterprise', label: 'Enterprise' },
	{ href: '/blog', label: 'Blog' },
	{ href: '/insights', label: 'Insights' },
	{ href: '/talk-to-sales', label: 'Talk to Sales' },
	{ href: '/pricing', label: 'Pricing' },
	{ href: '/#trust', label: 'Trust' },
	{ href: '/privacy', label: 'Privacy' },
	{ href: '/terms', label: 'Terms' },
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

export const PUBLIC_CONTACT_CHANNELS: readonly PublicContactChannel[] = Object.freeze([
	{ label: 'Sales', email: 'sales@valdrics.com', href: 'mailto:sales@valdrics.com' },
	{ label: 'Support', email: 'support@valdrics.com', href: 'mailto:support@valdrics.com' },
	{ label: 'Security', email: 'security@valdrics.com', href: 'mailto:security@valdrics.com' }
]);

export const PUBLIC_EXTENDED_CONTACT_CHANNELS: readonly PublicContactChannel[] = Object.freeze([
	{ label: 'Enterprise', email: 'enterprise@valdrics.com', href: 'mailto:enterprise@valdrics.com' },
	{ label: 'Sales', email: 'sales@valdrics.com', href: 'mailto:sales@valdrics.com' },
	{ label: 'Support', email: 'support@valdrics.com', href: 'mailto:support@valdrics.com' },
	{ label: 'Security', email: 'security@valdrics.com', href: 'mailto:security@valdrics.com' },
	{ label: 'Billing', email: 'billing@valdrics.com', href: 'mailto:billing@valdrics.com' },
	{ label: 'Privacy', email: 'privacy@valdrics.com', href: 'mailto:privacy@valdrics.com' },
	{ label: 'General', email: 'hello@valdrics.com', href: 'mailto:hello@valdrics.com' },
	{ label: 'Abuse', email: 'abuse@valdrics.com', href: 'mailto:abuse@valdrics.com' },
	{ label: 'Postmaster', email: 'postmaster@valdrics.com', href: 'mailto:postmaster@valdrics.com' }
]);
