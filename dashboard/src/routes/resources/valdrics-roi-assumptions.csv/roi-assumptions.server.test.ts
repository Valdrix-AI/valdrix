import { describe, expect, it } from 'vitest';
import { GET } from './+server';

describe('resources ROI assumptions download route', () => {
	it('returns attachment csv payload', async () => {
		const response = await GET({} as Parameters<typeof GET>[0]);
		expect(response.status).toBe(200);
		expect(response.headers.get('content-type')).toContain('text/csv');
		expect(response.headers.get('content-disposition')).toContain('attachment;');
		const body = await response.text();
		expect(body).toContain('variable,description,example_value');
		expect(body).toContain('monthly_spend_usd');
		expect(body).toContain('platform_annual_cost_usd');
	});
});
