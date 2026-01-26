<script lang="ts">
	/* eslint-disable svelte/no-navigation-without-resolve */
	import CloudLogo from '$lib/components/CloudLogo.svelte';

	let { data } = $props();

	// State management
	let currentStep = $state(0); // 0: Select Provider, 1: Setup, 2: Verify, 3: Done
	let selectedProvider: 'aws' | 'azure' | 'gcp' = $state('aws');
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

	let isLoading = $state(false);
	let isVerifying = $state(false);
	let error = $state('');
	let success = $state(false);
	let copied = $state(false);

	import { base } from '$app/paths';
	import { PUBLIC_API_URL } from '$env/static/public';

	const API_URL = PUBLIC_API_URL || 'http://localhost:8000';

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
			const res = await fetch(`${API_URL}/settings/onboard`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${token}`
				},
				body: JSON.stringify({ tenant_name: 'My Organization' })
			});

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
			const endpoint =
				selectedProvider === 'aws'
					? '/settings/connections/aws/setup'
					: selectedProvider === 'azure'
						? '/settings/connections/azure/setup'
						: '/settings/connections/gcp/setup';

			const res = await fetch(`${API_URL}${endpoint}`, {
				method: 'POST',
				headers: {
					Authorization: `Bearer ${token}`
				}
			});

			if (!res.ok) {
				const errData = await res.json();
				throw new Error(errData.detail || 'Failed to fetch setup data');
			}

			const data = await res.json();
			if (selectedProvider === 'aws') {
				externalId = data.external_id;
				magicLink = data.magic_link;
				cloudformationYaml = data.cloudformation_yaml;
				terraformHcl = data.terraform_hcl;
			} else {
				cloudShellSnippet = data.snippet;
			}
		} catch (e) {
			const err = e as Error;
			error = `Failed to initialize ${selectedProvider.toUpperCase()} setup: ${err.message}`;
		} finally {
			isLoading = false;
		}
	}

	async function handleContinueToSetup() {
		isLoading = true;
		const onboarded = await ensureOnboarded();
		if (!onboarded) {
			isLoading = false;
			return;
		}
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
				const res = await fetch(`${API_URL}/settings/connections/azure`, {
					method: 'POST',
					headers: {
						'Content-Type': 'application/json',
						Authorization: `Bearer ${token}`
					},
					body: JSON.stringify({
						name: `Azure-${azureSubscriptionId.slice(0, 8)}`,
						azure_tenant_id: azureTenantId,
						subscription_id: azureSubscriptionId,
						client_id: azureClientId,
						auth_method: 'workload_identity'
					})
				});
				if (!res.ok) {
					const errData = await res.json();
					throw new Error(errData.detail || 'Failed to connect');
				}

				const connection = await res.json();

				// Explicit verify step
				const verifyRes = await fetch(
					`${API_URL}/settings/connections/azure/${connection.id}/verify`,
					{
						method: 'POST',
						headers: { Authorization: `Bearer ${token}` }
					}
				);

				if (!verifyRes.ok) {
					const errData = await verifyRes.json();
					throw new Error(errData.detail || 'Verification failed');
				}

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
				const res = await fetch(`${API_URL}/settings/connections/gcp`, {
					method: 'POST',
					headers: {
						'Content-Type': 'application/json',
						Authorization: `Bearer ${token}`
					},
					body: JSON.stringify({
						name: `GCP-${gcpProjectId}`,
						project_id: gcpProjectId,
						billing_project_id: gcpBillingProjectId || gcpProjectId,
						billing_dataset: gcpBillingDataset,
						billing_table: gcpBillingTable,
						auth_method: 'workload_identity'
					})
				});
				if (!res.ok) {
					const errData = await res.json();
					throw new Error(errData.detail || 'Failed to connect');
				}

				const connection = await res.json();

				// Explicit verify step
				const verifyRes = await fetch(
					`${API_URL}/settings/connections/gcp/${connection.id}/verify`,
					{
						method: 'POST',
						headers: { Authorization: `Bearer ${token}` }
					}
				);

				if (!verifyRes.ok) {
					const errData = await verifyRes.json();
					throw new Error(errData.detail || 'Verification failed');
				}

				currentStep = 3; // Done
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

			const createRes = await fetch(`${API_URL}/settings/connections/aws`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${token}`
				},
				body: JSON.stringify({
					aws_account_id: awsAccountId,
					role_arn: roleArn,
					external_id: externalId, // Pass the SAME external_id from step 1!
					is_management_account: isManagementAccount,
					organization_id: organizationId,
					region: 'us-east-1'
				})
			});

			if (!createRes.ok) {
				const errData = await createRes.json();
				throw new Error(errData.detail || 'Failed to create connection');
			}

			const connection = await createRes.json();

			const verifyRes = await fetch(`${API_URL}/settings/connections/aws/${connection.id}/verify`, {
				method: 'POST',
				headers: { Authorization: `Bearer ${token}` }
			});

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

	$effect(() => {
		// This effect was likely intended to call fetchSetupData()
		// but was named getTemplates(). Correcting to fetchSetupData()
		// if that was the original intent, or removing if not needed.
		// Assuming it was meant to fetch setup data on component mount.
		if (currentStep === 1 && selectedProvider) {
			fetchSetupData();
		}
	});
