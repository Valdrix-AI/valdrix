import { edgeApiPath } from '$lib/edgeProxy';
import { fetchWithTimeout } from '$lib/fetchWithTimeout';
import { DEFAULT_PRICING_PLANS, type PricingPlan } from './plans';
import type { PageLoad } from './$types';

const PRICING_REQUEST_TIMEOUT_MS = 5000;

function isPricingPlan(value: unknown): value is PricingPlan {
	if (typeof value !== 'object' || value === null) return false;
	const plan = value as Partial<PricingPlan>;
	return (
		typeof plan.id === 'string' &&
		typeof plan.name === 'string' &&
		typeof plan.price_monthly === 'number' &&
		typeof plan.price_annual === 'number' &&
		typeof plan.period === 'string' &&
		typeof plan.description === 'string' &&
		Array.isArray(plan.features) &&
		plan.features.every((feature) => typeof feature === 'string') &&
		typeof plan.cta === 'string' &&
		typeof plan.popular === 'boolean'
	);
}

function isPricingPlanArray(value: unknown): value is PricingPlan[] {
	return Array.isArray(value) && value.every((item) => isPricingPlan(item));
}

export const load: PageLoad = async ({ fetch }) => {
	try {
		const response = await fetchWithTimeout(
			fetch,
			edgeApiPath('/billing/plans'),
			{},
			PRICING_REQUEST_TIMEOUT_MS
		);

		if (!response.ok) {
			return { plans: DEFAULT_PRICING_PLANS };
		}

		const payload = await response.json();
		if (isPricingPlanArray(payload) && payload.length > 0) {
			return { plans: payload };
		}
	} catch {
		return { plans: DEFAULT_PRICING_PLANS };
	}

	return { plans: DEFAULT_PRICING_PLANS };
};
