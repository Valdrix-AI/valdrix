import { base } from '$app/paths';

const PUBLIC_EXACT_PATHS = new Set<string>([
	'/',
	'/robots.txt',
	'/sitemap.xml',
	'/terms',
	'/privacy',
	'/insights',
	'/talk-to-sales',
	'/status'
]);

// Segment-safe prefixes: only match "/prefix" or "/prefix/...".
const PUBLIC_SEGMENT_PREFIXES = [
	'/auth',
	'/pricing',
	'/docs',
	'/resources',
	'/api/marketing',
	'/_app' // SvelteKit build assets
];

// Loose prefixes: allow "/favicon.ico", "/favicon.png", etc.
const PUBLIC_LOOSE_PREFIXES = ['/favicon', '/og-image'];

export function isPublicPath(pathname: string): boolean {
	const normalized = (() => {
		if (!base) return pathname;
		if (pathname === base) return '/';
		if (pathname.startsWith(`${base}/`)) return pathname.slice(base.length) || '/';
		return pathname;
	})();

	if (PUBLIC_EXACT_PATHS.has(normalized)) return true;
	if (PUBLIC_LOOSE_PREFIXES.some((prefix) => normalized.startsWith(prefix))) return true;
	return PUBLIC_SEGMENT_PREFIXES.some(
		(prefix) => normalized === prefix || normalized.startsWith(`${prefix}/`)
	);
}
