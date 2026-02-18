<script lang="ts">
	/* eslint-disable svelte/no-navigation-without-resolve */
	import { onMount } from 'svelte';
	import { PUBLIC_API_URL } from '$env/static/public';
	import { base } from '$app/paths';
	import { api } from '$lib/api';
	import { TimeoutError } from '$lib/fetchWithTimeout';
	import { z } from 'zod';

	const IDENTITY_REQUEST_TIMEOUT_MS = 8000;

	let {
		accessToken,
		tier
	}: {
		accessToken?: string | null;
		tier?: string | null;
	} = $props();

	type IdentitySettings = {
		sso_enabled: boolean;
		allowed_email_domains: string[];
		sso_federation_enabled: boolean;
		sso_federation_mode: 'domain' | 'provider_id';
		sso_federation_provider_id: string;
		scim_enabled: boolean;
		has_scim_token: boolean;
		scim_last_rotated_at: string | null;
		scim_group_mappings: ScimGroupMapping[];
	};

	type ScimGroupMapping = {
		group: string;
		role: 'admin' | 'member';
		persona: 'engineering' | 'finance' | 'platform' | 'leadership' | null;
	};

	type IdentityDiagnostics = {
		tier: string;
		sso: {
			enabled: boolean;
			allowed_email_domains: string[];
			enforcement_active: boolean;
			federation_enabled: boolean;
			federation_mode: 'domain' | 'provider_id';
			federation_ready: boolean;
			current_admin_domain: string | null;
			current_admin_domain_allowed: boolean | null;
			issues: string[];
		};
		scim: {
			available: boolean;
			enabled: boolean;
			has_token: boolean;
			token_blind_index_present: boolean;
			last_rotated_at: string | null;
			token_age_days: number | null;
			rotation_recommended_days: number;
			rotation_overdue: boolean;
			issues: string[];
		};
		recommendations: string[];
	};

	const PersonaSchema = z.enum(['engineering', 'finance', 'platform', 'leadership']);

	const ScimGroupMappingSchema = z.object({
		group: z.string().min(1).max(255),
		role: z.enum(['admin', 'member']),
		persona: PersonaSchema.nullable().optional()
	});

	const IdentitySettingsResponseSchema = z.object({
		sso_enabled: z.boolean(),
		allowed_email_domains: z.array(z.string().min(1).max(255)).max(50),
		sso_federation_enabled: z.boolean(),
		sso_federation_mode: z.enum(['domain', 'provider_id']),
		sso_federation_provider_id: z.string().max(255).nullable().optional(),
		scim_enabled: z.boolean(),
		has_scim_token: z.boolean(),
		scim_last_rotated_at: z.string().nullable(),
		scim_group_mappings: z.array(ScimGroupMappingSchema).max(50).default([])
	});

	const IdentitySettingsUpdateSchema = z.object({
		sso_enabled: z.boolean(),
		allowed_email_domains: z.array(z.string().min(1).max(255)).max(50),
		sso_federation_enabled: z.boolean(),
		sso_federation_mode: z.enum(['domain', 'provider_id']),
		sso_federation_provider_id: z.string().max(255).nullable().optional(),
		scim_enabled: z.boolean(),
		scim_group_mappings: z.array(ScimGroupMappingSchema).max(50)
	});

	const IdentityDiagnosticsSchema = z.object({
		tier: z.string(),
		sso: z.object({
			enabled: z.boolean(),
			allowed_email_domains: z.array(z.string()),
			enforcement_active: z.boolean(),
			federation_enabled: z.boolean(),
			federation_mode: z.enum(['domain', 'provider_id']),
			federation_ready: z.boolean(),
			current_admin_domain: z.string().nullable(),
			current_admin_domain_allowed: z.boolean().nullable(),
			issues: z.array(z.string())
		}),
		scim: z.object({
			available: z.boolean(),
			enabled: z.boolean(),
			has_token: z.boolean(),
			token_blind_index_present: z.boolean(),
			last_rotated_at: z.string().nullable(),
			token_age_days: z.number().int().nullable(),
			rotation_recommended_days: z.number().int(),
			rotation_overdue: z.boolean(),
			issues: z.array(z.string())
		}),
		recommendations: z.array(z.string())
	});

	const RotateTokenResponseSchema = z.object({
		scim_token: z.string().min(16),
		rotated_at: z.string().min(10)
	});

	const ScimTokenTestResponseSchema = z.object({
		status: z.string(),
		token_matches: z.boolean()
	});

	let loading = $state(true);
	let saving = $state(false);
	let rotating = $state(false);
	let diagnosticsLoading = $state(false);
	let scimTokenTesting = $state(false);
	let error = $state('');
	let success = $state('');

	let settings = $state<IdentitySettings | null>(null);
	let domainsText = $state('');
	let rotatedToken = $state<string>('');
	let rotatedAt = $state<string>('');
	let diagnostics = $state<IdentityDiagnostics | null>(null);
	let scimTokenInput = $state('');
	let scimTokenTestStatus = $state<string>('');

	function uniqueScimMappingsOrThrow(mappings: ScimGroupMapping[]): void {
		const seen: string[] = [];
		for (const mapping of mappings) {
			const key = mapping.group.trim().toLowerCase();
			if (!key) continue;
			if (seen.includes(key)) {
				throw new Error(`Duplicate SCIM group mapping: ${key}`);
			}
			seen.push(key);
		}
	}

	function extractErrorMessage(data: unknown, fallback: string): string {
		if (!data || typeof data !== 'object') return fallback;
		const payload = data as Record<string, unknown>;
		const detail = payload.detail;
		if (typeof detail === 'string' && detail.trim()) return detail;
		if (Array.isArray(detail)) {
			const parts = detail
				.map((entry) => {
					if (!entry || typeof entry !== 'object') return '';
					const obj = entry as Record<string, unknown>;
					if (typeof obj.msg === 'string') return obj.msg;
					if (typeof obj.message === 'string') return obj.message;
					return '';
				})
				.filter(Boolean);
			if (parts.length) return parts.join(', ');
		}
		const message = payload.message;
		if (typeof message === 'string' && message.trim()) return message;
		return fallback;
	}

	function isProPlus(currentTier: string | null | undefined): boolean {
		return ['pro', 'enterprise'].includes((currentTier ?? '').toLowerCase());
	}

	function isEnterprise(currentTier: string | null | undefined): boolean {
		return (currentTier ?? '').toLowerCase() === 'enterprise';
	}

	function apiRootFromPublicApiUrl(publicApiUrl: string): string {
		const cleaned = publicApiUrl.replace(/\/+$/, '');
		return cleaned.replace(/\/api\/v1$/, '');
	}

	function scimBaseUrl(): string {
		return `${apiRootFromPublicApiUrl(PUBLIC_API_URL)}/scim/v2`;
	}

	async function getHeaders() {
		return {
			Authorization: `Bearer ${accessToken}`
		};
	}

	async function getWithTimeout(url: string, headers?: Record<string, string>) {
		return api.get(url, {
			...(headers ? { headers } : {}),
			timeoutMs: IDENTITY_REQUEST_TIMEOUT_MS
		});
	}

	function normalizeDomain(value: string): string {
		let domain = value.trim().toLowerCase();
		if (!domain) return '';
		if (domain.includes('@')) domain = domain.split('@').pop()?.trim().toLowerCase() ?? '';
		domain = domain.replace(/^\.+/, '').replace(/\.+$/, '');
		return domain;
	}

	function parseDomains(raw: string): string[] {
		const tokens = raw
			.split(/[,\n\s]+/g)
			.map((t) => normalizeDomain(t))
			.filter(Boolean);
		const unique: string[] = [];
		for (const domain of tokens) {
			if (!unique.includes(domain)) unique.push(domain);
		}
		return unique;
	}

	async function loadIdentitySettings() {
		loading = true;
		error = '';
		success = '';
		rotatedToken = '';
		rotatedAt = '';
		try {
			if (!accessToken) {
				settings = null;
				return;
			}
			if (!isProPlus(tier)) {
				settings = null;
				return;
			}
			const headers = await getHeaders();
			const res = await getWithTimeout(`${PUBLIC_API_URL}/settings/identity`, headers);
			if (res.status === 403) {
				settings = null;
				return;
			}
			if (!res.ok) {
				const data = await res.json().catch(() => ({}));
				throw new Error(extractErrorMessage(data, 'Failed to load identity settings'));
			}
			const loaded = IdentitySettingsResponseSchema.parse(await res.json());
			settings = {
				...(loaded as IdentitySettings),
				sso_federation_provider_id: loaded.sso_federation_provider_id ?? ''
			};
			domainsText = (loaded.allowed_email_domains ?? []).join(', ');
			await loadDiagnostics();
		} catch (e) {
			console.error('Failed to load identity settings:', e);
			error =
				e instanceof TimeoutError
					? 'Identity settings request timed out. Try again.'
					: (e as Error).message;
		} finally {
			loading = false;
		}
	}

	async function loadDiagnostics() {
		diagnosticsLoading = true;
		scimTokenTestStatus = '';
		try {
			if (!accessToken) {
				diagnostics = null;
				return;
			}
			if (!isProPlus(tier)) {
				diagnostics = null;
				return;
			}
			const headers = await getHeaders();
			const res = await getWithTimeout(`${PUBLIC_API_URL}/settings/identity/diagnostics`, headers);
			if (res.status === 403) {
				diagnostics = null;
				return;
			}
			if (!res.ok) {
				const data = await res.json().catch(() => ({}));
				throw new Error(extractErrorMessage(data, 'Failed to load identity diagnostics'));
			}
			const parsed = IdentityDiagnosticsSchema.parse(await res.json());
			diagnostics = parsed as IdentityDiagnostics;
		} catch (e) {
			console.error('Failed to load identity diagnostics:', e);
			error =
				e instanceof TimeoutError
					? 'Identity diagnostics request timed out. Try again.'
					: (e as Error).message;
			diagnostics = null;
		} finally {
			diagnosticsLoading = false;
		}
	}

	async function testScimToken() {
		scimTokenTesting = true;
		scimTokenTestStatus = '';
		error = '';
		try {
			if (!scimTokenInput.trim()) return;
			const headers = await getHeaders();
			const res = await api.post(
				`${PUBLIC_API_URL}/settings/identity/scim/test-token`,
				{ scim_token: scimTokenInput.trim() },
				{ headers }
			);
			if (!res.ok) {
				const data = await res.json().catch(() => ({}));
				throw new Error(extractErrorMessage(data, 'Failed to test SCIM token'));
			}
			const payload = ScimTokenTestResponseSchema.parse(await res.json());
			scimTokenTestStatus = payload.token_matches ? 'Token matches.' : 'Token does not match.';
		} catch (e) {
			if (e instanceof z.ZodError) {
				error = e.issues.map((err: z.ZodIssue) => err.message).join(', ');
			} else {
				error = (e as Error).message;
			}
		} finally {
			scimTokenTesting = false;
			// Never keep tokens in UI state longer than needed.
			scimTokenInput = '';
		}
	}

	async function saveIdentitySettings() {
		if (!settings) return;
		saving = true;
		error = '';
		success = '';
		try {
			uniqueScimMappingsOrThrow(settings.scim_group_mappings ?? []);
			const payload = {
				sso_enabled: settings.sso_enabled,
				allowed_email_domains: parseDomains(domainsText),
				sso_federation_enabled: settings.sso_federation_enabled,
				sso_federation_mode: settings.sso_federation_mode,
				sso_federation_provider_id:
					settings.sso_federation_mode === 'provider_id'
						? (settings.sso_federation_provider_id?.trim() ?? null)
						: null,
				scim_enabled: settings.scim_enabled,
				scim_group_mappings: (settings.scim_group_mappings ?? []).map((mapping) => ({
					group: mapping.group.trim().toLowerCase(),
					role: mapping.role,
					persona: mapping.persona || null
				}))
			};
			const validated = IdentitySettingsUpdateSchema.parse(payload);

			const headers = await getHeaders();
			const res = await api.put(`${PUBLIC_API_URL}/settings/identity`, validated, { headers });
			if (!res.ok) {
				const data = await res.json().catch(() => ({}));
				throw new Error(extractErrorMessage(data, 'Failed to save identity settings'));
			}
			const updated = IdentitySettingsResponseSchema.parse(await res.json());
			settings = {
				...(updated as IdentitySettings),
				sso_federation_provider_id: updated.sso_federation_provider_id ?? ''
			};
			domainsText = (updated.allowed_email_domains ?? []).join(', ');
			success = 'Identity settings saved.';
			setTimeout(() => (success = ''), 2500);
			await loadDiagnostics();
		} catch (e) {
			if (e instanceof z.ZodError) {
				error = e.issues.map((err: z.ZodIssue) => err.message).join(', ');
			} else {
				error = (e as Error).message;
			}
		} finally {
			saving = false;
		}
	}

	async function rotateScimToken() {
		rotating = true;
		error = '';
		success = '';
		rotatedToken = '';
		rotatedAt = '';
		try {
			const headers = await getHeaders();
			const res = await api.post(
				`${PUBLIC_API_URL}/settings/identity/rotate-scim-token`,
				{},
				{ headers }
			);
			if (!res.ok) {
				const data = await res.json().catch(() => ({}));
				throw new Error(
					extractErrorMessage(
						data,
						res.status === 403
							? 'SCIM token rotation requires Enterprise tier and admin access.'
							: 'Failed to rotate SCIM token'
					)
				);
			}
			const payload = RotateTokenResponseSchema.parse(await res.json());
			rotatedToken = payload.scim_token;
			rotatedAt = payload.rotated_at;
			success = 'SCIM token rotated. Store it now; it is shown only once.';
			await loadIdentitySettings();
		} catch (e) {
			if (e instanceof z.ZodError) {
				error = e.issues.map((err: z.ZodIssue) => err.message).join(', ');
			} else {
				error = (e as Error).message;
			}
		} finally {
			rotating = false;
		}
	}

	async function copyToken() {
		if (!rotatedToken) return;
		try {
			await navigator.clipboard.writeText(rotatedToken);
			success = 'Copied token to clipboard.';
			setTimeout(() => (success = ''), 2000);
		} catch {
			error = 'Failed to copy token. Copy manually.';
		}
	}

	onMount(() => {
		void loadIdentitySettings();
	});

	function addGroupMapping() {
		if (!settings) return;
		settings.scim_group_mappings = [
			...(settings.scim_group_mappings ?? []),
			{ group: '', role: 'member', persona: null }
		];
	}

	function removeGroupMapping(index: number) {
		if (!settings) return;
		settings.scim_group_mappings = (settings.scim_group_mappings ?? []).filter(
			(_, i) => i !== index
		);
	}
