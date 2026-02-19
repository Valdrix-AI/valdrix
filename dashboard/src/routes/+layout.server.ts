/**
 * Root Layout - Server Load
 *
 * Runs on every page load (server-side).
 * Fetches session and makes it available to all pages.
 */

import { edgeApiPath } from '$lib/edgeProxy';
import { fetchWithTimeout } from '$lib/fetchWithTimeout';
import type { LayoutServerLoad } from './$types';

const SUBSCRIPTION_TIMEOUT_MS = 4000;
const PROFILE_TIMEOUT_MS = 4000;

export const load: LayoutServerLoad = async ({ locals, fetch }) => {
	const { session, user } = await locals.safeGetSession();

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
