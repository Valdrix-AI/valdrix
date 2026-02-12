import { describe, expect, it, vi } from 'vitest';
import { load } from './+page';

function jsonResponse(payload: unknown, status = 200): Response {
	return new Response(JSON.stringify(payload), {
		status,
		headers: { 'Content-Type': 'application/json' }
	});
}

describe('dashboard load contract', () => {
	it('derives freshness from costs summary and avoids legacy dead endpoints', async () => {
		const calls: string[] = [];
		const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
			const url = String(input);
			calls.push(url);

			if (url.includes('/costs?')) {
				return jsonResponse({ data_quality: { freshness: { status: 'final' } } });
			}
			if (url.includes('/carbon?')) {
				return jsonResponse({ total_co2_kg: 1.23 });
			}
			if (url.includes('/zombies?')) {
				return jsonResponse({ total_monthly_waste: 0, ai_analysis: null });
			}
			if (url.includes('/costs/attribution/summary')) {
				return jsonResponse({ buckets: [], total: 0 });
			}
			if (url.includes('/costs/unit-economics?')) {
				return jsonResponse({
					threshold_percent: 20,
					anomaly_count: 1,
					metrics: [
						{
							metric_key: 'cost_per_request',
							label: 'Cost Per Request',
							cost_per_unit: 0.1,
							baseline_cost_per_unit: 0.08,
							delta_percent: 25,
							is_anomalous: true
						}
					]
				});
			}
			return jsonResponse({}, 404);
		});

		const result = (await load({
			fetch: fetchMock as unknown as typeof fetch,
			parent: async () => ({
				session: { access_token: 'token' },
				user: { id: 'user-id' },
				subscription: { tier: 'pro', status: 'active' }
			}),
			url: new URL('http://localhost/?start_date=2024-01-01&end_date=2024-01-31')
		} as Parameters<typeof load>[0])) as {
			freshness: { status: string } | null;
			analysis: unknown;
			unitEconomics: { anomaly_count: number } | null;
		};

		expect(result.freshness).toEqual({ status: 'final' });
		expect(result.analysis).toBeNull();
		expect(result.unitEconomics?.anomaly_count).toBe(1);
		expect(calls.some((u) => u.includes('/costs/analyze'))).toBe(false);
		expect(calls.some((u) => u.includes('/costs/freshness'))).toBe(false);
		expect(calls.some((u) => u.includes('/costs/unit-economics?'))).toBe(true);
	});

	it('skips chargeback requests for free_trial tier while loading unit economics', async () => {
		const calls: string[] = [];
		const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
			const url = String(input);
			calls.push(url);
			if (url.includes('/costs?')) return jsonResponse({ data_quality: { freshness: { status: 'final' } } });
			if (url.includes('/carbon?')) return jsonResponse({ total_co2_kg: 1.23 });
			if (url.includes('/zombies?')) return jsonResponse({ total_monthly_waste: 0, ai_analysis: null });
			return jsonResponse({}, 404);
		});

		await load({
			fetch: fetchMock as unknown as typeof fetch,
			parent: async () => ({
				session: { access_token: 'token' },
				user: { id: 'user-id' },
				subscription: { tier: 'free_trial', status: 'active' }
			}),
			url: new URL('http://localhost/?start_date=2024-01-01&end_date=2024-01-31')
		} as Parameters<typeof load>[0]);

		expect(calls.some((u) => u.includes('/costs/attribution/summary'))).toBe(false);
		expect(calls.some((u) => u.includes('/costs/unit-economics?'))).toBe(true);
	});
});