</script>

<div
	class="card stagger-enter relative"
	class:opacity-60={!isProPlus(tier)}
	class:pointer-events-none={!isProPlus(tier)}
>
	<div class="flex items-center justify-between mb-5">
		<h2 class="text-lg font-semibold flex items-center gap-2">
			<span>🔐</span> Identity (SSO/SCIM)
		</h2>

		{#if !isProPlus(tier)}
			<span class="badge badge-warning text-xs">Pro Plan Required</span>
		{/if}
	</div>

	{#if !isProPlus(tier)}
		<div class="absolute inset-0 z-10 flex items-center justify-center bg-transparent">
			<a href={`${base}/billing`} class="btn btn-primary shadow-lg pointer-events-auto">
				Upgrade to Unlock Identity Controls
			</a>
		</div>
	{/if}

	{#if error}
		<div role="alert" class="mb-4 rounded-lg border border-danger-500/40 bg-danger-500/10 p-3">
			<p class="text-danger-300 text-sm">{error}</p>
		</div>
	{/if}

	{#if success}
		<div role="status" class="mb-4 rounded-lg border border-success-500/40 bg-success-500/10 p-3">
			<p class="text-success-300 text-sm">{success}</p>
		</div>
	{/if}

	{#if loading}
		<div class="skeleton h-4 w-48 mb-2"></div>
		<div class="skeleton h-4 w-full mb-2"></div>
		<div class="skeleton h-4 w-3/4"></div>
	{:else if !settings}
		<p class="text-sm text-ink-400">
			Identity controls are available to tenant admins on Pro/Enterprise. If you expected access,
			confirm your account role and subscription tier.
		</p>
	{:else}
		<div class="space-y-4">
			<div class="form-group">
				<label class="flex items-center gap-3 cursor-pointer">
					<input type="checkbox" bind:checked={settings.sso_enabled} class="toggle" />
					<span>Enable SSO enforcement (domain allowlisting)</span>
				</label>
				<p class="text-xs text-ink-500 mt-1">
					This blocks access when a user email domain is not in the allowlist.
				</p>
			</div>

			<div class="form-group">
				<label for="allowed_email_domains">Allowed Email Domains</label>
				<textarea
					id="allowed_email_domains"
					rows="2"
					bind:value={domainsText}
					placeholder="example.com, subsidiary.example"
				></textarea>
				<p class="text-xs text-ink-500 mt-1">
					Comma, whitespace, or newline separated. Include your current admin domain to avoid
					lockout.
				</p>
			</div>

			<div class="rounded-xl border border-ink-800/60 bg-ink-950/30 p-4">
				<div class="flex items-center justify-between gap-3">
					<div>
						<p class="font-medium">Federated SSO Login (OIDC/SAML via Supabase SSO)</p>
						<p class="text-xs text-ink-500 mt-1">
							Enables real IdP login flow on the sign-in page. Keep domain allowlisting enabled as a
							second-layer guardrail.
						</p>
					</div>
				</div>

				<div class="mt-4 space-y-3">
					<label class="flex items-center gap-3 cursor-pointer">
						<input type="checkbox" bind:checked={settings.sso_federation_enabled} class="toggle" />
						<span>Enable federated SSO login</span>
					</label>

					<div class="grid grid-cols-1 md:grid-cols-2 gap-3">
						<div>
							<label for="sso_federation_mode">Federation Mode</label>
							<select
								id="sso_federation_mode"
								bind:value={settings.sso_federation_mode}
								disabled={!settings.sso_federation_enabled}
							>
								<option value="domain">Domain discovery (recommended)</option>
								<option value="provider_id">Explicit provider_id</option>
							</select>
						</div>

						{#if settings.sso_federation_mode === 'provider_id'}
							<div>
								<label for="sso_federation_provider_id">Supabase provider_id</label>
								<input
									id="sso_federation_provider_id"
									bind:value={settings.sso_federation_provider_id}
									placeholder="sso_abc123"
									disabled={!settings.sso_federation_enabled}
								/>
								<p class="text-xs text-ink-500 mt-1">Required only for provider_id mode.</p>
							</div>
						{/if}
					</div>
				</div>
			</div>

			<div class="rounded-xl border border-ink-800/60 bg-ink-950/30 p-4">
				<div class="flex items-center justify-between gap-3">
					<div>
						<p class="font-medium">Onboarding Diagnostics</p>
						<p class="text-xs text-ink-500 mt-1">
							Validates SSO enforcement and SCIM readiness for this tenant.
						</p>
					</div>
					<button
						type="button"
						class="btn btn-secondary shrink-0"
						onclick={loadDiagnostics}
						disabled={diagnosticsLoading}
					>
						{diagnosticsLoading ? 'Refreshing…' : 'Refresh Diagnostics'}
					</button>
				</div>

				{#if diagnosticsLoading}
					<div class="mt-4 space-y-2">
						<div class="skeleton h-4 w-48"></div>
						<div class="skeleton h-4 w-full"></div>
						<div class="skeleton h-4 w-3/4"></div>
					</div>
				{:else if diagnostics}
					<div class="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
						<div class="rounded-lg border border-ink-800/60 bg-ink-950/40 p-3">
							<p class="text-xs text-ink-500 mb-2">SSO</p>
							<p class="text-sm">
								{diagnostics.sso.enforcement_active ? 'Enforcement active' : 'Enforcement inactive'}
							</p>
							<p class="text-xs text-ink-500 mt-2">
								Allowed domains: {diagnostics.sso.allowed_email_domains.length}
								{#if diagnostics.sso.current_admin_domain}
									• admin domain: <span class="font-mono"
										>{diagnostics.sso.current_admin_domain}</span
									>
								{/if}
							</p>
							<p class="text-xs text-ink-500 mt-1">
								Federation: {diagnostics.sso.federation_enabled
									? diagnostics.sso.federation_ready
										? `${diagnostics.sso.federation_mode} configured`
										: `${diagnostics.sso.federation_mode} misconfigured`
									: 'disabled'}
							</p>
							{#if diagnostics.sso.issues.length}
								<ul class="mt-2 text-xs text-danger-300 list-disc pl-5 space-y-1">
									{#each diagnostics.sso.issues as issue (issue)}
										<li>{issue}</li>
									{/each}
								</ul>
							{/if}
						</div>

						<div class="rounded-lg border border-ink-800/60 bg-ink-950/40 p-3">
							<p class="text-xs text-ink-500 mb-2">SCIM</p>
							<p class="text-sm">
								{#if diagnostics.scim.available}
									{diagnostics.scim.enabled ? 'Enabled' : 'Disabled'}
								{:else}
									Enterprise tier required
								{/if}
							</p>
							<p class="text-xs text-ink-500 mt-2">
								Token: {diagnostics.scim.has_token ? 'Configured' : 'Missing'}
								{#if diagnostics.scim.rotation_overdue}
									• rotation overdue
								{/if}
							</p>
							{#if diagnostics.scim.issues.length}
								<ul class="mt-2 text-xs text-danger-300 list-disc pl-5 space-y-1">
									{#each diagnostics.scim.issues as issue (issue)}
										<li>{issue}</li>
									{/each}
								</ul>
							{/if}
						</div>
					</div>

					{#if diagnostics.recommendations.length}
						<div class="mt-4 rounded-lg border border-ink-800/60 bg-ink-950/40 p-3">
							<p class="text-xs text-ink-500 mb-2">Recommendations</p>
							<ul class="text-xs text-ink-200 list-disc pl-5 space-y-1">
								{#each diagnostics.recommendations as rec (rec)}
									<li>{rec}</li>
								{/each}
							</ul>
						</div>
					{/if}
				{:else}
					<p class="text-xs text-ink-500 mt-3">
						Diagnostics are not available yet. Click refresh to validate tenant readiness.
					</p>
				{/if}
			</div>

			<div
				class="rounded-xl border border-ink-800/60 bg-ink-950/30 p-4"
				class:opacity-60={!isEnterprise(tier)}
				class:pointer-events-none={!isEnterprise(tier)}
			>
				<div class="flex items-center justify-between gap-3">
					<div>
						<p class="font-medium">SCIM Provisioning</p>
						<p class="text-xs text-ink-500 mt-1">
							Enterprise-only. Base URL: <span class="font-mono">{scimBaseUrl()}</span>
						</p>
					</div>
					{#if !isEnterprise(tier)}
						<span class="badge badge-warning text-xs shrink-0">Enterprise Required</span>
					{/if}
				</div>

				<div class="mt-4 space-y-3">
					<label class="flex items-center gap-3 cursor-pointer">
						<input type="checkbox" bind:checked={settings.scim_enabled} class="toggle" />
						<span>Enable SCIM provisioning</span>
					</label>

					<div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
						<p class="text-xs text-ink-500">
							Token status: {settings.has_scim_token
								? 'Configured'
								: 'Not set'}{settings.scim_last_rotated_at
								? ` • last rotated ${new Date(settings.scim_last_rotated_at).toLocaleString()}`
								: ''}
						</p>
						<button
							type="button"
							class="btn btn-secondary"
							onclick={rotateScimToken}
							disabled={rotating || !settings.scim_enabled}
						>
							{rotating ? 'Rotating…' : 'Rotate SCIM Token'}
						</button>
					</div>

					{#if rotatedToken}
						<div class="rounded-lg border border-ink-800/60 bg-ink-950/40 p-3">
							<p class="text-xs text-ink-500 mb-2">
								New token (store now; it will not be shown again){rotatedAt
									? ` • rotated ${rotatedAt}`
									: ''}:
							</p>
							<div class="flex flex-col gap-2 sm:flex-row sm:items-center">
								<input
									class="font-mono text-xs"
									readonly
									value={rotatedToken}
									aria-label="SCIM token"
								/>
								<button type="button" class="btn btn-primary" onclick={copyToken}>Copy</button>
							</div>
						</div>
					{/if}

					{#if isEnterprise(tier) && settings.scim_enabled && settings.has_scim_token}
						<div class="rounded-lg border border-ink-800/60 bg-ink-950/40 p-3">
							<p class="text-xs text-ink-500 mb-2">
								Test SCIM token (verifies match without revealing stored token):
							</p>
							<div class="flex flex-col gap-2 sm:flex-row sm:items-center">
								<input
									type="password"
									placeholder="Paste token from your IdP"
									bind:value={scimTokenInput}
									aria-label="SCIM token test input"
								/>
								<button
									type="button"
									class="btn btn-secondary"
									onclick={testScimToken}
									disabled={scimTokenTesting || !scimTokenInput.trim()}
								>
									{scimTokenTesting ? 'Testing…' : 'Test Token'}
								</button>
							</div>
							{#if scimTokenTestStatus}
								<p class="mt-2 text-xs text-ink-200">{scimTokenTestStatus}</p>
							{/if}
						</div>
					{/if}

					{#if isEnterprise(tier)}
						<div class="rounded-lg border border-ink-800/60 bg-ink-950/40 p-3">
							<div class="flex items-center justify-between gap-3">
								<div>
									<p class="text-sm font-medium">SCIM group mappings</p>
									<p class="text-xs text-ink-500 mt-1">
										Optional. Map IdP groups to Valdrix role/persona at provisioning time.
									</p>
								</div>
								<button type="button" class="btn btn-secondary" onclick={addGroupMapping}>
									Add mapping
								</button>
							</div>

							{#if (settings.scim_group_mappings ?? []).length === 0}
								<p class="mt-3 text-xs text-ink-500">
									No mappings configured. Users will default to <span class="font-mono">member</span
									>.
								</p>
							{:else}
								<div class="mt-4 space-y-3">
									{#each settings.scim_group_mappings as mapping, index (index)}
										<div class="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
											<div class="md:col-span-2">
												<label for={`scim-group-${index}`}>Group name</label>
												<input
													id={`scim-group-${index}`}
													placeholder="finops-admins"
													bind:value={mapping.group}
												/>
											</div>
											<div>
												<label for={`scim-role-${index}`}>Role</label>
												<select id={`scim-role-${index}`} bind:value={mapping.role}>
													<option value="member">Member</option>
													<option value="admin">Admin</option>
												</select>
											</div>
											<div>
												<label for={`scim-persona-${index}`}>Persona (optional)</label>
												<select id={`scim-persona-${index}`} bind:value={mapping.persona}>
													<option value={null}>(no default)</option>
													<option value="engineering">Engineering</option>
													<option value="finance">Finance</option>
													<option value="platform">Platform</option>
													<option value="leadership">Leadership</option>
												</select>
											</div>
											<div class="md:col-span-4 flex justify-end">
												<button
													type="button"
													class="btn btn-secondary"
													onclick={() => removeGroupMapping(index)}
												>
													Remove
												</button>
											</div>
										</div>
									{/each}
								</div>
							{/if}
						</div>
					{/if}
				</div>
			</div>

			<div class="flex items-center justify-end gap-3 pt-2">
				<button
					type="button"
					class="btn btn-secondary"
					onclick={loadIdentitySettings}
					disabled={saving}
				>
					Refresh
				</button>
				<button
					type="button"
					class="btn btn-primary"
					onclick={saveIdentitySettings}
					disabled={saving}
				>
					{saving ? 'Saving…' : 'Save Identity Settings'}
				</button>
			</div>
		</div>
	{/if}
</div>
