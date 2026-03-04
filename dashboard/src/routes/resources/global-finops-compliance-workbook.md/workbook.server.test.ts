import { describe, expect, it } from 'vitest';
import { GET } from './+server';

describe('global compliance workbook download route', () => {
	it('returns markdown attachment with cache headers', async () => {
		const response = await GET();
		expect(response.status).toBe(200);
		expect(response.headers.get('Content-Type')).toContain('text/markdown');
		expect(response.headers.get('Content-Disposition')).toContain(
			'global-finops-compliance-workbook.md'
		);
		expect(response.headers.get('Cache-Control')).toContain('public');
		const body = await response.text();
		expect(body).toContain('Valdrics Access Control and Compliance Checklist');
		expect(body).toContain('enterprise@valdrics.com');
		expect(body).toContain('sales@valdrics.com');
	});
});
