<!--
  Dashboard Home Page - Premium SaaS Design
  
  Features:
  - Stats cards with motion animations
  - Staggered entrance effects
  - Clean data visualization
  - Loading skeletons
-->

<script lang="ts">
	/* eslint-disable svelte/no-navigation-without-resolve */
	import { assets, base } from '$app/paths';
	import { AlertTriangle, Clock } from '@lucide/svelte';
	import { PUBLIC_API_URL } from '$env/static/public';
	import CloudLogo from '$lib/components/CloudLogo.svelte';
	import { api } from '$lib/api';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import DateRangePicker from '$lib/components/DateRangePicker.svelte';
	import ProviderSelector from '$lib/components/ProviderSelector.svelte';
	import AllocationBreakdown from '$lib/components/AllocationBreakdown.svelte';
	import StatsGrid from '$lib/components/StatsGrid.svelte';
	import UnitEconomicsCards from '$lib/components/UnitEconomicsCards.svelte';
	import SavingsHero from '$lib/components/SavingsHero.svelte';
	import FindingsTable from '$lib/components/FindingsTable.svelte';
	import GreenOpsWidget from '$lib/components/GreenOpsWidget.svelte';
	import CloudDistributionMatrix from '$lib/components/CloudDistributionMatrix.svelte';
	import ROAChart from '$lib/components/ROAChart.svelte';
	import UpgradeNotice from '$lib/components/UpgradeNotice.svelte';
	import { tierAtLeast } from '$lib/tier';

	let { data } = $props();

	let loading = $state(false); // Can be used for nav transitions
	let costs = $derived(data.costs);
	let carbon = $derived(data.carbon);
	let zombies = $derived(data.zombies);
	let analysis = $derived(data.analysis as { analysis?: string } | null);
	let allocation = $derived(data.allocation);
	let unitEconomics = $derived(data.unitEconomics);
	let freshness = $derived(data.freshness);
	let error = $derived(data.error || '');
	let startDate = $derived(data.startDate || '');
	let endDate = $derived(data.endDate || '');
	let provider = $derived(data.provider || ''); // Default to empty (All)
	let persona = $derived(String(data.profile?.persona ?? 'engineering').toLowerCase());
	let tier = $derived(data.subscription?.tier ?? 'free_trial');

	let personaTitle = $derived(
		(() => {
			switch (persona) {
				case 'finance':
					return 'Finance';
				case 'platform':
					return 'Platform';
				case 'leadership':
					return 'Leadership';
				case 'engineering':
				default:
					return 'Engineering';
			}
		})()
	);

	let personaSubtitle = $derived(
		(() => {
			switch (persona) {
				case 'finance':
					return 'Allocation coverage, unit economics, and spend drivers.';
				case 'platform':
					return 'Reliability, guardrails, and connector health.';
				case 'leadership':
					return 'Top drivers, carbon, and savings proof.';
				case 'engineering':
				default:
					return 'Waste signals, findings, and safe remediation.';
			}
		})()
	);

	const landingGridX = [...Array(13).keys()];
	const landingGridY = [...Array(9).keys()];

	// Table pagination state
	let remediating = $state<string | null>(null);
	let remediationModalOpen = $state(false);
	let remediationPreviewLoading = $state(false);
	let remediationSubmitting = $state(false);
	let remediationPreviewError = $state('');
	let remediationActionError = $state('');
	let remediationActionSuccess = $state('');

	type RemediationFinding = {
		resource_id: string;
		resource_type?: string;
		provider?: string;
		connection_id?: string;
		monthly_cost?: string | number;
		recommended_action?: string;
	};

	type RemediationPreview = {
		decision: string;
		summary: string;
		tier: string;
		rule_hits: Array<{ rule_id: string; message?: string }>;
	};

	let remediationCandidate = $state<RemediationFinding | null>(null);
	let remediationPreview = $state<RemediationPreview | null>(null);

	function deriveRemediationAction(finding: RemediationFinding): string {
		const suggested = finding.recommended_action?.toLowerCase() ?? '';
		const resourceType = finding.resource_type?.toLowerCase() ?? '';

		if (suggested.includes('delete')) {
			if (resourceType.includes('snapshot')) return 'delete_snapshot';
			if (resourceType.includes('ecr')) return 'delete_ecr_image';
			if (resourceType.includes('sagemaker')) return 'delete_sagemaker_endpoint';
			if (resourceType.includes('redshift')) return 'delete_redshift_cluster';
			if (resourceType.includes('nat')) return 'delete_nat_gateway';
			if (resourceType.includes('load balancer')) return 'delete_load_balancer';
			if (resourceType.includes('s3')) return 'delete_s3_bucket';
			if (resourceType.includes('rds')) return 'delete_rds_instance';
			return 'delete_volume';
		}

		if (resourceType.includes('elastic ip') || resourceType.includes('eip')) {
			return 'release_elastic_ip';
		}
		if (resourceType.includes('rds')) {
			return 'stop_rds_instance';
		}
		return 'stop_instance';
	}

	function parseMonthlyCost(value: string | number | undefined): number {
		if (typeof value === 'number') return value;
		return Number.parseFloat(String(value ?? '0').replace(/[^0-9.-]/g, '')) || 0;
	}

	function policyDecisionClass(decision: string | undefined): string {
		switch ((decision || '').toLowerCase()) {
			case 'allow':
				return 'badge badge-success';
			case 'warn':
				return 'badge badge-warning';
			case 'escalate':
				return 'badge badge-default';
			case 'block':
				return 'badge badge-error';
			default:
				return 'badge badge-default';
		}
	}

	function closeRemediationModal() {
		if (remediationSubmitting) return;
		remediationModalOpen = false;
		remediationCandidate = null;
		remediationPreview = null;
		remediationPreviewError = '';
		remediationActionError = '';
		remediationActionSuccess = '';
		remediating = null;
	}

	async function runRemediationPreview(finding: RemediationFinding) {
		const accessToken = data.session?.access_token;
		if (!accessToken) {
			remediationPreviewError = 'Not authenticated.';
			return;
		}

		remediationPreviewLoading = true;
		remediationPreviewError = '';
		remediationActionError = '';
		remediationActionSuccess = '';
		remediating = finding.resource_id;

		try {
			const headers = {
				Authorization: `Bearer ${accessToken}`,
				'Content-Type': 'application/json'
			};
			const action = deriveRemediationAction(finding);
			const previewResponse = await api.post(
				`${PUBLIC_API_URL}/zombies/policy-preview`,
				{
					resource_id: finding.resource_id,
					resource_type: finding.resource_type || 'unknown',
					provider: finding.provider || 'aws',
					action
				},
				{ headers }
			);

			if (!previewResponse.ok) {
				const payload = await previewResponse.json().catch(() => ({}));
				throw new Error(payload.detail || payload.message || 'Policy preview failed.');
			}

			remediationPreview = await previewResponse.json();
		} catch (e) {
			const err = e as Error;
			remediationPreview = null;
			remediationPreviewError = err.message || 'Policy preview failed.';
		} finally {
			remediationPreviewLoading = false;
			remediating = null;
		}
	}

	/**
	 * Open remediation modal and run deterministic policy preview.
	 */
	async function handleRemediate(finding: RemediationFinding) {
		if (remediationSubmitting || remediationPreviewLoading) return;
		remediationCandidate = finding;
		remediationModalOpen = true;
		remediationPreview = null;
		remediationPreviewError = '';
		remediationActionError = '';
		remediationActionSuccess = '';
		await runRemediationPreview(finding);
	}

	async function submitRemediationRequest() {
		if (!remediationCandidate || remediationSubmitting) return;
		if (remediationPreview?.decision?.toLowerCase() === 'block') {
			remediationActionError = 'Policy blocks this remediation request.';
			return;
		}

		const accessToken = data.session?.access_token;
		if (!accessToken) {
			remediationActionError = 'Not authenticated.';
			return;
		}

		remediationSubmitting = true;
		remediationActionError = '';
		remediationActionSuccess = '';

		try {
			const headers = {
				Authorization: `Bearer ${accessToken}`,
				'Content-Type': 'application/json'
			};
			const action = deriveRemediationAction(remediationCandidate);
			const response = await api.post(
				`${PUBLIC_API_URL}/zombies/request`,
				{
					resource_id: remediationCandidate.resource_id,
					resource_type: remediationCandidate.resource_type || 'unknown',
					provider: remediationCandidate.provider || 'aws',
					connection_id: remediationCandidate.connection_id,
					action,
					estimated_savings: parseMonthlyCost(remediationCandidate.monthly_cost),
					create_backup: true
				},
				{ headers }
			);

			if (!response.ok) {
				const payload = await response.json().catch(() => ({}));
				throw new Error(
					payload.detail ||
						payload.message ||
						(response.status === 403
							? 'Upgrade required: Auto-remediation requires Pro tier or higher.'
							: 'Failed to create remediation request.')
				);
			}

			const result = await response.json();
			const decision = remediationPreview?.decision?.toUpperCase();
			const summary = remediationPreview?.summary || '';
			remediationActionSuccess = `Request ${result.request_id} created.${
				decision ? ` Policy: ${decision}${summary ? ` - ${summary}` : ''}.` : ''
			}`;
		} catch (e) {
			const err = e as Error;
			remediationActionError = err.message || 'Failed to create remediation request.';
		} finally {
			remediationSubmitting = false;
		}
	}

	function handleDateChange(dates: { startDate: string; endDate: string }) {
		if (dates.startDate === startDate && dates.endDate === endDate) return;
		const providerQuery = provider ? `&provider=${provider}` : '';
		goto(`${base}/?start_date=${dates.startDate}&end_date=${dates.endDate}${providerQuery}`, {
			keepFocus: true,
			noScroll: true,
			replaceState: true
		});
	}

	function handleProviderChange(selectedProvider: string) {
		if (selectedProvider === provider) return;

		// Preserve date range if exists
		let query = '';
		if (startDate && endDate) {
			query = `?start_date=${startDate}&end_date=${endDate}`;
		} else {
			query = '?';
		}

		if (selectedProvider) {
			query += query === '?' ? `provider=${selectedProvider}` : `&provider=${selectedProvider}`;
		}

		goto(`${base}/${query}`, {
			keepFocus: true,
			noScroll: true,
			replaceState: true
		});
	}

	let zombieCount = $derived(
		zombies
			? Object.values(zombies).reduce((acc: number, val: unknown) => {
					return Array.isArray(val) ? acc + val.length : acc;
				}, 0)
			: 0
	);

	let analysisText = $derived(analysis?.analysis ?? '');

	// Calculate period label from dates
	let periodLabel = $derived(
		(() => {
			if (!startDate || !endDate) return 'Period';
			const start = new Date(startDate);
			const end = new Date(endDate);
			const days = Math.round((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24));
			if (days <= 7) return '7-Day';
			if (days <= 30) return '30-Day';
			if (days <= 90) return '90-Day';
			return `${days}-Day`;
		})()
	);
