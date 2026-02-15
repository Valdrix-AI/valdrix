import type { RequestHandler } from './$types';

function basePathFor(url: URL, suffix: string): string {
	const pathname = url.pathname;
	if (!pathname.endsWith(suffix)) return '';
	const basePath = pathname.slice(0, -suffix.length);
	return basePath === '/' ? '' : basePath;
}

export const GET: RequestHandler = ({ url }) => {
	const basePath = basePathFor(url, '/robots.txt');
	const sitemapUrl = `${url.origin}${basePath}/sitemap.xml`;

	// Keep robots conservative: allow crawl of marketing pages, discourage noisy/low-value paths.
	const body = [
		'User-agent: *',
		'Disallow: /auth/',
		'Disallow: /_app/',
		`Sitemap: ${sitemapUrl}`,
		''
	].join('\n');

	return new Response(body, {
		headers: {
			'Content-Type': 'text/plain; charset=utf-8',
			// Robots changes are infrequent; allow caching to reduce load.
			'Cache-Control': 'public, max-age=3600'
		}
	});
};
