import { PUBLIC_API_URL } from '$env/static/public';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, parent, url }) => {
	const { session, user, subscription } = await parent();

	const startDate = url.searchParams.get('start_date');
	const endDate = url.searchParams.get('end_date');
	const provider = url.searchParams.get('provider') || '';

	if (!user || !session?.access_token || !startDate || !endDate) {
		return {
			costs: null,
			carbon: null,
			zombies: null,
			analysis: null,
			allocation: null,
			unitEconomics: null,
			freshness: null,
			startDate,
			endDate,
			provider
		};
	}

	const headers = {
		Authorization: `Bearer ${session?.access_token}`
	};
	const tier = String(subscription?.tier ?? 'free_trial').toLowerCase();
	const hasChargeback = ['growth', 'pro', 'enterprise'].includes(tier);
	const hasUnitEconomics = ['starter', 'growth', 'pro', 'enterprise', 'free_trial'].includes(tier);

	const providerQuery = provider ? `&provider=${provider}` : '';

	try {
		const [costsRes, carbonRes, zombiesRes, allocationRes, unitEconomicsRes] = await Promise.all([
			fetch(`${PUBLIC_API_URL}/costs?start_date=${startDate}&end_date=${endDate}${providerQuery}`, {
				headers
			}),
			fetch(
				`${PUBLIC_API_URL}/carbon?start_date=${startDate}&end_date=${endDate}${providerQuery}`,
				{
					headers
				}
			),
			fetch(`${PUBLIC_API_URL}/zombies?analyze=true${providerQuery}`, { headers }),
			hasChargeback
				? fetch(
						`${PUBLIC_API_URL}/costs/attribution/summary?start_date=${startDate}&end_date=${endDate}`,
						{ headers }
					)
				: Promise.resolve(null),
			hasUnitEconomics
				? fetch(
						`${PUBLIC_API_URL}/costs/unit-economics?start_date=${startDate}&end_date=${endDate}${providerQuery}&alert_on_anomaly=false`,
						{ headers }
					)
				: Promise.resolve(null),
		]);

		const costs = costsRes.ok ? await costsRes.json() : null;
		const carbon = carbonRes.ok ? await carbonRes.json() : null;
		const zombies = zombiesRes.ok ? await zombiesRes.json() : null;
		const analysis: { analysis?: string } | null = null;
		const allocation = allocationRes && allocationRes.ok ? await allocationRes.json() : null;
		const unitEconomics = unitEconomicsRes && unitEconomicsRes.ok ? await unitEconomicsRes.json() : null;
		const freshness = costs?.data_quality?.freshness ?? null;

		return {
			costs,
			carbon,
			zombies,
			analysis,
			allocation,
			unitEconomics,
			freshness,
			startDate,
			endDate,
			provider
		};
	} catch (err) {
		const e = err as Error;
		return {
			costs: null,
			carbon: null,
			zombies: null,
			analysis: null,
			allocation: null,
			unitEconomics: null,
			freshness: null,
			startDate,
			endDate,
			error: e.message
		};
	}
};
