import { PUBLIC_API_URL } from '$env/static/public';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, parent, url }) => {
	const { session } = await parent();
	const selectedRegion = url.searchParams.get('region') || 'us-east-1';

	// Date range (default: last 30 days)
	const today = new Date();
	const thirtyDaysAgo = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000);
	const startDate = thirtyDaysAgo.toISOString().split('T')[0];
	const endDate = today.toISOString().split('T')[0];

	if (!session?.access_token) {
		return {
			selectedRegion,
			carbonData: null,
			gravitonData: null,
			budgetData: null
		};
	}

	const headers = {
		Authorization: `Bearer ${session.access_token}`
	};

	try {
		const [carbonRes, gravitonRes, budgetRes] = await Promise.all([
			fetch(
				`${PUBLIC_API_URL}/carbon?start_date=${startDate}&end_date=${endDate}&region=${selectedRegion}`,
				{ headers }
			),
			fetch(`${PUBLIC_API_URL}/graviton?region=${selectedRegion}`, { headers }),
			fetch(`${PUBLIC_API_URL}/carbon/budget?region=${selectedRegion}`, { headers })
		]);

		const carbonData = carbonRes.ok ? await carbonRes.json() : null;
		const gravitonData = gravitonRes.ok ? await gravitonRes.json() : null;
		const budgetData = budgetRes.ok ? await budgetRes.json() : null;

		let error = '';
		if (!carbonRes.ok && carbonRes.status === 401) {
			error = 'Session expired. Please refresh the page.';
		} else if (!carbonRes.ok) {
			error = 'Failed to fetch carbon data';
		}

		return {
			selectedRegion,
			carbonData,
			gravitonData,
			budgetData,
			error
		};
	} catch {
		return {
			selectedRegion,
			carbonData: null,
			gravitonData: null,
			budgetData: null,
			error: 'Network error fetching sustainability data'
		};
	}
};
