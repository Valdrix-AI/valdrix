import type { RequestHandler } from './$types';

type SitemapEntry = {
	path: string;
	changefreq?: 'daily' | 'weekly' | 'monthly' | 'yearly' | 'never';
	priority?: number;
};

const PUBLIC_ENTRIES: SitemapEntry[] = [
	{ path: '/', changefreq: 'weekly', priority: 1.0 },
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

export const GET: RequestHandler = ({ url }) => {
	const basePath = basePathFor(url, '/sitemap.xml');
	const lastMod = new Date().toISOString();

	const urlsXml = PUBLIC_ENTRIES.map((entry) => {
		const loc = new URL(`${basePath}${entry.path}`, url.origin).toString();
		const changefreq = entry.changefreq ? `<changefreq>${entry.changefreq}</changefreq>` : '';
		const priority =
			typeof entry.priority === 'number' ? `<priority>${entry.priority.toFixed(1)}</priority>` : '';

		return [
			'<url>',
			`<loc>${escapeXml(loc)}</loc>`,
			`<lastmod>${escapeXml(lastMod)}</lastmod>`,
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
