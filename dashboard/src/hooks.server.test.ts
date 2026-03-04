import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
	createServerClient: vi.fn(),
	isPublicPath: vi.fn(),
	canUseE2EAuthBypass: vi.fn(),
	shouldUseSecureCookies: vi.fn(),
	publicEnv: {
		PUBLIC_SUPABASE_URL: 'https://supabase.example.co',
		PUBLIC_SUPABASE_ANON_KEY: 'anon-key'
	},
	privateEnv: {
		NODE_ENV: 'production',
		TESTING: 'false',
		E2E_ALLOW_PROD_PREVIEW: 'false',
		E2E_AUTH_SECRET: ''
	}
}));

vi.mock('@supabase/ssr', () => ({
	createServerClient: (...args: unknown[]) => mocks.createServerClient(...args)
}));

vi.mock('$env/dynamic/public', () => ({
	env: mocks.publicEnv
}));

vi.mock('$env/dynamic/private', () => ({
	env: mocks.privateEnv
}));

vi.mock('$lib/routeProtection', () => ({
	isPublicPath: (...args: unknown[]) => mocks.isPublicPath(...args)
}));

vi.mock('$lib/serverSecurity', () => ({
	canUseE2EAuthBypass: (...args: unknown[]) => mocks.canUseE2EAuthBypass(...args),
	shouldUseSecureCookies: (...args: unknown[]) => mocks.shouldUseSecureCookies(...args)
}));

import { handle } from './hooks.server';

function createEvent(url: string): Parameters<typeof handle>[0]['event'] {
	return {
		request: new Request(url),
		url: new URL(url),
		cookies: {
			get: vi.fn(),
			set: vi.fn(),
			delete: vi.fn()
		},
		locals: {}
	} as unknown as Parameters<typeof handle>[0]['event'];
}

describe('hooks.server handle', () => {
	beforeEach(() => {
		mocks.publicEnv.PUBLIC_SUPABASE_URL = 'https://supabase.example.co';
		mocks.publicEnv.PUBLIC_SUPABASE_ANON_KEY = 'anon-key';
		mocks.isPublicPath.mockReset();
		mocks.createServerClient.mockReset();
		mocks.canUseE2EAuthBypass.mockReset();
		mocks.shouldUseSecureCookies.mockReset();
		mocks.canUseE2EAuthBypass.mockReturnValue(false);
		mocks.shouldUseSecureCookies.mockReturnValue(true);
	});

	it('allows public routes even when Supabase public env is missing', async () => {
		mocks.publicEnv.PUBLIC_SUPABASE_URL = '';
		mocks.publicEnv.PUBLIC_SUPABASE_ANON_KEY = '';
		mocks.isPublicPath.mockReturnValue(true);

		const event = createEvent('https://example.com/');
		const resolve = vi.fn(
			async () =>
				new Response('<html></html>', {
					status: 200,
					headers: { 'content-type': 'text/html' }
				})
		);

		const response = await handle({
			event,
			resolve
		} as Parameters<typeof handle>[0]);

		expect(response.status).toBe(200);
		expect(resolve).toHaveBeenCalledTimes(1);
		expect(mocks.createServerClient).not.toHaveBeenCalled();
		const sessionResult = await event.locals.safeGetSession();
		expect(sessionResult).toEqual({ session: null, user: null });
	});

	it('fails closed for protected routes when Supabase public env is missing', async () => {
		mocks.publicEnv.PUBLIC_SUPABASE_URL = '';
		mocks.publicEnv.PUBLIC_SUPABASE_ANON_KEY = '';
		mocks.isPublicPath.mockReturnValue(false);

		const event = createEvent('https://example.com/ops');
		const resolve = vi.fn();

		const response = await handle({
			event,
			resolve
		} as Parameters<typeof handle>[0]);

		expect(response.status).toBe(503);
		expect(resolve).not.toHaveBeenCalled();
	});

	it('redirects protected routes to login when session is absent', async () => {
		mocks.isPublicPath.mockReturnValue(false);
		mocks.createServerClient.mockReturnValue({
			auth: {
				getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
				getUser: vi.fn()
			}
		});

		const event = createEvent('https://example.com/settings');
		const resolve = vi.fn();

		const response = await handle({
			event,
			resolve
		} as Parameters<typeof handle>[0]);

		expect(response.status).toBe(303);
		expect(response.headers.get('location')).toBe('/auth/login');
		expect(resolve).not.toHaveBeenCalled();
	});
});
