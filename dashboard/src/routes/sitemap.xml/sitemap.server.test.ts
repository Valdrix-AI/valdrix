import { describe, expect, it } from 'vitest';
import { GET } from './+server';

describe('sitemap.xml route', () => {
	it('includes public docs and status entries', async () => {
		const response = await GET({
			url: new URL('https://example.com/sitemap.xml')
		} as Parameters<typeof GET>[0]);

		expect(response.status).toBe(200);
		const xml = await response.text();
		expect(xml).toContain('https://example.com/docs');
		expect(xml).toContain('https://example.com/docs/api');
		expect(xml).toContain('https://example.com/docs/technical-validation');
		expect(xml).toContain('https://example.com/status');
	});
});
