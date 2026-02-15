export type Persona = 'engineering' | 'finance' | 'platform' | 'leadership';

export function normalizePersona(value: unknown): Persona {
	const normalized = String(value || '')
		.toLowerCase()
		.trim();
	if (normalized === 'finance') return 'finance';
	if (normalized === 'platform') return 'platform';
	if (normalized === 'leadership') return 'leadership';
	return 'engineering';
}

export function isAdminRole(role: unknown): boolean {
	const normalized = String(role || '')
		.toLowerCase()
		.trim();
	return normalized === 'admin' || normalized === 'owner';
}

export function allowedNavHrefs(persona: unknown, role: unknown): Set<string> {
	const p = normalizePersona(persona);
	const isAdmin = isAdminRole(role);

	let hrefs: string[];
	switch (p) {
		case 'finance':
			hrefs = ['/', '/leaderboards', '/savings', '/billing', '/connections', '/greenops', '/audit'];
			break;
		case 'platform':
			hrefs = ['/ops', '/connections', '/audit', '/admin/health'];
			break;
		case 'leadership':
			hrefs = ['/', '/leaderboards', '/savings', '/greenops', '/audit'];
			break;
		case 'engineering':
		default:
			hrefs = ['/', '/ops', '/connections', '/greenops', '/llm', '/audit'];
			break;
	}

	// Safety: settings and onboarding should always be discoverable.
	hrefs.push('/settings', '/onboarding');

	// Subscription management is an admin concern, regardless of persona.
	if (isAdmin) {
		hrefs.push('/billing');
	}

	// Hide admin health unless admin/owner.
	if (!isAdmin) {
		hrefs = hrefs.filter((href) => href !== '/admin/health');
	}

	return new Set(hrefs);
}
