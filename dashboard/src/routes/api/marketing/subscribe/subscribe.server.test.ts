import { afterEach, describe, expect, it, vi } from 'vitest';
import { POST, _resetMarketingSubscribeRateLimitForTests } from './+server';

vi.mock('$lib/server/backend-origin', () => ({
	resolveBackendOrigin: () => 'https://api.example.com'
}));

const ORIGINAL_WEBHOOK_URL = process.env.MARKETING_SUBSCRIBE_WEBHOOK_URL;

function buildRequest(body: unknown): Request {
	return new Request('https://example.com/api/marketing/subscribe', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(body)
	});
}

afterEach(() => {
	_resetMarketingSubscribeRateLimitForTests();
	vi.restoreAllMocks();
	if (ORIGINAL_WEBHOOK_URL === undefined) {
		delete process.env.MARKETING_SUBSCRIBE_WEBHOOK_URL;
	} else {
		process.env.MARKETING_SUBSCRIBE_WEBHOOK_URL = ORIGINAL_WEBHOOK_URL;
	}
});

describe('marketing subscribe route', () => {
	it('accepts valid subscription payloads', async () => {
		const fetchMock = vi.fn().mockResolvedValue(
			new Response(JSON.stringify({ ok: true, accepted: true, emailHash: 'a'.repeat(64) }), {
				status: 202,
				headers: { 'content-type': 'application/json' }
			})
		);
		const response = await POST({
			request: buildRequest({
				email: 'buyer@example.com',
				company: 'Example Inc',
				role: 'FinOps'
			}),
			fetch: fetchMock
		} as Parameters<typeof POST>[0]);

		expect(response.status).toBe(202);
		const payload = await response.json();
		expect(payload.ok).toBe(true);
		expect(payload.accepted).toBe(true);
		expect(String(payload.emailHash)).toHaveLength(64);
		expect(fetchMock).toHaveBeenCalledOnce();
	});

	it('rejects invalid payloads', async () => {
		const response = await POST({
			request: buildRequest({ email: 'not-an-email' }),
			getClientAddress: () => '127.0.0.2'
		} as Parameters<typeof POST>[0]);

		expect(response.status).toBe(400);
		const payload = await response.json();
		expect(payload.ok).toBe(false);
		expect(payload.error).toBe('invalid_payload');
	});

	it('silently accepts honeypot submissions', async () => {
		const fetchMock = vi.fn();
		const response = await POST({
			request: buildRequest({ email: 'bot@example.com', honey: 'filled' }),
			fetch: fetchMock
		} as Parameters<typeof POST>[0]);

		expect(response.status).toBe(202);
		const payload = await response.json();
		expect(payload.ok).toBe(true);
		expect(payload.accepted).toBe(true);
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('surfaces backend rate limiting responses', async () => {
		const fetchMock = vi.fn().mockResolvedValue(
			new Response(JSON.stringify({ ok: false, error: 'rate_limited' }), {
				status: 429,
				headers: { 'content-type': 'application/json' }
			})
		);
		const blocked = await POST({
			request: buildRequest({ email: 'ops+blocked@example.com' }),
			fetch: fetchMock
		} as Parameters<typeof POST>[0]);
		expect(blocked.status).toBe(429);
		const payload = await blocked.json();
		expect(payload.error).toBe('rate_limited');
	});

	it('returns delivery failure when backend subscribe proxy fails', async () => {
		const response = await POST({
			request: buildRequest({ email: 'cfo@example.com' }),
			fetch: vi.fn().mockRejectedValue(new Error('upstream unavailable'))
		} as Parameters<typeof POST>[0]);

		expect(response.status).toBe(503);
		const payload = await response.json();
		expect(payload.ok).toBe(false);
		expect(payload.error).toBe('delivery_failed');
	});
});
