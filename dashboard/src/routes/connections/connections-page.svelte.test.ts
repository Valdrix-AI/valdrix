import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import Page from './+page.svelte';
import type { PageData } from './$types';
import { TimeoutError } from '$lib/fetchWithTimeout';

const { getMock, postMock, deleteMock } = vi.hoisted(() => ({
	getMock: vi.fn(),
	postMock: vi.fn(),
	deleteMock: vi.fn()
}));

vi.mock('$env/static/public', () => ({
	PUBLIC_API_URL: 'https://api.test/api/v1'
}));

vi.mock('$app/paths', () => ({
	base: ''
}));

vi.mock('$lib/api', () => ({
	api: {
		get: (...args: unknown[]) => getMock(...args),
		post: (...args: unknown[]) => postMock(...args),
		delete: (...args: unknown[]) => deleteMock(...args)
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

function pageData(tier: string = 'pro'): PageData {
	return {
		user: { id: 'user-id', tenant_id: 'tenant-id' },
		session: { access_token: 'token' },
		subscription: { tier, status: 'active' }
	} as unknown as PageData;
}

function setupGetDefaults() {
	getMock.mockImplementation(async (url: string) => {
		const path = String(url);
		if (path === endpoint('/settings/connections/aws')) {
			return jsonResponse([
				{
					id: 'aws-conn-1',
					provider: 'aws',
					aws_account_id: '123456789012',
					is_management_account: false
				}
			]);
		}
		if (
			[
				endpoint('/settings/connections/azure'),
				endpoint('/settings/connections/gcp'),
				endpoint('/settings/connections/saas'),
				endpoint('/settings/connections/license'),
				endpoint('/settings/connections/platform'),
				endpoint('/settings/connections/hybrid')
			].includes(path)
		) {
			return jsonResponse([]);
		}
		if (path === endpoint('/settings/connections/aws/discovered')) {
			return jsonResponse([]);
		}
		return jsonResponse({}, 404);
	});
}

function setupPostDefaults() {
	postMock.mockImplementation(async (url: string) => {
		const path = String(url);
		if (path === endpoint('/settings/connections/saas')) {
			return jsonResponse({ id: 'saas-conn-1' });
		}
		if (path === endpoint('/settings/connections/saas/saas-conn-1/verify')) {
			return jsonResponse({ status: 'success' });
		}
		return jsonResponse({ status: 'ok' });
	});
}

describe('connections page API wiring', () => {
	beforeEach(() => {
		getMock.mockReset();
		postMock.mockReset();
		deleteMock.mockReset();
		setupGetDefaults();
		setupPostDefaults();
		vi.spyOn(window, 'confirm').mockReturnValue(true);
	});

	afterEach(() => {
		cleanup();
		vi.restoreAllMocks();
	});

	it('loads cloud connection sections via edge proxy paths', async () => {
		render(Page, { data: pageData('enterprise') });
		await screen.findByText('Cloud Accounts');

		await waitFor(() => {
			expect(getMock).toHaveBeenCalledWith(
				endpoint('/settings/connections/aws'),
				expect.objectContaining({ headers: expect.any(Object), timeoutMs: 8000 })
			);
			expect(getMock).toHaveBeenCalledWith(
				endpoint('/settings/connections/azure'),
				expect.objectContaining({ headers: expect.any(Object), timeoutMs: 8000 })
			);
			expect(getMock).toHaveBeenCalledWith(
				endpoint('/settings/connections/gcp'),
				expect.objectContaining({ headers: expect.any(Object), timeoutMs: 8000 })
			);
			expect(getMock).toHaveBeenCalledWith(
				endpoint('/settings/connections/saas'),
				expect.objectContaining({ headers: expect.any(Object), timeoutMs: 8000 })
			);
			expect(getMock).toHaveBeenCalledWith(
				endpoint('/settings/connections/license'),
				expect.objectContaining({ headers: expect.any(Object), timeoutMs: 8000 })
			);
			expect(getMock).toHaveBeenCalledWith(
				endpoint('/settings/connections/platform'),
				expect.objectContaining({ headers: expect.any(Object), timeoutMs: 8000 })
			);
			expect(getMock).toHaveBeenCalledWith(
				endpoint('/settings/connections/hybrid'),
				expect.objectContaining({ headers: expect.any(Object), timeoutMs: 8000 })
			);
		});
	});

	it('creates and verifies SaaS connector through edge proxy write endpoints', async () => {
		render(Page, { data: pageData('pro') });
		await screen.findByText('Create SaaS connector');
		const saasSummary = screen.getByText('Create SaaS connector');
		const saasPanel = saasSummary.closest('details');
		expect(saasPanel).toBeTruthy();

		await fireEvent.click(saasSummary);
		await fireEvent.input(
			within(saasPanel as HTMLElement).getByPlaceholderText(
				'Connection name (e.g. Stripe Billing)'
			),
			{
				target: { value: 'Stripe Prod' }
			}
		);
		await fireEvent.input(
			within(saasPanel as HTMLElement).getByPlaceholderText('Vendor (stripe, salesforce, etc.)'),
			{
				target: { value: 'stripe' }
			}
		);
		await fireEvent.input(
			within(saasPanel as HTMLElement).getByPlaceholderText('API key / OAuth token'),
			{
				target: { value: 'saas-api-key' }
			}
		);

		await fireEvent.click(
			within(saasPanel as HTMLElement).getByRole('button', {
				name: /Create & Verify SaaS Connector/i
			})
		);

		await waitFor(() => {
			expect(postMock).toHaveBeenCalledWith(
				endpoint('/settings/connections/saas'),
				expect.objectContaining({ name: 'Stripe Prod', vendor: 'stripe' }),
				expect.objectContaining({ headers: expect.any(Object) })
			);
			expect(postMock).toHaveBeenCalledWith(
				endpoint('/settings/connections/saas/saas-conn-1/verify'),
				{},
				expect.objectContaining({ headers: expect.any(Object) })
			);
		});
		await screen.findByText('SAAS connection created and verified.');
	});

	it('shows timeout and write error states from connection APIs', async () => {
		setupGetDefaults();
		getMock.mockImplementationOnce(async () => {
			throw new TimeoutError(8000);
		});
		postMock.mockImplementation(async (url: string) => {
			if (String(url) === endpoint('/settings/connections/saas')) {
				return jsonResponse({ detail: 'SaaS connector validation failed' }, 400);
			}
			return jsonResponse({ status: 'ok' });
		});

		render(Page, { data: pageData('enterprise') });
		await screen.findByText('Cloud Accounts');
		await screen.findByText(/connection sections timed out/i);
		const saasSummary = screen.getByText('Create SaaS connector');
		const saasPanel = saasSummary.closest('details');
		expect(saasPanel).toBeTruthy();

		await fireEvent.click(saasSummary);
		await fireEvent.input(
			within(saasPanel as HTMLElement).getByPlaceholderText(
				'Connection name (e.g. Stripe Billing)'
			),
			{
				target: { value: 'Stripe QA' }
			}
		);
		await fireEvent.input(
			within(saasPanel as HTMLElement).getByPlaceholderText('API key / OAuth token'),
			{
				target: { value: 'bad-key' }
			}
		);
		await fireEvent.click(
			within(saasPanel as HTMLElement).getByRole('button', {
				name: /Create & Verify SaaS Connector/i
			})
		);
		await screen.findByText('SaaS connector validation failed');
	});
});
