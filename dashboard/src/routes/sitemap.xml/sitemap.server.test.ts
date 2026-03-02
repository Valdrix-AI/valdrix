import { afterEach, describe, expect, it } from 'vitest';
import { GET } from './+server';

const ORIGINAL_PUBLIC_LASTMOD = process.env.PUBLIC_SITEMAP_LASTMOD;
const ORIGINAL_PRIVATE_LASTMOD = process.env.SITEMAP_LASTMOD;

afterEach(() => {
	if (ORIGINAL_PUBLIC_LASTMOD === undefined) {
		delete process.env.PUBLIC_SITEMAP_LASTMOD;
	} else {
		process.env.PUBLIC_SITEMAP_LASTMOD = ORIGINAL_PUBLIC_LASTMOD;
	}
	if (ORIGINAL_PRIVATE_LASTMOD === undefined) {
		delete process.env.SITEMAP_LASTMOD;
	} else {
		process.env.SITEMAP_LASTMOD = ORIGINAL_PRIVATE_LASTMOD;
	}
});

describe('sitemap.xml route', () => {
	it('includes public docs and status entries', async () => {
		delete process.env.PUBLIC_SITEMAP_LASTMOD;
		delete process.env.SITEMAP_LASTMOD;

		const response = await GET({
			url: new URL('https://example.com/sitemap.xml')
		} as Parameters<typeof GET>[0]);

		expect(response.status).toBe(200);
		const xml = await response.text();
		expect(xml).toContain('https://example.com/docs');
		expect(xml).toContain('https://example.com/docs/api');
		expect(xml).toContain('https://example.com/docs/technical-validation');
		expect(xml).toContain('https://example.com/insights');
		expect(xml).toContain('https://example.com/resources');
		expect(xml).toContain('https://example.com/talk-to-sales');
		expect(xml).toContain('https://example.com/status');
		expect(xml).not.toContain('<lastmod>');
	});

	it('emits deterministic lastmod when configured', async () => {
		process.env.PUBLIC_SITEMAP_LASTMOD = '2026-03-01T12:00:00Z';
		delete process.env.SITEMAP_LASTMOD;

		const response = await GET({
			url: new URL('https://example.com/sitemap.xml')
		} as Parameters<typeof GET>[0]);

		const xml = await response.text();
		expect(xml).toContain('<lastmod>2026-03-01T12:00:00.000Z</lastmod>');
		expect(xml).toContain('https://example.com/pricing');
	});

	it('ignores invalid configured lastmod values', async () => {
		process.env.PUBLIC_SITEMAP_LASTMOD = 'not-a-date';
		delete process.env.SITEMAP_LASTMOD;

		const response = await GET({
			url: new URL('https://example.com/sitemap.xml')
		} as Parameters<typeof GET>[0]);

		const xml = await response.text();
		expect(xml).not.toContain('<lastmod>');
	});
});
