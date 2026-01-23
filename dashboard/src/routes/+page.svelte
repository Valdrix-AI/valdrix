<!--
  Dashboard Home Page - Premium SaaS Design
  
  Features:
  - Stats cards with motion animations
  - Staggered entrance effects
  - Clean data visualization
  - Loading skeletons
-->

<script lang="ts">
	import { PUBLIC_API_URL } from '$env/static/public';
	import { base } from '$app/paths';
	import { createSupabaseBrowserClient } from '$lib/supabase';
	import { AlertTriangle } from '@lucide/svelte';
	import CloudLogo from '$lib/components/CloudLogo.svelte';
	import { api } from '$lib/api';
	import { goto } from '$app/navigation';
	import DateRangePicker from '$lib/components/DateRangePicker.svelte';
	import ProviderSelector from '$lib/components/ProviderSelector.svelte';
	import AllocationBreakdown from '$lib/components/AllocationBreakdown.svelte';
	import StatsGrid from '$lib/components/StatsGrid.svelte';
	import SavingsHero from '$lib/components/SavingsHero.svelte';
	import FindingsTable from '$lib/components/FindingsTable.svelte';
	import CarbonImpact from '$lib/components/CarbonImpact.svelte';

	let { data } = $props();

	let loading = $state(false); // Can be used for nav transitions
	let costs = $derived(data.costs);
	let carbon = $derived(data.carbon);
	let zombies = $derived(data.zombies);
	let analysis = $derived(data.analysis);
	let allocation = $derived(data.allocation);
	let freshness = $derived(data.freshness);
	let error = $derived(data.error || '');
	let startDate = $derived(data.startDate || '');
	let endDate = $derived(data.endDate || '');
	let provider = $derived(data.provider || ''); // Default to empty (All)

	// Table pagination state
	let remediating = $state<string | null>(null);

	/**
	 * Handle remediation action for a zombie resource.
	 */
	async function handleRemediate(finding: {
		resource_id: string;
		resource_type?: string;
		provider?: string;
		connection_id?: string;
		monthly_cost?: string | number;
		recommended_action?: string;
	}) {
		if (remediating) return;
		remediating = finding.resource_id;

		try {
			const accessToken = data.session?.access_token;
			if (!accessToken) throw new Error('Not authenticated');

			const headers = {
				Authorization: `Bearer ${accessToken}`,
				'Content-Type': 'application/json'
			};

			const response = await api.post(
				`${PUBLIC_API_URL}/zombies/request`,
				{
					resource_id: finding.resource_id,
					resource_type: finding.resource_type || 'unknown',
					provider: finding.provider || 'aws',
					connection_id: finding.connection_id,
					action: finding.recommended_action?.toLowerCase().includes('delete')
						? 'delete_volume'
						: 'stop_instance',
					estimated_savings: parseFloat(finding.monthly_cost?.toString().replace('$', '') || '0'),
					create_backup: true
				},
				{ headers }
			);

			if (!response.ok) {
				const errData = await response.json();
				if (response.status === 403) {
					alert('⚡ Upgrade Required: Auto-remediation requires Pro tier or higher.');
				} else {
					alert(`Error: ${errData.detail || 'Failed to create remediation request'}`);
				}
				return;
			}

			const result = await response.json();
			alert(
				`✅ Remediation request created! ID: ${result.request_id}\n\nAn admin must approve before execution.`
			);
		} catch (e) {
			const err = e as Error;
			alert(`Error: ${err.message}`);
		} finally {
			remediating = null;
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
	<title>Dashboard | Valdrix</title>
</svelte:head>

{#if !data.user}
	<!-- Public Landing -->
	<div class="min-h-[85vh] flex flex-col items-center justify-center text-center px-4">
		<!-- Floating Cloud Icon -->
		<div class="hero-icon mb-6">
			<span class="text-7xl drop-shadow-lg">☁️</span>
		</div>

		<!-- Main Heading -->
		<h1
			class="fade-in-up text-4xl md:text-6xl font-bold mb-5 max-w-3xl leading-tight"
			style="animation-delay: 100ms;"
		>
			<span class="text-gradient">Cloud Cost</span> Intelligence
		</h1>

		<!-- Subheading -->
		<p
			class="fade-in-up text-lg md:text-xl mb-10 max-w-xl leading-relaxed"
			style="animation-delay: 200ms; color: var(--color-ink-400);"
		>
			A FinOps engine that continuously optimizes cloud value by eliminating waste, controlling
			cost, and reducing unnecessary overhead.
		</p>

		<!-- CTA Buttons -->
		<div class="fade-in-up flex flex-col sm:flex-row gap-4" style="animation-delay: 300ms;">
			<a href="/auth/login" class="btn btn-primary text-base px-8 py-3 pulse-glow">
				Get Started Free →
			</a>
			<a href="#features" class="btn btn-secondary text-base px-8 py-3"> Learn More </a>
		</div>

		<!-- Feature Pills -->
		<div
			class="fade-in-up flex flex-wrap justify-center gap-3 mt-16"
			style="animation-delay: 500ms;"
		>
			<span class="badge badge-accent">💰 Cost Tracking</span>
			<span class="badge badge-success">🌱 Carbon Footprint</span>
			<span class="badge badge-warning">👻 Zombie Detection</span>
			<span class="badge badge-default">🤖 AI Analysis</span>
		</div>
	</div>
{:else}
	<div class="space-y-8">
		<!-- Page Header with Date Range Picker -->
		<div class="flex flex-col gap-4">
			<div class="flex items-center justify-between">
				<div>
					<h1 class="text-2xl font-bold mb-1">Dashboard</h1>
					<p class="text-ink-400 text-sm">Overview of your cloud infrastructure</p>
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
			<!-- Stats Grid -->
			<StatsGrid
				{costs}
				{carbon}
				{zombieCount}
				totalMonthlyWaste={zombies?.total_monthly_waste}
				{periodLabel}
			/>

			<!-- AI Insights - Interactive Cards -->
			{#if zombies?.ai_analysis}
				{@const aiData = zombies.ai_analysis}

				<SavingsHero {aiData} />

				<!-- AI Findings Table - Scalable Design -->
				{#if aiData.resources && aiData.resources.length > 0}
					<FindingsTable resources={aiData.resources} onRemediate={handleRemediate} {remediating} />
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

			<!-- Carbon Impact Section -->
			<CarbonImpact {carbon} />

			<!-- Cost Allocation Breakdown -->
			{#if allocation && allocation.buckets && allocation.buckets.length > 0}
				<AllocationBreakdown data={allocation} />
			{/if}

			<!-- Zombie Resources Table -->
			{#if zombieCount > 0}
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
													<span class="badge badge-error py-0 text-[9px] uppercase font-bold">GPU</span>
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
								{#each zombies?.legacy_ecr_images ?? [] as ecr (ecr.resource_id)}
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

<style>
	.border-danger-500\/50 {
		border-color: rgb(244 63 94 / 0.5);
	}
</style>
