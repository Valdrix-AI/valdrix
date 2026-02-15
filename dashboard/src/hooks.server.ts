/**
 * Server Hooks - Runs on every request
 *
 * Purpose:
 * 1. Creates Supabase client for server-side use
 * 2. Validates and refreshes sessions
 * 3. Makes session available to routes via locals
 */

import { createServerClient } from '@supabase/ssr';
import { PUBLIC_SUPABASE_URL, PUBLIC_SUPABASE_ANON_KEY } from '$env/static/public';
import type { Handle } from '@sveltejs/kit';
import { isPublicPath } from '$lib/routeProtection';

export const handle: Handle = async ({ event, resolve }) => {
	const forwardedProto = event.request.headers.get('x-forwarded-proto');
	const isHttps = forwardedProto === 'https' || event.url.protocol === 'https:';

	// Create a Supabase client with cookie handling
	event.locals.supabase = createServerClient(PUBLIC_SUPABASE_URL, PUBLIC_SUPABASE_ANON_KEY, {
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
