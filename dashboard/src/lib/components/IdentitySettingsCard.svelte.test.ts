import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import IdentitySettingsCard from './IdentitySettingsCard.svelte';

const { getMock, putMock, postMock } = vi.hoisted(() => ({
	getMock: vi.fn(),
	putMock: vi.fn(),
	postMock: vi.fn()
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
		put: (...args: unknown[]) => putMock(...args),
		post: (...args: unknown[]) => postMock(...args)
	}
}));

function jsonResponse(payload: unknown, status = 200): Response {
	return new Response(JSON.stringify(payload), {
		status,
		headers: { 'Content-Type': 'application/json' }
	});
}

describe('IdentitySettingsCard', () => {
	afterEach(() => {
		cleanup();
		getMock.mockReset();
		putMock.mockReset();
		postMock.mockReset();
	});

	it('renders upgrade overlay when tier is below pro', async () => {
		render(IdentitySettingsCard, {
			accessToken: 'token',
			tier: 'free'
		});

		expect(screen.getByText('Identity (SSO/SCIM)')).toBeTruthy();
		expect(screen.getByText('Pro Plan Required')).toBeTruthy();
		expect(screen.getByRole('link', { name: /Upgrade to Unlock Identity Controls/i })).toBeTruthy();
		await waitFor(() => {
			expect(getMock).not.toHaveBeenCalled();
		});
	});

	it('shows guidance when pro tier but no access token', async () => {
		render(IdentitySettingsCard, {
			accessToken: null,
			tier: 'pro'
		});

		await screen.findByText(/Identity controls are available to tenant admins/i);
		expect(getMock).not.toHaveBeenCalled();
	});

	it('loads and renders identity settings for pro tier', async () => {
		getMock.mockResolvedValueOnce(
			jsonResponse({
				sso_enabled: false,
				allowed_email_domains: ['valdrix.io'],
				sso_federation_enabled: false,
				sso_federation_mode: 'domain',
				sso_federation_provider_id: null,
				scim_enabled: false,
				has_scim_token: false,
				scim_last_rotated_at: null
			})
		);
		getMock.mockResolvedValueOnce(
			jsonResponse({
				tier: 'pro',
				sso: {
					enabled: false,
					allowed_email_domains: ['valdrix.io'],
					enforcement_active: false,
					federation_enabled: false,
					federation_mode: 'domain',
					federation_ready: false,
					current_admin_domain: 'valdrix.io',
					current_admin_domain_allowed: true,
					issues: []
				},
				scim: {
					available: false,
					enabled: false,
					has_token: false,
					token_blind_index_present: false,
					last_rotated_at: null,
					token_age_days: null,
					rotation_recommended_days: 90,
					rotation_overdue: false,
					issues: []
				},
				recommendations: []
			})
		);
		getMock.mockResolvedValue(
			jsonResponse({
				tier: 'pro',
				sso: {
					enabled: true,
					allowed_email_domains: ['example.com'],
					enforcement_active: true,
					federation_enabled: true,
					federation_mode: 'provider_id',
					federation_ready: true,
					current_admin_domain: 'example.com',
					current_admin_domain_allowed: true,
					issues: []
				},
				scim: {
					available: false,
					enabled: false,
					has_token: false,
					token_blind_index_present: false,
					last_rotated_at: null,
					token_age_days: null,
					rotation_recommended_days: 90,
					rotation_overdue: false,
					issues: []
				},
				recommendations: []
			})
		);

		render(IdentitySettingsCard, {
			accessToken: 'token',
			tier: 'pro'
		});

		await screen.findByText(/Enable SSO enforcement/i);
		expect(screen.getByLabelText('Allowed Email Domains')).toBeTruthy();
		const textarea = screen.getByLabelText('Allowed Email Domains') as HTMLTextAreaElement;
		expect(textarea.value).toContain('valdrix.io');
	});

	it('saves enterprise SCIM group mappings in identity settings payload', async () => {
		getMock.mockResolvedValueOnce(
			jsonResponse({
				sso_enabled: false,
				allowed_email_domains: [],
				sso_federation_enabled: false,
				sso_federation_mode: 'domain',
				sso_federation_provider_id: null,
				scim_enabled: false,
				has_scim_token: true,
				scim_last_rotated_at: null,
				scim_group_mappings: []
			})
		);
		getMock.mockResolvedValueOnce(
			jsonResponse({
				tier: 'enterprise',
				sso: {
					enabled: false,
					allowed_email_domains: [],
					enforcement_active: false,
					federation_enabled: false,
					federation_mode: 'domain',
					federation_ready: false,
					current_admin_domain: 'valdrix.io',
					current_admin_domain_allowed: true,
					issues: []
				},
				scim: {
					available: true,
					enabled: false,
					has_token: true,
					token_blind_index_present: true,
					last_rotated_at: null,
					token_age_days: null,
					rotation_recommended_days: 90,
					rotation_overdue: false,
					issues: []
				},
				recommendations: []
			})
		);
		putMock.mockResolvedValueOnce(
			jsonResponse({
				sso_enabled: false,
				allowed_email_domains: [],
				sso_federation_enabled: false,
				sso_federation_mode: 'domain',
				sso_federation_provider_id: null,
				scim_enabled: false,
				has_scim_token: true,
				scim_last_rotated_at: null,
				scim_group_mappings: [{ group: 'finops-admins', role: 'admin', persona: 'finance' }]
			})
		);
		// Diagnostics refresh after save.
		getMock.mockResolvedValueOnce(
			jsonResponse({
				tier: 'enterprise',
				sso: {
					enabled: false,
					allowed_email_domains: [],
					enforcement_active: false,
					federation_enabled: false,
					federation_mode: 'domain',
					federation_ready: false,
					current_admin_domain: 'valdrix.io',
					current_admin_domain_allowed: true,
					issues: []
				},
				scim: {
					available: true,
					enabled: false,
					has_token: true,
					token_blind_index_present: true,
					last_rotated_at: null,
					token_age_days: null,
					rotation_recommended_days: 90,
					rotation_overdue: false,
					issues: []
				},
				recommendations: []
			})
		);

		render(IdentitySettingsCard, {
			accessToken: 'token',
			tier: 'enterprise'
		});

		await screen.findByText('SCIM group mappings');

		await fireEvent.click(screen.getByRole('button', { name: /Add mapping/i }));

		const groupInput = screen.getByLabelText('Group name') as HTMLInputElement;
		const roleSelect = screen.getByLabelText('Role') as HTMLSelectElement;
		const personaSelect = screen.getByLabelText('Persona (optional)') as HTMLSelectElement;

		await fireEvent.input(groupInput, { target: { value: 'FinOps-Admins' } });
		await fireEvent.change(roleSelect, { target: { value: 'admin' } });
		await fireEvent.change(personaSelect, { target: { value: 'finance' } });

		await fireEvent.click(screen.getByRole('button', { name: /Save Identity Settings/i }));

		await waitFor(() => {
			expect(putMock).toHaveBeenCalled();
		});

		const [url, payload] = putMock.mock.calls[0] as [string, Record<string, unknown>];
		expect(url).toBe('/api/edge/api/v1/settings/identity');
		expect(payload.sso_federation_enabled).toBe(false);
		expect(payload.sso_federation_mode).toBe('domain');
		expect(payload.scim_group_mappings).toEqual([
			{ group: 'finops-admins', role: 'admin', persona: 'finance' }
		]);
	});

	it('saves provider_id federation mode when federated sso is enabled', async () => {
		getMock.mockResolvedValueOnce(
			jsonResponse({
				sso_enabled: true,
				allowed_email_domains: ['example.com'],
				sso_federation_enabled: false,
				sso_federation_mode: 'domain',
				sso_federation_provider_id: null,
				scim_enabled: false,
				has_scim_token: false,
				scim_last_rotated_at: null,
				scim_group_mappings: []
			})
		);
		getMock.mockResolvedValueOnce(
			jsonResponse({
				tier: 'pro',
				sso: {
					enabled: true,
					allowed_email_domains: ['example.com'],
					enforcement_active: true,
					federation_enabled: false,
					federation_mode: 'domain',
					federation_ready: false,
					current_admin_domain: 'example.com',
					current_admin_domain_allowed: true,
					issues: []
				},
				scim: {
					available: false,
					enabled: false,
					has_token: false,
					token_blind_index_present: false,
					last_rotated_at: null,
					token_age_days: null,
					rotation_recommended_days: 90,
					rotation_overdue: false,
					issues: []
				},
				recommendations: []
			})
		);
		putMock.mockResolvedValueOnce(
			jsonResponse({
				sso_enabled: true,
				allowed_email_domains: ['example.com'],
				sso_federation_enabled: true,
				sso_federation_mode: 'provider_id',
				sso_federation_provider_id: 'sso-provider-abc',
				scim_enabled: false,
				has_scim_token: false,
				scim_last_rotated_at: null,
				scim_group_mappings: []
			})
		);
		getMock.mockResolvedValueOnce(
			jsonResponse({
				tier: 'pro',
				sso: {
					enabled: true,
					allowed_email_domains: ['example.com'],
					enforcement_active: true,
					federation_enabled: true,
					federation_mode: 'provider_id',
					federation_ready: true,
					current_admin_domain: 'example.com',
					current_admin_domain_allowed: true,
					issues: []
				},
				scim: {
					available: false,
					enabled: false,
					has_token: false,
					token_blind_index_present: false,
					last_rotated_at: null,
					token_age_days: null,
					rotation_recommended_days: 90,
					rotation_overdue: false,
					issues: []
				},
				recommendations: []
			})
		);

		render(IdentitySettingsCard, {
			accessToken: 'token',
			tier: 'pro'
		});

		const enableFederation = (await screen.findByLabelText(
			'Enable federated SSO login'
		)) as HTMLInputElement;
		await fireEvent.click(enableFederation);

		const modeSelect = screen.getByLabelText('Federation Mode') as HTMLSelectElement;
		await fireEvent.change(modeSelect, { target: { value: 'provider_id' } });

		const providerInput = await screen.findByLabelText('Supabase provider_id');
		await fireEvent.input(providerInput, { target: { value: 'sso-provider-abc' } });

		await fireEvent.click(screen.getByRole('button', { name: /Save Identity Settings/i }));

		await waitFor(() => {
			expect(putMock).toHaveBeenCalled();
		});
		const [, payload] = putMock.mock.calls[0] as [string, Record<string, unknown>];
		expect(payload.sso_federation_enabled).toBe(true);
		expect(payload.sso_federation_mode).toBe('provider_id');
		expect(payload.sso_federation_provider_id).toBe('sso-provider-abc');
	});
});
