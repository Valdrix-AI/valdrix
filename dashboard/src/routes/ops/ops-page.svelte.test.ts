import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import Page from './+page.svelte';
import type { PageData } from './$types';

const { getMock, postMock, putMock, deleteMock } = vi.hoisted(() => ({
	getMock: vi.fn(),
	postMock: vi.fn(),
	putMock: vi.fn(),
	deleteMock: vi.fn()
}));

vi.mock('$env/static/public', () => ({
	PUBLIC_API_URL: 'https://api.test/api/v1'
}));

vi.mock('$lib/api', () => ({
	api: {
		get: (...args: unknown[]) => getMock(...args),
		post: (...args: unknown[]) => postMock(...args),
		put: (...args: unknown[]) => putMock(...args),
		delete: (...args: unknown[]) => deleteMock(...args)
	}
}));

function jsonResponse(payload: unknown, status = 200): Response {
	return new Response(JSON.stringify(payload), {
		status,
		headers: { 'Content-Type': 'application/json' }
	});
}

function setupOpsGetMocks({
	requests = [],
	closePackage,
	policyPreview = {
		decision: 'allow',
		summary: 'Allowed by policy',
		tier: 'pro',
		rule_hits: []
	}
}: {
	requests?: Array<Record<string, unknown>>;
	closePackage?: Record<string, unknown>;
	policyPreview?: Record<string, unknown>;
} = {}) {
	getMock.mockImplementation(async (url: string) => {
		if (url.includes('/zombies/pending')) return jsonResponse({ requests });
		if (url.includes('/zombies/policy-preview/')) return jsonResponse(policyPreview);
		if (url.includes('/jobs/status')) {
			return jsonResponse({ pending: 0, running: 0, completed: 0, failed: 0, dead_letter: 0 });
		}
		if (url.includes('/jobs/slo?')) {
			return jsonResponse({
				window_hours: 168,
				target_success_rate_percent: 95,
				overall_meets_slo: true,
				metrics: [
					{
						job_type: 'cost_ingestion',
						window_hours: 168,
						target_success_rate_percent: 95,
						total_jobs: 5,
						successful_jobs: 5,
						failed_jobs: 0,
						success_rate_percent: 100,
						meets_slo: true,
						latest_completed_at: '2026-02-12T10:00:00Z',
						avg_duration_seconds: 120,
						p95_duration_seconds: 180
					}
				]
			});
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
		if (url.includes('/costs/acceptance/kpis?') && url.includes('response_format=csv')) {
			return new Response('section,key,value\nmetric,test,ok\n', {
				status: 200,
				headers: {
					'Content-Type': 'text/csv',
					'Content-Disposition': 'attachment; filename="acceptance-kpis-test.csv"'
				}
			});
		}
		if (url.includes('/costs/acceptance/kpis/evidence?')) {
			return jsonResponse({ total: 0, items: [] });
		}
		if (url.includes('/costs/acceptance/kpis?')) {
			return jsonResponse({
				start_date: '2026-01-01',
				end_date: '2026-01-31',
				tier: 'pro',
				all_targets_met: false,
				available_metrics: 3,
				metrics: [
					{
						key: 'ingestion_reliability',
						label: 'Ingestion Reliability + Recency',
						available: true,
						target: '>=95.00% success and 0 stale active connections (>48h)',
						actual: '66.67% success, stale/never 1/3',
						meets_target: false,
						details: {}
					},
					{
						key: 'chargeback_coverage',
						label: 'Chargeback Allocation Coverage',
						available: true,
						target: '>=90.00%',
						actual: '92.00%',
						meets_target: true,
						details: {}
					},
					{
						key: 'unit_economics_stability',
						label: 'Unit Economics Stability',
						available: true,
						target: '<= 0 anomalous metrics',
						actual: '1 anomalous metrics',
						meets_target: false,
						details: {}
					}
				]
			});
		}
		if (url.includes('/settings/notifications/acceptance-evidence?')) {
			return jsonResponse({
				total: 4,
				items: [
					{
						event_id: 'evt-suite',
						run_id: 'run-acceptance-001',
						event_type: 'integration_test.suite',
						channel: 'suite',
						success: false,
						status_code: 207,
						message: 'Acceptance suite completed (2 passed, 1 failed).',
						actor_email: 'admin@test-ops.com',
						event_timestamp: '2026-02-12T11:00:00Z',
						details: {
							overall_status: 'partial_failure',
							passed: 2,
							failed: 1,
							checked_channels: ['slack', 'jira', 'workflow']
						}
					},
					{
						event_id: 'evt-slack',
						run_id: 'run-acceptance-001',
						event_type: 'integration_test.slack',
						channel: 'slack',
						success: true,
						status_code: 200,
						message: 'Slack notification sent successfully.',
						actor_email: 'admin@test-ops.com',
						event_timestamp: '2026-02-12T10:59:10Z',
						details: {}
					},
					{
						event_id: 'evt-jira',
						run_id: 'run-acceptance-001',
						event_type: 'integration_test.jira',
						channel: 'jira',
						success: false,
						status_code: 400,
						message: 'Jira integration not configured.',
						actor_email: 'admin@test-ops.com',
						event_timestamp: '2026-02-12T10:59:20Z',
						details: {}
					},
					{
						event_id: 'evt-workflow',
						run_id: 'run-acceptance-001',
						event_type: 'integration_test.workflow',
						channel: 'workflow',
						success: true,
						status_code: 200,
						message: 'Workflow dispatch succeeded.',
						actor_email: 'admin@test-ops.com',
						event_timestamp: '2026-02-12T10:59:30Z',
						details: {}
					}
				]
			});
		}
		if (
			url.includes('/costs/reconciliation/close-package?') &&
			url.includes('response_format=csv')
		) {
			return new Response('section,key,value\nmeta,tenant_id,test\n', {
				status: 200,
				headers: {
					'Content-Type': 'text/csv',
					'Content-Disposition': 'attachment; filename="close-package-test.csv"'
				}
			});
		}
		if (url.includes('/costs/reconciliation/close-package?')) {
			return jsonResponse(
				closePackage ?? {
					tenant_id: 'tenant-id',
					provider: 'all',
					period: { start_date: '2026-01-01', end_date: '2026-01-31' },
					close_status: 'ready',
					lifecycle: {
						total_records: 120,
						preliminary_records: 0,
						final_records: 120,
						total_cost_usd: 1200,
						preliminary_cost_usd: 0,
						final_cost_usd: 1200
					},
					reconciliation: {
						status: 'healthy',
						discrepancy_percentage: 0.42,
						confidence: 0.92
					},
					restatements: {
						count: 2,
						net_delta_usd: -4.2,
						absolute_delta_usd: 8.1
					},
					integrity_hash: 'abc123hash',
					package_version: 'reconciliation-v2'
				}
			);
		}
		if (
			url.includes('/costs/reconciliation/restatements?') &&
			url.includes('response_format=csv')
		) {
			return new Response('usage_date,recorded_at,service\n2026-01-01,2026-02-01,Zendesk\n', {
				status: 200,
				headers: {
					'Content-Type': 'text/csv',
					'Content-Disposition': 'attachment; filename="restatements-test.csv"'
				}
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

const testOpsPageData = {
	user: { id: 'user-id' },
	session: { access_token: 'token' },
	subscription: { tier: 'pro', status: 'active' }
} as unknown as PageData;

describe('ops page unit economics interactions', () => {
	let createObjectUrlSpy: ReturnType<typeof vi.spyOn>;
	let revokeObjectUrlSpy: ReturnType<typeof vi.spyOn>;
	let anchorClickSpy: ReturnType<typeof vi.spyOn>;

	beforeEach(() => {
		getMock.mockReset();
		postMock.mockReset();
		putMock.mockReset();
		createObjectUrlSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test');
		revokeObjectUrlSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
		anchorClickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
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
		createObjectUrlSpy.mockRestore();
		revokeObjectUrlSpy.mockRestore();
		anchorClickSpy.mockRestore();
		cleanup();
	});

	it('refreshes unit economics using the selected date window', async () => {
		render(Page, {
			data: testOpsPageData
		});

		await screen.findByText('Unit Economics Monitor');

		const unitCard = screen.getByText('Unit Economics Monitor').closest('.card') as HTMLElement;
		const dateInputs = Array.from(
			unitCard.querySelectorAll('input[type="date"]')
		) as HTMLInputElement[];
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
			data: testOpsPageData
		});

		await screen.findByText('Cost Ingestion SLA');
		await screen.findByText('SLA At Risk');

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

	it('loads and refreshes job SLO using selected window', async () => {
		render(Page, {
			data: testOpsPageData
		});

		await screen.findByText('Job Reliability SLO');
		await screen.findByText('SLO Healthy');
		await screen.findByText('cost_ingestion');

		await fireEvent.change(screen.getByLabelText('Job SLO Window'), { target: { value: '72' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Refresh SLO' }));

		await waitFor(() => {
			expect(
				getMock.mock.calls.some(
					(call) =>
						String(call[0]).includes('/jobs/slo?') &&
						String(call[0]).includes('window_hours=72') &&
						String(call[0]).includes('target_success_rate_percent=95')
				)
			).toBe(true);
		});
	});

	it('refreshes acceptance kpis using selected windows', async () => {
		render(Page, {
			data: testOpsPageData
		});

		await screen.findByText('Acceptance KPI Evidence');
		await screen.findByText('Gaps Open');

		const unitCard = screen.getByText('Unit Economics Monitor').closest('.card') as HTMLElement;
		const dateInputs = Array.from(
			unitCard.querySelectorAll('input[type="date"]')
		) as HTMLInputElement[];
		expect(dateInputs.length).toBe(2);
		await fireEvent.input(dateInputs[0], { target: { value: '2026-02-01' } });
		await fireEvent.input(dateInputs[1], { target: { value: '2026-02-28' } });
		await fireEvent.change(screen.getByLabelText('SLA Window'), { target: { value: '168' } });

		await fireEvent.click(screen.getByRole('button', { name: 'Refresh KPI Evidence' }));

		await waitFor(() => {
			expect(
				getMock.mock.calls.some(
					(call) =>
						String(call[0]).includes('/costs/acceptance/kpis?') &&
						String(call[0]).includes('start_date=2026-02-01') &&
						String(call[0]).includes('end_date=2026-02-28') &&
						String(call[0]).includes('ingestion_window_hours=168')
				)
			).toBe(true);
		});
	});

	it('loads and refreshes integration acceptance run evidence', async () => {
		render(Page, {
			data: testOpsPageData
		});

		await screen.findByText('Integration Acceptance Runs');
		await screen.findByText('PARTIAL FAILURE');
		expect(screen.getByText('2 passed / 1 failed')).toBeTruthy();
		expect(screen.getByText('slack: OK')).toBeTruthy();
		expect(screen.getByText('jira: FAIL')).toBeTruthy();

		await fireEvent.click(screen.getByRole('button', { name: 'Refresh Runs' }));

		await waitFor(() => {
			expect(
				getMock.mock.calls.some((call) =>
					String(call[0]).includes('/settings/notifications/acceptance-evidence?')
				)
			).toBe(true);
		});
	});

	it('captures integration acceptance run from ops and refreshes evidence', async () => {
		postMock.mockImplementation(async (url: string) => {
			if (url.includes('/settings/notifications/acceptance-evidence/capture')) {
				return jsonResponse({
					run_id: 'run-acceptance-xyz12345',
					tenant_id: 'tenant-id',
					captured_at: '2026-02-12T12:00:00Z',
					overall_status: 'success',
					passed: 3,
					failed: 0,
					results: []
				});
			}
			return jsonResponse({}, 404);
		});

		render(Page, {
			data: testOpsPageData
		});

		await screen.findByText('Integration Acceptance Runs');
		await fireEvent.click(screen.getByRole('button', { name: 'Run Checks' }));

		await waitFor(() => {
			expect(
				postMock.mock.calls.some((call) =>
					String(call[0]).includes('/settings/notifications/acceptance-evidence/capture')
				)
			).toBe(true);
		});
		expect(postMock.mock.calls[0]?.[1]).toMatchObject({
			include_slack: true,
			include_jira: true,
			include_workflow: true,
			fail_fast: false
		});

		await waitFor(() => {
			expect(
				getMock.mock.calls.filter((call) =>
					String(call[0]).includes('/settings/notifications/acceptance-evidence?')
				).length
			).toBeGreaterThan(1);
		});
		expect(await screen.findByText(/Integration acceptance run captured/i)).toBeTruthy();
	});

	it('captures acceptance run with selected channels and fail-fast options', async () => {
		postMock.mockImplementation(async (url: string) => {
			if (url.includes('/settings/notifications/acceptance-evidence/capture')) {
				return jsonResponse({
					run_id: 'run-acceptance-custom001',
					tenant_id: 'tenant-id',
					captured_at: '2026-02-12T12:10:00Z',
					overall_status: 'partial_failure',
					passed: 1,
					failed: 1,
					results: []
				});
			}
			return jsonResponse({}, 404);
		});

		render(Page, {
			data: testOpsPageData
		});

		await screen.findByText('Integration Acceptance Runs');
		await fireEvent.click(screen.getByLabelText('Include Jira checks'));
		await fireEvent.click(screen.getByLabelText('Fail fast checks'));
		await fireEvent.click(screen.getByRole('button', { name: 'Run Checks' }));

		await waitFor(() => {
			expect(
				postMock.mock.calls.some((call) =>
					String(call[0]).includes('/settings/notifications/acceptance-evidence/capture')
				)
			).toBe(true);
		});
		expect(postMock.mock.calls[0]?.[1]).toMatchObject({
			include_slack: true,
			include_jira: false,
			include_workflow: true,
			fail_fast: true
		});
		expect(await screen.findByText(/Last run run-acce/i)).toBeTruthy();
	});

	it('disables run checks when no acceptance channel is selected', async () => {
		render(Page, {
			data: testOpsPageData
		});

		await screen.findByText('Integration Acceptance Runs');
		await fireEvent.click(screen.getByLabelText('Include Slack checks'));
		await fireEvent.click(screen.getByLabelText('Include Jira checks'));
		await fireEvent.click(screen.getByLabelText('Include Workflow checks'));

		const runButton = screen.getByRole('button', { name: 'Run Checks' });
		expect(runButton.hasAttribute('disabled')).toBe(true);
	});

	it('exports acceptance kpi csv', async () => {
		render(Page, {
			data: testOpsPageData
		});

		await screen.findByText('Acceptance KPI Evidence');
		await fireEvent.click(screen.getByRole('button', { name: 'Download CSV' }));

		await waitFor(() => {
			expect(
				getMock.mock.calls.some(
					(call) =>
						String(call[0]).includes('/costs/acceptance/kpis?') &&
						String(call[0]).includes('response_format=csv')
				)
			).toBe(true);
		});
		expect(createObjectUrlSpy).toHaveBeenCalled();
	});

	it('refreshes reconciliation close package with selected provider', async () => {
		render(Page, {
			data: testOpsPageData
		});

		await screen.findByText('Reconciliation Close Workflow');
		await fireEvent.change(screen.getByLabelText('Provider'), { target: { value: 'aws' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Preview Close Status' }));

		await waitFor(() => {
			expect(
				getMock.mock.calls.some(
					(call) =>
						String(call[0]).includes('/costs/reconciliation/close-package?') &&
						String(call[0]).includes('provider=aws') &&
						String(call[0]).includes('response_format=json')
				)
			).toBe(true);
		});
		expect(screen.getByText('READY')).toBeTruthy();
	});

	it('saves a provider invoice from the close workflow card', async () => {
		setupOpsGetMocks({
			closePackage: {
				tenant_id: 'tenant-id',
				provider: 'aws',
				period: { start_date: '2026-01-01', end_date: '2026-01-31' },
				close_status: 'ready',
				lifecycle: {
					total_records: 120,
					preliminary_records: 0,
					final_records: 120,
					total_cost_usd: 1200,
					preliminary_cost_usd: 0,
					final_cost_usd: 1200
				},
				reconciliation: {
					status: 'healthy',
					discrepancy_percentage: 0.42,
					confidence: 0.92
				},
				restatements: {
					count: 2,
					net_delta_usd: -4.2,
					absolute_delta_usd: 8.1
				},
				invoice_reconciliation: {
					status: 'missing_invoice',
					provider: 'aws',
					period: { start_date: '2026-01-01', end_date: '2026-01-31' },
					threshold_percent: 1,
					ledger_final_cost_usd: 1200
				},
				integrity_hash: 'abc123hash',
				package_version: 'reconciliation-v3'
			}
		});
		postMock.mockResolvedValueOnce(jsonResponse({ status: 'success', invoice: { id: 'inv-1' } }));

		render(Page, {
			data: testOpsPageData
		});

		await screen.findByText('Reconciliation Close Workflow');
		const closeCard = screen
			.getByText('Reconciliation Close Workflow')
			.closest('.card') as HTMLElement;
		const closeCardUtils = within(closeCard);
		await fireEvent.input(closeCardUtils.getByLabelText('Start'), {
			target: { value: '2026-01-01' }
		});
		await fireEvent.input(closeCardUtils.getByLabelText('End'), {
			target: { value: '2026-01-31' }
		});
		await fireEvent.change(closeCardUtils.getByLabelText('Provider'), { target: { value: 'aws' } });
		await fireEvent.click(closeCardUtils.getByRole('button', { name: 'Preview Close Status' }));

		await screen.findByText('Invoice Reconciliation');
		await fireEvent.click(screen.getByRole('button', { name: 'Save Invoice' }));

		await waitFor(() => {
			expect(
				postMock.mock.calls.some((call) =>
					String(call[0]).includes('/costs/reconciliation/invoices')
				)
			).toBe(true);
		});
		const [url, body] = postMock.mock.calls.find((call) =>
			String(call[0]).includes('/costs/reconciliation/invoices')
		)!;
		expect(String(url)).toContain('/costs/reconciliation/invoices');
		expect(body).toMatchObject({
			provider: 'aws',
			start_date: '2026-01-01',
			end_date: '2026-01-31',
			currency: 'USD',
			total_amount: 1200,
			status: 'submitted'
		});
	});

	it('downloads close and restatement csv artifacts', async () => {
		render(Page, {
			data: testOpsPageData
		});

		await screen.findByText('Reconciliation Close Workflow');
		await fireEvent.click(screen.getByRole('button', { name: 'Download Close CSV' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Download Restatements CSV' }));

		await waitFor(() => {
			expect(
				getMock.mock.calls.some(
					(call) =>
						String(call[0]).includes('/costs/reconciliation/close-package?') &&
						String(call[0]).includes('response_format=csv')
				)
			).toBe(true);
			expect(
				getMock.mock.calls.some(
					(call) =>
						String(call[0]).includes('/costs/reconciliation/restatements?') &&
						String(call[0]).includes('response_format=csv')
				)
			).toBe(true);
		});
		expect(createObjectUrlSpy).toHaveBeenCalled();
	});

	it('submits default volume settings through the unit economics settings API', async () => {
		render(Page, {
			data: testOpsPageData
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

	it('opens remediation review modal and loads policy preview', async () => {
		setupOpsGetMocks({
			requests: [
				{
					id: '7f2d7ca8-18e3-472f-9d65-ec7f0da8d0f1',
					status: 'pending',
					resource_id: 'i-gpu-node',
					resource_type: 'GPU Instance',
					action: 'terminate_instance',
					estimated_savings: 123.45,
					created_at: '2026-02-12T10:00:00Z',
					escalation_required: true,
					escalation_reason: 'Owner approval required'
				}
			],
			policyPreview: {
				decision: 'escalate',
				summary: 'High-risk action requires owner approval.',
				tier: 'pro',
				rule_hits: [{ rule_id: 'gpu_high_risk', message: 'GPU termination policy' }]
			}
		});

		render(Page, { data: testOpsPageData });
		await screen.findByText('Remediation Queue');
		const reviewButton = await screen.findByRole('button', { name: 'Review' });
		await fireEvent.click(reviewButton);

		const dialog = await screen.findByRole('dialog', { name: 'Remediation review' });
		expect(within(dialog).getByText('High-risk action requires owner approval.')).toBeTruthy();
		expect(within(dialog).getByText('ESCALATE')).toBeTruthy();

		await waitFor(() => {
			expect(
				getMock.mock.calls.some((call) =>
					String(call[0]).includes('/zombies/policy-preview/7f2d7ca8-18e3-472f-9d65-ec7f0da8d0f1')
				)
			).toBe(true);
		});
	});

	it('approves a request from the remediation review modal', async () => {
		setupOpsGetMocks({
			requests: [
				{
					id: 'f11f8fa7-c2f6-4e3d-bcd8-8e7d42574512',
					status: 'pending_approval',
					resource_id: 'i-owner-review',
					resource_type: 'Instance',
					action: 'stop_instance',
					estimated_savings: 40,
					created_at: '2026-02-12T10:00:00Z'
				}
			]
		});
		postMock.mockImplementation(async (url: string) => {
			if (url.includes('/zombies/approve/')) {
				return jsonResponse({
					status: 'approved',
					request_id: 'f11f8fa7-c2f6-4e3d-bcd8-8e7d42574512'
				});
			}
			return jsonResponse({}, 404);
		});

		render(Page, { data: testOpsPageData });
		await screen.findByText('Remediation Queue');
		const reviewButton = await screen.findByRole('button', { name: 'Review' });
		await fireEvent.click(reviewButton);

		const dialog = await screen.findByRole('dialog', { name: 'Remediation review' });
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Approve' }));

		await waitFor(() => {
			expect(
				postMock.mock.calls.some((call) =>
					String(call[0]).includes('/zombies/approve/f11f8fa7-c2f6-4e3d-bcd8-8e7d42574512')
				)
			).toBe(true);
		});
		expect(await within(dialog).findByText(/approved\./i)).toBeTruthy();
	});

	it('executes a request from the remediation review modal when approved', async () => {
		setupOpsGetMocks({
			requests: [
				{
					id: '8454e787-4f57-4e98-969f-d8b16a74817e',
					status: 'approved',
					resource_id: 'i-exec-ready',
					resource_type: 'Instance',
					action: 'stop_instance',
					estimated_savings: 22.5,
					created_at: '2026-02-12T10:00:00Z'
				}
			]
		});
		postMock.mockImplementation(async (url: string) => {
			if (url.includes('/zombies/execute/')) {
				return jsonResponse({
					status: 'scheduled',
					request_id: '8454e787-4f57-4e98-969f-d8b16a74817e'
				});
			}
			return jsonResponse({}, 404);
		});

		render(Page, { data: testOpsPageData });
		await screen.findByText('Remediation Queue');
		const reviewButton = await screen.findByRole('button', { name: 'Review' });
		await fireEvent.click(reviewButton);

		const dialog = await screen.findByRole('dialog', { name: 'Remediation review' });
		await fireEvent.click(within(dialog).getByRole('button', { name: 'Execute' }));

		await waitFor(() => {
			expect(
				postMock.mock.calls.some((call) =>
					String(call[0]).includes('/zombies/execute/8454e787-4f57-4e98-969f-d8b16a74817e')
				)
			).toBe(true);
		});
		expect(await within(dialog).findByText(/scheduled after grace period\./i)).toBeTruthy();
	});

	it('keeps execute disabled when request is pending approval', async () => {
		setupOpsGetMocks({
			requests: [
				{
					id: '18280f41-599e-40a1-b651-4f2f5a5f45a7',
					status: 'pending_approval',
					resource_id: 'i-awaiting-approval',
					resource_type: 'Instance',
					action: 'stop_instance',
					estimated_savings: 11,
					created_at: '2026-02-12T10:00:00Z'
				}
			]
		});

		render(Page, { data: testOpsPageData });
		await screen.findByText('Remediation Queue');
		const reviewButton = await screen.findByRole('button', { name: 'Review' });
		await fireEvent.click(reviewButton);

		const dialog = await screen.findByRole('dialog', { name: 'Remediation review' });
		const executeButton = within(dialog).getByRole('button', { name: 'Awaiting Approval' });
		expect(executeButton.hasAttribute('disabled')).toBe(true);
	});
});
