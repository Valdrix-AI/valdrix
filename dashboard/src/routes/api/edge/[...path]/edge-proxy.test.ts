import { beforeEach, describe, expect, it, vi } from 'vitest';
import { GET } from './+server';

const upstreamFetch = vi.fn();

describe('edge proxy auth forwarding', () => {
	beforeEach(() => {
		process.env.PRIVATE_API_ORIGIN = 'http://upstream.test';
		upstreamFetch.mockReset();
		upstreamFetch.mockResolvedValue(
			new Response(JSON.stringify({ ok: true }), {
				status: 200,
				headers: { 'content-type': 'application/json' }
			})
		);
		vi.stubGlobal('fetch', upstreamFetch);
	});

	it('injects session bearer for jobs stream when request has no authorization header', async () => {
		const event = {
			request: new Request('http://localhost:4173/api/edge/jobs/stream'),
			params: { path: 'jobs/stream' },
			locals: {
				safeGetSession: vi.fn().mockResolvedValue({
					session: { access_token: 'session-token' }
				})
			},
			platform: undefined
		};

		const response = await GET(event as unknown as Parameters<typeof GET>[0]);
		expect(response.status).toBe(200);
		expect(upstreamFetch).toHaveBeenCalledTimes(1);
		const [, init] = upstreamFetch.mock.calls[0] as [string, RequestInit];
		const headers = init.headers as Headers;
		expect(headers.get('authorization')).toBe('Bearer session-token');
		expect(headers.get('x-valdrics-edge-proxy')).toBe('1');
	});

	it('does not accept query-string token fallback for jobs stream', async () => {
		const event = {
			request: new Request(
				'http://localhost:4173/api/edge/jobs/stream?sse_access_token=attacker-token'
			),
			params: { path: 'jobs/stream' },
			locals: {
				safeGetSession: vi.fn().mockResolvedValue({
					session: null
				})
			},
			platform: undefined
		};

		const response = await GET(event as unknown as Parameters<typeof GET>[0]);
		expect(response.status).toBe(200);
		expect(upstreamFetch).toHaveBeenCalledTimes(1);
		const [, init] = upstreamFetch.mock.calls[0] as [string, RequestInit];
		const headers = init.headers as Headers;
		expect(headers.get('authorization')).toBeNull();
	});
});
