/**
 * Supabase Client for SvelteKit SSR
 *
 * Uses @supabase/ssr for proper server-side rendering support.
 * Creates browser and server clients with cookie-based session management.
 */

import { createBrowserClient, createServerClient } from '@supabase/ssr';
import { PUBLIC_SUPABASE_URL, PUBLIC_SUPABASE_ANON_KEY } from '$env/static/public';

/**
 * Creates a Supabase client for browser-side usage.
 * Sessions are stored in cookies for SSR compatibility.
 */
export function createSupabaseBrowserClient() {
	return createBrowserClient(PUBLIC_SUPABASE_URL, PUBLIC_SUPABASE_ANON_KEY);
}

/**
 * Creates a Supabase client for server-side usage (hooks, server routes).
 * Requires cookie handling for session management.
 */
export function createSupabaseServerClient(cookies: {
	get: (key: string) => string | undefined;
	set: (key: string, value: string, options: object) => void;
	remove: (key: string, options: object) => void;
}) {
	return createServerClient(PUBLIC_SUPABASE_URL, PUBLIC_SUPABASE_ANON_KEY, {
		cookies: {
			get: (key) => cookies.get(key),
			set: (key, value, options) => {
				cookies.set(key, value, { path: '/', ...options });
			},
			remove: (key, options) => {
				cookies.remove(key, { path: '/', ...options });
			}
		}
	});
}

/**
 * Type-safe session getter
 */
export async function getSession(supabase: ReturnType<typeof createBrowserClient>) {
	const {
		data: { session },
		error
	} = await supabase.auth.getSession();
	if (error) {
		return null;
	}
	return session;
}

/**
 * Type-safe user getter
 */
export async function getUser(supabase: ReturnType<typeof createBrowserClient>) {
	const {
		data: { user },
		error
	} = await supabase.auth.getUser();
	if (error) {
		return null;
	}
	return user;
}
