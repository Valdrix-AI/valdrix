import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import EnforcementOpsCard from './EnforcementOpsCard.svelte';

const { getMock, postMock } = vi.hoisted(() => ({
	getMock: vi.fn(),
	postMock: vi.fn()
}));

vi.mock('$app/paths', () => ({
	base: ''
}));

vi.mock('$env/static/public', () => ({
	PUBLIC_API_URL: 'https://api.test/api/v1'
}));

vi.mock('$lib/api', () => ({
	api: {
		get: (...args: unknown[]) => getMock(...args),
		post: (...args: unknown[]) => postMock(...args)
	}
}));

function jsonResponse(payload: unknown, status = 200): Response {
	return new Response(JSON.stringify(payload), {
		status,
		headers: { 'Content-Type': 'application/json' }
	});
}

const EDGE_BASE = '/api/edge/api/v1';
const endpoint = (path: string): string => `${EDGE_BASE}${path}`;

describe('EnforcementOpsCard', () => {
	beforeEach(() => {
		getMock.mockReset();
		postMock.mockReset();
	});

	afterEach(() => {
		cleanup();
	});

	it('renders upgrade overlay and skips API calls for lower tiers', async () => {
		render(EnforcementOpsCard, {
			accessToken: 'token',
			tier: 'starter'
		});

		expect(screen.getByText('Enforcement Ops Reconciliation')).toBeTruthy();
		expect(screen.getByText('Pro Plan Required')).toBeTruthy();
		expect(
			screen.getByRole('link', { name: /Upgrade to Unlock Enforcement Ops Views/i })
		).toBeTruthy();

		await waitFor(() => {
			expect(getMock).not.toHaveBeenCalled();
		});
	});

	it('loads active reservations and drift exceptions', async () => {
		getMock.mockImplementation(async (url: string) => {
			if (String(url) === endpoint('/enforcement/reservations/active')) {
				return jsonResponse([
					{
						decision_id: '11111111-1111-1111-1111-111111111111',
						source: 'terraform',
						environment: 'nonprod',
						project_id: 'default',
						action: 'terraform.apply',
						resource_reference: 'module.app.aws_instance.web',
						reason_codes: ['approval_required'],
						reserved_allocation_usd: '75.0000',
						reserved_credit_usd: '0.0000',
						reserved_total_usd: '75.0000',
						created_at: '2026-02-22T18:00:00Z',
						age_seconds: 7200
					}
				]);
			}
			if (
				String(url) === endpoint('/enforcement/reservations/reconciliation-exceptions?limit=200')
			) {
				return jsonResponse([
					{
						decision_id: '22222222-2222-2222-2222-222222222222',
						source: 'terraform',
						environment: 'nonprod',
						project_id: 'default',
						action: 'terraform.apply',
						resource_reference: 'module.db.aws_db_instance.main',
						expected_reserved_usd: '75.0000',
						actual_monthly_delta_usd: '80.0000',
						drift_usd: '5.0000',
						status: 'overage',
						reconciled_at: '2026-02-22T19:00:00Z',
						notes: 'month close'
					}
				]);
			}
			return jsonResponse({}, 404);
		});

		render(EnforcementOpsCard, {
			accessToken: 'token',
			tier: 'enterprise'
		});

		await screen.findByText('Active Reservations');

		await waitFor(() => {
			expect(getMock).toHaveBeenCalledWith(
				endpoint('/enforcement/reservations/active'),
				expect.objectContaining({ headers: expect.any(Object), timeoutMs: 8000 })
			);
			expect(getMock).toHaveBeenCalledWith(
				endpoint('/enforcement/reservations/reconciliation-exceptions?limit=200'),
				expect.objectContaining({ headers: expect.any(Object), timeoutMs: 8000 })
			);
		});

		expect(screen.getByText('module.app.aws_instance.web')).toBeTruthy();
		expect(screen.getByText('module.db.aws_db_instance.main')).toBeTruthy();
	});

	it('runs overdue auto-reconciliation and manual match reconcile', async () => {
		getMock.mockImplementation(async (url: string) => {
			if (String(url) === endpoint('/enforcement/reservations/active')) {
				return jsonResponse([
					{
						decision_id: '33333333-3333-3333-3333-333333333333',
						source: 'terraform',
						environment: 'nonprod',
						project_id: 'default',
						action: 'terraform.apply',
						resource_reference: 'module.cache.aws_elasticache_cluster.main',
						reason_codes: ['approval_required'],
						reserved_allocation_usd: '20.0000',
						reserved_credit_usd: '0.0000',
						reserved_total_usd: '20.0000',
						created_at: '2026-02-22T18:00:00Z',
						age_seconds: 5400
					}
				]);
			}
			if (
				String(url) === endpoint('/enforcement/reservations/reconciliation-exceptions?limit=200')
			) {
				return jsonResponse([]);
			}
			return jsonResponse({}, 404);
		});

		postMock.mockImplementation(async (url: string) => {
			if (String(url) === endpoint('/enforcement/reservations/reconcile-overdue')) {
				return jsonResponse({ released_count: 1 });
			}
			if (
				String(url) ===
				endpoint('/enforcement/reservations/33333333-3333-3333-3333-333333333333/reconcile')
			) {
				return jsonResponse({ status: 'matched' });
			}
			return jsonResponse({}, 404);
		});

		render(EnforcementOpsCard, {
			accessToken: 'token',
			tier: 'pro'
		});

		await screen.findByText('module.cache.aws_elasticache_cluster.main');

		await fireEvent.click(screen.getByRole('button', { name: /Run overdue auto-reconciliation/i }));
		await waitFor(() => {
			expect(postMock).toHaveBeenCalledWith(
				endpoint('/enforcement/reservations/reconcile-overdue'),
				expect.objectContaining({ limit: 200 }),
				expect.objectContaining({ headers: expect.any(Object) })
			);
		});

		await fireEvent.click(screen.getByRole('button', { name: /Reconcile as matched/i }));
		await waitFor(() => {
			expect(postMock).toHaveBeenCalledWith(
				endpoint('/enforcement/reservations/33333333-3333-3333-3333-333333333333/reconcile'),
				expect.objectContaining({
					actual_monthly_delta_usd: 20,
					notes: 'ops_matched_reconcile'
				}),
				expect.objectContaining({ headers: expect.any(Object) })
			);
		});
	});
});
