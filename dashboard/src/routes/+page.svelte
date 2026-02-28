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
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { onDestroy } from 'svelte';
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
	import LandingHero from '$lib/components/LandingHero.svelte';
	import ZombieTable from '$lib/components/ZombieTable.svelte';
	import RemediationModal from '$lib/components/RemediationModal.svelte';
	import { countZombieFindings, type ZombieCollections } from '$lib/zombieCollections';

	type RemediationFinding = {
		resource_id: string;
		resource_type?: string;
		provider?: string;
		connection_id?: string;
		monthly_cost?: string | number;
		recommended_action?: string;
		owner?: string;
		explainability_notes?: string;
		confidence_score?: number;
		db_class?: string;
		lb_type?: string;
		is_gpu?: boolean;
		instance_type?: string;
	};

	let { data } = $props();

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
	let tier = $derived(data.subscription?.tier ?? 'free');

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
	// Remediation state
	let remediationCandidate = $state<RemediationFinding | null>(null);
	let remediationModalOpen = $state(false);
	let pendingNavigationTimeout = $state<ReturnType<typeof setTimeout> | null>(null);

	const DASHBOARD_NAV_DEBOUNCE_MS = 300;

	function scheduleNavigation(targetPath: string) {
		if (pendingNavigationTimeout) {
			clearTimeout(pendingNavigationTimeout);
		}

		pendingNavigationTimeout = setTimeout(() => {
			void goto(targetPath, {
				keepFocus: true,
				noScroll: true,
				replaceState: true
			});
			pendingNavigationTimeout = null;
		}, DASHBOARD_NAV_DEBOUNCE_MS);
	}

	onDestroy(() => {
		if (pendingNavigationTimeout) {
			clearTimeout(pendingNavigationTimeout);
			pendingNavigationTimeout = null;
		}
	});

	function handleRemediate(finding: RemediationFinding) {
		remediationCandidate = finding;
		remediationModalOpen = true;
	}

	function handleDateChange(dates: { startDate: string; endDate: string }) {
		if (dates.startDate === startDate && dates.endDate === endDate) return;
		const params = new URLSearchParams({
			start_date: dates.startDate,
			end_date: dates.endDate
		});
		if (provider) {
			params.set('provider', provider);
		}
		scheduleNavigation(`${base}/?${params.toString()}`);
	}

	function handleProviderChange(selectedProvider: string) {
		if (selectedProvider === provider) return;

		const params = new URLSearchParams();
		if (startDate && endDate) {
			params.set('start_date', startDate);
			params.set('end_date', endDate);
		}
		if (selectedProvider) {
			params.set('provider', selectedProvider);
		}
		const query = params.toString();
		const targetPath = query.length > 0 ? `${base}/?${query}` : `${base}/`;

		scheduleNavigation(targetPath);
	}

	let zombieCount = $derived(countZombieFindings(zombies as ZombieCollections | null | undefined));

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
		<title>Dashboard | Valdrics</title>
	{:else}
		<title>Valdrics | Economic Control Plane for Cloud and Software Spend</title>
		<meta
			name="description"
			content="Valdrics helps teams control cloud and software spend with clear ownership, safer actions, and measurable outcomes."
		/>
		<meta
			property="og:title"
			content="Valdrics | Economic Control Plane for Cloud and Software Spend"
		/>
		<meta
			property="og:description"
			content="Control every cloud and software dollar with clear ownership, governed actions, and faster decisions."
		/>
		<meta property="og:type" content="website" />
		<meta property="og:url" content={new URL($page.url.pathname, $page.url.origin).toString()} />
		<meta
			property="og:image"
			content={new URL(`${assets}/og-image.png`, $page.url.origin).toString()}
		/>
		<meta name="twitter:card" content="summary_large_image" />
		<meta
			name="twitter:title"
			content="Valdrics | Economic Control Plane for Cloud and Software Spend"
		/>
		<meta
			name="twitter:description"
			content="Control every cloud and software dollar with clear ownership, governed actions, and faster decisions."
		/>
		<meta
			name="twitter:image"
			content={new URL(`${assets}/og-image.png`, $page.url.origin).toString()}
		/>
	{/if}
</svelte:head>

{#if !data.user}
	<!-- Public Landing -->
	<LandingHero />
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

		{#if error}
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
						<FindingsTable resources={aiData.resources} onRemediate={handleRemediate} />
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
					{:else if !tierAtLeast(tier, 'growth')}
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
				</div>
			{/if}

			<!-- Zombie Resources Table -->
			{#if persona === 'engineering' && zombieCount > 0}
				<ZombieTable {zombies} {zombieCount} onRemediate={handleRemediate} />
			{/if}
		{/if}
	</div>
{/if}

{#if remediationModalOpen && remediationCandidate}
	<RemediationModal
		bind:isOpen={remediationModalOpen}
		finding={remediationCandidate}
		accessToken={data.session?.access_token}
		onClose={() => {
			remediationCandidate = null;
		}}
	/>
{/if}

<style>
	.border-danger-500\/50 {
		border-color: rgb(244 63 94 / 0.5);
	}
</style>
