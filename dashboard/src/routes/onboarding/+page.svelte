<script lang="ts">
	/* eslint-disable svelte/no-navigation-without-resolve */
	import CloudLogo from '$lib/components/CloudLogo.svelte';
	import { api } from '$lib/api';
	import AuthGate from '$lib/components/AuthGate.svelte';
	import { edgeApiPath } from '$lib/edgeProxy';
	import { base } from '$app/paths';

	type CloudPlusAuthMethod = 'manual' | 'api_key' | 'oauth' | 'csv';
	type CloudPlusProvider = 'saas' | 'license';
	type IdpProvider = 'microsoft_365' | 'google_workspace';
	type DiscoveryStatus = 'pending' | 'accepted' | 'ignored' | 'connected';

	interface NativeConnectorMeta {
		vendor: string;
		display_name: string;
		recommended_auth_method: CloudPlusAuthMethod;
		supported_auth_methods: CloudPlusAuthMethod[];
		required_connector_config_fields: string[];
		optional_connector_config_fields: string[];
	}

	interface ManualFeedSchema {
		required_fields: string[];
		optional_fields: string[];
	}

	interface DiscoveryCandidate {
		id: string;
		domain: string;
		category: string;
		provider: string;
		source: string;
		status: DiscoveryStatus;
		confidence_score: number;
		requires_admin_auth: boolean;
		connection_target: string | null;
		connection_vendor_hint: string | null;
		evidence: string[];
		details: Record<string, unknown>;
		last_seen_at: string;
		created_at: string;
		updated_at: string;
	}

	interface DiscoveryStageResponse {
		domain: string;
		candidates: DiscoveryCandidate[];
		warnings: string[];
		total_candidates: number;
	}

	const CLOUD_PLUS_AUTH_METHODS: CloudPlusAuthMethod[] = ['manual', 'api_key', 'oauth', 'csv'];

	let { data } = $props();

	// State management
	let currentStep = $state(0); // 0: Select Provider, 1: Setup, 2: Verify, 3: Done
	let selectedProvider: 'aws' | 'azure' | 'gcp' | 'saas' | 'license' = $state('aws');
	let selectedTab: 'cloudformation' | 'terraform' = $state('cloudformation');
	let externalId = $state('');
	let magicLink = $state('');
	let cloudformationYaml = $state('');
	let terraformHcl = $state('');
	let roleArn = $state('');
	let awsAccountId = $state('');
	let isManagementAccount = $state(false);
	let organizationId = $state('');

	// Azure/GCP specific
	let azureSubscriptionId = $state('');
	let azureTenantId = $state('');
	let azureClientId = $state('');
	let gcpProjectId = $state('');
	let gcpBillingProjectId = $state('');
	let gcpBillingDataset = $state('');
	let gcpBillingTable = $state('');
	let cloudShellSnippet = $state('');
	let cloudPlusSampleFeed = $state('');

	// SaaS / License specific
	let cloudPlusName = $state('');
	let cloudPlusVendor = $state('');
	let cloudPlusAuthMethod: CloudPlusAuthMethod = $state('manual');
	let cloudPlusApiKey = $state('');
	let cloudPlusFeedInput = $state('[]');
	let cloudPlusConnectorConfigInput = $state('{}');
	let cloudPlusNativeConnectors = $state<NativeConnectorMeta[]>([]);
	let cloudPlusManualFeedSchema = $state<ManualFeedSchema>({
		required_fields: [],
		optional_fields: []
	});
	let cloudPlusRequiredConfigValues = $state<Record<string, string>>({});
	let cloudPlusConfigProvider = $state<CloudPlusProvider | null>(null);

	// Discovery wizard state
	let discoveryEmail = $state('');
	let discoveryDomain = $state('');
	let discoveryIdpProvider: IdpProvider = $state('microsoft_365');
	let discoveryCandidates = $state<DiscoveryCandidate[]>([]);
	let discoveryWarnings = $state<string[]>([]);
	let discoveryLoadingStageA = $state(false);
	let discoveryLoadingStageB = $state(false);
	let discoveryActionCandidateId = $state<string | null>(null);
	let discoveryError = $state('');
	let discoveryInfo = $state('');

	$effect(() => {
		if (discoveryEmail.trim().length > 0) {
			return;
		}
		if (typeof data?.user?.email !== 'string') {
			return;
		}
		const normalized = data.user.email.trim();
		if (normalized.length > 0) {
			discoveryEmail = normalized;
		}
	});

	let isLoading = $state(false);
	let isVerifying = $state(false);
	let error = $state('');
	let success = $state(false);
	let copied = $state(false);

	const growthAndAbove = ['growth', 'pro', 'enterprise'];
	const cloudPlusAllowed = ['pro', 'enterprise'];
	const idpDeepScanAllowed = ['pro', 'enterprise'];

	function canUseGrowthFeatures(): boolean {
		return growthAndAbove.includes(data?.subscription?.tier);
	}

	function canUseCloudPlusFeatures(): boolean {
		return cloudPlusAllowed.includes(data?.subscription?.tier);
	}

	function canUseIdpDeepScan(): boolean {
		return idpDeepScanAllowed.includes(data?.subscription?.tier);
	}

	function getProviderLabel(provider: typeof selectedProvider): string {
		switch (provider) {
			case 'aws':
				return 'AWS';
			case 'azure':
				return 'Azure';
			case 'gcp':
				return 'GCP';
			case 'saas':
				return 'SaaS';
			case 'license':
				return 'License';
		}
	}

	function extractDomainFromEmail(value: string): string {
		const normalized = value.trim().toLowerCase();
		const at = normalized.lastIndexOf('@');
		if (at <= 0 || at >= normalized.length - 1) {
			return '';
		}
		return normalized.slice(at + 1);
	}

	function getDiscoveryCategoryLabel(category: string): string {
		if (category === 'cloud_provider') return 'Cloud';
		if (category === 'cloud_plus') return 'Cloud+';
		if (category === 'license') return 'License';
		if (category === 'platform') return 'Platform';
		return category;
	}

	function formatDiscoveryConfidence(score: number): string {
		if (!Number.isFinite(score)) {
			return '0%';
		}
		const bounded = Math.max(0, Math.min(score, 1));
		return `${Math.round(bounded * 100)}%`;
	}

	function resolveProviderFromCandidate(
		candidate: DiscoveryCandidate
	): 'aws' | 'azure' | 'gcp' | 'saas' | 'license' | null {
		if (candidate.category === 'cloud_provider') {
			if (
				candidate.provider === 'aws' ||
				candidate.provider === 'azure' ||
				candidate.provider === 'gcp'
			) {
				return candidate.provider;
			}
			return null;
		}
		if (candidate.category === 'license') {
			return 'license';
		}
		if (candidate.category === 'cloud_plus') {
			return 'saas';
		}
		return null;
	}

	function applyDiscoveryCandidateLocally(updated: DiscoveryCandidate): void {
		discoveryCandidates = discoveryCandidates.map((candidate) =>
			candidate.id === updated.id ? updated : candidate
		);
	}

	function upsertDiscoveryCandidates(candidates: DiscoveryCandidate[]): void {
		const merged = [...discoveryCandidates];
		for (const candidate of candidates) {
			const existingIndex = merged.findIndex((item) => item.id === candidate.id);
			if (existingIndex >= 0) {
				merged[existingIndex] = candidate;
			} else {
				merged.push(candidate);
			}
		}
		discoveryCandidates = merged.sort((a, b) => {
			if (b.confidence_score !== a.confidence_score) {
				return b.confidence_score - a.confidence_score;
			}
			return a.provider.localeCompare(b.provider);
		});
	}

	async function runDiscoveryStageA(): Promise<void> {
		discoveryError = '';
		discoveryInfo = '';
		const normalizedEmail = discoveryEmail.trim();
		if (!normalizedEmail) {
			discoveryError = 'Enter a valid work email to run discovery.';
			return;
		}

		discoveryLoadingStageA = true;
		try {
			const token = await getAccessToken();
			if (!token) {
				throw new Error('Please log in first');
			}
			const onboarded = await ensureOnboarded();
			if (!onboarded) {
				return;
			}

			const res = await api.post(
				edgeApiPath('/settings/connections/discovery/stage-a'),
				{ email: normalizedEmail },
				{
					headers: { Authorization: `Bearer ${token}` }
				}
			);
			const payload = (await res.json().catch(() => ({}))) as Partial<DiscoveryStageResponse> & {
				detail?: string;
			};
			if (!res.ok) {
				throw new Error(payload.detail || 'Failed to run Stage A discovery');
			}

			discoveryDomain = typeof payload.domain === 'string' ? payload.domain : '';
			discoveryWarnings = Array.isArray(payload.warnings)
				? payload.warnings.filter((warning): warning is string => typeof warning === 'string')
				: [];
			const candidates = Array.isArray(payload.candidates) ? payload.candidates : [];
			upsertDiscoveryCandidates(candidates);
			discoveryInfo = `Stage A complete: found ${candidates.length} candidate(s).`;
		} catch (e) {
			const err = e as Error;
			discoveryError = err.message || 'Failed to run Stage A discovery';
		} finally {
			discoveryLoadingStageA = false;
		}
	}

	async function runDiscoveryStageB(): Promise<void> {
		discoveryError = '';
		discoveryInfo = '';
		if (!canUseIdpDeepScan()) {
			discoveryError = 'Deep scan requires Pro tier or higher.';
			return;
		}

		const domain = discoveryDomain || extractDomainFromEmail(discoveryEmail);
		if (!domain) {
			discoveryError = 'Run Stage A first or enter a valid email domain.';
			return;
		}

		discoveryLoadingStageB = true;
		try {
			const token = await getAccessToken();
			if (!token) {
				throw new Error('Please log in first');
			}
			const onboarded = await ensureOnboarded();
			if (!onboarded) {
				return;
			}

			const res = await api.post(
				edgeApiPath('/settings/connections/discovery/deep-scan'),
				{
					domain,
					idp_provider: discoveryIdpProvider,
					max_users: 20
				},
				{
					headers: { Authorization: `Bearer ${token}` }
				}
			);
			const payload = (await res.json().catch(() => ({}))) as Partial<DiscoveryStageResponse> & {
				detail?: string;
			};
			if (!res.ok) {
				throw new Error(payload.detail || 'Failed to run Stage B deep scan');
			}

			discoveryDomain = typeof payload.domain === 'string' ? payload.domain : domain;
			discoveryWarnings = Array.isArray(payload.warnings)
				? payload.warnings.filter((warning): warning is string => typeof warning === 'string')
				: [];
			const candidates = Array.isArray(payload.candidates) ? payload.candidates : [];
			upsertDiscoveryCandidates(candidates);
			discoveryInfo = `Stage B complete: ${candidates.length} candidate(s) now in scope.`;
		} catch (e) {
			const err = e as Error;
			discoveryError = err.message || 'Failed to run Stage B deep scan';
		} finally {
			discoveryLoadingStageB = false;
		}
	}

	async function updateDiscoveryCandidateStatus(
		candidate: DiscoveryCandidate,
		action: 'accept' | 'ignore' | 'connected'
	): Promise<DiscoveryCandidate | null> {
		discoveryError = '';
		discoveryInfo = '';
		discoveryActionCandidateId = candidate.id;
		try {
			const token = await getAccessToken();
			if (!token) {
				throw new Error('Please log in first');
			}
			const res = await api.post(
				edgeApiPath(`/settings/connections/discovery/candidates/${candidate.id}/${action}`),
				undefined,
				{
					headers: { Authorization: `Bearer ${token}` }
				}
			);
			const payload = (await res.json().catch(() => ({}))) as DiscoveryCandidate & {
				detail?: string;
			};
			if (!res.ok) {
				throw new Error(payload.detail || `Failed to ${action} discovery candidate`);
			}
			applyDiscoveryCandidateLocally(payload);
			return payload;
		} catch (e) {
			const err = e as Error;
			discoveryError = err.message || `Failed to ${action} discovery candidate`;
			return null;
		} finally {
			discoveryActionCandidateId = null;
		}
	}

	async function ignoreDiscoveryCandidate(candidate: DiscoveryCandidate): Promise<void> {
		const updated = await updateDiscoveryCandidateStatus(candidate, 'ignore');
		if (updated) {
			discoveryInfo = `${updated.provider} ignored.`;
		}
	}

	async function markDiscoveryCandidateConnected(candidate: DiscoveryCandidate): Promise<void> {
		const updated = await updateDiscoveryCandidateStatus(candidate, 'connected');
		if (updated) {
			discoveryInfo = `${updated.provider} marked as connected.`;
		}
	}

	async function connectDiscoveryCandidate(candidate: DiscoveryCandidate): Promise<void> {
		const provider = resolveProviderFromCandidate(candidate);
		if (!provider) {
			discoveryError =
				'This candidate maps to a connector not yet supported in this onboarding flow. Use Connections page.';
			return;
		}

		if ((provider === 'azure' || provider === 'gcp') && !canUseGrowthFeatures()) {
			discoveryError = `${getProviderLabel(provider)} onboarding requires Growth tier or higher.`;
			return;
		}
		if ((provider === 'saas' || provider === 'license') && !canUseCloudPlusFeatures()) {
			discoveryError = `${getProviderLabel(provider)} onboarding requires Pro tier or higher.`;
			return;
		}

		const accepted = await updateDiscoveryCandidateStatus(candidate, 'accept');
		if (!accepted) {
			return;
		}

		selectedProvider = provider;
		currentStep = 1;
		await fetchSetupData();

		if (provider === 'saas' || provider === 'license') {
			const preferredVendor = (accepted.connection_vendor_hint || accepted.provider || '')
				.trim()
				.toLowerCase();
			if (preferredVendor) {
				const knownConnector = cloudPlusNativeConnectors.find(
					(connector) => connector.vendor === preferredVendor
				);
				if (knownConnector) {
					chooseNativeCloudPlusVendor(knownConnector.vendor);
				} else {
					cloudPlusVendor = preferredVendor;
					applyCloudPlusVendorDefaults(false);
				}
			}
			if (!cloudPlusName.trim()) {
				const label = accepted.provider.replace(/_/g, ' ');
				cloudPlusName = `${label} connector`;
			}
		}
		discoveryInfo = `${accepted.provider} ready for setup.`;
	}

	function toCloudPlusAuthMethod(
		value: unknown,
		fallback: CloudPlusAuthMethod = 'manual'
	): CloudPlusAuthMethod {
		if (typeof value !== 'string') {
			return fallback;
		}
		const normalized = value.trim().toLowerCase();
		if (
			normalized === 'manual' ||
			normalized === 'api_key' ||
			normalized === 'oauth' ||
			normalized === 'csv'
		) {
			return normalized;
		}
		return fallback;
	}

	function parseStringArray(value: unknown): string[] {
		if (!Array.isArray(value)) {
			return [];
		}
		return value
			.filter((item): item is string => typeof item === 'string')
			.map((item) => item.trim())
			.filter((item) => item.length > 0);
	}

	function normalizeNativeConnectors(value: unknown): NativeConnectorMeta[] {
		if (!Array.isArray(value)) {
			return [];
		}

		return value
			.map((raw) => {
				if (!raw || typeof raw !== 'object') {
					return null;
				}
				const item = raw as Record<string, unknown>;
				const vendor = typeof item.vendor === 'string' ? item.vendor.trim().toLowerCase() : '';
				if (!vendor) {
					return null;
				}
				const displayName =
					typeof item.display_name === 'string' && item.display_name.trim().length > 0
						? item.display_name.trim()
						: vendor;
				const supportedAuthMethodsRaw = parseStringArray(item.supported_auth_methods).map(
					(authMethod) => toCloudPlusAuthMethod(authMethod)
				);
				const supportedAuthMethods: CloudPlusAuthMethod[] = supportedAuthMethodsRaw.length
					? supportedAuthMethodsRaw
					: ['manual'];

				return {
					vendor,
					display_name: displayName,
					recommended_auth_method: toCloudPlusAuthMethod(
						item.recommended_auth_method,
						supportedAuthMethods[0] ?? 'manual'
					),
					supported_auth_methods: supportedAuthMethods,
					required_connector_config_fields: parseStringArray(item.required_connector_config_fields),
					optional_connector_config_fields: parseStringArray(item.optional_connector_config_fields)
				} satisfies NativeConnectorMeta;
			})
			.filter((item): item is NativeConnectorMeta => item !== null);
	}

	function parseManualFeedSchema(value: unknown): ManualFeedSchema {
		if (!value || typeof value !== 'object') {
			return { required_fields: [], optional_fields: [] };
		}
		const schema = value as Record<string, unknown>;
		return {
			required_fields: parseStringArray(schema.required_fields),
			optional_fields: parseStringArray(schema.optional_fields)
		};
	}

	function parseConnectorConfigInputSafely(): Record<string, unknown> {
		if (!cloudPlusConnectorConfigInput.trim()) {
			return {};
		}
		try {
			const parsed = JSON.parse(cloudPlusConnectorConfigInput);
			if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
				return {};
			}
			return parsed as Record<string, unknown>;
		} catch {
			return {};
		}
	}

	function getSelectedNativeConnector(): NativeConnectorMeta | null {
		const vendor = cloudPlusVendor.trim().toLowerCase();
		if (!vendor) {
			return null;
		}
		return cloudPlusNativeConnectors.find((connector) => connector.vendor === vendor) ?? null;
	}

	function getAvailableCloudPlusAuthMethods(): CloudPlusAuthMethod[] {
		const connector = getSelectedNativeConnector();
		if (!connector) {
			return CLOUD_PLUS_AUTH_METHODS;
		}
		return connector.supported_auth_methods.length
			? connector.supported_auth_methods
			: CLOUD_PLUS_AUTH_METHODS;
	}

	function applyCloudPlusVendorDefaults(forceRecommendedAuth: boolean = false): void {
		const connector = getSelectedNativeConnector();
		if (!connector) {
			cloudPlusRequiredConfigValues = {};
			return;
		}

		const supportedAuthMethods = connector.supported_auth_methods.length
			? connector.supported_auth_methods
			: CLOUD_PLUS_AUTH_METHODS;
		if (forceRecommendedAuth || !supportedAuthMethods.includes(cloudPlusAuthMethod)) {
			cloudPlusAuthMethod = supportedAuthMethods.includes(connector.recommended_auth_method)
				? connector.recommended_auth_method
				: (supportedAuthMethods[0] ?? 'manual');
		}

		const existingConfig = parseConnectorConfigInputSafely();
		const requiredFields = connector.required_connector_config_fields;
		const nextValues: Record<string, string> = {};
		for (const field of requiredFields) {
			const currentValue = cloudPlusRequiredConfigValues[field];
			if (typeof currentValue === 'string' && currentValue.trim().length > 0) {
				nextValues[field] = currentValue;
				continue;
			}
			const configuredValue = existingConfig[field];
			nextValues[field] =
				configuredValue === undefined || configuredValue === null ? '' : String(configuredValue);
		}
		cloudPlusRequiredConfigValues = nextValues;
	}

	function handleCloudPlusVendorInputChanged(): void {
		cloudPlusVendor = cloudPlusVendor.trim().toLowerCase();
		applyCloudPlusVendorDefaults(false);
	}

	function chooseNativeCloudPlusVendor(vendor: string): void {
		cloudPlusVendor = vendor.trim().toLowerCase();
		applyCloudPlusVendorDefaults(true);
	}

	function handleCloudPlusAuthMethodChanged(): void {
		const supportedAuthMethods = getAvailableCloudPlusAuthMethods();
		if (!supportedAuthMethods.includes(cloudPlusAuthMethod)) {
			cloudPlusAuthMethod = supportedAuthMethods[0] ?? 'manual';
		}
		if (cloudPlusAuthMethod !== 'api_key' && cloudPlusAuthMethod !== 'oauth') {
			cloudPlusApiKey = '';
		}
	}

	function isCloudPlusNativeAuthMethod(): boolean {
		return cloudPlusAuthMethod === 'api_key' || cloudPlusAuthMethod === 'oauth';
	}

	function setRequiredConfigField(field: string, value: string): void {
		cloudPlusRequiredConfigValues = { ...cloudPlusRequiredConfigValues, [field]: value };
	}

	function getRequiredConfigFieldValue(field: string): string {
		return cloudPlusRequiredConfigValues[field] ?? '';
	}

	// Get access token from server-loaded session (avoids getSession warning)
	async function getAccessToken(): Promise<string | null> {
		return data.session?.access_token ?? null;
	}

	// Ensure user is onboarded in our database (creates user + tenant)
	async function ensureOnboarded() {
		const token = await getAccessToken();
		if (!token) {
			error = 'Please log in first';
			return false;
		}

		try {
			const res = await api.post(
				edgeApiPath('/settings/onboard'),
				{ tenant_name: 'My Organization' },
				{
					headers: {
						Authorization: `Bearer ${token}`
					}
				}
			);

			if (res.ok) {
				return true;
			} else if (res.status === 400) {
				// Already onboarded - this is fine
				const data = await res.json();
				if (data.detail === 'Already onboarded') {
					return true;
				}
			}
			return true; // Continue anyway
		} catch (e) {
			console.error('Onboarding check failed:', e);
			return true; // Continue anyway - the endpoints will catch it
		}
	}

	// Step 1: Get templates from backend
	async function fetchSetupData() {
		isLoading = true;
		error = '';
		try {
			const token = await getAccessToken();
			if (!token) {
				throw new Error('Please log in first');
			}
			const endpoint =
				selectedProvider === 'aws'
					? '/settings/connections/aws/setup'
					: selectedProvider === 'azure'
						? '/settings/connections/azure/setup'
						: selectedProvider === 'gcp'
							? '/settings/connections/gcp/setup'
							: selectedProvider === 'saas'
								? '/settings/connections/saas/setup'
								: '/settings/connections/license/setup';

			const res = await api.post(edgeApiPath(endpoint), undefined, {
				headers: {
					Authorization: `Bearer ${token}`
				}
			});

			if (!res.ok) {
				const errData = await res.json();
				throw new Error(errData.detail || 'Failed to fetch setup data');
			}

			const responseData = await res.json();
			if (selectedProvider === 'aws') {
				externalId = responseData.external_id;
				magicLink = responseData.magic_link;
				cloudformationYaml = responseData.cloudformation_yaml;
				terraformHcl = responseData.terraform_hcl;
			} else if (selectedProvider === 'azure' || selectedProvider === 'gcp') {
				cloudShellSnippet = responseData.snippet;
			} else {
				const providerDefaults: Record<CloudPlusProvider, { vendor: string; config: string }> = {
					saas: { vendor: 'stripe', config: '{}' },
					license: { vendor: 'microsoft_365', config: '{"default_seat_price_usd": 36}' }
				};
				const providerKey = selectedProvider as CloudPlusProvider;
				const defaults = providerDefaults[providerKey];
				const providerSwitched = cloudPlusConfigProvider !== providerKey;
				cloudPlusConfigProvider = providerKey;

				cloudShellSnippet = responseData.snippet;
				cloudPlusSampleFeed = responseData.sample_feed || '[]';
				cloudPlusFeedInput = responseData.sample_feed || '[]';
				cloudPlusNativeConnectors = normalizeNativeConnectors(responseData.native_connectors);
				cloudPlusManualFeedSchema = parseManualFeedSchema(responseData.manual_feed_schema);
				if (providerSwitched || !cloudPlusVendor.trim()) {
					cloudPlusVendor = cloudPlusNativeConnectors[0]?.vendor || defaults.vendor;
				} else {
					cloudPlusVendor = cloudPlusVendor.trim().toLowerCase();
				}
				if (providerSwitched || !cloudPlusConnectorConfigInput.trim()) {
					cloudPlusConnectorConfigInput = defaults.config;
					cloudPlusRequiredConfigValues = {};
				}
				applyCloudPlusVendorDefaults(true);
			}
		} catch (e) {
			const err = e as Error;
			error = `Failed to initialize ${selectedProvider.toUpperCase()} setup: ${err.message}`;
		} finally {
			isLoading = false;
		}
	}

	async function handleContinueToSetup() {
		if ((selectedProvider === 'azure' || selectedProvider === 'gcp') && !canUseGrowthFeatures()) {
			error = `${getProviderLabel(selectedProvider)} onboarding requires Growth tier or higher.`;
			return;
		}
		if (
			(selectedProvider === 'saas' || selectedProvider === 'license') &&
			!canUseCloudPlusFeatures()
		) {
			error = `${getProviderLabel(selectedProvider)} onboarding requires Pro tier or higher.`;
			return;
		}

		isLoading = true;
		const onboarded = await ensureOnboarded();
		if (!onboarded) {
			isLoading = false;
			return;
		}
		error = '';
		currentStep = 1;
		await fetchSetupData();
	}

	// Copy template to clipboard
	function copyTemplate() {
		const template = selectedTab === 'cloudformation' ? cloudformationYaml : terraformHcl;
		navigator.clipboard.writeText(template);
		copied = true;
		setTimeout(() => (copied = false), 2000);
	}

	// Download template as file
	function downloadTemplate() {
		const template = selectedTab === 'cloudformation' ? cloudformationYaml : terraformHcl;
		const filename = selectedTab === 'cloudformation' ? 'valdrix-role.yaml' : 'valdrix-role.tf';

		const blob = new Blob([template], { type: 'text/plain' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = filename;
		a.click();
		URL.revokeObjectURL(url);
	}

	// Move to step 2 or verify directly for Azure/GCP
	function parseCloudPlusFeed(): Array<Record<string, unknown>> {
		if (!cloudPlusFeedInput.trim()) {
			return [];
		}
		const parsed = JSON.parse(cloudPlusFeedInput);
		if (!Array.isArray(parsed)) {
			throw new Error('Feed JSON must be an array of records.');
		}
		return parsed as Array<Record<string, unknown>>;
	}

	function parseCloudPlusConnectorConfig(): Record<string, unknown> {
		let parsed: unknown = {};
		if (cloudPlusConnectorConfigInput.trim()) {
			try {
				parsed = JSON.parse(cloudPlusConnectorConfigInput);
			} catch {
				throw new Error('Connector config JSON must be valid.');
			}
			if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
				throw new Error('Connector config JSON must be an object.');
			}
		}

		const connectorConfig: Record<string, unknown> = {
			...(parsed as Record<string, unknown>)
		};
		const selectedConnector = getSelectedNativeConnector();
		if (!selectedConnector || !isCloudPlusNativeAuthMethod()) {
			return connectorConfig;
		}

		for (const field of selectedConnector.required_connector_config_fields) {
			const fieldValue = getRequiredConfigFieldValue(field).trim();
			if (!fieldValue) {
				throw new Error(
					`connector_config.${field} is required for ${selectedConnector.display_name}.`
				);
			}
			if (field.toLowerCase().includes('url') && !/^https?:\/\//i.test(fieldValue)) {
				throw new Error(`connector_config.${field} must be an http(s) URL.`);
			}
			connectorConfig[field] = fieldValue;
		}

		return connectorConfig;
	}

	async function proceedToVerify() {
		error = ''; // Clear previous errors
		if (selectedProvider === 'aws') {
			currentStep = 2; // For AWS, proceed to the verification input step
		} else if (selectedProvider === 'azure') {
			if (!azureTenantId || !azureSubscriptionId || !azureClientId) {
				error = 'Please enter Tenant ID, Subscription ID, and Client ID';
				return;
			}
			isVerifying = true;
			try {
				const token = await getAccessToken();
				if (!token) {
					throw new Error('Please log in first');
				}
				const res = await api.post(
					edgeApiPath('/settings/connections/azure'),
					{
						name: `Azure-${azureSubscriptionId.slice(0, 8)}`,
						azure_tenant_id: azureTenantId,
						subscription_id: azureSubscriptionId,
						client_id: azureClientId,
						auth_method: 'workload_identity'
					},
					{
						headers: {
							Authorization: `Bearer ${token}`
						}
					}
				);
				if (!res.ok) {
					const errData = await res.json();
					throw new Error(errData.detail || 'Failed to connect');
				}

				const connection = await res.json();

				// Explicit verify step
				const verifyRes = await api.post(
					edgeApiPath(`/settings/connections/azure/${connection.id}/verify`),
					undefined,
					{
						headers: { Authorization: `Bearer ${token}` }
					}
				);

				if (!verifyRes.ok) {
					const errData = await verifyRes.json();
					throw new Error(errData.detail || 'Verification failed');
				}

				success = true;
				currentStep = 3; // Done
			} catch (e) {
				const err = e as Error;
				error = err.message;
			} finally {
				isVerifying = false;
			}
		} else if (selectedProvider === 'gcp') {
			if (!gcpProjectId) {
				error = 'Please enter Project ID';
				return;
			}
			isVerifying = true;
			try {
				const token = await getAccessToken();
				if (!token) {
					throw new Error('Please log in first');
				}
				const res = await api.post(
					edgeApiPath('/settings/connections/gcp'),
					{
						name: `GCP-${gcpProjectId}`,
						project_id: gcpProjectId,
						billing_project_id: gcpBillingProjectId || gcpProjectId,
						billing_dataset: gcpBillingDataset,
						billing_table: gcpBillingTable,
						auth_method: 'workload_identity'
					},
					{
						headers: {
							Authorization: `Bearer ${token}`
						}
					}
				);
				if (!res.ok) {
					const errData = await res.json();
					throw new Error(errData.detail || 'Failed to connect');
				}

				const connection = await res.json();

				// Explicit verify step
				const verifyRes = await api.post(
					edgeApiPath(`/settings/connections/gcp/${connection.id}/verify`),
					undefined,
					{
						headers: { Authorization: `Bearer ${token}` }
					}
				);

				if (!verifyRes.ok) {
					const errData = await verifyRes.json();
					throw new Error(errData.detail || 'Verification failed');
				}

				success = true;
				currentStep = 3; // Done
			} catch (e) {
				const err = e as Error;
				error = err.message;
			} finally {
				isVerifying = false;
			}
		} else if (selectedProvider === 'saas' || selectedProvider === 'license') {
			if (!cloudPlusName.trim() || cloudPlusName.trim().length < 3) {
				error = 'Please enter a connection name (minimum 3 characters).';
				return;
			}
			if (!cloudPlusVendor.trim() || cloudPlusVendor.trim().length < 2) {
				error = 'Please enter a vendor name (minimum 2 characters).';
				return;
			}
			if (
				(cloudPlusAuthMethod === 'api_key' || cloudPlusAuthMethod === 'oauth') &&
				!cloudPlusApiKey.trim()
			) {
				error = 'API key / OAuth token is required for this auth method.';
				return;
			}
			isVerifying = true;
			try {
				const token = await getAccessToken();
				if (!token) {
					throw new Error('Please log in first');
				}
				const feed = parseCloudPlusFeed();
				const connectorConfig = parseCloudPlusConnectorConfig();
				const createPath = selectedProvider === 'saas' ? 'saas' : 'license';
				const payload =
					selectedProvider === 'saas'
						? {
								name: cloudPlusName.trim(),
								vendor: cloudPlusVendor.trim().toLowerCase(),
								auth_method: cloudPlusAuthMethod,
								api_key: cloudPlusApiKey.trim() || null,
								connector_config: connectorConfig,
								spend_feed: feed
							}
						: {
								name: cloudPlusName.trim(),
								vendor: cloudPlusVendor.trim().toLowerCase(),
								auth_method: cloudPlusAuthMethod,
								api_key: cloudPlusApiKey.trim() || null,
								connector_config: connectorConfig,
								license_feed: feed
							};

				const res = await api.post(edgeApiPath(`/settings/connections/${createPath}`), payload, {
					headers: {
						Authorization: `Bearer ${token}`
					}
				});
				if (!res.ok) {
					const errData = await res.json();
					throw new Error(errData.detail || 'Failed to connect');
				}

				const connection = await res.json();
				const verifyRes = await api.post(
					edgeApiPath(`/settings/connections/${createPath}/${connection.id}/verify`),
					undefined,
					{
						headers: { Authorization: `Bearer ${token}` }
					}
				);
				if (!verifyRes.ok) {
					const errData = await verifyRes.json();
					throw new Error(errData.detail || 'Verification failed');
				}
				success = true;
				currentStep = 3;
			} catch (e) {
				const err = e as Error;
				error = err.message;
			} finally {
				isVerifying = false;
			}
		}
	}

	// Verify connection (AWS specific)
	async function verifyConnection() {
		if (!roleArn || !awsAccountId) {
			error = 'Please enter both AWS Account ID and Role ARN';
			return;
		}

		isVerifying = true;
		error = '';

		try {
			// 1. Ensure user is in our DB (Fixes 403 Forbidden)
			const onboarded = await ensureOnboarded();
			if (!onboarded) {
				isVerifying = false;
				return;
			}

			// 2. Get the access token from Supabase session
			const token = await getAccessToken();

			if (!token) {
				error = 'Please log in first to verify your AWS connection';
				isVerifying = false;
				return;
			}

			const createRes = await api.post(
				edgeApiPath('/settings/connections/aws'),
				{
					aws_account_id: awsAccountId,
					role_arn: roleArn,
					external_id: externalId, // Pass the SAME external_id from step 1!
					is_management_account: isManagementAccount,
					organization_id: organizationId,
					region: 'us-east-1'
				},
				{
					headers: {
						Authorization: `Bearer ${token}`
					}
				}
			);

			if (!createRes.ok) {
				const errData = await createRes.json();
				throw new Error(errData.detail || 'Failed to create connection');
			}

			const connection = await createRes.json();

			const verifyRes = await api.post(
				edgeApiPath(`/settings/connections/aws/${connection.id}/verify`),
				undefined,
				{
					headers: { Authorization: `Bearer ${token}` }
				}
			);

			if (!verifyRes.ok) {
				const errData = await verifyRes.json();
				throw new Error(errData.detail || 'Verification failed');
			}

			success = true;
			currentStep = 3;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Unknown error';
		} finally {
			isVerifying = false;
		}
	}
</script>

<svelte:head>
	<title>Onboarding | Valdrics</title>
</svelte:head>

<AuthGate authenticated={!!data.user} action="connect providers">
	<div class="onboarding-container">
		<h1>🔗 Connect Cloud & Cloud+ Providers</h1>

		<!-- Progress indicator -->
		<div class="progress-steps">
			<div class="step" class:active={currentStep === 0} class:complete={currentStep > 0}>
				1. Choose Cloud
			</div>
			<div class="step" class:active={currentStep === 1} class:complete={currentStep > 1}>
				2. Configure
			</div>
			<div class="step" class:active={currentStep === 2} class:complete={currentStep > 2}>
				3. Verify
			</div>
			<div class="step" class:active={currentStep === 3}>4. Done!</div>
		</div>

		{#if isLoading}
			<div class="loading-overlay">
				<div class="spinner mb-4"></div>
				<p class="text-sm text-ink-300">Fetching configuration details...</p>
			</div>
		{/if}

		{#if error}
			<div class="error-banner">{error}</div>
		{/if}

		<!-- Step 0: Select Provider -->
		{#if currentStep === 0}
			<div class="step-content">
				<h2>Choose Your Cloud Provider</h2>
				<p class="text-muted mb-8">
					Valdrics uses read-only access to analyze your infrastructure and find waste.
				</p>

				<div class="provider-grid">
					<button
						class="provider-card"
						class:selected={selectedProvider === 'aws'}
						onclick={() => (selectedProvider = 'aws')}
					>
						<div class="logo-circle">
							<CloudLogo provider="aws" size={32} />
						</div>
						<h3>Amazon Web Services</h3>
						<p>Standard across all tiers</p>
					</button>

					<button
						class="provider-card"
						class:selected={selectedProvider === 'azure'}
						onclick={() => (selectedProvider = 'azure')}
					>
						<div class="logo-circle">
							<CloudLogo provider="azure" size={32} />
						</div>
						<h3>Microsoft Azure</h3>
						<span class="badge">Growth Tier+</span>
					</button>

					<button
						class="provider-card"
						class:selected={selectedProvider === 'gcp'}
						onclick={() => (selectedProvider = 'gcp')}
					>
						<div class="logo-circle">
							<CloudLogo provider="gcp" size={32} />
						</div>
						<h3>Google Cloud</h3>
						<span class="badge">Growth Tier+</span>
					</button>

					<button
						class="provider-card"
						class:selected={selectedProvider === 'saas'}
						onclick={() => (selectedProvider = 'saas')}
					>
						<div class="logo-circle">
							<CloudLogo provider="saas" size={32} />
						</div>
						<h3>SaaS Spend Connector</h3>
						<span class="badge">Pro Tier+</span>
					</button>

					<button
						class="provider-card"
						class:selected={selectedProvider === 'license'}
						onclick={() => (selectedProvider = 'license')}
					>
						<div class="logo-circle">
							<CloudLogo provider="license" size={32} />
						</div>
						<h3>License / ITAM Connector</h3>
						<span class="badge">Pro Tier+</span>
					</button>
				</div>

				<div class="discovery-panel mt-8">
					<div class="discovery-header">
						<h3>Discovery Wizard (Prefill)</h3>
						<p class="text-xs text-ink-400">
							Best-effort signals to find likely providers first, then choose what to connect.
						</p>
					</div>

					<div class="discovery-stage-a">
						<div class="form-group">
							<label for="discoveryEmail">Work Email</label>
							<input
								type="email"
								id="discoveryEmail"
								bind:value={discoveryEmail}
								placeholder="you@company.com"
							/>
						</div>
						<div class="discovery-actions">
							<button
								type="button"
								class="secondary-btn !w-auto px-4"
								onclick={runDiscoveryStageA}
								disabled={discoveryLoadingStageA || isLoading}
							>
								{discoveryLoadingStageA ? '⏳ Running Stage A...' : 'Run Stage A'}
							</button>
							{#if discoveryDomain}
								<span class="text-xs text-ink-400">Domain: {discoveryDomain}</span>
							{/if}
						</div>
					</div>

					<div class="discovery-stage-b">
						<div class="form-group">
							<label for="idpProvider">IdP Deep Scan (Stage B)</label>
							<select id="idpProvider" bind:value={discoveryIdpProvider}>
								<option value="microsoft_365">microsoft_365</option>
								<option value="google_workspace">google_workspace</option>
							</select>
						</div>
						<div class="discovery-actions">
							<button
								type="button"
								class="secondary-btn !w-auto px-4"
								onclick={runDiscoveryStageB}
								disabled={discoveryLoadingStageB || isLoading || !canUseIdpDeepScan()}
							>
								{discoveryLoadingStageB ? '⏳ Running Stage B...' : 'Run Stage B'}
							</button>
							{#if !canUseIdpDeepScan()}
								<span class="text-xs text-ink-500">Pro tier required</span>
							{/if}
						</div>
					</div>

					{#if discoveryError}
						<p class="discovery-error">{discoveryError}</p>
					{/if}
					{#if discoveryInfo}
						<p class="discovery-info">{discoveryInfo}</p>
					{/if}
					{#if discoveryWarnings.length > 0}
						<div class="discovery-warnings">
							<p class="text-xs text-ink-400 mb-2">Warnings</p>
							<ul>
								{#each discoveryWarnings.slice(0, 3) as warning (warning)}
									<li>{warning}</li>
								{/each}
							</ul>
						</div>
					{/if}

					{#if discoveryCandidates.length > 0}
						<div class="candidate-list">
							{#each discoveryCandidates as candidate (candidate.id)}
								<div class="candidate-row">
									<div class="candidate-main">
										<div class="candidate-title">
											<strong>{candidate.provider}</strong>
											<span class="candidate-pill"
												>{getDiscoveryCategoryLabel(candidate.category)}</span
											>
											<span class="candidate-pill status">{candidate.status}</span>
										</div>
										<p class="candidate-meta">
											Confidence: {formatDiscoveryConfidence(candidate.confidence_score)} · Source:
											{candidate.source}
											{#if candidate.connection_target}
												· Target: {candidate.connection_target}
											{/if}
										</p>
									</div>
									<div class="candidate-actions">
										<button
											type="button"
											class="secondary-btn !w-auto px-3 py-1.5 text-xs"
											onclick={() => connectDiscoveryCandidate(candidate)}
											disabled={discoveryActionCandidateId === candidate.id ||
												candidate.status === 'connected'}
										>
											{candidate.status === 'connected' ? 'Connected' : 'Connect'}
										</button>
										<button
											type="button"
											class="secondary-btn !w-auto px-3 py-1.5 text-xs"
											onclick={() => ignoreDiscoveryCandidate(candidate)}
											disabled={discoveryActionCandidateId === candidate.id ||
												candidate.status === 'ignored'}
										>
											Ignore
										</button>
										<button
											type="button"
											class="secondary-btn !w-auto px-3 py-1.5 text-xs"
											onclick={() => markDiscoveryCandidateConnected(candidate)}
											disabled={discoveryActionCandidateId === candidate.id ||
												candidate.status === 'connected'}
										>
											Mark Connected
										</button>
									</div>
								</div>
							{/each}
						</div>
					{/if}
				</div>

				{#if (selectedProvider === 'azure' || selectedProvider === 'gcp') && !canUseGrowthFeatures()}
					<a href={`${base}/billing`} class="primary-btn mt-8">Upgrade to Growth →</a>
				{:else if (selectedProvider === 'saas' || selectedProvider === 'license') && !canUseCloudPlusFeatures()}
					<a href={`${base}/billing`} class="primary-btn mt-8">Upgrade to Pro →</a>
				{:else}
					<button class="primary-btn mt-8" onclick={handleContinueToSetup}
						>Continue to Setup →</button
					>
				{/if}
			</div>
		{/if}

		<!-- Step 1: Configuration -->
		{#if currentStep === 1}
			<div class="step-content">
				{#if selectedProvider === 'aws'}
					<h2>Step 2: Connect AWS Account</h2>
					<p class="mb-6">We've generated a secure IAM role template for your account.</p>

					{#if magicLink}
						<!-- Innovation: Magic Link -->
						<div
							class="magic-link-box p-6 bg-accent-950/20 border border-accent-500/30 rounded-2xl mb-8 flex flex-col items-center gap-4"
						>
							<div class="text-3xl">🧩</div>
							<div class="text-center">
								<h4 class="font-bold text-lg mb-1">Recommended: 1-Click Setup</h4>
								<p class="text-sm text-ink-400">
									Launch a CloudFormation stack with all parameters pre-filled.
								</p>
							</div>
							<a
								href={magicLink}
								target="_blank"
								rel="noopener noreferrer"
								class="primary-btn !w-auto px-8 py-3 bg-accent-500 hover:bg-accent-600"
							>
								⚡ Launch AWS Stack
							</a>
						</div>

						<div class="divider text-xs text-ink-500 mb-6 flex items-center gap-4">
							<div class="h-px flex-1 bg-ink-800"></div>
							OR USE MANUAL TEMPLATES
							<div class="h-px flex-1 bg-ink-800"></div>
						</div>
					{/if}

					<!-- Manual Templates (Old Flow) -->
					<div class="tab-selector">
						<button
							class="tab"
							class:active={selectedTab === 'cloudformation'}
							onclick={() => (selectedTab = 'cloudformation')}
						>
							☁️ CloudFormation
						</button>
						<button
							class="tab"
							class:active={selectedTab === 'terraform'}
							onclick={() => (selectedTab = 'terraform')}
						>
							🏗️ Terraform
						</button>
					</div>

					<div class="manual-guide mb-8">
						<h4 class="font-bold text-ink-100 flex items-center gap-2 mb-4">
							<span class="text-accent-500">🛡️</span> Security & Deployment Guide
						</h4>

						<div class="space-y-3">
							<div
								class="flex items-start gap-4 p-4 bg-ink-900 border border-ink-800 rounded-xl transition-all hover:border-ink-700"
							>
								<div
									class="flex-shrink-0 w-8 h-8 rounded-lg bg-accent-500/10 flex items-center justify-center text-accent-500 font-bold"
								>
									1
								</div>
								<div>
									<p class="text-sm font-semibold text-ink-100 mb-1">
										Acquire Infrastructure Template
									</p>
									<p class="text-xs text-ink-400">
										Select either CloudFormation or Terraform below. Use the <strong>Copy</strong>
										or
										<strong>Download</strong> buttons to save the configuration file to your local machine.
									</p>
								</div>
							</div>

							<div
								class="flex items-start gap-4 p-4 bg-ink-900 border border-ink-800 rounded-xl transition-all hover:border-ink-700"
							>
								<div
									class="flex-shrink-0 w-8 h-8 rounded-lg bg-accent-500/10 flex items-center justify-center text-accent-500 font-bold"
								>
									2
								</div>
								<div>
									<p class="text-sm font-semibold text-ink-100 mb-1">Provision Resources in AWS</p>
									<p class="text-xs text-ink-400">
										Navigate to the <a
											href="https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/create/template"
											target="_blank"
											rel="noopener noreferrer"
											class="text-accent-400 hover:text-accent-300 underline underline-offset-4 decoration-accent-500/30"
											>AWS CloudFormation Console</a
										>. Select <strong>Create Stack</strong> and choose
										<strong>Upload a template file</strong> to begin the deployment.
									</p>
								</div>
							</div>

							<div
								class="flex items-start gap-4 p-4 bg-ink-900 border border-ink-800 rounded-xl transition-all hover:border-ink-700"
							>
								<div
									class="flex-shrink-0 w-8 h-8 rounded-lg bg-accent-500/10 flex items-center justify-center text-accent-500 font-bold"
								>
									3
								</div>
								<div>
									<p class="text-sm font-semibold text-ink-100 mb-1">
										Finalize Deployment & Capture ARN
									</p>
									<p class="text-xs text-ink-400">
										Follow the AWS wizard. Once the stack status is <strong>CREATE_COMPLETE</strong
										>, navigate to the <strong>Outputs</strong> tab to find and copy your new
										<strong>RoleArn</strong>.
									</p>
								</div>
							</div>

							<div
								class="flex items-start gap-4 p-4 bg-ink-900 border border-ink-800 rounded-xl transition-all hover:border-ink-700"
							>
								<div
									class="flex-shrink-0 w-8 h-8 rounded-lg bg-accent-500/10 flex items-center justify-center text-accent-500 font-bold"
								>
									4
								</div>
								<div>
									<p class="text-sm font-semibold text-ink-100 mb-1">Verify Connection</p>
									<p class="text-xs text-ink-400">
										Return to this page and paste the captured <strong>RoleArn</strong> into the verification
										field in Step 3 to activate your connection.
									</p>
								</div>
							</div>
						</div>
					</div>

					<div class="code-container">
						<div class="code-header">
							<span
								>{selectedTab === 'cloudformation' ? 'valdrix-role.yaml' : 'valdrix-role.tf'}</span
							>
							<div class="code-actions">
								<button class="icon-btn" onclick={copyTemplate}>{copied ? '✅' : '📋 Copy'}</button>
								<button class="icon-btn" onclick={downloadTemplate}>📥</button>
							</div>
						</div>
						<pre class="code-block">{selectedTab === 'cloudformation'
								? cloudformationYaml
								: terraformHcl}</pre>
					</div>

					<div class="divider text-xs text-ink-500 my-8 flex items-center gap-4">
						<div class="h-px flex-1 bg-ink-800"></div>
						STEP 3: VERIFY CONNECTION
						<div class="h-px flex-1 bg-ink-800"></div>
					</div>

					<div class="verification-section p-6 bg-ink-900 border border-ink-800 rounded-2xl mb-8">
						<div class="form-group">
							<label for="accountId">AWS Account ID (12 digits)</label>
							<input
								type="text"
								id="accountId"
								bind:value={awsAccountId}
								placeholder="123456789012"
								maxlength="12"
								class="input"
							/>
						</div>

						<div class="form-group">
							<label for="roleArn">Role ARN (from CloudFormation Outputs)</label>
							<input
								type="text"
								id="roleArn"
								bind:value={roleArn}
								placeholder="arn:aws:iam::123456789012:role/ValdrixReadOnly"
								class="input"
							/>
						</div>

						<div
							class="form-group pt-4 border-t border-ink-800 relative mt-4"
							class:opacity-50={!['growth', 'pro', 'enterprise'].includes(data?.subscription?.tier)}
						>
							<label class="flex items-center justify-between gap-3 cursor-pointer">
								<div class="flex items-center gap-3">
									<input
										type="checkbox"
										bind:checked={isManagementAccount}
										class="toggle"
										disabled={!['growth', 'pro', 'enterprise'].includes(data?.subscription?.tier)}
									/>
									<span class="font-bold">Register as Management Account</span>
								</div>
								{#if !['growth', 'pro', 'enterprise'].includes(data?.subscription?.tier)}
									<span class="badge badge-warning text-[10px]">Growth Tier +</span>
								{/if}
							</label>
							<p class="text-xs text-ink-500 mt-2">
								Enable this if this account is the Management Account of an AWS Organization.
								Valdrics may discover likely member accounts and prefill linking suggestions for
								review when organization permissions allow.
							</p>
						</div>

						{#if isManagementAccount}
							<div class="form-group stagger-enter mt-4">
								<label for="org_id">Organization ID (Optional)</label>
								<input
									type="text"
									id="org_id"
									bind:value={organizationId}
									placeholder="o-xxxxxxxxxx"
									class="input"
								/>
							</div>
						{/if}
					</div>
				{:else if selectedProvider === 'azure'}
					<!-- ... existing azure code ... -->
					<h2>Step 2: Connect Microsoft Azure</h2>
					<p class="mb-6">
						Connect using <strong>Workload Identity Federation</strong> (Zero-Secret).
					</p>

					<div class="space-y-4 mb-8">
						<div class="form-group">
							<label for="azTenant">Azure Tenant ID</label>
							<input
								type="text"
								id="azTenant"
								bind:value={azureTenantId}
								placeholder="00000000-0000-0000-0000-000000000000"
							/>
						</div>
						<div class="form-group">
							<label for="azSub">Subscription ID</label>
							<input
								type="text"
								id="azSub"
								bind:value={azureSubscriptionId}
								placeholder="00000000-0000-0000-0000-000000000000"
							/>
						</div>
						<div class="form-group">
							<label for="azClient">Application (Client) ID</label>
							<input
								type="text"
								id="azClient"
								bind:value={azureClientId}
								placeholder="00000000-0000-0000-0000-000000000000"
							/>
						</div>
					</div>

					<div class="info-box mb-6">
						<h4 class="text-sm font-bold mb-2">🚀 Magic Snippet</h4>
						<p class="text-xs text-ink-400 mb-3">
							Copy and paste this into your Azure Cloud Shell to establish trust.
						</p>
						<div class="bg-black/50 p-3 rounded font-mono text-xs break-all text-green-400">
							{cloudShellSnippet ||
								'# Establishing Workload Identity Trust... (Wait for initialization)'}
						</div>
					</div>
				{:else if selectedProvider === 'gcp'}
					<h2>Step 2: Connect Google Cloud</h2>
					<p class="mb-6">Connect using <strong>Identity Federation</strong>.</p>

					<div class="form-group mb-5">
						<label for="gcpProject">GCP Project ID</label>
						<input
							type="text"
							id="gcpProject"
							bind:value={gcpProjectId}
							placeholder="my-awesome-project"
						/>
					</div>

					<div class="p-4 rounded-xl bg-ink-900 border border-ink-800 mb-8">
						<h4 class="text-xs font-bold text-accent-400 uppercase tracking-wider mb-4">
							BigQuery Cost Export (Required for FinOps)
						</h4>
						<div class="space-y-4">
							<div class="form-group">
								<label for="gcpBillingProject">Billing Data Project ID (Optional)</label>
								<input
									type="text"
									id="gcpBillingProject"
									bind:value={gcpBillingProjectId}
									placeholder={gcpProjectId || 'GCP Project ID'}
								/>
								<p class="text-[10px] text-ink-500">
									Project where the BigQuery dataset resides (defaults to the project ID above).
								</p>
							</div>
							<div class="form-group">
								<label for="gcpBillingDataset">BigQuery Dataset ID</label>
								<input
									type="text"
									id="gcpBillingDataset"
									bind:value={gcpBillingDataset}
									placeholder="billing_dataset"
								/>
							</div>
							<div class="form-group">
								<label for="gcpBillingTable">BigQuery Table ID</label>
								<input
									type="text"
									id="gcpBillingTable"
									bind:value={gcpBillingTable}
									placeholder="gcp_billing_export_resource_v1_..."
								/>
							</div>
						</div>
					</div>

					<div class="info-box mb-6">
						<h4 class="text-sm font-bold mb-2">🚀 Magic Snippet</h4>
						<p class="text-xs text-ink-400 mb-3">Run this gcloud command in your GCP Console.</p>
						<div class="bg-black/50 p-3 rounded font-mono text-xs break-all text-yellow-400">
							{cloudShellSnippet ||
								'# Establishing Workload Identity Trust... (Wait for initialization)'}
						</div>
					</div>
				{:else if selectedProvider === 'saas' || selectedProvider === 'license'}
					<h2>Step 2: Connect {selectedProvider === 'saas' ? 'SaaS' : 'License / ITAM'} Spend</h2>
					<p class="mb-6">
						Configure a Cloud+ connector using API key or manual/CSV feed ingestion.
					</p>

					<div class="space-y-4 mb-8">
						{#if cloudPlusNativeConnectors.length > 0}
							<div class="info-box mb-4">
								<h4 class="text-sm font-bold mb-2">🔌 Native Connectors</h4>
								<p class="text-xs text-ink-400 mb-3">
									Choose a supported vendor to auto-configure recommended auth and required fields.
								</p>
								<div class="flex flex-wrap gap-2">
									{#each cloudPlusNativeConnectors as connector (connector.vendor)}
										<button
											type="button"
											class="secondary-btn !w-auto px-3 py-1.5 text-xs"
											class:opacity-70={cloudPlusVendor.trim().toLowerCase() !== connector.vendor}
											onclick={() => chooseNativeCloudPlusVendor(connector.vendor)}
										>
											{connector.display_name}
										</button>
									{/each}
								</div>
							</div>
						{/if}

						<div class="form-group">
							<label for="cloudPlusName">Connection Name</label>
							<input
								type="text"
								id="cloudPlusName"
								bind:value={cloudPlusName}
								placeholder={selectedProvider === 'saas'
									? 'Salesforce Spend Feed'
									: 'Microsoft 365 Seats'}
							/>
						</div>
						<div class="form-group">
							<label for="cloudPlusVendor">Vendor</label>
							<input
								type="text"
								id="cloudPlusVendor"
								bind:value={cloudPlusVendor}
								onchange={handleCloudPlusVendorInputChanged}
								placeholder={selectedProvider === 'saas' ? 'salesforce' : 'microsoft'}
							/>
						</div>
						<div class="form-group">
							<label for="cloudPlusAuthMethod">Auth Method</label>
							<select
								id="cloudPlusAuthMethod"
								bind:value={cloudPlusAuthMethod}
								onchange={handleCloudPlusAuthMethodChanged}
							>
								{#each getAvailableCloudPlusAuthMethods() as authMethod (authMethod)}
									<option value={authMethod}>{authMethod}</option>
								{/each}
							</select>
						</div>
						{#if cloudPlusAuthMethod === 'api_key' || cloudPlusAuthMethod === 'oauth'}
							<div class="form-group">
								<label for="cloudPlusApiKey">API Key / OAuth Token</label>
								<input
									type="password"
									id="cloudPlusApiKey"
									bind:value={cloudPlusApiKey}
									placeholder="Paste vendor API key or OAuth access token"
								/>
							</div>
						{/if}

						{#if isCloudPlusNativeAuthMethod() && getSelectedNativeConnector()?.required_connector_config_fields?.length}
							<div class="info-box">
								<h4 class="text-sm font-bold mb-2">⚙️ Required Connector Fields</h4>
								<p class="text-xs text-ink-400 mb-3">
									These fields are required for {getSelectedNativeConnector()?.display_name} native mode.
								</p>
								<div class="space-y-3">
									{#each getSelectedNativeConnector()?.required_connector_config_fields ?? [] as field (field)}
										<div class="form-group">
											<label for={`cfg-${field}`}>connector_config.{field}</label>
											<input
												type="text"
												id={`cfg-${field}`}
												value={getRequiredConfigFieldValue(field)}
												oninput={(event) =>
													setRequiredConfigField(
														field,
														(event.currentTarget as HTMLInputElement).value
													)}
												placeholder={field === 'instance_url'
													? 'https://your-org.my.salesforce.com'
													: `Enter ${field}`}
											/>
										</div>
									{/each}
								</div>
							</div>
						{/if}
					</div>

					<div class="info-box mb-6">
						<h4 class="text-sm font-bold mb-2">📘 Setup Snippet</h4>
						<p class="text-xs text-ink-400 mb-3">Use this as your setup guide and feed template.</p>
						<div
							class="bg-black/50 p-3 rounded font-mono text-xs whitespace-pre-wrap break-all text-accent-300"
						>
							{cloudShellSnippet || '# Cloud+ setup snippet is loading...'}
						</div>
					</div>

					<div class="info-box mb-6">
						<h4 class="text-sm font-bold mb-2">🧩 Connector Config JSON (Optional)</h4>
						<p class="text-xs text-ink-400 mb-3">
							Add non-secret vendor options to <code>connector_config</code> (required fields above are
							merged automatically).
						</p>
						{#if getSelectedNativeConnector()?.optional_connector_config_fields?.length}
							<p class="text-[11px] text-ink-500 mb-3">
								Optional keys: {getSelectedNativeConnector()?.optional_connector_config_fields.join(
									', '
								)}
							</p>
						{/if}
						<textarea
							rows="5"
							class="input font-mono text-xs"
							bind:value={cloudPlusConnectorConfigInput}
							placeholder={selectedProvider === 'license' ? '{"default_seat_price_usd": 36}' : '{}'}
						></textarea>
					</div>

					<div class="info-box mb-6">
						<h4 class="text-sm font-bold mb-2">🧾 Feed JSON (Optional)</h4>
						<p class="text-xs text-ink-400 mb-3">
							Provide an initial feed payload to validate ingestion immediately.
						</p>
						{#if cloudPlusManualFeedSchema.required_fields.length > 0}
							<p class="text-[11px] text-ink-500 mb-3">
								Required feed keys: {cloudPlusManualFeedSchema.required_fields.join(', ')}
							</p>
						{/if}
						<textarea
							rows="10"
							class="input font-mono text-xs"
							bind:value={cloudPlusFeedInput}
							placeholder={cloudPlusSampleFeed || '[]'}
						></textarea>
					</div>
				{/if}

				<div class="flex gap-4 mt-8">
					<button class="secondary-btn !w-auto px-6" onclick={() => (currentStep = 0)}
						>← Back</button
					>
					{#if selectedProvider === 'aws'}
						<button class="primary-btn !flex-1" onclick={verifyConnection} disabled={isVerifying}>
							{isVerifying ? '⏳ Verifying...' : '✅ Verify Connection'}
						</button>
					{:else}
						<button class="primary-btn !flex-1" onclick={proceedToVerify} disabled={isVerifying}>
							{#if isVerifying}
								⏳ Verifying...
							{:else if selectedProvider === 'saas' || selectedProvider === 'license'}
								✅ Create & Verify Connector
							{:else}
								Next: Verify Connection →
							{/if}
						</button>
					{/if}
				</div>
			</div>
		{/if}

		<!-- Step 2: Verify -->
		{#if currentStep === 2}
			<div class="step-content">
				<h2>Step 2: Verify Your Connection</h2>
				<p>Enter the details from your AWS CloudFormation stack outputs.</p>

				<div class="form-group">
					<label for="accountId">AWS Account ID (12 digits)</label>
					<input
						type="text"
						id="accountId"
						bind:value={awsAccountId}
						placeholder="123456789012"
						maxlength="12"
					/>
				</div>

				<div class="form-group">
					<label for="roleArn">Role ARN (from CloudFormation Outputs)</label>
					<input
						type="text"
						id="roleArn"
						bind:value={roleArn}
						placeholder="arn:aws:iam::123456789012:role/ValdrixReadOnly"
					/>
				</div>

				<div
					class="form-group pt-4 border-t border-ink-800 relative"
					class:opacity-50={!['growth', 'pro', 'enterprise'].includes(data?.subscription?.tier)}
				>
					<label class="flex items-center justify-between gap-3 cursor-pointer">
						<div class="flex items-center gap-3">
							<input
								type="checkbox"
								bind:checked={isManagementAccount}
								class="toggle"
								disabled={!['growth', 'pro', 'enterprise'].includes(data?.subscription?.tier)}
							/>
							<span class="font-bold">Register as Management Account</span>
						</div>
						{#if !['growth', 'pro', 'enterprise'].includes(data?.subscription?.tier)}
							<span class="badge badge-warning text-[10px]">Growth Tier +</span>
						{/if}
					</label>
					<p class="text-xs text-ink-500 mt-2">
						Enable this if this account is the Management Account of an AWS Organization. Valdrics
						may discover likely member accounts and prefill linking suggestions for review when
						organization permissions allow.
					</p>
					{#if !['growth', 'pro', 'enterprise'].includes(data?.subscription?.tier)}
						<p class="text-[10px] text-accent-400 mt-1">
							⚡ Multi-account discovery requires Growth tier or higher.
						</p>
					{/if}
				</div>

				{#if isManagementAccount}
					<div class="form-group stagger-enter">
						<label for="org_id">Organization ID (Optional)</label>
						<input
							type="text"
							id="org_id"
							bind:value={organizationId}
							placeholder="o-xxxxxxxxxx"
							class="input"
						/>
					</div>
				{/if}

				<button class="primary-btn" onclick={verifyConnection} disabled={isVerifying}>
					{isVerifying ? '⏳ Verifying...' : '✅ Verify Connection'}
				</button>

				<button class="secondary-btn" onclick={() => (currentStep = 1)}>
					← Back to Template
				</button>
			</div>
		{/if}

		<!-- Step 3: Success -->
		{#if currentStep === 3 && success}
			<div class="step-content success">
				<div class="success-icon">🎉</div>
				<h2>Connection Successful!</h2>
				<p>
					Valdrics can now analyze your {getProviderLabel(selectedProvider)} spend and include it in Cloud+
					optimization workflows.
				</p>

				<a href={`${base}/`} class="primary-btn"> Go to Dashboard → </a>
			</div>
		{/if}
	</div>
</AuthGate>

<style>
	.onboarding-container {
		max-width: 900px;
		margin: 2rem auto;
		padding: 2rem;
	}

	/* Provider Selector */
	.provider-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
		gap: 1.5rem;
		margin-top: 2rem;
	}

	.discovery-panel {
		margin-top: 2rem;
		padding: 1.25rem;
		border: 1px solid var(--border, #333);
		border-radius: 12px;
		background: var(--bg-secondary, #0f0f1a);
	}

	.discovery-header {
		display: flex;
		flex-wrap: wrap;
		align-items: flex-start;
		justify-content: space-between;
		gap: 0.5rem 1rem;
	}

	.discovery-stage-a,
	.discovery-stage-b {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		align-items: end;
		gap: 0.75rem;
		margin-top: 0.75rem;
	}

	.discovery-actions {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 0.4rem;
		min-width: 180px;
	}

	.discovery-error {
		margin-top: 0.75rem;
		padding: 0.65rem 0.8rem;
		border-radius: 8px;
		border: 1px solid #f43f5e66;
		background: #f43f5e14;
		color: #fda4af;
		font-size: 0.82rem;
	}

	.discovery-info {
		margin-top: 0.75rem;
		padding: 0.65rem 0.8rem;
		border-radius: 8px;
		border: 1px solid #22c55e66;
		background: #22c55e14;
		color: #86efac;
		font-size: 0.82rem;
	}

	.discovery-warnings {
		margin-top: 0.75rem;
		padding: 0.75rem 0.85rem;
		border-radius: 8px;
		border: 1px solid #f59e0b55;
		background: #f59e0b14;
	}

	.discovery-warnings ul {
		margin: 0;
		padding-left: 1rem;
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
		font-size: 0.78rem;
		color: #fcd34d;
	}

	.candidate-list {
		display: flex;
		flex-direction: column;
		gap: 0.6rem;
		margin-top: 0.9rem;
	}

	.candidate-row {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 0.9rem;
		padding: 0.75rem;
		border: 1px solid var(--border, #333);
		border-radius: 10px;
		background: rgba(255, 255, 255, 0.02);
	}

	.candidate-main {
		min-width: 0;
	}

	.candidate-title {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.35rem;
	}

	.candidate-pill {
		display: inline-flex;
		align-items: center;
		padding: 0.1rem 0.45rem;
		border-radius: 999px;
		border: 1px solid var(--border, #333);
		background: var(--card-bg, #1a1a2e);
		color: var(--text-muted, #888);
		font-size: 0.67rem;
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}

	.candidate-pill.status {
		text-transform: capitalize;
	}

	.candidate-meta {
		margin: 0.2rem 0 0;
		font-size: 0.76rem;
		color: var(--text-muted, #888);
	}

	.candidate-actions {
		display: flex;
		flex-wrap: wrap;
		justify-content: flex-end;
		gap: 0.4rem;
	}

	.provider-card {
		background: var(--card-bg, #1a1a2e);
		border: 1px solid var(--border, #333);
		border-radius: 16px;
		padding: 2rem;
		text-align: center;
		cursor: pointer;
		transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
		position: relative;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 1rem;
		width: 100%;
	}

	.provider-card:hover {
		border-color: var(--primary, #6366f1);
		transform: translateY(-5px);
		box-shadow: 0 12px 24px rgba(0, 0, 0, 0.4);
	}

	.loading-overlay {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		background: rgba(10, 13, 18, 0.8);
		backdrop-filter: blur(8px);
		z-index: 100;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		animation: fadeIn 0.3s ease-out;
	}

	.verification-section {
		animation: slideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1);
	}

	@keyframes fadeIn {
		from {
			opacity: 0;
		}
		to {
			opacity: 1;
		}
	}

	@keyframes slideUp {
		from {
			opacity: 0;
			transform: translateY(20px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	.spinner {
		width: 40px;
		height: 40px;
		border: 3px solid var(--ink-800);
		border-top-color: var(--accent-500);
		border-radius: 50%;
		animation: spin 1s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	.provider-card.selected {
		border-color: var(--primary, #6366f1);
		background: rgba(99, 102, 241, 0.05);
		box-shadow: 0 0 0 2px var(--primary, #6366f1);
	}

	.logo-circle {
		width: 64px;
		height: 64px;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 12px;
		margin-bottom: 0.5rem;
	}

	.provider-card h3 {
		font-size: 1.1rem;
		font-weight: 600;
	}

	.provider-card p {
		font-size: 0.85rem;
		color: var(--text-muted, #888);
	}

	.provider-card .badge {
		position: absolute;
		top: 1rem;
		right: 1rem;
		background: rgba(99, 102, 241, 0.1);
		color: var(--primary, #6366f1);
		font-size: 0.7rem;
		font-weight: 700;
		padding: 0.25rem 0.6rem;
		border-radius: 20px;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	h1 {
		text-align: center;
		margin-bottom: 2rem;
	}

	.progress-steps {
		display: flex;
		justify-content: space-between;
		margin-bottom: 2rem;
	}

	.step {
		flex: 1;
		text-align: center;
		padding: 0.75rem;
		background: var(--card-bg, #1a1a2e);
		border-radius: 8px;
		margin: 0 0.25rem;
		color: var(--text-muted, #888);
		font-size: 0.9rem;
	}

	.step.active {
		background: var(--primary, #6366f1);
		color: white;
	}

	.step.complete {
		background: var(--success, #10b981);
		color: white;
	}

	.step-content {
		background: var(--card-bg, #1a1a2e);
		padding: 2rem;
		border-radius: 12px;
	}

	.tab-selector {
		display: flex;
		gap: 0.5rem;
		margin-bottom: 1.5rem;
	}

	.tab {
		flex: 1;
		padding: 0.75rem;
		border: 1px solid var(--border, #333);
		background: transparent;
		color: var(--text-muted, #888);
		border-radius: 8px;
		cursor: pointer;
		transition: all 0.2s;
	}

	.tab.active {
		background: var(--primary, #6366f1);
		border-color: var(--primary, #6366f1);
		color: white;
	}

	.info-box {
		background: var(--bg-secondary, #0f0f1a);
		padding: 1rem;
		border-radius: 8px;
		margin: 1rem 0;
	}

	.code-container {
		border: 1px solid var(--border, #333);
		border-radius: 8px;
		overflow: hidden;
		margin: 1rem 0;
	}

	.code-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.5rem 1rem;
		background: var(--bg-secondary, #0f0f1a);
		border-bottom: 1px solid var(--border, #333);
	}

	.code-actions {
		display: flex;
		gap: 0.5rem;
	}

	.icon-btn {
		padding: 0.25rem 0.5rem;
		background: transparent;
		border: 1px solid var(--border, #333);
		border-radius: 4px;
		color: var(--text-muted, #888);
		cursor: pointer;
		font-size: 0.8rem;
	}

	.icon-btn:hover {
		background: var(--primary, #6366f1);
		color: white;
	}

	.code-block {
		padding: 1rem;
		margin: 0;
		background: #000;
		color: #0f0;
		font-size: 0.75rem;
		line-height: 1.4;
		overflow-x: auto;
		max-height: 300px;
		white-space: pre-wrap;
	}

	.form-group {
		margin: 1rem 0;
	}

	label {
		display: block;
		margin-bottom: 0.5rem;
		font-weight: 500;
	}

	input {
		width: 100%;
		padding: 0.75rem;
		border: 1px solid var(--border, #333);
		border-radius: 8px;
		background: var(--bg-secondary, #0f0f1a);
		color: white;
		font-size: 1rem;
	}

	.primary-btn {
		display: inline-block;
		width: 100%;
		padding: 1rem;
		background: var(--primary, #6366f1);
		color: white;
		border: none;
		border-radius: 8px;
		font-size: 1rem;
		cursor: pointer;
		text-align: center;
		text-decoration: none;
		margin-top: 1rem;
	}

	.primary-btn:hover {
		opacity: 0.9;
	}

	.primary-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.secondary-btn {
		display: block;
		width: 100%;
		padding: 0.75rem;
		background: transparent;
		color: var(--text-muted, #888);
		border: 1px solid var(--border, #333);
		border-radius: 8px;
		margin-top: 0.5rem;
		cursor: pointer;
	}

	.error-banner {
		background: #f43f5e22;
		border: 1px solid #f43f5e;
		color: #f43f5e;
		padding: 1rem;
		border-radius: 8px;
		margin-bottom: 1rem;
	}

	.success {
		text-align: center;
		padding: 3rem 2rem;
	}

	.success-icon {
		font-size: 4rem;
		margin-bottom: 1rem;
	}

	@media (max-width: 768px) {
		.onboarding-container {
			padding: 1rem;
		}

		.discovery-stage-a,
		.discovery-stage-b {
			grid-template-columns: 1fr;
		}

		.discovery-actions {
			min-width: 0;
			width: 100%;
			align-items: stretch;
		}

		.candidate-row {
			flex-direction: column;
		}

		.candidate-actions {
			justify-content: flex-start;
		}
	}
</style>
