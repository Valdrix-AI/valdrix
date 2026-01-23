/**
 * Root Layout - Server Load
 *
 * Runs on every page load (server-side).
 * Fetches session and makes it available to all pages.
 */

import { PUBLIC_API_URL } from '$env/static/public';
import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = async ({ locals, fetch }) => {
	const { session, user } = await locals.safeGetSession();

	let subscription = { tier: 'free', status: 'active' };

	// Fetch subscription tier if user is authenticated
	if (session?.access_token) {
		try {
			const res = await fetch(`${PUBLIC_API_URL}/billing/subscription`, {
				headers: {
					Authorization: `Bearer ${session.access_token}`
				}
			});
			if (res.ok) {
				subscription = await res.json();
			}
		} catch (e) {
			// Default to free if fetch fails
			console.error('Failed to fetch subscription:', e);
		}
	}

	return {
		session,
		user,
		subscription
	};
};
