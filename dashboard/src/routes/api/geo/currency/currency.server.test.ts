import { describe, expect, it } from 'vitest';
import { GET } from './+server';

function buildRequest(headers: Record<string, string> = {}): Request {
	return new Request('https://example.com/api/geo/currency', {
		method: 'GET',
		headers
	});
}

describe('geo currency route', () => {
	it('resolves NGN from Cloudflare country header', async () => {
		const response = await GET({
			request: buildRequest({ 'cf-ipcountry': 'NG' })
		} as Parameters<typeof GET>[0]);

		expect(response.status).toBe(200);
		expect(response.headers.get('cache-control')).toContain('private');
		const payload = await response.json();
		expect(payload.currencyCode).toBe('NGN');
		expect(payload.countryCode).toBe('NG');
		expect(payload.source).toBe('ip_country_header');
	});

	it('falls back to secondary country header when Cloudflare header is absent', async () => {
		const response = await GET({
			request: buildRequest({ 'x-vercel-ip-country': 'GB' })
		} as Parameters<typeof GET>[0]);

		expect(response.status).toBe(200);
		const payload = await response.json();
		expect(payload.currencyCode).toBe('GBP');
		expect(payload.countryCode).toBe('GB');
		expect(payload.source).toBe('ip_country_header');
	});

	it('returns USD default when no country hint is available', async () => {
		const response = await GET({
			request: buildRequest()
		} as Parameters<typeof GET>[0]);

		expect(response.status).toBe(200);
		const payload = await response.json();
		expect(payload.currencyCode).toBe('USD');
		expect(payload.countryCode).toBeNull();
		expect(payload.source).toBe('default');
	});

	it('ignores untrusted country-code header and keeps USD default', async () => {
		const response = await GET({
			request: buildRequest({ 'x-country-code': 'NG' })
		} as Parameters<typeof GET>[0]);

		expect(response.status).toBe(200);
		const payload = await response.json();
		expect(payload.currencyCode).toBe('USD');
		expect(payload.countryCode).toBeNull();
		expect(payload.source).toBe('default');
	});
});
