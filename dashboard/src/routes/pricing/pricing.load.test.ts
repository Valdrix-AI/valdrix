import { describe, expect, it, vi } from 'vitest';
import { load } from './+page';
import { DEFAULT_PRICING_PLANS } from './plans';

vi.mock('$env/static/public', () => ({
	PUBLIC_API_URL: 'https://api.test/api/v1'
}));

function jsonResponse(payload: unknown, status = 200): Response {
	return new Response(JSON.stringify(payload), {
		status,
		headers: { 'Content-Type': 'application/json' }
	});
}

describe('pricing load contract', () => {
	it('returns API plans when payload is valid', async () => {
		const plans = [
			{
				id: 'growth',
				name: 'Growth',
				price_monthly: 149,
				price_annual: 1490,
				period: '/mo',
				description: 'Growth plan',
				features: ['Feature A'],
				cta: 'Start',
				popular: true
			}
		];

		const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
			expect(String(input)).toContain('/api/edge/api/v1/billing/plans');
			return jsonResponse(plans);
		});

		const result = (await load({
			fetch: fetchMock as unknown as typeof fetch
		} as Parameters<typeof load>[0])) as { plans: typeof plans };

		expect(result.plans).toEqual(plans);
	});

	it('falls back to defaults for non-200 responses', async () => {
		const fetchMock = vi.fn(async () => jsonResponse({ detail: 'error' }, 500));

		const result = (await load({
			fetch: fetchMock as unknown as typeof fetch
		} as Parameters<typeof load>[0])) as { plans: typeof DEFAULT_PRICING_PLANS };

		expect(result.plans).toEqual(DEFAULT_PRICING_PLANS);
	});

	it('falls back to defaults for invalid payload shape', async () => {
		const fetchMock = vi.fn(async () => jsonResponse([{ id: 'broken' }]));

		const result = (await load({
			fetch: fetchMock as unknown as typeof fetch
		} as Parameters<typeof load>[0])) as { plans: typeof DEFAULT_PRICING_PLANS };

		expect(result.plans).toEqual(DEFAULT_PRICING_PLANS);
	});

	it('falls back to defaults when fetch throws', async () => {
		const fetchMock = vi.fn(async () => {
			throw new Error('network down');
		});

		const result = (await load({
			fetch: fetchMock as unknown as typeof fetch
		} as Parameters<typeof load>[0])) as { plans: typeof DEFAULT_PRICING_PLANS };

		expect(result.plans).toEqual(DEFAULT_PRICING_PLANS);
	});
});
