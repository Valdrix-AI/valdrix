<script lang="ts">
	import { base } from '$app/paths';

	type InsightEntry = {
		title: string;
		audience: string;
		summary: string;
		ctaLabel: string;
		href: string;
	};

	const insights: readonly InsightEntry[] = [
		{
			title: 'How Engineering and Finance Run One Weekly Spend Review',
			audience: 'Engineering + FinOps',
			summary:
				'A practical operating rhythm for moving from spend signal to owner-assigned action in under one week.',
			ctaLabel: 'Open Playbook',
			href: `${base}/resources`
		},
		{
			title: 'GreenOps Decision Framework for Cost, Carbon, and Risk',
			audience: 'Platform + Sustainability',
			summary:
				'Use deterministic decision criteria to balance budget pressure with cleaner-runtime opportunities.',
			ctaLabel: 'Open GreenOps Guide',
			href: `${base}/greenops`
		},
		{
			title: 'CFO Brief: Building a Procurement-Ready TCO Narrative',
			audience: 'CFO + Procurement',
			summary:
				'Structure subscription, rollout effort, and expected recovery opportunities for executive approval.',
			ctaLabel: 'Download ROI Worksheet',
			href: `${base}/resources/valdrics-roi-assumptions.csv`
		}
	];
</script>

<svelte:head>
	<title>Insights | Valdrics</title>
	<meta
		name="description"
		content="Valdrics insights and operating playbooks for cloud, SaaS, ITAM/license, GreenOps, and finance-led spend control execution."
	/>
</svelte:head>

<section class="container mx-auto px-6 py-12 space-y-8">
	<header class="space-y-3 max-w-3xl">
		<h1 class="text-3xl font-bold text-ink-100">Insights</h1>
		<p class="text-ink-300">
			Operator-focused guides for engineering, finance, and leadership teams building governed spend
			execution across cloud and software.
		</p>
	</header>

	<div class="grid gap-6 md:grid-cols-3">
		{#each insights as insight (insight.title)}
			<article class="glass-panel space-y-3">
				<p class="text-xs uppercase tracking-[0.12em] text-ink-500">{insight.audience}</p>
				<h2 class="text-xl font-semibold">{insight.title}</h2>
				<p class="text-ink-300">{insight.summary}</p>
				<a href={insight.href} class="btn btn-secondary w-fit">{insight.ctaLabel}</a>
			</article>
		{/each}
	</div>
</section>
