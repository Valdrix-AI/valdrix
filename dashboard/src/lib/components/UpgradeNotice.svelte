<script lang="ts">
	/* eslint-disable svelte/no-navigation-without-resolve */
	import { base } from '$app/paths';
	import { formatTierLabel, type Tier } from '$lib/tier';

	let {
		currentTier,
		requiredTier,
		feature,
		ctaHref = '/billing',
		ctaText
	}: {
		currentTier: unknown;
		requiredTier: Tier;
		feature: string;
		ctaHref?: string;
		ctaText?: string;
	} = $props();

	const requiredLabel = $derived(formatTierLabel(requiredTier));
	const currentLabel = $derived(formatTierLabel(currentTier));
</script>

<div class="glass-panel flex flex-col items-center justify-center text-center gap-3 p-6">
	<span class="badge badge-warning text-xs w-fit justify-center"
		>{requiredLabel} Tier Required</span
	>
	<p class="text-sm text-ink-300">
		Upgrade to <span class="font-semibold text-ink-100">{requiredLabel}</span> (or higher) to unlock
		<span class="font-semibold text-ink-100">{feature}</span>.
	</p>
	<a href={`${base}${ctaHref}`} class="btn btn-primary text-xs">
		{ctaText || `Upgrade to ${requiredLabel}`}
	</a>
	<p class="text-xs text-ink-500">Current plan: {currentLabel}</p>
</div>
