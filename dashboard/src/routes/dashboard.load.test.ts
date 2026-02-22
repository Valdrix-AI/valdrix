import { describe, expect, it, vi } from 'vitest';
import { TimeoutError } from '$lib/fetchWithTimeout';
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
			if (url.includes('/zombies')) {
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
				subscription: { tier: 'pro', status: 'active' },
				profile: { persona: 'finance' }
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

	it('skips chargeback requests for free tier while loading unit economics', async () => {
		const calls: string[] = [];
		const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
			const url = String(input);
			calls.push(url);
			if (url.includes('/costs?'))
				return jsonResponse({ data_quality: { freshness: { status: 'final' } } });
			if (url.includes('/carbon?')) return jsonResponse({ total_co2_kg: 1.23 });
			if (url.includes('/zombies'))
				return jsonResponse({ total_monthly_waste: 0, ai_analysis: null });
			return jsonResponse({}, 404);
		});

		await load({
			fetch: fetchMock as unknown as typeof fetch,
			parent: async () => ({
				session: { access_token: 'token' },
				user: { id: 'user-id' },
				subscription: { tier: 'free', status: 'active' },
				profile: { persona: 'finance' }
			}),
			url: new URL('http://localhost/?start_date=2024-01-01&end_date=2024-01-31')
		} as Parameters<typeof load>[0]);

		expect(calls.some((u) => u.includes('/costs/attribution/summary'))).toBe(false);
		expect(calls.some((u) => u.includes('/costs/unit-economics?'))).toBe(true);
	});

	it('returns partial data when one widget request times out', async () => {
		const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
			const url = String(input);
			if (url.includes('/costs?')) {
				return jsonResponse({ data_quality: { freshness: { status: 'fresh' } } });
			}
			if (url.includes('/carbon?')) {
				throw new TimeoutError(8000);
			}
			if (url.includes('/zombies')) {
				return jsonResponse({ total_monthly_waste: 12.5, ai_analysis: null });
			}
			if (url.includes('/costs/attribution/summary')) {
				return jsonResponse({ buckets: [], total: 0 });
			}
			if (url.includes('/costs/unit-economics?')) {
				return jsonResponse({ threshold_percent: 20, anomaly_count: 0, metrics: [] });
			}
			return jsonResponse({}, 404);
		});

		const result = (await load({
			fetch: fetchMock as unknown as typeof fetch,
			parent: async () => ({
				session: { access_token: 'token' },
				user: { id: 'user-id' },
				subscription: { tier: 'pro', status: 'active' },
				profile: { persona: 'finance' }
			}),
			url: new URL('http://localhost/?start_date=2024-01-01&end_date=2024-01-31')
		} as Parameters<typeof load>[0])) as {
			costs: { data_quality: { freshness: { status: string } } } | null;
			carbon: unknown;
			zombies: { total_monthly_waste: number } | null;
			error?: string;
		};

		expect(result.costs?.data_quality.freshness.status).toBe('fresh');
		expect(result.carbon).toBeNull();
		expect(result.zombies?.total_monthly_waste).toBe(12.5);
		expect(result.error).toContain('1 dashboard widgets timed out');
	});

	it('surfaces non-2xx widget failures while still returning successful widget payloads', async () => {
		const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
			const url = String(input);
			if (url.includes('/costs?')) {
				return jsonResponse({ detail: 'upstream unavailable' }, 503);
			}
			if (url.includes('/carbon?')) {
				return jsonResponse({ total_co2_kg: 2.4 });
			}
			if (url.includes('/zombies')) {
				return jsonResponse({ detail: 'forbidden' }, 403);
			}
			if (url.includes('/costs/attribution/summary')) {
				return jsonResponse({ buckets: [], total: 0 });
			}
			if (url.includes('/costs/unit-economics?')) {
				return jsonResponse({ threshold_percent: 20, anomaly_count: 0, metrics: [] });
			}
			return jsonResponse({}, 404);
		});

		const result = (await load({
			fetch: fetchMock as unknown as typeof fetch,
			parent: async () => ({
				session: { access_token: 'token' },
				user: { id: 'user-id' },
				subscription: { tier: 'pro', status: 'active' },
				profile: { persona: 'finance' }
			}),
			url: new URL('http://localhost/?start_date=2024-01-01&end_date=2024-01-31')
		} as Parameters<typeof load>[0])) as {
			costs: unknown;
			carbon: { total_co2_kg: number } | null;
			zombies: unknown;
			error?: string;
		};

		expect(result.costs).toBeNull();
		expect(result.carbon?.total_co2_kg).toBe(2.4);
		expect(result.zombies).toBeNull();
		expect(result.error).toContain('costs (503)');
		expect(result.error).toContain('zombies (403)');
	});
});
