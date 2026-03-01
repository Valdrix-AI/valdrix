/**
 * Root Layout - Server Load
 *
 * Runs on every page load (server-side).
 * Fetches session and makes it available to all pages.
 */

import { edgeApiPath } from '$lib/edgeProxy';
import { fetchWithTimeout } from '$lib/fetchWithTimeout';
import { isPublicPath } from '$lib/routeProtection';
import type { LayoutServerLoad } from './$types';

const SUBSCRIPTION_TIMEOUT_MS = 4000;
const PROFILE_TIMEOUT_MS = 4000;

function hasSupabaseSessionCookies(cookieNames: string[]): boolean {
	return cookieNames.some((cookieName) => cookieName.startsWith('sb-'));
}

export const load: LayoutServerLoad = async ({ locals, fetch, url, cookies }) => {
	const publicPath = isPublicPath(url.pathname);
	const cookieNames = cookies.getAll().map((cookie) => cookie.name);
	const shouldResolveSession = !publicPath || hasSupabaseSessionCookies(cookieNames);

	let session = null;
	let user = null;
	if (shouldResolveSession) {
		try {
			const sessionResult = await locals.safeGetSession();
			session = sessionResult.session;
			user = sessionResult.user;
		} catch {
			if (!publicPath) {
				throw new Error('session_resolution_failed');
			}
			session = null;
			user = null;
		}
	}

	let subscription = { tier: 'free', status: 'active' };
	let profile: { persona: string; role?: string; tier?: string } | null = null;

	// Fetch subscription tier if user is authenticated
	if (session?.access_token) {
		try {
			const res = await fetchWithTimeout(
				fetch,
				edgeApiPath('/billing/subscription'),
				{
					headers: {
						Authorization: `Bearer ${session.access_token}`
					}
				},
				SUBSCRIPTION_TIMEOUT_MS
			);
			if (res.ok) {
				subscription = await res.json();
			}
		} catch {
			// Default to free if fetch fails
		}

		// Fetch user profile (persona preference) for persona-aware UX defaults
		try {
			const res = await fetchWithTimeout(
				fetch,
				edgeApiPath('/settings/profile'),
				{
					headers: {
						Authorization: `Bearer ${session.access_token}`
					}
				},
				PROFILE_TIMEOUT_MS
			);
			if (res.ok) {
				profile = await res.json();
			}
		} catch {
			// Profile fetch failed
		}
	}

	return {
		session,
		user,
		subscription,
		profile
	};
};
