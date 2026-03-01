import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
	fetchWithTimeout: vi.fn(),
	isPublicPath: vi.fn(),
	edgeApiPath: vi.fn((path: string) => path)
}));

vi.mock('$lib/fetchWithTimeout', () => ({
	fetchWithTimeout: mocks.fetchWithTimeout
}));

vi.mock('$lib/routeProtection', () => ({
	isPublicPath: mocks.isPublicPath
}));

vi.mock('$lib/edgeProxy', () => ({
	edgeApiPath: mocks.edgeApiPath
}));

import { load } from './+layout.server';

function jsonResponse(payload: unknown, status = 200): Response {
	return new Response(JSON.stringify(payload), {
		status,
		headers: { 'Content-Type': 'application/json' }
	});
}

function createCookies(names: string[]) {
	return {
		getAll: () => names.map((name) => ({ name, value: 'cookie-value' }))
	};
}

describe('layout server load', () => {
	beforeEach(() => {
		mocks.fetchWithTimeout.mockReset();
		mocks.isPublicPath.mockReset();
		mocks.edgeApiPath.mockClear();
	});

	it('skips session resolution for anonymous public requests', async () => {
		mocks.isPublicPath.mockReturnValue(true);

		const safeGetSession = vi.fn();
		const result = await load({
			locals: { safeGetSession },
			fetch: vi.fn() as unknown as typeof fetch,
			url: new URL('https://example.com/'),
			cookies: createCookies([])
		} as unknown as Parameters<typeof load>[0]);

		expect(safeGetSession).not.toHaveBeenCalled();
		expect(mocks.fetchWithTimeout).not.toHaveBeenCalled();
		expect(result.user).toBeNull();
		expect(result.session).toBeNull();
		expect(result.subscription).toEqual({ tier: 'free', status: 'active' });
	});

	it('resolves session on public requests when supabase cookies exist', async () => {
		mocks.isPublicPath.mockReturnValue(true);

		const safeGetSession = vi.fn().mockResolvedValue({
			session: { access_token: 'token' },
			user: { id: 'user-1' }
		});
		mocks.fetchWithTimeout
			.mockResolvedValueOnce(jsonResponse({ tier: 'pro', status: 'active' }))
			.mockResolvedValueOnce(jsonResponse({ persona: 'finance', role: 'owner' }));

		const result = await load({
			locals: { safeGetSession },
			fetch: vi.fn() as unknown as typeof fetch,
			url: new URL('https://example.com/'),
			cookies: createCookies(['sb-project-auth-token'])
		} as unknown as Parameters<typeof load>[0]);

		expect(safeGetSession).toHaveBeenCalledTimes(1);
		expect(mocks.fetchWithTimeout).toHaveBeenCalledTimes(2);
		expect(result.subscription).toEqual({ tier: 'pro', status: 'active' });
		expect(result.profile).toEqual({ persona: 'finance', role: 'owner' });
	});

	it('degrades gracefully when public session resolution fails', async () => {
		mocks.isPublicPath.mockReturnValue(true);
		const safeGetSession = vi.fn().mockRejectedValue(new Error('dns failure'));

		const result = await load({
			locals: { safeGetSession },
			fetch: vi.fn() as unknown as typeof fetch,
			url: new URL('https://example.com/'),
			cookies: createCookies(['sb-project-auth-token'])
		} as unknown as Parameters<typeof load>[0]);

		expect(safeGetSession).toHaveBeenCalledTimes(1);
		expect(result.session).toBeNull();
		expect(result.user).toBeNull();
		expect(mocks.fetchWithTimeout).not.toHaveBeenCalled();
	});

	it('throws when protected-path session resolution fails', async () => {
		mocks.isPublicPath.mockReturnValue(false);
		const safeGetSession = vi.fn().mockRejectedValue(new Error('dns failure'));

		await expect(
			load({
				locals: { safeGetSession },
				fetch: vi.fn() as unknown as typeof fetch,
				url: new URL('https://example.com/ops'),
				cookies: createCookies(['sb-project-auth-token'])
			} as unknown as Parameters<typeof load>[0])
		).rejects.toThrow('session_resolution_failed');
	});
});
