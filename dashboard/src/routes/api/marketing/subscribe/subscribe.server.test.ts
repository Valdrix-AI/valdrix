import { afterEach, describe, expect, it, vi } from 'vitest';
import { POST, _resetMarketingSubscribeRateLimitForTests } from './+server';

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
		delete process.env.MARKETING_SUBSCRIBE_WEBHOOK_URL;
		const response = await POST({
			request: buildRequest({
				email: 'buyer@example.com',
				company: 'Example Inc',
				role: 'FinOps'
			}),
			getClientAddress: () => '127.0.0.1'
		} as Parameters<typeof POST>[0]);

		expect(response.status).toBe(202);
		const payload = await response.json();
		expect(payload.ok).toBe(true);
		expect(payload.accepted).toBe(true);
		expect(String(payload.emailHash)).toHaveLength(64);
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
		const response = await POST({
			request: buildRequest({ email: 'bot@example.com', honey: 'filled' }),
			getClientAddress: () => '127.0.0.3'
		} as Parameters<typeof POST>[0]);

		expect(response.status).toBe(202);
		const payload = await response.json();
		expect(payload.ok).toBe(true);
		expect(payload.accepted).toBe(true);
	});

	it('rate limits burst requests from the same client', async () => {
		const event = {
			request: buildRequest({ email: 'ops@example.com' }),
			getClientAddress: () => '127.0.0.4'
		} as Parameters<typeof POST>[0];

		for (let attempt = 0; attempt < 8; attempt += 1) {
			const response = await POST({
				...event,
				request: buildRequest({ email: `ops+${attempt}@example.com` })
			});
			expect(response.status).toBe(202);
		}

		const blocked = await POST({
			...event,
			request: buildRequest({ email: 'ops+blocked@example.com' })
		});
		expect(blocked.status).toBe(429);
	});

	it('returns delivery failure when webhook rejects payload', async () => {
		process.env.MARKETING_SUBSCRIBE_WEBHOOK_URL = 'https://hooks.example.com/subscribe';
		vi.spyOn(globalThis, 'fetch').mockResolvedValue(
			new Response('fail', { status: 500, statusText: 'Internal Server Error' })
		);

		const response = await POST({
			request: buildRequest({ email: 'cfo@example.com' }),
			getClientAddress: () => '127.0.0.5'
		} as Parameters<typeof POST>[0]);

		expect(response.status).toBe(503);
		const payload = await response.json();
		expect(payload.ok).toBe(false);
		expect(payload.error).toBe('delivery_failed');
	});
});
