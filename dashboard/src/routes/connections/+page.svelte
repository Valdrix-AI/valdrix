<script lang="ts">
	/* eslint-disable svelte/no-navigation-without-resolve */
	import { PUBLIC_API_URL } from '$env/static/public';
	import { base } from '$app/paths';
	import CloudLogo from '$lib/components/CloudLogo.svelte';
	import { onMount } from 'svelte';
	import { api } from '$lib/api';

	interface CloudConnection {
		id: string;
		provider: 'aws' | 'azure' | 'gcp' | 'saas' | 'license';
		aws_account_id?: string;
		subscription_id?: string;
		project_id?: string;
		name?: string;
		vendor?: string;
		is_management_account?: boolean;
		organization_id?: string;
		auth_method?: string;
		is_active?: boolean;
	}

	interface DiscoveredAccount {
		id: string;
		account_id: string;
		name: string;
		email: string;
		status: 'discovered' | 'linked';
	}

	let { data } = $props();
	let loadingAWS = $state(true);
	let loadingAzure = $state(true);
	let loadingGCP = $state(true);
	let loadingSaaS = $state(true);
	let loadingLicense = $state(true);

	let awsConnection = $state<CloudConnection | null>(null);
	let awsConnections = $state<CloudConnection[]>([]);
	let azureConnections = $state<CloudConnection[]>([]);
	let gcpConnections = $state<CloudConnection[]>([]);
	let saasConnections = $state<CloudConnection[]>([]);
	let licenseConnections = $state<CloudConnection[]>([]);

	let discoveredAccounts = $state<DiscoveredAccount[]>([]);
	let loadingDiscovered = $state(false);
	let syncingOrg = $state(false);
	let linkingAccount: string | null = $state(null);

	let error = $state('');
	let success = $state('');

	const cloudPlusTierAllowed = ['pro', 'enterprise'];
	let verifyingCloudPlus = $state<Record<string, boolean>>({});
	let creatingSaaS = $state(false);
	let creatingLicense = $state(false);

	let saasName = $state('');
	let saasVendor = $state('stripe');
	let saasAuthMethod = $state<'manual' | 'api_key' | 'oauth' | 'csv'>('api_key');
	let saasApiKey = $state('');
	let saasConnectorConfig = $state('{}');
	let saasFeedInput = $state('[]');

	let licenseName = $state('');
	let licenseVendor = $state('microsoft_365');
	let licenseAuthMethod = $state<'manual' | 'api_key' | 'oauth' | 'csv'>('oauth');
	let licenseApiKey = $state('');
	let licenseConnectorConfig = $state('{"default_seat_price_usd": 36}');
	let licenseFeedInput = $state('[]');

	function canUseCloudPlusFeatures(): boolean {
		return cloudPlusTierAllowed.includes(data.subscription?.tier);
	}

	function parseJsonObject(raw: string, fieldName: string): Record<string, unknown> {
		if (!raw.trim()) return {};
		let parsed: unknown;
		try {
			parsed = JSON.parse(raw);
		} catch {
			throw new Error(`${fieldName} must be valid JSON.`);
		}
		if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
			throw new Error(`${fieldName} must be a JSON object.`);
		}
		return parsed as Record<string, unknown>;
	}

	function parseJsonArray(raw: string, fieldName: string): Array<Record<string, unknown>> {
		if (!raw.trim()) return [];
		let parsed: unknown;
		try {
			parsed = JSON.parse(raw);
		} catch {
			throw new Error(`${fieldName} must be valid JSON.`);
		}
		if (!Array.isArray(parsed)) {
			throw new Error(`${fieldName} must be a JSON array.`);
		}
		return parsed as Array<Record<string, unknown>>;
	}

	function extractErrorMessage(payload: unknown, fallback: string): string {
		if (!payload || typeof payload !== 'object') return fallback;
		const maybeError = payload as { detail?: unknown; message?: unknown; error?: unknown };
		for (const candidate of [maybeError.detail, maybeError.message, maybeError.error]) {
			if (typeof candidate === 'string' && candidate.trim()) return candidate;
		}
		return fallback;
	}

	async function createCloudPlusConnection(provider: 'saas' | 'license') {
		if (!canUseCloudPlusFeatures()) {
			error = 'Cloud+ connectors require Pro tier or higher.';
			return;
		}

		const isSaaS = provider === 'saas';
		if (isSaaS ? creatingSaaS : creatingLicense) return;
		if (isSaaS) {
			creatingSaaS = true;
		} else {
			creatingLicense = true;
		}

		success = '';
		error = '';
		try {
			const headers = await getHeaders();
			const name = isSaaS ? saasName.trim() : licenseName.trim();
			const vendor = (isSaaS ? saasVendor : licenseVendor).trim();
			const authMethod = isSaaS ? saasAuthMethod : licenseAuthMethod;
			const apiKey = (isSaaS ? saasApiKey : licenseApiKey).trim();
			const configRaw = isSaaS ? saasConnectorConfig : licenseConnectorConfig;
			const feedRaw = isSaaS ? saasFeedInput : licenseFeedInput;

			if (name.length < 3) throw new Error('Connection name must have at least 3 characters.');
			if (vendor.length < 2) throw new Error('Vendor must have at least 2 characters.');
			if ((authMethod === 'api_key' || authMethod === 'oauth') && !apiKey) {
				throw new Error('API key or OAuth token is required for selected auth method.');
			}

			const connectorConfig = parseJsonObject(configRaw, 'Connector config');
			const feed = parseJsonArray(feedRaw, 'Feed');

			const payload = isSaaS
				? {
						name,
						vendor,
						auth_method: authMethod,
						api_key: apiKey || null,
						connector_config: connectorConfig,
						spend_feed: feed
					}
				: {
						name,
						vendor,
						auth_method: authMethod,
						api_key: apiKey || null,
						connector_config: connectorConfig,
						license_feed: feed
					};

			const response = await api.post(`${PUBLIC_API_URL}/settings/connections/${provider}`, payload, {
				headers
			});
			const body = await response.json().catch(() => ({}));
			if (!response.ok) {
				throw new Error(
					extractErrorMessage(body, `Failed to create ${provider.toUpperCase()} connection.`)
				);
			}

			success = `${provider.toUpperCase()} connection created. Run verify to activate it.`;
			await loadConnections();
			if (isSaaS) {
				saasName = '';
				saasApiKey = '';
				saasConnectorConfig = '{}';
				saasFeedInput = '[]';
			} else {
				licenseName = '';
				licenseApiKey = '';
				licenseConnectorConfig = '{"default_seat_price_usd": 36}';
				licenseFeedInput = '[]';
			}
		} catch (e) {
			const err = e as Error;
			error = err.message;
		} finally {
			if (isSaaS) {
				creatingSaaS = false;
			} else {
				creatingLicense = false;
			}
		}
	}

	async function verifyCloudPlusConnection(provider: 'saas' | 'license', connectionId: string) {
		verifyingCloudPlus = { ...verifyingCloudPlus, [connectionId]: true };
		success = '';
		error = '';
		try {
			const headers = await getHeaders();
			const response = await api.post(
				`${PUBLIC_API_URL}/settings/connections/${provider}/${connectionId}/verify`,
				{},
				{ headers }
			);
			const body = await response.json().catch(() => ({}));
			if (!response.ok) {
				throw new Error(
					extractErrorMessage(body, `Failed to verify ${provider.toUpperCase()} connection.`)
				);
			}
			success = extractErrorMessage(body, `${provider.toUpperCase()} connection verified.`);
			await loadConnections();
		} catch (e) {
			const err = e as Error;
			error = err.message;
		} finally {
			verifyingCloudPlus = { ...verifyingCloudPlus, [connectionId]: false };
		}
	}

	async function getHeaders() {
		return {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${data.session?.access_token}`
		};
	}

	async function loadConnections() {
		try {
			const headers = await getHeaders();

			// AWS
			const awsRes = await api.get(`${PUBLIC_API_URL}/settings/connections/aws`, { headers });
			if (awsRes.ok) {
				awsConnections = await awsRes.json();
				awsConnection = awsConnections.length > 0 ? awsConnections[0] : null;
			}
			loadingAWS = false;

			// Azure
			const azureRes = await api.get(`${PUBLIC_API_URL}/settings/connections/azure`, { headers });
			if (azureRes.ok) {
				azureConnections = await azureRes.json();
			}
			loadingAzure = false;

			// GCP
			const gcpRes = await api.get(`${PUBLIC_API_URL}/settings/connections/gcp`, { headers });
			if (gcpRes.ok) {
				gcpConnections = await gcpRes.json();
			}
			loadingGCP = false;

			// SaaS
			const saasRes = await api.get(`${PUBLIC_API_URL}/settings/connections/saas`, { headers });
			if (saasRes.ok) {
				saasConnections = await saasRes.json();
			}
			loadingSaaS = false;

			// License
			const licenseRes = await api.get(`${PUBLIC_API_URL}/settings/connections/license`, { headers });
			if (licenseRes.ok) {
				licenseConnections = await licenseRes.json();
			}
			loadingLicense = false;

			if (awsConnection?.is_management_account) {
				loadDiscoveredAccounts();
			}
		} catch {
			error = 'Failed to load cloud accounts. Check backend connection.';
			loadingAWS = loadingAzure = loadingGCP = loadingSaaS = loadingLicense = false;
		}
	}

	async function loadDiscoveredAccounts() {
		loadingDiscovered = true;
		try {
			const headers = await getHeaders();
			const res = await api.get(`${PUBLIC_API_URL}/settings/connections/aws/discovered`, {
				headers
			});
			if (res.ok) {
				discoveredAccounts = await res.json();
			}
		} catch (e) {
			console.error('Failed to load discovered accounts', e);
		} finally {
			loadingDiscovered = false;
		}
	}

	async function syncAWSOrg() {
		if (!awsConnection) return;
		syncingOrg = true;
		success = '';
		error = '';
		try {
			const headers = await getHeaders();
			const res = await api.post(
				`${PUBLIC_API_URL}/settings/connections/aws/${awsConnection.id}/sync-org`,
				{},
				{ headers }
			);
			const data = await res.json();
			if (!res.ok) throw new Error(data.detail || 'Sync failed');

			success = data.message;
			await loadDiscoveredAccounts();
			setTimeout(() => (success = ''), 3000);
		} catch (e) {
			const err = e as Error;
			error = err.message;
		} finally {
			syncingOrg = false;
		}
	}

	async function deleteConnection(provider: string, id: string) {
		if (
			!confirm(
				`Are you sure you want to delete this ${provider.toUpperCase()} connection? Data fetching will stop immediately.`
			)
		) {
			return;
		}

		success = '';
		error = '';
		try {
			const headers = await getHeaders();
			const res = await api.delete(`${PUBLIC_API_URL}/settings/connections/${provider}/${id}`, {
				headers
			});

			// Handle Success (204) OR Not Found (404 - already deleted)
			if (res.ok || res.status === 404) {
				success = `${provider.toUpperCase()} connection deleted successfully.`;

				// If this was the management account, clear discovered accounts
				if (provider === 'aws' && awsConnection?.id === id) {
					discoveredAccounts = [];
					awsConnection = null;
				}

				await loadConnections();
				setTimeout(() => (success = ''), 3000);
			} else {
				const data = await res.json();
				throw new Error(data.detail || 'Delete failed');
			}
		} catch (e) {
			const err = e as Error;
			error = err.message;
		}
	}

	async function linkDiscoveredAccount(discoveredId: string) {
		linkingAccount = discoveredId;
		success = '';
		error = '';
		try {
			const headers = await getHeaders();
			const res = await api.post(
				`${PUBLIC_API_URL}/settings/connections/aws/discovered/${discoveredId}/link`,
				{},
				{ headers }
			);
			const data = await res.json();
			if (!res.ok) throw new Error(data.detail || 'Linking failed');

			success = data.message;
			await loadDiscoveredAccounts();
			await loadConnections();
			setTimeout(() => (success = ''), 3000);
		} catch (e) {
			const err = e as Error;
			error = err.message;
		} finally {
			linkingAccount = null;
		}
	}

	onMount(() => {
		loadConnections();
	});
</script>

<svelte:head>
	<title>Cloud Accounts | Valdrix</title>
</svelte:head>

<div class="space-y-8">
	<div class="flex items-center justify-between">
		<div>
			<h1 class="text-3xl font-bold mb-2">Cloud Accounts</h1>
			<p class="text-ink-400">
				Manage your multi-cloud connectivity and enterprise organization discovery.
			</p>
		</div>
		<a href="{base}/onboarding" class="btn btn-primary !w-auto">
			<span>➕</span> Connect New Provider
		</a>
	</div>

	{#if error}
		<div class="card border-danger-500/50 bg-danger-500/10">
			<p class="text-danger-400">{error}</p>
		</div>
	{/if}

	{#if success}
		<div class="card border-success-500/50 bg-success-500/10">
			<p class="text-success-400">{success}</p>
		</div>
	{/if}

	<!-- Integration Status Cards -->
	<div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-6">
		<!-- AWS -->
		<div class="glass-panel stagger-enter" style="animation-delay: 0ms;">
			<div class="flex items-center justify-between mb-4">
				<div class="flex items-center gap-3">
					<CloudLogo provider="aws" size={40} />
					<div>
						<h3 class="font-bold text-lg">AWS</h3>
						<p class="text-xs text-ink-500">Public Cloud Provider</p>
					</div>
				</div>
				{#if loadingAWS}
					<div class="skeleton w-4 h-4 rounded-full"></div>
				{:else if awsConnections.length > 0}
					<span class="badge badge-success">Active ({awsConnections.length})</span>
				{:else}
					<span class="badge badge-default">Disconnected</span>
				{/if}
			</div>

			{#if awsConnections.length > 0}
				<div class="space-y-4 mb-6">
					{#each awsConnections as conn (conn.id)}
						<div
							class="p-3 rounded-xl bg-ink-900/50 border border-ink-800 group relative overflow-hidden"
						>
							<div class="flex justify-between items-start mb-2">
								<div>
									<div class="flex items-center gap-2 mb-1">
										<span class="text-[10px] text-ink-500 font-mono">ID: {conn.aws_account_id}</span
										>
										<span
											class="badge {conn.is_management_account
												? 'badge-accent'
												: 'badge-default'} text-[10px] px-1.5 py-0.5"
										>
											{conn.is_management_account ? 'Management' : 'Member'}
										</span>
									</div>
								</div>

								<button
									class="p-1.5 rounded-lg bg-danger-500/10 text-danger-400 hover:bg-danger-500 hover:text-white transition-all shadow-sm"
									onclick={() => deleteConnection('aws', conn.id)}
									title="Delete Connection"
								>
									<span class="text-xs">🗑️</span>
								</button>
							</div>

							{#if conn.organization_id}
								<div class="flex justify-between text-[10px]">
									<span class="text-ink-500">Organization:</span>
									<span class="text-ink-300 font-mono">{conn.organization_id}</span>
								</div>
							{/if}
						</div>
					{/each}
				</div>
				<a
					href="{base}/onboarding"
					class="btn btn-ghost text-xs w-full border-dashed border-ink-800 hover:border-accent-500/50"
				>
					<span>➕</span> Add Another Account
				</a>
			{:else if !loadingAWS}
				<p class="text-xs text-ink-400 mb-6">
					Establish a secure connection using our 1-click CloudFormation template.
				</p>
				<a href="{base}/onboarding" class="btn btn-primary text-xs w-full">Connect AWS</a>
			{/if}
		</div>

		<!-- Azure -->
		<div class="glass-panel stagger-enter" style="animation-delay: 100ms;">
			<div class="flex items-center justify-between mb-4">
				<div class="flex items-center gap-3">
					<CloudLogo provider="azure" size={40} />
					<div>
						<h3 class="font-bold text-lg">Azure</h3>
						<p class="text-xs text-ink-500">Public Cloud Provider</p>
					</div>
				</div>
				{#if loadingAzure}
					<div class="skeleton w-4 h-4 rounded-full"></div>
				{:else if azureConnections.length > 0}
					<span class="badge badge-accent">Secure ({azureConnections.length})</span>
				{:else}
					<span class="badge badge-default">Disconnected</span>
				{/if}
			</div>

			{#if azureConnections.length > 0}
				<div class="space-y-4 mb-6">
					{#each azureConnections as conn (conn.id)}
						<div
							class="p-3 rounded-xl bg-ink-900/50 border border-ink-800 group relative overflow-hidden"
						>
							<div class="flex justify-between items-start mb-2">
								<div>
									<div class="flex items-center gap-2 mb-1">
										<span class="text-[10px] text-ink-500 font-mono"
											>Sub ID: {conn.subscription_id
												? `${conn.subscription_id.slice(0, 8)}...`
												: 'N/A'}</span
										>
									</div>
								</div>

								<button
									class="p-1.5 rounded-lg bg-danger-500/10 text-danger-400 hover:bg-danger-500 hover:text-white transition-all shadow-sm"
									onclick={() => deleteConnection('azure', conn.id)}
									title="Delete Connection"
								>
									<span class="text-xs">🗑️</span>
								</button>
							</div>
							<div class="flex justify-between text-[10px]">
								<span class="text-ink-500">Auth Strategy:</span>
								<span class="text-accent-400">Identity Federation</span>
							</div>
						</div>
					{/each}
				</div>
				<a
					href="{base}/onboarding"
					class="btn btn-ghost text-xs w-full border-dashed border-ink-800 hover:border-accent-500/50"
				>
					<span>➕</span> Add Another Subscription
				</a>
			{:else if !loadingAzure}
				<p class="text-xs text-ink-400 mb-6">
					Connect via Workload Identity Federation for secret-less security.
				</p>
				<div class="flex flex-col gap-2">
					<a
						href={['growth', 'pro', 'enterprise'].includes(data.subscription?.tier)
							? `${base}/onboarding`
							: `${base}/billing`}
						class="btn btn-secondary text-xs w-full"
					>
						Connect Azure
					</a>
					<span class="badge badge-warning text-[10px] w-full justify-center"
						>Growth Tier Required</span
					>
				</div>
			{/if}
		</div>

		<!-- GCP -->
		<div class="glass-panel stagger-enter" style="animation-delay: 200ms;">
			<div class="flex items-center justify-between mb-4">
				<div class="flex items-center gap-3">
					<CloudLogo provider="gcp" size={40} />
					<div>
						<h3 class="font-bold text-lg">GCP</h3>
						<p class="text-xs text-ink-500">Public Cloud Provider</p>
					</div>
				</div>
				{#if loadingGCP}
					<div class="skeleton w-4 h-4 rounded-full"></div>
				{:else if gcpConnections.length > 0}
					<span class="badge badge-accent">Secure ({gcpConnections.length})</span>
				{:else}
					<span class="badge badge-default">Disconnected</span>
				{/if}
			</div>

			{#if gcpConnections.length > 0}
				<div class="space-y-4 mb-6">
					{#each gcpConnections as conn (conn.id)}
						<div
							class="p-3 rounded-xl bg-ink-900/50 border border-ink-800 group relative overflow-hidden"
						>
							<div class="flex justify-between items-start mb-2">
								<div>
									<div class="flex items-center gap-2 mb-1">
										<span class="text-[10px] text-ink-500 font-mono"
											>Project: {conn.project_id}</span
										>
									</div>
								</div>

								<button
									class="p-1.5 rounded-lg bg-danger-500/10 text-danger-400 hover:bg-danger-500 hover:text-white transition-all shadow-sm"
									onclick={() => deleteConnection('gcp', conn.id)}
									title="Delete Connection"
								>
									<span class="text-xs">🗑️</span>
								</button>
							</div>
							<div class="flex justify-between text-[10px]">
								<span class="text-ink-500">Auth Method:</span>
								<span class="text-accent-400 capitalize"
									>{conn.auth_method ? conn.auth_method.replace('_', ' ') : 'unknown'}</span
								>
							</div>
						</div>
					{/each}
				</div>
				<a
					href="{base}/onboarding"
					class="btn btn-ghost text-xs w-full border-dashed border-ink-800 hover:border-accent-500/50"
				>
					<span>➕</span> Add Another Project
				</a>
			{:else if !loadingGCP}
				<p class="text-xs text-ink-400 mb-6">
					Seamless integration using GCP Workload Identity pools.
				</p>
				<div class="flex flex-col gap-2">
					<a
						href={['growth', 'pro', 'enterprise'].includes(data.subscription?.tier)
							? `${base}/onboarding`
							: `${base}/billing`}
						class="btn btn-secondary text-xs w-full"
					>
						Connect GCP
					</a>
					<span class="badge badge-warning text-[10px] w-full justify-center"
						>Growth Tier Required</span
					>
				</div>
			{/if}
		</div>

		<!-- SaaS -->
		<div class="glass-panel stagger-enter" style="animation-delay: 300ms;">
			<div class="flex items-center justify-between mb-4">
				<div class="flex items-center gap-3">
					<CloudLogo provider="saas" size={40} />
					<div>
						<h3 class="font-bold text-lg">SaaS</h3>
						<p class="text-xs text-ink-500">Cloud+ Spend Connector</p>
					</div>
				</div>
				{#if loadingSaaS}
					<div class="skeleton w-4 h-4 rounded-full"></div>
				{:else if saasConnections.length > 0}
					<span class="badge badge-accent">Connected ({saasConnections.length})</span>
				{:else}
					<span class="badge badge-default">Disconnected</span>
				{/if}
			</div>

			{#if saasConnections.length > 0}
				<div class="space-y-4 mb-6">
					{#each saasConnections as conn (conn.id)}
						<div class="p-3 rounded-xl bg-ink-900/50 border border-ink-800">
							<div class="flex justify-between items-start mb-2">
								<div>
									<div class="text-[11px] text-ink-300 font-semibold">{conn.name || 'SaaS Feed'}</div>
									<div class="text-[10px] text-ink-500 font-mono">Vendor: {conn.vendor || 'unknown'}</div>
								</div>
								<div class="flex items-center gap-2">
									<button
										class="px-2 py-1 rounded-lg text-[10px] font-semibold bg-accent-500/10 text-accent-300 hover:bg-accent-500/20 transition-all"
										onclick={() => verifyCloudPlusConnection('saas', conn.id)}
										disabled={!!verifyingCloudPlus[conn.id]}
									>
										{verifyingCloudPlus[conn.id] ? 'Verifying...' : 'Verify'}
									</button>
									<button
										class="p-1.5 rounded-lg bg-danger-500/10 text-danger-400 hover:bg-danger-500 hover:text-white transition-all shadow-sm"
										onclick={() => deleteConnection('saas', conn.id)}
										title="Delete Connection"
									>
										<span class="text-xs">🗑️</span>
									</button>
								</div>
							</div>
							<div class="flex justify-between text-[10px]">
								<span class="text-ink-500">Auth Method:</span>
								<span class="text-accent-400">{conn.auth_method || 'manual'}</span>
							</div>
							<div class="flex justify-between text-[10px] mt-1">
								<span class="text-ink-500">Status:</span>
								<span class={conn.is_active ? 'text-success-400' : 'text-warning-400'}>
									{conn.is_active ? 'active' : 'pending verification'}
								</span>
							</div>
						</div>
					{/each}
				</div>
			{/if}

			{#if canUseCloudPlusFeatures()}
				<details class="rounded-xl border border-ink-800 bg-ink-900/40 p-3 space-y-3">
					<summary class="cursor-pointer text-xs font-semibold text-ink-200">
						{saasConnections.length > 0 ? 'Add another SaaS connector' : 'Create SaaS connector'}
					</summary>
					<div class="space-y-3 mt-3">
						<input
							class="w-full rounded-lg bg-ink-950 border border-ink-800 px-3 py-2 text-xs text-ink-200"
							placeholder="Connection name (e.g. Stripe Billing)"
							bind:value={saasName}
						/>
						<input
							class="w-full rounded-lg bg-ink-950 border border-ink-800 px-3 py-2 text-xs text-ink-200"
							placeholder="Vendor (stripe, salesforce, etc.)"
							bind:value={saasVendor}
						/>
						<select
							class="w-full rounded-lg bg-ink-950 border border-ink-800 px-3 py-2 text-xs text-ink-200"
							bind:value={saasAuthMethod}
						>
							<option value="api_key">API key</option>
							<option value="oauth">OAuth token</option>
							<option value="manual">Manual feed</option>
							<option value="csv">CSV feed</option>
						</select>
						<input
							class="w-full rounded-lg bg-ink-950 border border-ink-800 px-3 py-2 text-xs text-ink-200"
							type="password"
							placeholder="API key / OAuth token"
							bind:value={saasApiKey}
						/>
						<textarea
							class="w-full rounded-lg bg-ink-950 border border-ink-800 px-3 py-2 text-xs text-ink-200 h-20 font-mono"
							placeholder="Connector config JSON (example: include instance_url for Salesforce)"
							bind:value={saasConnectorConfig}
						></textarea>
						<textarea
							class="w-full rounded-lg bg-ink-950 border border-ink-800 px-3 py-2 text-xs text-ink-200 h-24 font-mono"
							placeholder="Spend feed JSON array for manual/csv mode"
							bind:value={saasFeedInput}
						></textarea>
						<button
							class="btn btn-secondary text-xs w-full"
							onclick={() => createCloudPlusConnection('saas')}
							disabled={creatingSaaS}
						>
							{creatingSaaS ? 'Creating...' : 'Create SaaS Connector'}
						</button>
					</div>
				</details>
			{:else if !loadingSaaS}
				<p class="text-xs text-ink-400 mb-4">
					Connect SaaS spend feeds for Cloud+ cost visibility and optimization.
				</p>
				<div class="flex flex-col gap-2">
					<a href="{base}/billing" class="btn btn-secondary text-xs w-full">Upgrade for SaaS Connectors</a>
					<span class="badge badge-warning text-[10px] w-full justify-center">Pro Tier Required</span>
				</div>
			{/if}
		</div>

		<!-- License / ITAM -->
		<div class="glass-panel stagger-enter" style="animation-delay: 400ms;">
			<div class="flex items-center justify-between mb-4">
				<div class="flex items-center gap-3">
					<CloudLogo provider="license" size={40} />
					<div>
						<h3 class="font-bold text-lg">License</h3>
						<p class="text-xs text-ink-500">Cloud+ ITAM Connector</p>
					</div>
				</div>
				{#if loadingLicense}
					<div class="skeleton w-4 h-4 rounded-full"></div>
				{:else if licenseConnections.length > 0}
					<span class="badge badge-accent">Connected ({licenseConnections.length})</span>
				{:else}
					<span class="badge badge-default">Disconnected</span>
				{/if}
			</div>

			{#if licenseConnections.length > 0}
				<div class="space-y-4 mb-6">
					{#each licenseConnections as conn (conn.id)}
						<div class="p-3 rounded-xl bg-ink-900/50 border border-ink-800">
							<div class="flex justify-between items-start mb-2">
								<div>
									<div class="text-[11px] text-ink-300 font-semibold">{conn.name || 'License Feed'}</div>
									<div class="text-[10px] text-ink-500 font-mono">Vendor: {conn.vendor || 'unknown'}</div>
								</div>
								<div class="flex items-center gap-2">
									<button
										class="px-2 py-1 rounded-lg text-[10px] font-semibold bg-accent-500/10 text-accent-300 hover:bg-accent-500/20 transition-all"
										onclick={() => verifyCloudPlusConnection('license', conn.id)}
										disabled={!!verifyingCloudPlus[conn.id]}
									>
										{verifyingCloudPlus[conn.id] ? 'Verifying...' : 'Verify'}
									</button>
									<button
										class="p-1.5 rounded-lg bg-danger-500/10 text-danger-400 hover:bg-danger-500 hover:text-white transition-all shadow-sm"
										onclick={() => deleteConnection('license', conn.id)}
										title="Delete Connection"
									>
										<span class="text-xs">🗑️</span>
									</button>
								</div>
							</div>
							<div class="flex justify-between text-[10px]">
								<span class="text-ink-500">Auth Method:</span>
								<span class="text-accent-400">{conn.auth_method || 'manual'}</span>
							</div>
							<div class="flex justify-between text-[10px] mt-1">
								<span class="text-ink-500">Status:</span>
								<span class={conn.is_active ? 'text-success-400' : 'text-warning-400'}>
									{conn.is_active ? 'active' : 'pending verification'}
								</span>
							</div>
						</div>
					{/each}
				</div>
			{/if}

			{#if canUseCloudPlusFeatures()}
				<details class="rounded-xl border border-ink-800 bg-ink-900/40 p-3 space-y-3">
					<summary class="cursor-pointer text-xs font-semibold text-ink-200">
						{licenseConnections.length > 0
							? 'Add another License connector'
							: 'Create License connector'}
					</summary>
					<div class="space-y-3 mt-3">
						<input
							class="w-full rounded-lg bg-ink-950 border border-ink-800 px-3 py-2 text-xs text-ink-200"
							placeholder="Connection name (e.g. Microsoft 365 Licenses)"
							bind:value={licenseName}
						/>
						<input
							class="w-full rounded-lg bg-ink-950 border border-ink-800 px-3 py-2 text-xs text-ink-200"
							placeholder="Vendor (microsoft_365, flexera, etc.)"
							bind:value={licenseVendor}
						/>
						<select
							class="w-full rounded-lg bg-ink-950 border border-ink-800 px-3 py-2 text-xs text-ink-200"
							bind:value={licenseAuthMethod}
						>
							<option value="oauth">OAuth token</option>
							<option value="api_key">API key</option>
							<option value="manual">Manual feed</option>
							<option value="csv">CSV feed</option>
						</select>
						<input
							class="w-full rounded-lg bg-ink-950 border border-ink-800 px-3 py-2 text-xs text-ink-200"
							type="password"
							placeholder="API key / OAuth token"
							bind:value={licenseApiKey}
						/>
						<textarea
							class="w-full rounded-lg bg-ink-950 border border-ink-800 px-3 py-2 text-xs text-ink-200 h-20 font-mono"
							placeholder="Connector config JSON (example: default_seat_price_usd and sku_prices)"
							bind:value={licenseConnectorConfig}
						></textarea>
						<textarea
							class="w-full rounded-lg bg-ink-950 border border-ink-800 px-3 py-2 text-xs text-ink-200 h-24 font-mono"
							placeholder="License feed JSON array for manual/csv mode"
							bind:value={licenseFeedInput}
						></textarea>
						<button
							class="btn btn-secondary text-xs w-full"
							onclick={() => createCloudPlusConnection('license')}
							disabled={creatingLicense}
						>
							{creatingLicense ? 'Creating...' : 'Create License Connector'}
						</button>
					</div>
				</details>
			{:else if !loadingLicense}
				<p class="text-xs text-ink-400 mb-4">
					Connect license/ITAM spend feeds to include seat and contract costs in FinOps.
				</p>
				<div class="flex flex-col gap-2">
					<a href="{base}/billing" class="btn btn-secondary text-xs w-full"
						>Upgrade for License Connectors</a
					>
					<span class="badge badge-warning text-[10px] w-full justify-center">Pro Tier Required</span>
				</div>
			{/if}
		</div>
	</div>

	<!-- AWS Organizations Hub (RELOCATED & POLISHED) -->
	{#if awsConnection?.is_management_account}
		<div
			class="card stagger-enter mt-12 border-accent-500/30 bg-accent-500/5 relative overflow-hidden"
			class:opacity-60={!['growth', 'pro', 'enterprise'].includes(data.subscription?.tier)}
		>
			<!-- Background pattern -->
			<div class="absolute top-0 right-0 p-8 opacity-10 pointer-events-none">
				<span class="text-9xl">🏢</span>
			</div>

			<div class="relative z-10">
				<div class="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
					<div>
						<h2 class="text-2xl font-bold flex items-center gap-2 mb-1">
							<span>🏢</span> AWS Organizations Hub
						</h2>
						<p class="text-sm text-ink-400">
							Managing Organization: <span class="text-accent-400 font-mono"
								>{awsConnection.organization_id || 'Global'}</span
							>
						</p>
					</div>

					<div class="flex items-center gap-3">
						{#if !['growth', 'pro', 'enterprise'].includes(data.subscription?.tier)}
							<span class="badge badge-warning">Growth Tier Required</span>
						{:else}
							<button
								class="btn btn-primary !w-auto flex items-center gap-2"
								onclick={syncAWSOrg}
								disabled={syncingOrg}
							>
								{#if syncingOrg}
									<div
										class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"
									></div>
									<span>Syncing...</span>
								{:else}
									<span>🔄</span>
									<span>Sync Accounts</span>
								{/if}
							</button>
						{/if}
					</div>
				</div>

				{#if !['growth', 'pro', 'enterprise'].includes(data.subscription?.tier)}
					<div class="py-20 text-center glass-panel bg-black/20 border-white/5">
						<div class="mb-6 text-5xl">🔒</div>
						<h3 class="text-xl font-bold mb-2">Enterprise Organization Discovery</h3>
						<p class="text-ink-400 max-w-md mx-auto mb-8">
							Unlock the ability to automatically discover, monitor, and optimize hundreds of member
							accounts across your entire AWS Organization.
						</p>
						<a href="{base}/billing" class="btn btn-primary !w-auto px-8 py-3"
							>Upgrade to Growth Tier</a
						>
					</div>
				{:else}
					<div class="grid grid-cols-1 lg:grid-cols-4 gap-6 mb-8">
						<div class="card bg-ink-900/50 p-4 border-ink-800">
							<p class="text-xs text-ink-500 mb-1">Total Discovered</p>
							<p class="text-2xl font-bold">{discoveredAccounts.length}</p>
						</div>
						<div class="card bg-ink-900/50 p-4 border-ink-800">
							<p class="text-xs text-ink-500 mb-1">Linked Accounts</p>
							<p class="text-2xl font-bold text-success-400">
								{discoveredAccounts.filter((a) => a.status === 'linked').length}
							</p>
						</div>
						<div class="card bg-ink-900/50 p-4 border-ink-800">
							<p class="text-xs text-ink-500 mb-1">Pending Link</p>
							<p class="text-2xl font-bold text-warning-400">
								{discoveredAccounts.filter((a) => a.status === 'discovered').length}
							</p>
						</div>
						<div class="card bg-ink-900/50 p-4 border-ink-800">
							<p class="text-xs text-ink-500 mb-1">Org Status</p>
							<p class="text-2xl font-bold text-accent-400">Synced</p>
						</div>
					</div>

					{#if loadingDiscovered}
						<div class="space-y-4">
							<div class="skeleton h-12 w-full"></div>
							<div class="skeleton h-12 w-full"></div>
							<div class="skeleton h-12 w-full"></div>
						</div>
					{:else if discoveredAccounts.length > 0}
						<div class="overflow-x-auto rounded-xl border border-ink-800">
							<table class="w-full text-sm text-left">
								<thead class="bg-ink-900/80 text-ink-400 uppercase text-[10px] tracking-wider">
									<tr>
										<th class="px-6 py-4 font-semibold uppercase">Account Details</th>
										<th class="px-6 py-4 font-semibold uppercase">Email</th>
										<th class="px-6 py-4 font-semibold uppercase">Status</th>
										<th class="px-6 py-4 font-semibold uppercase text-right">Action</th>
									</tr>
								</thead>
								<tbody class="divide-y divide-ink-800">
									{#each discoveredAccounts as acc (acc.id)}
										<tr class="hover:bg-accent-500/5 transition-colors">
											<td class="px-6 py-4">
												<div class="font-bold mb-0.5">{acc.name || 'Unnamed Account'}</div>
												<div class="text-xs font-mono text-ink-500">{acc.account_id}</div>
											</td>
											<td class="px-6 py-4 text-ink-400">{acc.email || '-'}</td>
											<td class="px-6 py-4">
												<div
													class="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium
                          {acc.status === 'linked'
														? 'bg-success-500/10 text-success-400 border border-success-500/20'
														: 'bg-ink-800 text-ink-400 border border-ink-700'}"
												>
													<span
														class="w-1.5 h-1.5 rounded-full {acc.status === 'linked'
															? 'bg-success-400'
															: 'bg-ink-500'}"
													></span>
													{acc.status}
												</div>
											</td>
											<td class="px-6 py-4 text-right">
												{#if acc.status === 'discovered'}
													<button
														class="btn btn-ghost btn-sm text-accent-400 hover:text-accent-300 hover:bg-accent-400/10"
														onclick={() => linkDiscoveredAccount(acc.id)}
														disabled={linkingAccount === acc.id}
													>
														{linkingAccount === acc.id ? 'Connecting...' : 'Link Account →'}
													</button>
												{:else}
													<span class="text-success-400 font-medium">✓ Linked</span>
												{/if}
											</td>
										</tr>
									{/each}
								</tbody>
							</table>
						</div>
					{:else}
						<div
							class="py-16 text-center border-2 border-dashed border-ink-800 rounded-3xl bg-ink-900/20"
						>
							<div class="text-5xl mb-4">🔍</div>
							<h3 class="text-xl font-bold mb-2">No Member Accounts Found</h3>
							<p class="text-ink-500 max-w-sm mx-auto mb-6">
								We couldn't find any member accounts. Run a sync to scan your Organization.
							</p>
							<button class="btn btn-primary !w-auto px-8" onclick={syncAWSOrg}>
								Start Organizational Scan
							</button>
						</div>
					{/if}
				{/if}
			</div>
		</div>
	{/if}
</div>

<style>
	.glass-panel {
		background: rgba(15, 23, 42, 0.4);
		backdrop-filter: blur(12px);
		border: 1px solid rgba(255, 255, 255, 0.05);
		border-radius: 24px;
		padding: 1.5rem;
		transition: all 0.3s ease;
	}

	.glass-panel:hover {
		border-color: rgba(6, 182, 212, 0.3);
		box-shadow: 0 10px 30px -15px rgba(6, 182, 212, 0.2);
		transform: translateY(-2px);
	}
</style>
