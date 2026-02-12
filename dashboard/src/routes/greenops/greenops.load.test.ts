import { describe, expect, it, vi } from 'vitest';
import { load } from './+page';

function jsonResponse(payload: unknown, status = 200): Response {
	return new Response(JSON.stringify(payload), {
		status,
		headers: { 'Content-Type': 'application/json' }
	});
}

describe('greenops load contract', () => {
	it('calls the namespaced graviton endpoint under /carbon', async () => {
		const calls: string[] = [];
		const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
			const url = String(input);
			calls.push(url);
			return jsonResponse({});
		});

		await load({
			fetch: fetchMock as unknown as typeof fetch,
			parent: async () => ({
				session: { access_token: 'token' }
			}),
			url: new URL('http://localhost/greenops?region=eu-west-1')
		} as Parameters<typeof load>[0]);

		expect(calls.some((u) => u.includes('/carbon/graviton?region=eu-west-1'))).toBe(true);
		expect(calls.some((u) => /\/api\/v1\/graviton\?region=eu-west-1/.test(u))).toBe(false);
	});
});
