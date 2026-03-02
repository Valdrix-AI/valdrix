import { describe, expect, it } from 'vitest';
import { GET } from './+server';

describe('resources one-pager download route', () => {
	it('returns attachment markdown payload', async () => {
		const response = await GET({} as Parameters<typeof GET>[0]);
		expect(response.status).toBe(200);
		expect(response.headers.get('content-type')).toContain('text/markdown');
		expect(response.headers.get('content-disposition')).toContain('attachment;');
		const body = await response.text();
		expect(body).toContain('# Valdrics Executive One-Pager');
		expect(body).toContain('economic control plane');
	});
});
