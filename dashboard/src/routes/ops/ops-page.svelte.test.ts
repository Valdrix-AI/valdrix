import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import Page from './+page.svelte';

const { getMock, postMock, putMock } = vi.hoisted(() => ({
	getMock: vi.fn(),
	postMock: vi.fn(),
	putMock: vi.fn()
}));

vi.mock('$env/static/public', () => ({
	PUBLIC_API_URL: 'https://api.test/api/v1'
}));

vi.mock('$lib/api', () => ({
	api: {
		get: (...args: unknown[]) => getMock(...args),
		post: (...args: unknown[]) => postMock(...args),
		put: (...args: unknown[]) => putMock(...args)
	}
}));

function jsonResponse(payload: unknown, status = 200): Response {
	return new Response(JSON.stringify(payload), {
		status,
		headers: { 'Content-Type': 'application/json' }
	});
}

function setupOpsGetMocks() {
	getMock.mockImplementation(async (url: string) => {
		if (url.includes('/zombies/pending')) return jsonResponse({ requests: [] });
		if (url.includes('/jobs/status')) {
			return jsonResponse({ pending: 0, running: 0, completed: 0, failed: 0, dead_letter: 0 });
		}
		if (url.includes('/jobs/list')) return jsonResponse([]);
		if (url.includes('/strategies/recommendations')) return jsonResponse([]);
		if (url.includes('/costs/ingestion/sla?')) {
			return jsonResponse({
				window_hours: 24,
				target_success_rate_percent: 95,
				total_jobs: 3,
				successful_jobs: 2,
				failed_jobs: 1,
				success_rate_percent: 66.67,
				meets_sla: false,
				latest_completed_at: '2026-02-12T10:00:00Z',
				avg_duration_seconds: 160,
				p95_duration_seconds: 300,
				records_ingested: 160
			});
		}
		if (url.includes('/costs/unit-economics/settings')) {
			return jsonResponse({
				id: 'd8a24b36-7b94-4a5f-9bd4-774ea239e3af',
				default_request_volume: 1000,
				default_workload_volume: 200,
				default_customer_volume: 50,
				anomaly_threshold_percent: 20
			});
		}
		if (url.includes('/costs/unit-economics?')) {
			return jsonResponse({
				start_date: '2026-01-01',
				end_date: '2026-01-31',
				total_cost: 1000,
				baseline_total_cost: 800,
				threshold_percent: 20,
				anomaly_count: 1,
				alert_dispatched: false,
				metrics: [
					{
						metric_key: 'cost_per_request',
						label: 'Cost Per Request',
						denominator: 1000,
						total_cost: 1000,
						cost_per_unit: 1,
						baseline_cost_per_unit: 0.8,
						delta_percent: 25,
						is_anomalous: true
					}
				]
			});
		}
		return jsonResponse({}, 404);
	});
}

describe('ops page unit economics interactions', () => {
	beforeEach(() => {
		getMock.mockReset();
		postMock.mockReset();
		putMock.mockReset();
		setupOpsGetMocks();
		putMock.mockResolvedValue(
			jsonResponse({
				id: 'd8a24b36-7b94-4a5f-9bd4-774ea239e3af',
				default_request_volume: 1500,
				default_workload_volume: 300,
				default_customer_volume: 70,
				anomaly_threshold_percent: 25
			})
		);
	});

	afterEach(() => {
		cleanup();
	});

	it('refreshes unit economics using the selected date window', async () => {
		const { container } = render(Page, {
			data: {
				user: { id: 'user-id' } as any,
				session: { access_token: 'token' } as any,
				subscription: { tier: 'pro', status: 'active' }
			}
		});

		await screen.findByText('Unit Economics Monitor');

		const dateInputs = Array.from(container.querySelectorAll('input[type="date"]')) as HTMLInputElement[];
		expect(dateInputs.length).toBe(2);
		await fireEvent.input(dateInputs[0], { target: { value: '2026-02-01' } });
		await fireEvent.input(dateInputs[1], { target: { value: '2026-02-28' } });

		await fireEvent.click(screen.getByRole('button', { name: 'Refresh Unit Metrics' }));

		await waitFor(() => {
			expect(
				getMock.mock.calls.some(
					(call) =>
						String(call[0]).includes('/costs/unit-economics?') &&
						String(call[0]).includes('start_date=2026-02-01') &&
						String(call[0]).includes('end_date=2026-02-28')
				)
			).toBe(true);
		});
	});

	it('refreshes ingestion SLA using selected window', async () => {
		render(Page, {
			data: {
				user: { id: 'user-id' } as any,
				session: { access_token: 'token' } as any,
				subscription: { tier: 'pro', status: 'active' }
			}
		});

		await screen.findByText('Cost Ingestion SLA');
		expect(screen.getByText('SLA At Risk')).toBeTruthy();

		await fireEvent.change(screen.getByLabelText('SLA Window'), { target: { value: '168' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Refresh SLA' }));

		await waitFor(() => {
			expect(
				getMock.mock.calls.some(
					(call) =>
						String(call[0]).includes('/costs/ingestion/sla?') &&
						String(call[0]).includes('window_hours=168') &&
						String(call[0]).includes('target_success_rate_percent=95')
				)
			).toBe(true);
		});
	});

	it('submits default volume settings through the unit economics settings API', async () => {
		render(Page, {
			data: {
				user: { id: 'user-id' } as any,
				session: { access_token: 'token' } as any,
				subscription: { tier: 'pro', status: 'active' }
			}
		});

		await screen.findByText('Default Unit Volumes');
		await fireEvent.click(screen.getByRole('button', { name: 'Save Defaults' }));

		await waitFor(() => {
			expect(putMock).toHaveBeenCalledTimes(1);
		});

		const [url, body] = putMock.mock.calls[0];
		expect(String(url)).toContain('/costs/unit-economics/settings');
		expect(body).toMatchObject({
			default_request_volume: 1000,
			default_workload_volume: 200,
			default_customer_volume: 50,
			anomaly_threshold_percent: 20
		});
	});
});
