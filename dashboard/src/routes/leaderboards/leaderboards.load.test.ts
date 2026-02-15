import { describe, expect, it, vi } from 'vitest';
import { load } from './+page';

type LeaderboardLoadResult = {
	period: string;
};

describe('leaderboards load contract', () => {
	it('returns normalized period immediately without API fetch', async () => {
		const fetchMock = vi.fn(async () => new Response('{}'));

		const result = (await load({
			fetch: fetchMock as unknown as typeof fetch,
			parent: async () => ({ session: null }),
			url: new URL('http://localhost/leaderboards?period=yearly')
		} as Parameters<typeof load>[0])) as LeaderboardLoadResult;

		expect(fetchMock).not.toHaveBeenCalled();
		expect(result.period).toBe('30d');
	});

	it('preserves supported period values', async () => {
		const fetchMock = vi.fn(async () => new Response('{}'));

		const result = (await load({
			fetch: fetchMock as unknown as typeof fetch,
			parent: async () => ({ session: { access_token: 'token' } }),
			url: new URL('http://localhost/leaderboards?period=7d')
		} as Parameters<typeof load>[0])) as LeaderboardLoadResult;

		expect(fetchMock).not.toHaveBeenCalled();
		expect(result.period).toBe('7d');
	});
});
