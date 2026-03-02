import type { RequestHandler } from './$types';

type SitemapEntry = {
	path: string;
	changefreq?: 'daily' | 'weekly' | 'monthly' | 'yearly' | 'never';
	priority?: number;
};

const PUBLIC_ENTRIES: SitemapEntry[] = [
	{ path: '/', changefreq: 'weekly', priority: 1.0 },
	{ path: '/docs', changefreq: 'weekly', priority: 0.8 },
	{ path: '/docs/api', changefreq: 'weekly', priority: 0.7 },
	{ path: '/docs/technical-validation', changefreq: 'weekly', priority: 0.7 },
	{ path: '/insights', changefreq: 'weekly', priority: 0.75 },
	{ path: '/resources', changefreq: 'weekly', priority: 0.75 },
	{ path: '/talk-to-sales', changefreq: 'weekly', priority: 0.8 },
	{ path: '/status', changefreq: 'daily', priority: 0.6 },
	{ path: '/pricing', changefreq: 'monthly', priority: 0.9 },
	{ path: '/auth/login', changefreq: 'monthly', priority: 0.7 },
	{ path: '/terms', changefreq: 'yearly', priority: 0.4 },
	{ path: '/privacy', changefreq: 'yearly', priority: 0.4 }
];

function basePathFor(url: URL, suffix: string): string {
	const pathname = url.pathname;
	if (!pathname.endsWith(suffix)) return '';
	const basePath = pathname.slice(0, -suffix.length);
	return basePath === '/' ? '' : basePath;
}

function escapeXml(value: string): string {
	return value
		.replaceAll('&', '&amp;')
		.replaceAll('<', '&lt;')
		.replaceAll('>', '&gt;')
		.replaceAll('"', '&quot;')
		.replaceAll("'", '&apos;');
}

function normalizeConfiguredLastMod(value: string | undefined): string | null {
	if (!value) return null;
	const parsed = new Date(value);
	if (Number.isNaN(parsed.getTime())) return null;
	return parsed.toISOString();
}

export const GET: RequestHandler = ({ url }) => {
	const basePath = basePathFor(url, '/sitemap.xml');
	const configuredLastMod = normalizeConfiguredLastMod(
		process.env.PUBLIC_SITEMAP_LASTMOD ?? process.env.SITEMAP_LASTMOD
	);

	const urlsXml = PUBLIC_ENTRIES.map((entry) => {
		const loc = new URL(`${basePath}${entry.path}`, url.origin).toString();
		const lastmod = configuredLastMod ? `<lastmod>${escapeXml(configuredLastMod)}</lastmod>` : '';
		const changefreq = entry.changefreq ? `<changefreq>${entry.changefreq}</changefreq>` : '';
		const priority =
			typeof entry.priority === 'number' ? `<priority>${entry.priority.toFixed(1)}</priority>` : '';

		return [
			'<url>',
			`<loc>${escapeXml(loc)}</loc>`,
			lastmod,
			changefreq,
			priority,
			'</url>'
		]
			.filter(Boolean)
			.join('');
	}).join('');

	const xml = [
		'<?xml version="1.0" encoding="UTF-8"?>',
		'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
		urlsXml,
		'</urlset>',
		''
	].join('\n');

	return new Response(xml, {
		headers: {
			'Content-Type': 'application/xml; charset=utf-8',
			'Cache-Control': 'public, max-age=3600'
		}
	});
};
