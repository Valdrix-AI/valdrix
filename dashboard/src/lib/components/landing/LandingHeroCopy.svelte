<script lang="ts">
	import { base } from '$app/paths';
	import { ABOVE_FOLD_TRUST_RAIL } from '$lib/landing/heroContent';

	const heroTrustRail = ABOVE_FOLD_TRUST_RAIL;

	let {
		heroTitle,
		heroSubtitle,
		quantPromise = '',
		primaryCtaLabel,
		secondaryCtaLabel,
		secondaryCtaHref,
		demoCtaHref = '#signal-map',
		primaryCtaHref,
		onPrimaryCta,
		onSecondaryCta,
		onDemoCta = () => {}
	}: {
		heroTitle: string;
		heroSubtitle: string;
		quantPromise?: string;
		primaryCtaLabel: string;
		secondaryCtaLabel: string;
		secondaryCtaHref: string;
		demoCtaHref?: string;
		primaryCtaHref: string;
		onPrimaryCta: () => void;
		onSecondaryCta: () => void;
		onDemoCta?: () => void;
	} = $props();
</script>

<div class="landing-copy">
	<div class="landing-kicker fade-in-up" style="animation-delay: 0ms;">
		<span class="badge badge-accent">Decision operating layer for spend control</span>
		<span class="landing-sep" aria-hidden="true">•</span>
		<span class="landing-kicker-text"
			>Route the right owner. Apply checks. Record the outcome.</span
		>
	</div>

	<h1 class="landing-title fade-in-up" style="animation-delay: 80ms;">
		{heroTitle}
	</h1>

	<p class="landing-subtitle fade-in-up" style="animation-delay: 180ms;">
		{heroSubtitle}
	</p>

	<div class="landing-problem-hook fade-in-up" style="animation-delay: 230ms;">
		<p class="landing-problem-k">The problem is not visibility. The problem is delayed action.</p>
		<p class="landing-problem-v">
			When ownership is unclear and approvals happen late, controllable waste compounds every week.
		</p>
	</div>

	<div class="landing-cta fade-in-up" style="animation-delay: 270ms;">
		<a
			href={primaryCtaHref}
			class="btn btn-primary landing-cta-primary text-base px-8 py-3 pulse-glow"
			onclick={onPrimaryCta}
		>
			{primaryCtaLabel}
		</a>
		<a
			href={secondaryCtaHref}
			class="btn btn-secondary landing-cta-secondary text-base px-8 py-3"
			onclick={onSecondaryCta}
		>
			{secondaryCtaLabel}
		</a>
	</div>

	<div class="landing-hero-credibility fade-in-up" style="animation-delay: 300ms;">
		<p class="landing-hero-credibility-k">What you can verify now</p>
		<div class="landing-hero-proof-rail" role="list" aria-label="Prelaunch proof in hero">
			{#each heroTrustRail as item (item.title)}
				<article class="landing-hero-proof-rail-item" role="listitem">
					<p class="landing-hero-proof-rail-title">{item.title}</p>
					<p class="landing-hero-proof-rail-detail">{item.detail}</p>
				</article>
			{/each}
		</div>
		<p class="landing-hero-credibility-note">
			Verify now:
			<a href={`${base}/docs/technical-validation`} class="landing-cta-link">
				Technical validation
			</a>
			<span aria-hidden="true">•</span>
			<a href={`${base}/resources/global-finops-compliance-workbook.md`} class="landing-cta-link">
				Access checklist
			</a>
			<span aria-hidden="true">•</span>
			<a href={demoCtaHref} class="landing-cta-link" onclick={onDemoCta}>Live signal map</a>
		</p>
	</div>

	{#if quantPromise}
		<div class="landing-quant-promise fade-in-up" style="animation-delay: 330ms;">
			<p class="landing-quant-k">Modeled first-quarter range</p>
			<p class="landing-quant-v">{quantPromise}</p>
			<p class="landing-quant-meta">
				Based on targeted validation packs and rollout assumptions.
				<a href={`${base}/docs/technical-validation`} class="landing-cta-link">
					Review methodology
				</a>
			</p>
		</div>
	{/if}
</div>
