import { describe, expect, it } from 'vitest';
import { GET } from './+server';

describe('customer comments feed route', () => {
	it('returns public customer comments with cache headers', async () => {
		const response = await GET({} as Parameters<typeof GET>[0]);
		expect(response.status).toBe(200);
		expect(response.headers.get('cache-control')).toContain('max-age=15');
		const payload = (await response.json()) as {
			items: Array<{ quote: string; attribution: string; stage: string }>;
			meta: { total: number; hasLiveCustomerEvidence: boolean };
		};
		expect(Array.isArray(payload.items)).toBe(true);
		expect(payload.items.length).toBeGreaterThan(0);
		expect(payload.items[0]?.quote).toBeTruthy();
		expect(payload.items[0]?.attribution).toBeTruthy();
		expect(payload.meta.total).toBe(payload.items.length);
	});
});