</script>

<div class="onboarding-container">
	<h1>🔗 Connect Your AWS Account</h1>

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
				Valdrix uses read-only access to analyze your infrastructure and find waste.
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
					<span class="badge">Growth Tier +</span>
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
					<span class="badge">Growth Tier +</span>
				</button>
			</div>

			<button class="primary-btn mt-8" onclick={handleContinueToSetup}>
				Continue to Setup →
			</button>
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
									Select either CloudFormation or Terraform below. Use the <strong>Copy</strong> or
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
									Follow the AWS wizard. Once the stack status is <strong>CREATE_COMPLETE</strong>,
									navigate to the <strong>Outputs</strong> tab to find and copy your new
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
						<span>{selectedTab === 'cloudformation' ? 'valdrix-role.yaml' : 'valdrix-role.tf'}</span
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
						class:opacity-50={!['growth', 'pro', 'enterprise', 'trial'].includes(
							data?.subscription?.tier
						)}
					>
						<label class="flex items-center justify-between gap-3 cursor-pointer">
							<div class="flex items-center gap-3">
								<input
									type="checkbox"
									bind:checked={isManagementAccount}
									class="toggle"
									disabled={!['growth', 'pro', 'enterprise', 'trial'].includes(
										data?.subscription?.tier
									)}
								/>
								<span class="font-bold">Register as Management Account</span>
							</div>
							{#if !['growth', 'pro', 'enterprise', 'trial'].includes(data?.subscription?.tier)}
								<span class="badge badge-warning text-[10px]">Growth Tier +</span>
							{/if}
						</label>
						<p class="text-xs text-ink-500 mt-2">
							Enable this if this account is the Management Account of an AWS Organization. Valdrix
							will automatically discover and help you link member accounts.
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
						# Establishing Workload Identity Trust... (Snippet coming soon)
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
			{/if}

			<div class="flex gap-4 mt-8">
				<button class="secondary-btn !w-auto px-6" onclick={() => (currentStep = 0)}>← Back</button>
				{#if selectedProvider === 'aws'}
					<button class="primary-btn !flex-1" onclick={verifyConnection} disabled={isVerifying}>
						{isVerifying ? '⏳ Verifying...' : '✅ Verify Connection'}
					</button>
				{:else}
					<button class="primary-btn !flex-1" onclick={proceedToVerify}
						>Next: Verify Connection →</button
					>
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
				class:opacity-50={!['growth', 'pro', 'enterprise', 'trial'].includes(
					data?.subscription?.tier
				)}
			>
				<label class="flex items-center justify-between gap-3 cursor-pointer">
					<div class="flex items-center gap-3">
						<input
							type="checkbox"
							bind:checked={isManagementAccount}
							class="toggle"
							disabled={!['growth', 'pro', 'enterprise', 'trial'].includes(
								data?.subscription?.tier
							)}
						/>
						<span class="font-bold">Register as Management Account</span>
					</div>
					{#if !['growth', 'pro', 'enterprise', 'trial'].includes(data?.subscription?.tier)}
						<span class="badge badge-warning text-[10px]">Growth Tier +</span>
					{/if}
				</label>
				<p class="text-xs text-ink-500 mt-2">
					Enable this if this account is the Management Account of an AWS Organization. Valdrix will
					automatically discover and help you link member accounts.
				</p>
				{#if !['growth', 'pro', 'enterprise', 'trial'].includes(data?.subscription?.tier)}
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

			<button class="secondary-btn" onclick={() => (currentStep = 1)}> ← Back to Template </button>
		</div>
	{/if}

	<!-- Step 3: Success -->
	{#if currentStep === 3 && success}
		<div class="step-content success">
			<div class="success-icon">🎉</div>
			<h2>Connection Successful!</h2>
			<p>Valdrix can now analyze your AWS costs and help you save money.</p>

			<a href="{base}/" class="primary-btn"> Go to Dashboard → </a>
		</div>
	{/if}
</div>

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
		items-center: center;
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
</style>
