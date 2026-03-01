<script lang="ts">
	import { browser } from '$app/environment';
	import { onMount } from 'svelte';
	import {
		buildLandingWeeklyTrendChecks,
		readLandingFunnelReport,
		readLandingWeeklyFunnelReport,
		type LandingFunnelSummary,
		type LandingWeeklyFunnelSummary,
		type LandingWeeklyTrendCheck
	} from '$lib/landing/landingFunnel';

	const REFRESH_INTERVAL_MS = 30000;

	const EMPTY_SUMMARY: LandingFunnelSummary = {
		counts: {
			view: 0,
			engaged: 0,
			cta: 0,
			signup_intent: 0
		},
		conversion: {
			engagementRate: 0,
			ctaRate: 0,
			signupIntentRate: 0
		}
	};

	const EMPTY_WEEKLY: LandingWeeklyFunnelSummary[] = [];
	const EMPTY_TRENDS: LandingWeeklyTrendCheck[] = buildLandingWeeklyTrendChecks([]);

	let allTimeSummary = $state<LandingFunnelSummary>(EMPTY_SUMMARY);
	let weeklySummaries = $state<LandingWeeklyFunnelSummary[]>(EMPTY_WEEKLY);
	let trendChecks = $state<LandingWeeklyTrendCheck[]>(EMPTY_TRENDS);
	let capturedAt = $state<string>('');

	function formatPercent(rate: number): string {
		return `${(rate * 100).toFixed(1)}%`;
	}

	function formatTrendLabel(trend: LandingWeeklyTrendCheck): string {
		if (trend.direction === 'flat') return 'Flat';
		return trend.direction === 'up' ? 'Up' : 'Down';
	}

	function refreshFromStorage(): void {
		if (!browser) return;
		const weekly = readLandingWeeklyFunnelReport(window.localStorage, 8);
		weeklySummaries = weekly;
		allTimeSummary = readLandingFunnelReport(window.localStorage);
		trendChecks = buildLandingWeeklyTrendChecks(weekly);
		capturedAt = new Date().toISOString();
	}

	onMount(() => {
		refreshFromStorage();
		const intervalId = window.setInterval(refreshFromStorage, REFRESH_INTERVAL_MS);
		return () => window.clearInterval(intervalId);
	});
</script>

<svelte:head>
	<title>Landing Intelligence | Valdrics</title>
	<meta
		name="description"
		content="Weekly landing conversion instrumentation across views, engagement, CTA, and signup intent."
	/>
</svelte:head>

<section class="space-y-6">
	<header class="card">
		<p class="text-xs uppercase tracking-[0.14em] text-accent-300 font-bold">Growth Intelligence</p>
		<h1 class="text-2xl font-bold mt-1">Landing conversion dashboard</h1>
		<p class="text-sm text-ink-400 mt-2">
			Weekly conversion checks for view, engagement, CTA intent, and signup intent progression.
		</p>
		{#if capturedAt}
			<p class="text-xs text-ink-500 mt-3">Last refresh: {capturedAt}</p>
		{/if}
	</header>

	<div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
		<article class="card">
			<p class="text-xs uppercase tracking-[0.08em] text-ink-500">All-time views</p>
			<p class="text-2xl font-bold mt-1">{allTimeSummary.counts.view}</p>
		</article>
		<article class="card">
			<p class="text-xs uppercase tracking-[0.08em] text-ink-500">Engagement rate</p>
			<p class="text-2xl font-bold mt-1">
				{formatPercent(allTimeSummary.conversion.engagementRate)}
			</p>
		</article>
		<article class="card">
			<p class="text-xs uppercase tracking-[0.08em] text-ink-500">CTA rate</p>
			<p class="text-2xl font-bold mt-1">{formatPercent(allTimeSummary.conversion.ctaRate)}</p>
		</article>
		<article class="card">
			<p class="text-xs uppercase tracking-[0.08em] text-ink-500">Signup intent rate</p>
			<p class="text-2xl font-bold mt-1">
				{formatPercent(allTimeSummary.conversion.signupIntentRate)}
			</p>
		</article>
	</div>

	<div class="grid gap-4 lg:grid-cols-3">
		{#each trendChecks as trend (trend.metric)}
			<article class="card">
				<p class="text-xs uppercase tracking-[0.08em] text-ink-500">{trend.metric}</p>
				<p class="text-lg font-semibold mt-1">{formatTrendLabel(trend)}</p>
				<p class="text-sm text-ink-400 mt-2">
					Latest {formatPercent(trend.latest)} vs previous {formatPercent(trend.previous)}
				</p>
			</article>
		{/each}
	</div>

	<section class="card overflow-x-auto">
		<h2 class="text-lg font-semibold">Weekly funnel detail</h2>
		{#if weeklySummaries.length === 0}
			<p class="text-sm text-ink-400 mt-3">
				No weekly landing telemetry is currently stored in this browser context.
			</p>
		{:else}
			<table class="w-full text-sm mt-4">
				<thead>
					<tr class="text-left text-ink-500">
						<th class="py-2 pr-4 font-medium">Week Start (UTC)</th>
						<th class="py-2 pr-4 font-medium">Views</th>
						<th class="py-2 pr-4 font-medium">Engaged</th>
						<th class="py-2 pr-4 font-medium">CTA</th>
						<th class="py-2 pr-4 font-medium">Signup Intent</th>
						<th class="py-2 pr-4 font-medium">Engagement Rate</th>
						<th class="py-2 pr-4 font-medium">CTA Rate</th>
						<th class="py-2 font-medium">Signup Intent Rate</th>
					</tr>
				</thead>
				<tbody>
					{#each weeklySummaries as week (week.weekStart)}
						<tr class="border-t border-ink-800">
							<td class="py-2 pr-4 font-medium text-ink-200">{week.weekStart}</td>
							<td class="py-2 pr-4">{week.counts.view}</td>
							<td class="py-2 pr-4">{week.counts.engaged}</td>
							<td class="py-2 pr-4">{week.counts.cta}</td>
							<td class="py-2 pr-4">{week.counts.signup_intent}</td>
							<td class="py-2 pr-4">{formatPercent(week.conversion.engagementRate)}</td>
							<td class="py-2 pr-4">{formatPercent(week.conversion.ctaRate)}</td>
							<td class="py-2">{formatPercent(week.conversion.signupIntentRate)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}
	</section>
</section>
