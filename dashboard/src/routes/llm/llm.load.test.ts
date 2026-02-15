import { describe, expect, it, vi } from 'vitest';
import { load } from './+page';

type LlmLoadResult = {
	[key: string]: unknown;
};

describe('llm load contract', () => {
	it('returns immediately without API fetch when unauthenticated', async () => {
		const fetchMock = vi.fn(async () => new Response('{}'));

		const result = (await load({
			fetch: fetchMock as unknown as typeof fetch,
			parent: async () => ({ session: null })
		} as Parameters<typeof load>[0])) as LlmLoadResult;

		expect(fetchMock).not.toHaveBeenCalled();
		expect(result).toEqual({});
	});

	it('returns immediately without API fetch when authenticated', async () => {
		const fetchMock = vi.fn(async () => new Response('{}'));

		const result = (await load({
			fetch: fetchMock as unknown as typeof fetch,
			parent: async () => ({ session: { access_token: 'token' } })
		} as Parameters<typeof load>[0])) as LlmLoadResult;

		expect(fetchMock).not.toHaveBeenCalled();
		expect(result).toEqual({});
	});
});
