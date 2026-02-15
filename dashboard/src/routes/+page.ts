import { PUBLIC_API_URL } from '$env/static/public';
import { TimeoutError, fetchWithTimeout } from '$lib/fetchWithTimeout';
import type { PageLoad } from './$types';

const DASHBOARD_REQUEST_TIMEOUT_MS = 8000;

export const load: PageLoad = async ({ fetch, parent, url }) => {
	const { session, user, subscription, profile } = await parent();

	const startDate = url.searchParams.get('start_date');
	const endDate = url.searchParams.get('end_date');
	const provider = url.searchParams.get('provider') || '';
	const persona = String(profile?.persona ?? 'engineering').toLowerCase();

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
	const getWithTimeout = (input: string) =>
		fetchWithTimeout(fetch, input, { headers }, DASHBOARD_REQUEST_TIMEOUT_MS);

	try {
		const wantsUnitEconomics = persona === 'finance' || persona === 'leadership';
		const wantsAllocation = persona === 'finance' || persona === 'leadership';
		const wantsCarbon = persona !== 'engineering';
		const wantsZombiesAnalysis = persona === 'engineering';

		const carbonPromise = wantsCarbon
			? getWithTimeout(
					`${PUBLIC_API_URL}/carbon?start_date=${startDate}&end_date=${endDate}${providerQuery}`
				)
			: Promise.resolve(null);

		const zombiesProviderQuery = provider
			? wantsZombiesAnalysis
				? `&provider=${provider}`
				: `?provider=${provider}`
			: '';

		const zombiesUrl = wantsZombiesAnalysis
			? `${PUBLIC_API_URL}/zombies?analyze=true${zombiesProviderQuery}`
			: `${PUBLIC_API_URL}/zombies${zombiesProviderQuery}`;

		const results = await Promise.allSettled([
			getWithTimeout(
				`${PUBLIC_API_URL}/costs?start_date=${startDate}&end_date=${endDate}${providerQuery}`
			),
			carbonPromise,
			getWithTimeout(zombiesUrl),
			hasChargeback && wantsAllocation
				? getWithTimeout(
						`${PUBLIC_API_URL}/costs/attribution/summary?start_date=${startDate}&end_date=${endDate}`
					)
				: Promise.resolve(null),
			hasUnitEconomics && wantsUnitEconomics
				? getWithTimeout(
						`${PUBLIC_API_URL}/costs/unit-economics?start_date=${startDate}&end_date=${endDate}${providerQuery}&alert_on_anomaly=false`
					)
				: Promise.resolve(null)
		]);

		const responseOrNull = (index: number): Response | null =>
			results[index]?.status === 'fulfilled'
				? ((results[index] as PromiseFulfilledResult<Response | null>).value ?? null)
				: null;

		const costsRes = responseOrNull(0);
		const carbonRes = responseOrNull(1);
		const zombiesRes = responseOrNull(2);
		const allocationRes = responseOrNull(3);
		const unitEconomicsRes = responseOrNull(4);

		const costs = costsRes?.ok ? await costsRes.json() : null;
		const carbon = carbonRes?.ok ? await carbonRes.json() : null;
		const zombies = zombiesRes?.ok ? await zombiesRes.json() : null;
		const analysis: { analysis?: string } | null = null;
		const allocation = allocationRes && allocationRes.ok ? await allocationRes.json() : null;
		const unitEconomics =
			unitEconomicsRes && unitEconomicsRes.ok ? await unitEconomicsRes.json() : null;
		const freshness = costs?.data_quality?.freshness ?? null;
		const timedOutCount = results.filter(
			(result) => result.status === 'rejected' && result.reason instanceof TimeoutError
		).length;

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
			provider,
			error:
				timedOutCount > 0
					? `${timedOutCount} dashboard widgets timed out. Partial data shown; refresh to retry.`
					: undefined
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
