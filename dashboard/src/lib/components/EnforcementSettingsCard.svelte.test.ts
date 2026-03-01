import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import EnforcementSettingsCard from './EnforcementSettingsCard.svelte';

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

vi.mock('$env/dynamic/public', () => ({
	env: {
		PUBLIC_API_URL: 'https://api.test/api/v1'
	}
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

describe('EnforcementSettingsCard', () => {
	beforeEach(() => {
		getMock.mockReset();
		postMock.mockReset();
	});

	afterEach(() => {
		cleanup();
	});

	it('renders upgrade overlay and skips API calls for lower tiers', async () => {
		render(EnforcementSettingsCard, {
			accessToken: 'token',
			tier: 'starter'
		});

		expect(screen.getByText('Enforcement Control Plane')).toBeTruthy();
		expect(screen.getByText('Pro Plan Required')).toBeTruthy();
		expect(
			screen.getByRole('link', { name: /Upgrade to Unlock Enforcement Controls/i })
		).toBeTruthy();

		await waitFor(() => {
			expect(getMock).not.toHaveBeenCalled();
		});
	});

	it('loads and saves policy, budget, and credit endpoints', async () => {
		getMock.mockImplementation(async (url: string) => {
			if (String(url) === endpoint('/enforcement/policies')) {
				return jsonResponse({
					terraform_mode: 'soft',
					k8s_admission_mode: 'hard',
					require_approval_for_prod: true,
					require_approval_for_nonprod: false,
					auto_approve_below_monthly_usd: '25.0000',
					hard_deny_above_monthly_usd: '5000.0000',
					default_ttl_seconds: 900,
					policy_version: 4,
					updated_at: '2026-02-22T18:00:00Z'
				});
			}
			if (String(url) === endpoint('/enforcement/budgets')) {
				return jsonResponse([
					{
						id: 'b1',
						scope_key: 'default',
						monthly_limit_usd: '1000.0000',
						active: true
					}
				]);
			}
			if (String(url) === endpoint('/enforcement/credits')) {
				return jsonResponse([
					{
						id: 'c1',
						scope_key: 'default',
						total_amount_usd: '100.0000',
						remaining_amount_usd: '80.0000',
						expires_at: null,
						reason: 'pilot',
						active: true
					}
				]);
			}
			return jsonResponse({}, 404);
		});

		postMock.mockImplementation(async (url: string) => {
			if (String(url) === endpoint('/enforcement/policies')) {
				return jsonResponse({ status: 'ok' });
			}
			if (String(url) === endpoint('/enforcement/budgets')) {
				return jsonResponse({ status: 'ok' });
			}
			if (String(url) === endpoint('/enforcement/credits')) {
				return jsonResponse({ status: 'ok' });
			}
			return jsonResponse({}, 404);
		});

		render(EnforcementSettingsCard, {
			accessToken: 'token',
			tier: 'pro'
		});

		await screen.findByLabelText('Terraform gate mode');

		await waitFor(() => {
			expect(getMock).toHaveBeenCalledWith(
				endpoint('/enforcement/policies'),
				expect.objectContaining({ headers: expect.any(Object), timeoutMs: 8000 })
			);
			expect(getMock).toHaveBeenCalledWith(
				endpoint('/enforcement/budgets'),
				expect.objectContaining({ headers: expect.any(Object), timeoutMs: 8000 })
			);
			expect(getMock).toHaveBeenCalledWith(
				endpoint('/enforcement/credits'),
				expect.objectContaining({ headers: expect.any(Object), timeoutMs: 8000 })
			);
		});

		const autoApprove = screen.getByLabelText(
			'Auto approve threshold per month'
		) as HTMLInputElement;
		await fireEvent.input(autoApprove, { target: { value: '40' } });
		await fireEvent.click(screen.getByRole('button', { name: /Save enforcement policy/i }));

		await waitFor(() => {
			expect(postMock).toHaveBeenCalledWith(
				endpoint('/enforcement/policies'),
				expect.objectContaining({
					terraform_mode: expect.any(String),
					auto_approve_below_monthly_usd: expect.any(Number)
				}),
				expect.objectContaining({ headers: expect.any(Object) })
			);
		});

		const budgetLimit = screen.getByLabelText(
			'Enforcement budget monthly limit'
		) as HTMLInputElement;
		await fireEvent.input(budgetLimit, { target: { value: '1500' } });
		await fireEvent.click(screen.getByRole('button', { name: /Save enforcement budget/i }));

		await waitFor(() => {
			expect(postMock).toHaveBeenCalledWith(
				endpoint('/enforcement/budgets'),
				expect.objectContaining({
					scope_key: expect.any(String),
					monthly_limit_usd: expect.any(Number)
				}),
				expect.objectContaining({ headers: expect.any(Object) })
			);
		});

		const creditAmount = screen.getByLabelText(
			'Enforcement credit total amount'
		) as HTMLInputElement;
		await fireEvent.input(creditAmount, { target: { value: '300' } });
		await fireEvent.click(screen.getByRole('button', { name: /Create enforcement credit/i }));

		await waitFor(() => {
			expect(postMock).toHaveBeenCalledWith(
				endpoint('/enforcement/credits'),
				expect.objectContaining({
					scope_key: expect.any(String),
					total_amount_usd: expect.any(Number)
				}),
				expect.objectContaining({ headers: expect.any(Object) })
			);
		});
	});
});
