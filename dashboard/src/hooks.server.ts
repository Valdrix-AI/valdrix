/**
 * Server Hooks - Runs on every request
 *
 * Purpose:
 * 1. Creates Supabase client for server-side use
 * 2. Validates and refreshes sessions
 * 3. Makes session available to routes via locals
 */

import { createServerClient } from '@supabase/ssr';
import { env as publicEnv } from '$env/dynamic/public';
import { env } from '$env/dynamic/private';
import type { Handle } from '@sveltejs/kit';
import type { Session, User } from '@supabase/supabase-js';
import { isPublicPath } from '$lib/routeProtection';
import { canUseE2EAuthBypass, shouldUseSecureCookies } from '$lib/serverSecurity';

const E2E_AUTH_HEADER = 'x-valdrics-e2e-auth';

function buildE2EBypassAuth(): { session: Session; user: User } {
	const now = Math.floor(Date.now() / 1000);
	const user = {
		id: '00000000-0000-4000-8000-000000000001',
		aud: 'authenticated',
		role: 'authenticated',
		email: 'e2e@valdrics.test',
		email_confirmed_at: new Date(0).toISOString(),
		phone: '',
		app_metadata: { provider: 'email', providers: ['email'] },
		user_metadata: { name: 'E2E Test User', source: 'playwright' },
		identities: [],
		created_at: new Date(0).toISOString(),
		updated_at: new Date().toISOString(),
		is_anonymous: false
	} as unknown as User;

	const session = {
		access_token: 'e2e-access-token',
		refresh_token: 'e2e-refresh-token',
		expires_in: 3600,
		expires_at: now + 3600,
		token_type: 'bearer',
		user
	} as unknown as Session;

	return { session, user };
}

export const handle: Handle = async ({ event, resolve }) => {
	const isHttps = shouldUseSecureCookies(event.url, env.NODE_ENV || '');
	const publicSupabaseUrl = String(publicEnv.PUBLIC_SUPABASE_URL || '').trim();
	const publicSupabaseAnonKey = String(publicEnv.PUBLIC_SUPABASE_ANON_KEY || '').trim();

	if (!publicSupabaseUrl || !publicSupabaseAnonKey) {
		throw new Error(
			'Supabase public environment is not configured. Set PUBLIC_SUPABASE_URL and PUBLIC_SUPABASE_ANON_KEY.'
		);
	}

	// Create a Supabase client with cookie handling
	event.locals.supabase = createServerClient(publicSupabaseUrl, publicSupabaseAnonKey, {
		cookies: {
			get: (key) => event.cookies.get(key),
			set: (key, value, options) => {
				event.cookies.set(key, value, {
					path: '/',
					httpOnly: true,
					secure: isHttps,
					sameSite: 'strict',
					...options
				});
			},
			remove: (key, options) => {
				event.cookies.delete(key, {
					path: '/',
					httpOnly: true,
					secure: isHttps,
					sameSite: 'strict',
					...options
				});
			}
		}
	});

	event.locals.safeGetSession = async () => {
		const testingMode = env.TESTING === 'true';
		const allowProdPreviewBypass = env.E2E_ALLOW_PROD_PREVIEW === 'true';
		const canUseBypass = canUseE2EAuthBypass({
			testingMode,
			allowProdPreviewBypass,
			isDevBuild: import.meta.env.DEV,
			hostname: event.url.hostname
		});
		if (canUseBypass) {
			const provided = event.request.headers.get(E2E_AUTH_HEADER);
			const expected = String(env.E2E_AUTH_SECRET || '').trim();
			if (provided && expected && provided === expected) {
				return buildE2EBypassAuth();
			}
		}

		try {
			const {
				data: { session }
			} = await event.locals.supabase.auth.getSession();
			if (!session) return { session: null, user: null };

			const {
				data: { user },
				error
			} = await event.locals.supabase.auth.getUser();

			if (error || !user) {
				// validation failed
				return { session: null, user: null };
			}

			return { session, user };
		} catch {
			// Public edge hardening: avoid request crashes on auth provider resolution faults.
			return { session: null, user: null };
		}
	};

	// Auth Guard: Protect all application routes by default.
	// Only allow public access to explicit public paths (auth, pricing, landing, assets).
	if (!isPublicPath(event.url.pathname)) {
		const { session } = await event.locals.safeGetSession();
		if (!session) {
			return new Response(null, {
				status: 303,
				headers: { Location: '/auth/login' }
			});
		}
	}

	const response = await resolve(event, {
		// Filter out sensitive auth headers from responses
		filterSerializedResponseHeaders(name) {
			return name === 'content-range' || name === 'x-supabase-api-version';
		}
	});

	// Security: prevent intermediary caching of authenticated HTML responses.
	const contentType = response.headers.get('content-type') || '';
	if (contentType.startsWith('text/html') && !isPublicPath(event.url.pathname)) {
		response.headers.set('Cache-Control', 'no-store');
	}

	// Baseline modern security headers (CSP is configured in `dashboard/svelte.config.js`).
	// Keep these conservative to avoid breaking embedded/auth flows.
	response.headers.set('X-Content-Type-Options', 'nosniff');
	response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
	response.headers.set('X-Frame-Options', 'DENY');
	response.headers.set(
		'Permissions-Policy',
		'camera=(), microphone=(), geolocation=(), payment=(), usb=()'
	);
	if (isHttps) {
		response.headers.set(
			'Strict-Transport-Security',
			'max-age=63072000; includeSubDomains; preload'
		);
	}

	return response;
};

/**
 * Global Error Handler - Catches unhandled errors during request processing
 */
export const handleError: import('@sveltejs/kit').HandleServerError = ({ error, event }) => {
	const errorId = crypto.randomUUID();

	console.error('Unhandled server error:', {
		errorId,
		error: error instanceof Error ? error.message : error,
		stack: error instanceof Error ? error.stack : undefined,
		url: event.url.toString()
	});

	return {
		message: 'An internal error occurred. Our engineering team has been notified.',
		errorId,
		code: 'INTERNAL_SERVER_ERROR'
	};
};
