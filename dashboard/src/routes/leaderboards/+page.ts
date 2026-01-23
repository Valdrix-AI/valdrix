import { PUBLIC_API_URL } from '$env/static/public';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, parent, url }) => {
	const { session } = await parent();
	const period = url.searchParams.get('period') || '30d';

	if (!session?.access_token) {
		return {
			period,
			leaderboard: {
				period: 'Last 30 Days',
				entries: [],
				total_team_savings: 0
			}
		};
	}

	const res = await fetch(`${PUBLIC_API_URL}/leaderboards?period=${period}`, {
		headers: {
			Authorization: `Bearer ${session.access_token}`
		}
	});

	if (!res.ok) {
		return {
			period,
			leaderboard: {
				period: 'Last 30 Days',
				entries: [],
				total_team_savings: 0
			},
			error: 'Failed to load leaderboard'
		};
	}

	const leaderboard = await res.json();

	return {
		period,
		leaderboard
	};
};
