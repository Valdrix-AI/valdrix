import { describe, expect, it } from 'vitest';
import { GET } from './+server';

describe('security.txt route', () => {
	it('returns RFC 9116-style contact metadata', async () => {
		const response = await GET();
		expect(response.status).toBe(200);
		expect(response.headers.get('Content-Type')).toContain('text/plain');
		expect(response.headers.get('Cache-Control')).toContain('public');
		const body = await response.text();
		expect(body).toContain('Contact: mailto:security@valdrics.com');
		expect(body).toContain('Contact: mailto:privacy@valdrics.com');
		expect(body).toContain('Policy: https://valdrics.com/privacy');
		expect(body).toContain('Canonical: https://valdrics.com/.well-known/security.txt');
		expect(body).toContain('Expires: 2027-03-04T00:00:00.000Z');
	});
});
