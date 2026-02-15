import { describe, expect, it, vi } from 'vitest';
import { load } from './+page';

describe('greenops load contract', () => {
	it('returns selected region immediately without API fetch', async () => {
		const fetchMock = vi.fn(async () => new Response('{}'));

		const result = (await load({
			fetch: fetchMock as unknown as typeof fetch,
			parent: async () => ({
				session: { access_token: 'token' }
			}),
			url: new URL('http://localhost/greenops?region=eu-west-1')
		} as Parameters<typeof load>[0])) as { selectedRegion: string };

		expect(fetchMock).not.toHaveBeenCalled();
		expect(result.selectedRegion).toBe('eu-west-1');
	});
});
