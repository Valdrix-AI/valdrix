/**
 * Supabase Client for SvelteKit SSR
 *
 * Uses @supabase/ssr for proper server-side rendering support.
 * Creates browser and server clients with cookie-based session management.
 */

import { createBrowserClient, createServerClient } from '@supabase/ssr';
import { env as publicEnv } from '$env/dynamic/public';

function readSupabasePublicConfig(): { url: string; anonKey: string } {
	const url = String(publicEnv.PUBLIC_SUPABASE_URL || '').trim();
	const anonKey = String(publicEnv.PUBLIC_SUPABASE_ANON_KEY || '').trim();

	if (!url || !anonKey) {
		throw new Error(
			'Supabase public environment is not configured. Set PUBLIC_SUPABASE_URL and PUBLIC_SUPABASE_ANON_KEY.'
		);
	}

	return { url, anonKey };
}

/**
 * Creates a Supabase client for browser-side usage.
 * Sessions are stored in cookies for SSR compatibility.
 */
export function createSupabaseBrowserClient() {
	const { url, anonKey } = readSupabasePublicConfig();
	return createBrowserClient(url, anonKey);
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
	const { url, anonKey } = readSupabasePublicConfig();
	return createServerClient(url, anonKey, {
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