</script>

<svelte:head>
	{#if data.user}
		<title>Dashboard | Valdrix</title>
	{:else}
		<title>Valdrix | Cloud Cost Intelligence</title>
		<meta
			name="description"
			content="Valdrix unifies FinOps, GreenOps, and ActiveOps into a single cloud intelligence surface with policy-driven remediation and audit-ready evidence."
		/>
		<meta property="og:title" content="Valdrix | Cloud Cost Intelligence" />
		<meta
			property="og:description"
			content="Unify spend, carbon, and risk into a single signal map with policy-driven remediation and an exportable audit trail."
		/>
		<meta property="og:type" content="website" />
		<meta property="og:url" content={new URL($page.url.pathname, $page.url.origin).toString()} />
		<meta
			property="og:image"
			content={new URL(`${assets}/valdrix_icon.png`, $page.url.origin).toString()}
		/>
		<meta name="twitter:card" content="summary" />
		<meta name="twitter:title" content="Valdrix | Cloud Cost Intelligence" />
		<meta
			name="twitter:description"
			content="FinOps + GreenOps + ActiveOps with policy-driven remediation and audit-ready exports."
		/>
	{/if}
</svelte:head>

{#if !data.user}
	<!-- Public Landing -->
	<div class="landing" itemscope itemtype="https://schema.org/SoftwareApplication">
		<meta itemprop="name" content="Valdrix" />
		<meta itemprop="operatingSystem" content="Web" />
		<meta itemprop="applicationCategory" content="BusinessApplication" />
		<meta
			itemprop="description"
			content="Valdrix unifies FinOps, GreenOps, and ActiveOps into a single cloud intelligence surface with policy-driven remediation and audit-ready evidence."
		/>
		<meta itemprop="url" content={new URL($page.url.pathname, $page.url.origin).toString()} />
		<meta
			itemprop="image"
			content={new URL(`${assets}/valdrix_icon.png`, $page.url.origin).toString()}
		/>
		<section class="landing-hero">
			<div class="container mx-auto px-6 pt-10 pb-14">
				<div class="landing-hero-grid">
					<div class="landing-copy">
						<div class="landing-kicker fade-in-up" style="animation-delay: 0ms;">
							<span class="badge badge-default">2026 Beta</span>
							<span class="landing-sep" aria-hidden="true">•</span>
							<span class="landing-kicker-text">FinOps + GreenOps + ActiveOps</span>
						</div>

						<h1 class="landing-title fade-in-up" style="animation-delay: 120ms;">
							Cloud Cost Intelligence,
							<span class="landing-kinetic">operationalized</span>.
						</h1>

						<p class="landing-subtitle fade-in-up" style="animation-delay: 220ms;">
							Unify spend, carbon, and risk into a single signal map with policy-driven remediation
							and an audit trail you can export.
						</p>

						<div class="landing-cta fade-in-up" style="animation-delay: 320ms;">
							<a href={`${base}/auth/login`} class="btn btn-primary text-base px-8 py-3 pulse-glow">
								Get Started Free →
							</a>
							<a href="#features" class="btn btn-secondary text-base px-8 py-3">
								Explore Features
							</a>
							<a href="#how" class="btn btn-ghost text-base px-6 py-3"> How It Works </a>
						</div>

						<div class="landing-proof fade-in-up" style="animation-delay: 420ms;">
							<div class="landing-proof-item">
								<p class="landing-proof-k">Policy-first remediation</p>
								<p class="landing-proof-v">Deterministic previews before you click approve.</p>
							</div>
							<div class="landing-proof-item">
								<p class="landing-proof-k">Audit-ready evidence</p>
								<p class="landing-proof-v">Event types, traces, and exports for reviews.</p>
							</div>
							<div class="landing-proof-item">
								<p class="landing-proof-k">Operator UX</p>
								<p class="landing-proof-v">Queues, jobs, and a command palette for speed.</p>
							</div>
						</div>
					</div>

					<div class="landing-preview fade-in-up" style="animation-delay: 180ms;">
						<div class="glass-panel landing-preview-card">
							<div class="landing-preview-header">
								<div class="landing-preview-title">
									<span class="landing-live-dot" aria-hidden="true"></span>
									Realtime Signal Map
								</div>
								<span class="landing-preview-pill">Live</span>
							</div>

							<div
								class="signal-map"
								role="img"
								aria-label="Signal map preview: cost, carbon, and remediation"
							>
								<svg class="signal-svg" viewBox="0 0 640 420" aria-hidden="true">
									<defs>
										<linearGradient id="sigLine" x1="0" y1="0" x2="1" y2="1">
											<stop offset="0" stop-color="var(--color-accent-400)" stop-opacity="0.9" />
											<stop offset="1" stop-color="var(--color-success-400)" stop-opacity="0.7" />
										</linearGradient>
										<radialGradient id="sigGlow" cx="50%" cy="50%" r="60%">
											<stop offset="0" stop-color="var(--color-accent-400)" stop-opacity="0.35" />
											<stop offset="1" stop-color="var(--color-accent-400)" stop-opacity="0" />
										</radialGradient>
									</defs>

									<rect x="0" y="0" width="640" height="420" fill="rgba(0,0,0,0)" />
									<g class="sig-grid">
										{#each landingGridX as i (i)}
											<line x1={i * 54} y1="0" x2={i * 54} y2="420" />
										{/each}
										{#each landingGridY as i (i)}
											<line x1="0" y1={i * 52} x2="640" y2={i * 52} />
										{/each}
									</g>

									<circle cx="320" cy="210" r="150" fill="url(#sigGlow)" />

									<path
										class="sig-line"
										d="M 320 210 L 140 120 L 460 88 L 520 300"
										fill="none"
										stroke="url(#sigLine)"
										stroke-width="2"
										stroke-linecap="round"
										stroke-dasharray="6 10"
									/>

									<circle class="sig-node sig-node--center" cx="320" cy="210" r="10" />
									<circle class="sig-node sig-node--a" cx="140" cy="120" r="8" />
									<circle class="sig-node sig-node--b" cx="460" cy="88" r="8" />
									<circle class="sig-node sig-node--c" cx="520" cy="300" r="8" />
								</svg>

								<div class="signal-label signal-label--center">
									<p class="signal-label-k">Valdrix</p>
									<p class="signal-label-v">Signals</p>
								</div>
								<div class="signal-label signal-label--a">
									<p class="signal-label-k">FinOps</p>
									<p class="signal-label-v">Spend + anomalies</p>
								</div>
								<div class="signal-label signal-label--b">
									<p class="signal-label-k">GreenOps</p>
									<p class="signal-label-v">Carbon + Graviton</p>
								</div>
								<div class="signal-label signal-label--c">
									<p class="signal-label-k">ActiveOps</p>
									<p class="signal-label-v">Policy remediation</p>
								</div>
							</div>

							<div class="landing-metrics">
								<div class="landing-metric glass-card">
									<p class="landing-metric-k">Drift</p>
									<p class="landing-metric-v text-gradient">-12%</p>
									<p class="landing-metric-h">Budget trend</p>
								</div>
								<div class="landing-metric glass-card">
									<p class="landing-metric-k">Carbon</p>
									<p class="landing-metric-v text-success-400">-8%</p>
									<p class="landing-metric-h">Graviton wins</p>
								</div>
								<div class="landing-metric glass-card">
									<p class="landing-metric-k">Waste</p>
									<p class="landing-metric-v text-warning-400">14</p>
									<p class="landing-metric-h">Zombies queued</p>
								</div>
							</div>
						</div>

						<div class="landing-pills fade-in-up" style="animation-delay: 520ms;">
							<span class="badge badge-accent">💰 Cost signals</span>
							<span class="badge badge-success">🌱 Carbon intelligence</span>
							<span class="badge badge-warning">👻 Zombie remediation</span>
							<span class="badge badge-default">🧾 Audit evidence</span>
						</div>
					</div>
				</div>
			</div>
		</section>

		<section id="features" class="container mx-auto px-6 pb-20">
			<div class="landing-section-head">
				<h2 class="landing-h2">A bento of operational leverage</h2>
				<p class="landing-section-sub">
					Built for teams that want fewer dashboards, clearer decisions, and actions that leave an
					audit trail.
				</p>
			</div>

			<div class="bento-grid">
				<div class="glass-panel col-span-2">
					<h3 class="landing-h3">Cost signals that don't rot</h3>
					<p class="landing-p">
						Track spend by provider, detect anomalies, and keep a freshness signal so you know when
						to trust the numbers.
					</p>
					<div class="landing-tag-row">
						<span class="badge badge-accent">Allocation</span>
						<span class="badge badge-default">Unit economics</span>
						<span class="badge badge-default">Data quality</span>
					</div>
				</div>

				<div class="glass-panel">
					<h3 class="landing-h3">Carbon without the guilt trip</h3>
					<p class="landing-p">
						Make carbon a first-class constraint alongside cost, and spotlight Graviton
						optimization.
					</p>
					<p class="landing-mini text-ink-400">GreenOps page included.</p>
				</div>

				<div class="glass-panel row-span-2">
					<h3 class="landing-h3">Zombie detection with policy gates</h3>
					<p class="landing-p">
						Surface likely waste, preview the policy outcome, then queue approved actions for
						controlled execution.
					</p>
					<div class="landing-mini-grid">
						<div class="landing-mini-card">
							<p class="landing-mini-k">Preview</p>
							<p class="landing-mini-v">Allow / Warn / Block</p>
						</div>
						<div class="landing-mini-card">
							<p class="landing-mini-k">Queue</p>
							<p class="landing-mini-v">Approve then execute</p>
						</div>
					</div>
				</div>

				<div class="glass-panel">
					<h3 class="landing-h3">Ops Center</h3>
					<p class="landing-p">
						Jobs, queues, and strategy recommendations in a single operator surface.
					</p>
					<p class="landing-mini text-ink-400">Designed for "runbook mode".</p>
				</div>

				<div class="glass-panel">
					<h3 class="landing-h3">Audit Logs</h3>
					<p class="landing-p">
						Event types, detail views, and CSV exports to support reviews and investigations.
					</p>
					<p class="landing-mini text-ink-400">Evidence-first workflow.</p>
				</div>

				<div class="glass-panel col-span-2">
					<h3 class="landing-h3">Ship with calm guardrails</h3>
					<p class="landing-p">
						Privacy-safe UI defaults, CSRF hygiene, and a design system tuned for high-signal,
						low-noise operations.
					</p>
					<div class="landing-tag-row">
						<span class="badge badge-default">Least privilege</span>
						<span class="badge badge-default">Exportability</span>
						<span class="badge badge-default">Progressive disclosure</span>
					</div>
				</div>
			</div>
		</section>

		<section id="how" class="container mx-auto px-6 pb-20">
			<div class="landing-section-head">
				<h2 class="landing-h2">How it works</h2>
				<p class="landing-section-sub">Connect, observe, decide, then act with guardrails.</p>
			</div>

			<div class="landing-steps">
				<div class="glass-panel landing-step">
					<p class="landing-step-n">01</p>
					<h3 class="landing-h3">Connect accounts</h3>
					<p class="landing-p">
						Bring AWS, Azure, or GCP under one model and normalize the messy parts.
					</p>
				</div>
				<div class="glass-panel landing-step">
					<p class="landing-step-n">02</p>
					<h3 class="landing-h3">Generate signals</h3>
					<p class="landing-p">
						Costs, carbon, and waste analysis are turned into prioritizable findings.
					</p>
				</div>
				<div class="glass-panel landing-step">
					<p class="landing-step-n">03</p>
					<h3 class="landing-h3">Remediate safely</h3>
					<p class="landing-p">
						Policy previews, approval queues, and audit logs keep actions accountable.
					</p>
				</div>
			</div>
		</section>

		<section class="container mx-auto px-6 pb-24">
			<div class="landing-final glass-panel">
				<div>
					<h2 class="landing-h2">Turn cloud waste into a controlled operation</h2>
					<p class="landing-section-sub">
						Start free. You can stay in observation mode, or graduate to policy-driven remediation
						when you're ready.
					</p>
				</div>
				<div class="landing-final-cta">
					<a href={`${base}/auth/login`} class="btn btn-primary text-base px-8 py-3 pulse-glow">
						Get Started Free →
					</a>
					<a href="#features" class="btn btn-secondary text-base px-8 py-3"> Review Features </a>
				</div>
			</div>
		</section>
	</div>
{:else}
	<div class="space-y-8">
		<!-- Page Header with Date Range Picker -->
		<div class="flex flex-col gap-4">
			<div class="flex items-center justify-between">
				<div>
					<h1 class="text-2xl font-bold mb-1">{personaTitle} Dashboard</h1>
					<p class="text-ink-400 text-sm">{personaSubtitle}</p>
				</div>

				<!-- Provider Selector -->
				<ProviderSelector selectedProvider={provider} onSelect={handleProviderChange} />
			</div>

			<DateRangePicker onDateChange={handleDateChange} />
		</div>

		{#if loading}
			<!-- Loading Skeletons -->
			<div class="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
				{#each [1, 2, 3, 4] as i (i)}
					<div class="card" style="animation-delay: {i * 50}ms;">
						<div class="skeleton h-4 w-20 mb-3"></div>
						<div class="skeleton h-8 w-32"></div>
					</div>
				{/each}
			</div>
		{:else if error}
			<div class="card border-danger-500/50 bg-danger-500/10">
				<p class="text-danger-400">{error}</p>
			</div>
		{:else}
			<!-- Persona Next Actions -->
			<div class="card stagger-enter" style="animation-delay: 160ms;">
				<div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
					<div>
						<h2 class="text-sm font-semibold text-ink-200">Next actions</h2>
						<p class="text-xs text-ink-400 mt-1">
							{#if persona === 'finance'}
								Review allocation coverage, unit economics anomalies, and savings proof.
							{:else if persona === 'platform'}
								Check job reliability, policy guardrails, and connector health.
							{:else if persona === 'leadership'}
								Validate savings impact and monitor high-level cost drivers.
							{:else}
								Triage findings and run policy-previewed remediation safely.
							{/if}
						</p>
					</div>

					<div class="flex flex-wrap items-center gap-2">
						{#if persona === 'finance'}
							<a href={`${base}/leaderboards`} class="btn btn-secondary text-sm">Leaderboards</a>
							<a href={`${base}/savings`} class="btn btn-primary text-sm">Savings Proof</a>
						{:else if persona === 'platform'}
							<a href={`${base}/ops`} class="btn btn-primary text-sm">Ops Center</a>
							<a href={`${base}/settings`} class="btn btn-secondary text-sm">Guardrails</a>
						{:else if persona === 'leadership'}
							<a href={`${base}/savings`} class="btn btn-primary text-sm">Savings Proof</a>
							<a href={`${base}/leaderboards`} class="btn btn-secondary text-sm">Leaderboards</a>
						{:else}
							<a href={`${base}/ops`} class="btn btn-primary text-sm">Review Findings</a>
							<a href={`${base}/connections`} class="btn btn-secondary text-sm">Add Connection</a>
						{/if}
					</div>
				</div>
			</div>

			<!-- Stats Grid -->
			<StatsGrid
				{costs}
				{carbon}
				{zombieCount}
				totalMonthlyWaste={zombies?.total_monthly_waste}
				{periodLabel}
			/>

			{#if persona === 'finance' || persona === 'leadership'}
				<UnitEconomicsCards {unitEconomics} />
			{/if}

			<!-- AI Insights - Interactive Cards -->
			{#if persona === 'engineering'}
				{#if zombies?.ai_analysis}
					{@const aiData = zombies.ai_analysis}

					<SavingsHero {aiData} />

					<!-- AI Findings Table - Scalable Design -->
					{#if aiData.resources && aiData.resources.length > 0}
						<FindingsTable
							resources={aiData.resources}
							onRemediate={handleRemediate}
							{remediating}
						/>
					{/if}

					<!-- General Recommendations -->
					{#if aiData.general_recommendations && aiData.general_recommendations.length > 0}
						<div class="card stagger-enter" style="animation-delay: 400ms;">
							<h3 class="text-lg font-semibold mb-3">💡 Recommendations</h3>
							<ul class="space-y-2">
								{#each aiData.general_recommendations as rec (rec)}
									<li class="flex items-start gap-2 text-sm text-ink-300">
										<span class="text-accent-400">•</span>
										{rec}
									</li>
								{/each}
							</ul>
						</div>
					{/if}
				{:else if analysisText}
					<!-- Fallback: Plain text analysis -->
					<div class="card stagger-enter" style="animation-delay: 200ms;">
						<div class="flex items-center justify-between mb-3">
							<h2 class="text-lg font-semibold">AI Insights</h2>
							<span class="badge badge-default">LLM</span>
						</div>
						<div class="text-sm text-ink-300 whitespace-pre-wrap leading-relaxed">
							{analysisText}
						</div>
					</div>
				{/if}
			{/if}

			<!-- Data Freshness Status -->
			{#if freshness}
				<div class="freshness-indicator stagger-enter" style="animation-delay: 240ms;">
					<div class="flex items-center gap-2">
						<Clock class="h-4 w-4 text-ink-400" />
						<span class="text-sm text-ink-400">Data Freshness:</span>
						{#if freshness.status === 'final'}
							<span class="badge badge-success">✓ Finalized</span>
						{:else if freshness.status === 'preliminary'}
							<span class="badge badge-warning flex items-center gap-1">
								<AlertTriangle class="h-3 w-3" />
								Preliminary ({freshness.preliminary_records} records may change)
							</span>
						{:else if freshness.status === 'mixed'}
							<span class="badge badge-default">
								{freshness.freshness_percentage}% Finalized
							</span>
						{:else}
							<span class="badge badge-default">No Data</span>
						{/if}
					</div>
					{#if freshness.latest_record_date}
						<span class="text-xs text-ink-500">Latest: {freshness.latest_record_date}</span>
					{/if}
				</div>
			{/if}

			<!-- ESG & Multi-Cloud Matrix -->
			{#if persona === 'finance' || persona === 'leadership'}
				<div class="grid gap-6 md:grid-cols-2 lg:grid-cols-2">
					<GreenOpsWidget />
					<CloudDistributionMatrix />
				</div>
			{/if}

			<!-- Long-Term Value & Allocation -->
			{#if persona === 'finance' || persona === 'leadership'}
				<div class="grid gap-6 md:grid-cols-1 lg:grid-cols-2">
					<ROAChart />
					{#if allocation && allocation.buckets && allocation.buckets.length > 0}
						<AllocationBreakdown data={allocation} />
					{:else}
						{#if !tierAtLeast(tier, 'growth')}
							<UpgradeNotice
								currentTier={tier}
								requiredTier="growth"
								feature="Cost Allocation (chargeback/showback)"
							/>
						{:else}
							<div class="glass-panel flex flex-col items-center justify-center text-ink-500">
								<p>Cost Allocation data will appear here once attribution rules are defined.</p>
							</div>
						{/if}
					{/if}
				</div>
			{/if}

			<!-- Zombie Resources Table -->
			{#if persona === 'engineering' && zombieCount > 0}
				<div class="card stagger-enter" style="animation-delay: 250ms;">
					<div class="flex items-center justify-between mb-5">
						<h2 class="text-lg font-semibold">Zombie Resources</h2>
						<span class="badge badge-warning">{zombieCount} found</span>
					</div>

					<div class="overflow-x-auto">
						<table class="table">
							<thead>
								<tr>
									<th>Cloud</th>
									<th>Resource</th>
									<th>Type</th>
									<th>Monthly Cost</th>
									<th>Owner</th>
									<th>AI Reasoning & Confidence</th>
									<th>Action</th>
								</tr>
							</thead>
							<tbody>
								{#each zombies?.unattached_volumes ?? [] as vol (vol.resource_id)}
									<tr>
										<td class="flex items-center gap-1.5">
											<CloudLogo provider={vol.provider} size={12} />
											<span
												class="text-[10px] font-bold uppercase {vol.provider === 'aws'
													? 'text-orange-400'
													: vol.provider === 'azure'
														? 'text-blue-400'
														: 'text-yellow-400'}"
											>
												{vol.provider || 'AWS'}
											</span>
										</td>
										<td class="font-mono text-xs">{vol.resource_id}</td>
										<td><span class="badge badge-default">EBS Volume</span></td>
										<td class="text-danger-400">${vol.monthly_cost}</td>
										<td class="text-xs text-ink-400">{vol.owner || 'unknown'}</td>
										<td>
											<div class="flex flex-col gap-1 max-w-xs">
												<p class="text-[10px] leading-tight text-ink-300">
													{vol.explainability_notes || 'Resource detached and accruing idle costs.'}
												</p>
												<div class="flex items-center gap-2">
													<div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
														<div
															class="h-full bg-accent-500"
															style="width: {vol.confidence_score
																? vol.confidence_score * 100
																: 0}%"
														></div>
													</div>
													<span class="text-[10px] font-bold text-accent-400"
														>{vol.confidence_score
															? Math.round(vol.confidence_score * 100) + '% Match'
															: 'N/A'}</span
													>
												</div>
											</div>
										</td>
										<td>
											<button class="btn btn-ghost text-xs" onclick={() => handleRemediate(vol)}
												>Review</button
											>
										</td>
									</tr>
								{/each}
								{#each zombies?.old_snapshots ?? [] as snap (snap.resource_id)}
									<tr>
										<td class="flex items-center gap-1.5">
											<CloudLogo provider={snap.provider} size={12} />
											<span
												class="text-[10px] font-bold uppercase {snap.provider === 'aws'
													? 'text-orange-400'
													: snap.provider === 'azure'
														? 'text-blue-400'
														: 'text-yellow-400'}"
											>
												{snap.provider || 'AWS'}
											</span>
										</td>
										<td class="font-mono text-xs">{snap.resource_id}</td>
										<td><span class="badge badge-default">Snapshot</span></td>
										<td class="text-danger-400">${snap.monthly_cost}</td>
										<td class="text-xs text-ink-400">{snap.owner || 'unknown'}</td>
										<td>
											<div class="flex flex-col gap-1 max-w-xs">
												<p class="text-[10px] leading-tight text-ink-300">
													{snap.explainability_notes ||
														'Snapshot age exceeds standard retention policy.'}
												</p>
												<div class="flex items-center gap-2">
													<div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
														<div
															class="h-full bg-accent-500"
															style="width: {snap.confidence_score
																? snap.confidence_score * 100
																: 0}%"
														></div>
													</div>
													<span class="text-[10px] font-bold text-accent-400"
														>{snap.confidence_score
															? Math.round(snap.confidence_score * 100) + '% Match'
															: 'N/A'}</span
													>
												</div>
											</div>
										</td>
										<td>
											<button class="btn btn-ghost text-xs" onclick={() => handleRemediate(snap)}
												>Review</button
											>
										</td>
									</tr>
								{/each}
								{#each zombies?.unused_elastic_ips ?? [] as eip (eip.resource_id)}
									<tr>
										<td class="flex items-center gap-1.5">
											<CloudLogo provider={eip.provider} size={12} />
											<span
												class="text-[10px] font-bold uppercase {eip.provider === 'aws'
													? 'text-orange-400'
													: eip.provider === 'azure'
														? 'text-blue-400'
														: 'text-yellow-400'}"
											>
												{eip.provider || 'AWS'}
											</span>
										</td>
										<td class="font-mono text-xs">{eip.resource_id}</td>
										<td><span class="badge badge-default">Elastic IP</span></td>
										<td class="text-danger-400">${eip.monthly_cost}</td>
										<td class="text-xs text-ink-400">{eip.owner || 'unknown'}</td>
										<td>
											<div class="flex flex-col gap-1 max-w-xs">
												<p class="text-[10px] leading-tight text-ink-300">
													{eip.explainability_notes || 'Unassociated EIP address found.'}
												</p>
												<div class="flex items-center gap-2">
													<div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
														<div
															class="h-full bg-accent-500"
															style="width: {eip.confidence_score
																? eip.confidence_score * 100
																: 0}%"
														></div>
													</div>
													<span class="text-[10px] font-bold text-accent-400"
														>{eip.confidence_score
															? Math.round(eip.confidence_score * 100) + '% Match'
															: 'N/A'}</span
													>
												</div>
											</div>
										</td>
										<td
											><button class="btn btn-ghost text-xs" onclick={() => handleRemediate(eip)}
												>Review</button
											></td
										>
									</tr>
								{/each}
								{#each zombies?.idle_instances ?? [] as ec2 (ec2.resource_id)}
									<tr>
										<td class="flex items-center gap-1.5">
											<CloudLogo provider={ec2.provider} size={12} />
											<span
												class="text-[10px] font-bold uppercase {ec2.provider === 'aws'
													? 'text-orange-400'
													: ec2.provider === 'azure'
														? 'text-blue-400'
														: 'text-yellow-400'}"
											>
												{ec2.provider || 'AWS'}
											</span>
										</td>
										<td class="font-mono text-xs">{ec2.resource_id}</td>
										<td>
											<div class="flex items-center gap-1.5">
												<span class="badge badge-default">Idle EC2 ({ec2.instance_type})</span>
												{#if ec2.is_gpu}
													<span class="badge badge-error py-0 text-[9px] uppercase font-bold"
														>GPU</span
													>
												{/if}
											</div>
										</td>
										<td class="text-danger-400">${ec2.monthly_cost}</td>
										<td class="text-xs text-ink-400">{ec2.owner || 'unknown'}</td>
										<td>
											<div class="flex flex-col gap-1 max-w-xs">
												<p class="text-[10px] leading-tight text-ink-300">
													{ec2.explainability_notes ||
														'Low CPU and network utilization detected over 7 days.'}
												</p>
												<div class="flex items-center gap-2">
													<div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
														<div
															class="h-full bg-accent-500"
															style="width: {ec2.confidence_score
																? ec2.confidence_score * 100
																: 0}%"
														></div>
													</div>
													<span class="text-[10px] font-bold text-accent-400"
														>{ec2.confidence_score
															? Math.round(ec2.confidence_score * 100) + '% Match'
															: 'N/A'}</span
													>
												</div>
											</div>
										</td>
										<td
											><button class="btn btn-ghost text-xs" onclick={() => handleRemediate(ec2)}
												>Review</button
											></td
										>
									</tr>
								{/each}
								{#each zombies?.orphan_load_balancers ?? [] as lb (lb.resource_id)}
									<tr>
										<td class="flex items-center gap-1.5">
											<CloudLogo provider={lb.provider} size={12} />
											<span
												class="text-[10px] font-bold uppercase {lb.provider === 'aws'
													? 'text-orange-400'
													: lb.provider === 'azure'
														? 'text-blue-400'
														: 'text-yellow-400'}"
											>
												{lb.provider || 'AWS'}
											</span>
										</td>
										<td class="font-mono text-xs">{lb.resource_id}</td>
										<td
											><span class="badge badge-default">Orphan {lb.lb_type.toUpperCase()}</span
											></td
										>
										<td class="text-danger-400">${lb.monthly_cost}</td>
										<td class="text-xs text-ink-400">{lb.owner || 'unknown'}</td>
										<td>
											<div class="flex flex-col gap-1 max-w-xs">
												<p class="text-[10px] leading-tight text-ink-300">
													{lb.explainability_notes ||
														'Load balancer has no healthy targets associated.'}
												</p>
												<div class="flex items-center gap-2">
													<div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
														<div
															class="h-full bg-accent-500"
															style="width: {lb.confidence_score ? lb.confidence_score * 100 : 0}%"
														></div>
													</div>
													<span class="text-[10px] font-bold text-accent-400"
														>{lb.confidence_score
															? Math.round(lb.confidence_score * 100) + '% Match'
															: 'N/A'}</span
													>
												</div>
											</div>
										</td>
										<td
											><button class="btn btn-ghost text-xs" onclick={() => handleRemediate(lb)}
												>Review</button
											></td
										>
									</tr>
								{/each}
								{#each zombies?.idle_rds_databases ?? [] as rds (rds.resource_id)}
									<tr>
										<td class="flex items-center gap-1.5">
											<CloudLogo provider={rds.provider} size={12} />
											<span
												class="text-[10px] font-bold uppercase {rds.provider === 'aws'
													? 'text-orange-400'
													: rds.provider === 'azure'
														? 'text-blue-400'
														: 'text-yellow-400'}"
											>
												{rds.provider || 'AWS'}
											</span>
										</td>
										<td class="font-mono text-xs">{rds.resource_id}</td>
										<td><span class="badge badge-default">Idle RDS ({rds.db_class})</span></td>
										<td class="text-danger-400">${rds.monthly_cost}</td>
										<td class="text-xs text-ink-400">{rds.owner || 'unknown'}</td>
										<td>
											<div class="flex flex-col gap-1 max-w-xs">
												<p class="text-[10px] leading-tight text-ink-300">
													{rds.explainability_notes ||
														'No connections detected in the last billing cycle.'}
												</p>
												<div class="flex items-center gap-2">
													<div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
														<div
															class="h-full bg-accent-500"
															style="width: {rds.confidence_score
																? rds.confidence_score * 100
																: 0}%"
														></div>
													</div>
													<span class="text-[10px] font-bold text-accent-400"
														>{rds.confidence_score
															? Math.round(rds.confidence_score * 100) + '% Match'
															: 'N/A'}</span
													>
												</div>
											</div>
										</td>
										<td
											><button class="btn btn-ghost text-xs" onclick={() => handleRemediate(rds)}
												>Review</button
											></td
										>
									</tr>
								{/each}
								{#each zombies?.underused_nat_gateways ?? [] as nat (nat.resource_id)}
									<tr>
										<td class="flex items-center gap-1.5">
											<CloudLogo provider={nat.provider} size={12} />
											<span
												class="text-[10px] font-bold uppercase {nat.provider === 'aws'
													? 'text-orange-400'
													: nat.provider === 'azure'
														? 'text-blue-400'
														: 'text-yellow-400'}"
											>
												{nat.provider || 'AWS'}
											</span>
										</td>
										<td class="font-mono text-xs">{nat.resource_id}</td>
										<td><span class="badge badge-default">Idle NAT Gateway</span></td>
										<td class="text-danger-400">${nat.monthly_cost}</td>
										<td class="text-xs text-ink-400">{nat.owner || 'unknown'}</td>
										<td>
											<div class="flex flex-col gap-1 max-w-xs">
												<p class="text-[10px] leading-tight text-ink-300">
													{nat.explainability_notes ||
														'Minimal data processing detected compared to runtime cost.'}
												</p>
												<div class="flex items-center gap-2">
													<div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
														<div
															class="h-full bg-accent-500"
															style="width: {nat.confidence_score
																? nat.confidence_score * 100
																: 0}%"
														></div>
													</div>
													<span class="text-[10px] font-bold text-accent-400"
														>{nat.confidence_score
															? Math.round(nat.confidence_score * 100) + '% Match'
															: 'N/A'}</span
													>
												</div>
											</div>
										</td>
										<td
											><button class="btn btn-ghost text-xs" onclick={() => handleRemediate(nat)}
												>Review</button
											></td
										>
									</tr>
								{/each}
								{#each zombies?.idle_s3_buckets ?? [] as s3 (s3.resource_id)}
									<tr>
										<td class="flex items-center gap-1.5">
											<CloudLogo provider={s3.provider} size={12} />
											<span
												class="text-[10px] font-bold uppercase {s3.provider === 'aws'
													? 'text-orange-400'
													: s3.provider === 'azure'
														? 'text-blue-400'
														: 'text-yellow-400'}"
											>
												{s3.provider || 'AWS'}
											</span>
										</td>
										<td class="font-mono text-xs">{s3.resource_id}</td>
										<td><span class="badge badge-default">Idle S3 Bucket</span></td>
										<td class="text-danger-400">${s3.monthly_cost}</td>
										<td class="text-xs text-ink-400">{s3.owner || 'unknown'}</td>
										<td>
											<div class="flex flex-col gap-1 max-w-xs">
												<p class="text-[10px] leading-tight text-ink-300">
													{s3.explainability_notes ||
														'No GET/PUT requests recorded in the last 30 days.'}
												</p>
												<div class="flex items-center gap-2">
													<div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
														<div
															class="h-full bg-accent-500"
															style="width: {s3.confidence_score ? s3.confidence_score * 100 : 0}%"
														></div>
													</div>
													<span class="text-[10px] font-bold text-accent-400"
														>{s3.confidence_score
															? Math.round(s3.confidence_score * 100) + '% Match'
															: 'N/A'}</span
													>
												</div>
											</div>
										</td>
										<td
											><button class="btn btn-ghost text-xs" onclick={() => handleRemediate(s3)}
												>Review</button
											></td
										>
									</tr>
								{/each}
								{#each zombies?.stale_ecr_images ?? [] as ecr (ecr.resource_id)}
									<tr>
										<td class="flex items-center gap-1.5">
											<CloudLogo provider={ecr.provider} size={12} />
											<span
												class="text-[10px] font-bold uppercase {ecr.provider === 'aws'
													? 'text-orange-400'
													: ecr.provider === 'azure'
														? 'text-blue-400'
														: 'text-yellow-400'}"
											>
												{ecr.provider || 'AWS'}
											</span>
										</td>
										<td class="font-mono text-xs truncate max-w-[150px]">{ecr.resource_id}</td>
										<td><span class="badge badge-default">ECR Image</span></td>
										<td class="text-danger-400">${ecr.monthly_cost}</td>
										<td class="text-xs text-ink-400">{ecr.owner || 'unknown'}</td>
										<td>
											<div class="flex flex-col gap-1 max-w-xs">
												<p class="text-[10px] leading-tight text-ink-300">
													{ecr.explainability_notes ||
														'Untagged or superseded by multiple newer versions.'}
												</p>
												<div class="flex items-center gap-2">
													<div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
														<div
															class="h-full bg-accent-500"
															style="width: {ecr.confidence_score
																? ecr.confidence_score * 100
																: 0}%"
														></div>
													</div>
													<span class="text-[10px] font-bold text-accent-400"
														>{ecr.confidence_score
															? Math.round(ecr.confidence_score * 100) + '% Match'
															: 'N/A'}</span
													>
												</div>
											</div>
										</td>
										<td
											><button class="btn btn-ghost text-xs" onclick={() => handleRemediate(ecr)}
												>Review</button
											></td
										>
									</tr>
								{/each}
								{#each zombies?.idle_sagemaker_endpoints ?? [] as sm (sm.resource_id)}
									<tr>
										<td class="flex items-center gap-1.5">
											<CloudLogo provider={sm.provider} size={12} />
											<span
												class="text-[10px] font-bold uppercase {sm.provider === 'aws'
													? 'text-orange-400'
													: sm.provider === 'azure'
														? 'text-blue-400'
														: 'text-yellow-400'}"
											>
												{sm.provider || 'AWS'}
											</span>
										</td>
										<td class="font-mono text-xs">{sm.resource_id}</td>
										<td><span class="badge badge-default">SageMaker Endpoint</span></td>
										<td class="text-danger-400">${sm.monthly_cost}</td>
										<td class="text-xs text-ink-400">{sm.owner || 'unknown'}</td>
										<td>
											<div class="flex flex-col gap-1 max-w-xs">
												<p class="text-[10px] leading-tight text-ink-300">
													{sm.explainability_notes ||
														'Endpoint has not processed any inference requests recently.'}
												</p>
												<div class="flex items-center gap-2">
													<div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
														<div
															class="h-full bg-accent-500"
															style="width: {sm.confidence_score ? sm.confidence_score * 100 : 0}%"
														></div>
													</div>
													<span class="text-[10px] font-bold text-accent-400"
														>{sm.confidence_score
															? Math.round(sm.confidence_score * 100) + '% Match'
															: 'N/A'}</span
													>
												</div>
											</div>
										</td>
										<td
											><button class="btn btn-ghost text-xs" onclick={() => handleRemediate(sm)}
												>Review</button
											></td
										>
									</tr>
								{/each}
								{#each zombies?.cold_redshift_clusters ?? [] as rs (rs.resource_id)}
									<tr>
										<td class="flex items-center gap-1.5">
											<CloudLogo provider={rs.provider} size={12} />
											<span
												class="text-[10px] font-bold uppercase {rs.provider === 'aws'
													? 'text-orange-400'
													: rs.provider === 'azure'
														? 'text-blue-400'
														: 'text-yellow-400'}"
											>
												{rs.provider || 'AWS'}
											</span>
										</td>
										<td class="font-mono text-xs">{rs.resource_id}</td>
										<td><span class="badge badge-default">Redshift Cluster</span></td>
										<td class="text-danger-400">${rs.monthly_cost}</td>
										<td class="text-xs text-ink-400">{rs.owner || 'unknown'}</td>
										<td>
											<div class="flex flex-col gap-1 max-w-xs">
												<p class="text-[10px] leading-tight text-ink-300">
													{rs.explainability_notes ||
														'Cluster has been in idle state for over 14 days.'}
												</p>
												<div class="flex items-center gap-2">
													<div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
														<div
															class="h-full bg-accent-500"
															style="width: {rs.confidence_score ? rs.confidence_score * 100 : 0}%"
														></div>
													</div>
													<span class="text-[10px] font-bold text-accent-400"
														>{rs.confidence_score
															? Math.round(rs.confidence_score * 100) + '% Match'
															: 'N/A'}</span
													>
												</div>
											</div>
										</td>
										<td
											><button class="btn btn-ghost text-xs" onclick={() => handleRemediate(rs)}
												>Review</button
											></td
										>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				</div>
			{/if}
		{/if}
	</div>
{/if}

{#if remediationModalOpen && remediationCandidate}
	<div class="fixed inset-0 z-[150] flex items-center justify-center p-4">
		<button
			type="button"
			class="absolute inset-0 bg-ink-950/70 backdrop-blur-sm border-0"
			aria-label="Close remediation modal"
			onclick={closeRemediationModal}
		></button>
		<div
			class="relative w-full max-w-2xl card border border-ink-700"
			role="dialog"
			aria-modal="true"
			aria-label="Remediation policy preview"
		>
			<div class="flex items-center justify-between mb-4">
				<div>
					<h3 class="text-lg font-semibold">Remediation Review</h3>
					<p class="text-xs text-ink-400 mt-1 font-mono">{remediationCandidate.resource_id}</p>
				</div>
				<button class="btn btn-secondary text-xs" onclick={closeRemediationModal}>Close</button>
			</div>

			<div class="space-y-3 text-sm">
				<div class="text-ink-300">
					<span class="text-ink-500">Resource type:</span>
					{remediationCandidate.resource_type || 'unknown'}
				</div>
				<div class="text-ink-300">
					<span class="text-ink-500">Provider:</span>
					{(remediationCandidate.provider || 'aws').toUpperCase()}
				</div>
				<div class="text-ink-300">
					<span class="text-ink-500">Suggested action:</span>
					{deriveRemediationAction(remediationCandidate).replaceAll('_', ' ')}
				</div>

				{#if remediationPreviewLoading}
					<div class="card border border-ink-700">
						<div class="skeleton h-4 w-40 mb-2"></div>
						<div class="skeleton h-4 w-full"></div>
					</div>
				{:else if remediationPreview}
					<div class="flex items-center gap-2">
						<span class={policyDecisionClass(remediationPreview.decision)}>
							{remediationPreview.decision.toUpperCase()}
						</span>
						<span class="text-xs text-ink-500 uppercase">{remediationPreview.tier}</span>
					</div>
					<p class="text-ink-300">{remediationPreview.summary}</p>
					{#if remediationPreview.rule_hits.length > 0}
						<div class="rounded-lg border border-ink-700 p-3">
							<p class="text-xs uppercase tracking-wide text-ink-500 mb-2">Rule Hits</p>
							<ul class="space-y-1 text-xs text-ink-300">
								{#each remediationPreview.rule_hits as hit (hit.rule_id)}
									<li>
										<span class="font-semibold">{hit.rule_id}</span>
										{#if hit.message}
											: {hit.message}
										{/if}
									</li>
								{/each}
							</ul>
						</div>
					{/if}
				{/if}

				{#if remediationPreviewError}
					<div class="card border-danger-500/50 bg-danger-500/10">
						<p class="text-danger-400 text-xs">{remediationPreviewError}</p>
					</div>
				{/if}

				{#if remediationActionError}
					<div class="card border-danger-500/50 bg-danger-500/10">
						<p class="text-danger-400 text-xs">{remediationActionError}</p>
					</div>
				{/if}

				{#if remediationActionSuccess}
					<div class="card border-success-500/50 bg-success-500/10">
						<p class="text-success-400 text-xs">{remediationActionSuccess}</p>
					</div>
				{/if}
			</div>

			<div class="mt-5 flex items-center justify-end gap-2">
				<button
					class="btn btn-secondary text-xs"
					onclick={() => remediationCandidate && runRemediationPreview(remediationCandidate)}
					disabled={remediationPreviewLoading || remediationSubmitting}
				>
					{remediationPreviewLoading ? 'Refreshing...' : 'Re-run Preview'}
				</button>
				<button
					class="btn btn-primary text-xs"
					onclick={submitRemediationRequest}
					disabled={remediationSubmitting ||
						remediationPreviewLoading ||
						remediationPreview?.decision?.toLowerCase() === 'block'}
				>
					{#if remediationSubmitting}
						Creating...
					{:else if remediationPreview?.decision?.toLowerCase() === 'escalate'}
						Create Escalated Request
					{:else if remediationPreview?.decision?.toLowerCase() === 'warn'}
						Create Request with Warning
					{:else if remediationPreview?.decision?.toLowerCase() === 'block'}
						Blocked by Policy
					{:else if remediationPreviewError}
						Create Request Anyway
					{:else}
						Create Request
					{/if}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.border-danger-500\/50 {
		border-color: rgb(244 63 94 / 0.5);
	}

	/* ===== Landing (2026) ===== */
	.landing {
		position: relative;
		isolation: isolate;
	}

	.landing-hero {
		position: relative;
		overflow: hidden;
	}

	/* Atmospheric mesh + dot grid */
	.landing-hero::before {
		content: '';
		position: absolute;
		inset: -260px -120px auto -120px;
		height: 640px;
		background:
			radial-gradient(520px 320px at 18% 18%, rgb(6 182 212 / 0.22), transparent 62%),
			radial-gradient(520px 360px at 58% 22%, rgb(34 211 238 / 0.18), transparent 65%),
			radial-gradient(520px 420px at 82% 38%, rgb(16 185 129 / 0.14), transparent 68%),
			radial-gradient(420px 360px at 70% 74%, rgb(245 158 11 / 0.1), transparent 70%);
		filter: blur(46px);
		opacity: 1;
		pointer-events: none;
		z-index: 0;
	}

	.landing-hero::after {
		content: '';
		position: absolute;
		inset: 0;
		background-image: radial-gradient(rgb(255 255 255 / 0.1) 1px, transparent 1px);
		background-size: 24px 24px;
		opacity: 0.1;
		pointer-events: none;
		z-index: 0;
	}

	.landing-hero :global(.container) {
		position: relative;
		z-index: 1;
	}

	.landing-hero-grid {
		display: grid;
		gap: 2.5rem;
		align-items: start;
	}

	@media (min-width: 1024px) {
		.landing-hero-grid {
			grid-template-columns: 1.15fr 0.85fr;
			gap: 3rem;
		}
	}

	.landing-copy {
		text-align: center;
	}

	@media (min-width: 1024px) {
		.landing-copy {
			text-align: left;
			padding-top: 0.75rem;
		}
	}

	.landing-kicker {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.55rem;
		flex-wrap: wrap;
	}

	@media (min-width: 1024px) {
		.landing-kicker {
			justify-content: flex-start;
		}
	}

	.landing-kicker-text {
		color: var(--color-ink-400);
		font-size: 0.9rem;
		font-weight: 500;
		letter-spacing: 0.01em;
	}

	.landing-sep {
		color: var(--color-ink-600);
	}

	.landing-title {
		font-family: ui-serif, 'Iowan Old Style', 'Palatino Linotype', Palatino, serif;
		font-weight: 800;
		letter-spacing: -0.04em;
		line-height: 1.02;
		font-size: clamp(2.6rem, 5vw, 4.4rem);
		margin-top: 0.9rem;
		margin-bottom: 1rem;
	}

	.landing-kinetic {
		display: inline-block;
		padding: 0 0.08em;
		background: linear-gradient(135deg, var(--color-accent-400), var(--color-success-400));
		background-size: 200% 200%;
		-webkit-background-clip: text;
		-webkit-text-fill-color: transparent;
		background-clip: text;
		color: transparent;
		animation: kineticShift 6s var(--ease-in-out) infinite;
	}

	@keyframes kineticShift {
		0% {
			background-position: 0% 50%;
		}
		50% {
			background-position: 100% 50%;
		}
		100% {
			background-position: 0% 50%;
		}
	}

	.landing-subtitle {
		color: var(--color-ink-300);
		font-size: 1.125rem;
		line-height: 1.65;
		max-width: 42rem;
		margin: 0 auto;
	}

	@media (min-width: 1024px) {
		.landing-subtitle {
			margin-left: 0;
		}
	}

	.landing-cta {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		justify-content: center;
		margin-top: 1.4rem;
	}

	@media (min-width: 1024px) {
		.landing-cta {
			justify-content: flex-start;
		}
	}

	.landing-proof {
		margin-top: 1.75rem;
		display: grid;
		gap: 0.85rem;
		grid-template-columns: 1fr;
	}

	@media (min-width: 768px) {
		.landing-proof {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
	}

	.landing-proof-item {
		border: 1px solid rgb(255 255 255 / 0.06);
		border-radius: var(--radius-lg);
		padding: 0.95rem 1rem;
		background: rgb(15 19 24 / 0.35);
		backdrop-filter: blur(10px);
		-webkit-backdrop-filter: blur(10px);
	}

	.landing-proof-k {
		margin: 0 0 0.25rem 0;
		font-size: 0.72rem;
		letter-spacing: 0.09em;
		text-transform: uppercase;
		font-weight: 800;
		color: var(--color-ink-200);
	}

	.landing-proof-v {
		margin: 0;
		font-size: 0.875rem;
		color: var(--color-ink-400);
	}

	.landing-preview {
		max-width: 40rem;
		margin: 0 auto;
	}

	@media (min-width: 1024px) {
		.landing-preview {
			max-width: none;
			margin: 0;
		}
	}

	.landing-preview-card {
		padding: 1.1rem;
	}

	.landing-preview-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		margin-bottom: 0.85rem;
	}

	.landing-preview-title {
		display: flex;
		align-items: center;
		gap: 0.55rem;
		font-weight: 700;
		color: var(--color-ink-100);
	}

	.landing-preview-pill {
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.12em;
		font-weight: 800;
		padding: 0.25rem 0.55rem;
		border-radius: 9999px;
		color: var(--color-success-400);
		background: rgb(16 185 129 / 0.1);
		border: 1px solid rgb(16 185 129 / 0.22);
	}

	.landing-live-dot {
		width: 8px;
		height: 8px;
		border-radius: 9999px;
		background: var(--color-success-400);
		box-shadow: 0 0 0 6px rgb(16 185 129 / 0.12);
		animation: livePulse 1.8s var(--ease-in-out) infinite;
	}

	@keyframes livePulse {
		0%,
		100% {
			transform: scale(1);
			opacity: 0.95;
		}
		50% {
			transform: scale(1.4);
			opacity: 0.55;
		}
	}

	.signal-map {
		position: relative;
		border-radius: var(--radius-lg);
		overflow: hidden;
		border: 1px solid rgb(255 255 255 / 0.07);
		background:
			radial-gradient(
				120% 90% at 30% 20%,
				rgb(34 211 238 / 0.18) 0%,
				rgb(6 182 212 / 0.06) 38%,
				rgb(15 19 24 / 0.55) 70%
			),
			radial-gradient(90% 120% at 75% 70%, rgb(16 185 129 / 0.12) 0%, rgb(15 19 24 / 0) 62%);
		height: 300px;
	}

	.signal-map::after {
		content: '';
		position: absolute;
		inset: 0;
		background-image: radial-gradient(rgb(255 255 255 / 0.1) 1px, transparent 1px);
		background-size: 26px 26px;
		opacity: 0.12;
		pointer-events: none;
	}

	.signal-svg {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
	}

	.sig-grid line {
		stroke: rgb(255 255 255 / 0.06);
		stroke-width: 1;
	}

	.sig-line {
		opacity: 0.85;
		animation: lineDash 7s linear infinite;
	}

	@keyframes lineDash {
		to {
			stroke-dashoffset: -220;
		}
	}

	.sig-node {
		fill: rgb(10 13 18 / 0.8);
		stroke: var(--color-accent-400);
		stroke-width: 2.2;
		filter: drop-shadow(0 0 10px rgb(34 211 238 / 0.2));
		transform-box: fill-box;
		transform-origin: center;
		animation: nodePulse 2.9s var(--ease-in-out) infinite;
	}

	.sig-node--center {
		fill: rgb(6 182 212 / 0.65);
		stroke: var(--color-accent-400);
		animation-duration: 3.8s;
	}

	.sig-node--b {
		stroke: var(--color-success-400);
		filter: drop-shadow(0 0 10px rgb(16 185 129 / 0.22));
	}

	.sig-node--c {
		stroke: var(--color-warning-400);
		filter: drop-shadow(0 0 10px rgb(245 158 11 / 0.2));
	}

	@keyframes nodePulse {
		0%,
		100% {
			transform: scale(1);
		}
		50% {
			transform: scale(1.18);
		}
	}

	.signal-label {
		position: absolute;
		padding: 0.55rem 0.65rem;
		border-radius: 0.85rem;
		background: rgb(10 13 18 / 0.55);
		backdrop-filter: blur(10px);
		-webkit-backdrop-filter: blur(10px);
		border: 1px solid rgb(255 255 255 / 0.08);
		pointer-events: none;
	}

	.signal-label-k {
		margin: 0;
		font-size: 0.7rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		font-weight: 800;
		color: var(--color-ink-200);
	}

	.signal-label-v {
		margin: 0.15rem 0 0 0;
		font-size: 0.8rem;
		color: var(--color-ink-400);
	}

	.signal-label--center {
		left: 50%;
		top: 50%;
		transform: translate(-50%, -50%);
		text-align: center;
	}

	.signal-label--a {
		left: 22%;
		top: 28%;
		transform: translate(-10%, -100%);
	}

	.signal-label--b {
		left: 72%;
		top: 22%;
		transform: translate(-50%, -110%);
	}

	.signal-label--c {
		left: 78%;
		top: 72%;
		transform: translate(-20%, 10%);
	}

	.landing-metrics {
		margin-top: 0.9rem;
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 0.75rem;
	}

	@media (max-width: 420px) {
		.landing-metrics {
			grid-template-columns: 1fr;
		}
	}

	.landing-metric {
		padding: 0.85rem 0.9rem;
		border-radius: var(--radius-lg);
	}

	.landing-metric-k {
		margin: 0;
		font-size: 0.72rem;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		font-weight: 800;
		color: var(--color-ink-400);
	}

	.landing-metric-v {
		margin: 0.25rem 0 0 0;
		font-size: 1.4rem;
		font-weight: 800;
		line-height: 1.1;
	}

	.landing-metric-h {
		margin: 0.25rem 0 0 0;
		font-size: 0.8rem;
		color: var(--color-ink-500);
	}

	.landing-pills {
		display: flex;
		flex-wrap: wrap;
		gap: 0.55rem;
		margin-top: 1rem;
		justify-content: center;
	}

	@media (min-width: 1024px) {
		.landing-pills {
			justify-content: flex-end;
		}
	}

	.landing-section-head {
		max-width: 52rem;
		margin: 0 auto 1.25rem auto;
		text-align: center;
	}

	.landing-h2 {
		font-family: ui-serif, 'Iowan Old Style', 'Palatino Linotype', Palatino, serif;
		font-weight: 800;
		letter-spacing: -0.03em;
		line-height: 1.1;
		font-size: clamp(1.85rem, 3vw, 2.3rem);
		margin: 0;
	}

	.landing-section-sub {
		margin: 0.7rem auto 0 auto;
		color: var(--color-ink-400);
		font-size: 1.05rem;
		max-width: 46rem;
	}

	.landing-h3 {
		font-weight: 700;
		font-size: 1.1rem;
		margin: 0 0 0.55rem 0;
	}

	.landing-p {
		margin: 0;
		color: var(--color-ink-300);
		font-size: 0.95rem;
		line-height: 1.65;
	}

	.landing-mini {
		margin-top: 0.8rem;
		font-size: 0.85rem;
	}

	.landing-tag-row {
		display: flex;
		flex-wrap: wrap;
		gap: 0.55rem;
		margin-top: 0.95rem;
	}

	.landing-mini-grid {
		margin-top: 1rem;
		display: grid;
		gap: 0.65rem;
		grid-template-columns: 1fr;
	}

	.landing-mini-card {
		border: 1px solid rgb(255 255 255 / 0.06);
		border-radius: var(--radius-lg);
		padding: 0.75rem 0.85rem;
		background: rgb(15 19 24 / 0.25);
	}

	.landing-mini-k {
		margin: 0;
		font-size: 0.72rem;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		font-weight: 800;
		color: var(--color-ink-500);
	}

	.landing-mini-v {
		margin: 0.25rem 0 0 0;
		font-size: 0.9rem;
		color: var(--color-ink-300);
	}

	.landing-steps {
		display: grid;
		grid-template-columns: 1fr;
		gap: var(--space-4);
	}

	@media (min-width: 768px) {
		.landing-steps {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
	}

	.landing-step {
		position: relative;
		overflow: hidden;
	}

	.landing-step::before {
		content: '';
		position: absolute;
		inset: 0 0 auto 0;
		height: 2px;
		background: linear-gradient(90deg, rgb(34 211 238 / 0.9), rgb(16 185 129 / 0.75));
		opacity: 0.75;
	}

	.landing-step-n {
		margin: 0 0 0.35rem 0;
		font-size: 0.75rem;
		letter-spacing: 0.16em;
		font-weight: 900;
		color: var(--color-ink-500);
		text-transform: uppercase;
	}

	.landing-final {
		display: flex;
		flex-direction: column;
		gap: 1.1rem;
		align-items: stretch;
		text-align: center;
	}

	@media (min-width: 768px) {
		.landing-final {
			flex-direction: row;
			align-items: center;
			justify-content: space-between;
			text-align: left;
		}
	}

	.landing-final-cta {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		justify-content: center;
	}

	@media (min-width: 768px) {
		.landing-final-cta {
			justify-content: flex-end;
		}
	}
</style>
