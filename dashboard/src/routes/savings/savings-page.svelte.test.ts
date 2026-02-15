import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/svelte';
import Page from './+page.svelte';
import type { PageData } from './$types';

const { getMock } = vi.hoisted(() => ({
	getMock: vi.fn()
}));

vi.mock('$env/static/public', () => ({
	PUBLIC_API_URL: 'https://api.test/api/v1'
}));

vi.mock('$app/paths', () => ({
	base: ''
}));

vi.mock('$lib/api', () => ({
	api: {
		get: (...args: unknown[]) => getMock(...args)
	}
}));

function jsonResponse(payload: unknown, status = 200): Response {
	return new Response(JSON.stringify(payload), {
		status,
		headers: { 'Content-Type': 'application/json' }
	});
}

describe('savings proof page', () => {
	afterEach(() => {
		cleanup();
		getMock.mockReset();
	});

	it('renders savings proof breakdown from API', async () => {
		getMock.mockImplementation(async () =>
			jsonResponse({
				start_date: '2026-02-01',
				end_date: '2026-02-10',
				as_of: '2026-02-13T00:00:00Z',
				tier: 'pro',
				opportunity_monthly_usd: 123.45,
				realized_monthly_usd: 67.89,
				open_recommendations: 3,
				applied_recommendations: 1,
				pending_remediations: 2,
				completed_remediations: 1,
				breakdown: [
					{
						provider: 'aws',
						opportunity_monthly_usd: 100.0,
						realized_monthly_usd: 50.0,
						open_recommendations: 2,
						applied_recommendations: 1,
						pending_remediations: 1,
						completed_remediations: 1
					}
				],
				notes: ['Opportunity is a snapshot.']
			})
		);

		const data = {
			user: { id: 'user-id' },
			session: { access_token: 'token' },
			subscription: { tier: 'pro', status: 'active' }
		} as unknown as PageData;

		render(Page, { data });

		await screen.findByText('Breakdown');
		expect(screen.getByText('aws')).toBeTruthy();

		await waitFor(() => {
			expect(getMock).toHaveBeenCalled();
		});
	});
});
