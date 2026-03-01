import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import Page from './+page.svelte';
import type { PageData } from './$types';

const { postMock } = vi.hoisted(() => ({
	postMock: vi.fn()
}));

vi.mock('$env/static/public', () => ({
	PUBLIC_API_URL: 'https://api.test/api/v1'
}));

vi.mock('$env/dynamic/public', () => ({
	env: {
		PUBLIC_API_URL: 'https://api.test/api/v1'
	}
}));

vi.mock('$app/paths', () => ({
	base: ''
}));

vi.mock('$lib/api', () => ({
	api: {
		post: (...args: unknown[]) => postMock(...args)
	}
}));

vi.mock('$lib/security/turnstile', () => ({
	getTurnstileToken: vi.fn().mockResolvedValue(null)
}));

function jsonResponse(payload: unknown, status = 200): Response {
	return new Response(JSON.stringify(payload), {
		status,
		headers: { 'Content-Type': 'application/json' }
	});
}

function setupPostMocks() {
	postMock.mockImplementation(async (url: string) => {
		if (url.endsWith('/settings/onboard')) {
			return jsonResponse({ ok: true });
		}
		if (url.endsWith('/settings/connections/saas/setup')) {
			return jsonResponse({
				subject: 'tenant:test-tenant',
				snippet: 'native setup snippet',
				sample_feed: '[]',
				native_connectors: [
					{
						vendor: 'stripe',
						display_name: 'Stripe',
						recommended_auth_method: 'api_key',
						supported_auth_methods: ['api_key', 'manual', 'csv'],
						required_connector_config_fields: []
					},
					{
						vendor: 'salesforce',
						display_name: 'Salesforce',
						recommended_auth_method: 'oauth',
						supported_auth_methods: ['oauth', 'api_key', 'manual', 'csv'],
						required_connector_config_fields: ['instance_url']
					}
				],
				manual_feed_schema: {
					required_fields: ['timestamp|date', 'cost_usd|amount_usd'],
					optional_fields: ['service', 'usage_type', 'currency', 'tags']
				}
			});
		}
		if (url.endsWith('/settings/connections/saas')) {
			return jsonResponse({ id: 'saas-conn-123' });
		}
		if (url.endsWith('/settings/connections/saas/saas-conn-123/verify')) {
			return jsonResponse({ status: 'success' });
		}
		return jsonResponse({ detail: 'not found' }, 404);
	});
}

function renderPage() {
	const data = {
		user: { id: 'user-id', tenant_id: 'tenant-id' },
		session: { access_token: 'token' },
		subscription: { tier: 'pro', status: 'active' }
	} as unknown as PageData;
	return render(Page, {
		data
	});
}

async function enterSaasStep(container: HTMLElement) {
	await fireEvent.click(screen.getByRole('button', { name: /SaaS Spend Connector/i }));
	await fireEvent.click(screen.getByRole('button', { name: /Continue to Setup/i }));
	await screen.findByText('Step 2: Connect SaaS Spend');
	await waitFor(() => {
		expect(screen.queryByText('Fetching configuration details...')).toBeNull();
	});
	await screen.findByText('native setup snippet');
	const textareas = container.querySelectorAll('textarea');
	expect(textareas.length).toBeGreaterThanOrEqual(2);
	return textareas;
}

describe('onboarding cloud+ flow', () => {
	beforeEach(() => {
		postMock.mockReset();
		setupPostMocks();
	});

	afterEach(() => {
		cleanup();
	});

	it('renders native connector metadata and required field UI', async () => {
		renderPage();
		await enterSaasStep(document.body);

		expect(screen.getByText(/Native Connectors/i)).toBeTruthy();
		expect(screen.getByRole('button', { name: 'Stripe' })).toBeTruthy();
		expect(screen.getByRole('button', { name: 'Salesforce' })).toBeTruthy();

		await fireEvent.click(screen.getByRole('button', { name: 'Salesforce' }));
		await screen.findByLabelText('connector_config.instance_url');
		await waitFor(() => {
			const authMethod = screen.getByLabelText('Auth Method') as HTMLSelectElement;
			expect(authMethod.value).toBe('oauth');
		});
	});

	it('sends connector_config in create payload for cloud+ onboarding', async () => {
		const { container } = renderPage();
		const textareas = await enterSaasStep(container);

		await fireEvent.input(screen.getByLabelText('Connection Name'), {
			target: { value: 'Stripe Billing' }
		});
		await fireEvent.input(screen.getByLabelText('Vendor'), {
			target: { value: 'Stripe' }
		});
		await fireEvent.change(screen.getByLabelText('Auth Method'), {
			target: { value: 'manual' }
		});

		const connectorConfigTextarea = textareas[0] as HTMLTextAreaElement;
		await fireEvent.input(connectorConfigTextarea, {
			target: { value: '{"cost_center":"finance"}' }
		});

		await fireEvent.click(screen.getByRole('button', { name: /Create & Verify Connector/i }));

		await waitFor(() => {
			expect(
				postMock.mock.calls.some((call) => String(call[0]).endsWith('/settings/connections/saas'))
			).toBe(true);
		});

		const createCall = postMock.mock.calls.find((call) =>
			String(call[0]).endsWith('/settings/connections/saas')
		);
		expect(createCall).toBeTruthy();
		const payload = createCall?.[1] as Record<string, unknown>;
		expect(payload.vendor).toBe('stripe');
		expect(payload.connector_config).toEqual({ cost_center: 'finance' });
	});

	it('requires oauth token and required connector config field in native mode', async () => {
		renderPage();
		await enterSaasStep(document.body);

		await fireEvent.click(screen.getByRole('button', { name: 'Salesforce' }));
		await fireEvent.input(screen.getByLabelText('Connection Name'), {
			target: { value: 'Salesforce Contracts' }
		});

		await fireEvent.click(screen.getByRole('button', { name: /Create & Verify Connector/i }));
		await screen.findByText('API key / OAuth token is required for this auth method.');

		await fireEvent.input(screen.getByLabelText('API Key / OAuth Token'), {
			target: { value: 'oauth-token' }
		});
		await fireEvent.click(screen.getByRole('button', { name: /Create & Verify Connector/i }));
		await screen.findByText('connector_config.instance_url is required for Salesforce.');
	});
});
