<script lang="ts">
	import { HERO_OUTCOME_CHIPS, HERO_PROOF_POINTS } from '$lib/landing/heroContent';

	let {
		heroTitle,
		heroSubtitle,
		heroQuantPromise,
		primaryCtaLabel,
		secondaryCtaLabel,
		secondaryCtaHref,
		primaryCtaHref,
		onPrimaryCta,
		onSecondaryCta,
		onSimulatorCta
	}: {
		heroTitle: string;
		heroSubtitle: string;
		heroQuantPromise: string;
		primaryCtaLabel: string;
		secondaryCtaLabel: string;
		secondaryCtaHref: string;
		primaryCtaHref: string;
		onPrimaryCta: () => void;
		onSecondaryCta: () => void;
		onSimulatorCta: () => void;
	} = $props();
</script>

<div class="landing-copy">
	<div class="landing-kicker fade-in-up" style="animation-delay: 0ms;">
		<span class="badge badge-accent">Cloud + Software Spend Control</span>
		<span class="landing-sep" aria-hidden="true">•</span>
		<span class="landing-kicker-text">See waste early. Act faster. Protect margin.</span>
	</div>

	<div class="landing-problem-hook fade-in-up" style="animation-delay: 70ms;">
		<p class="landing-problem-k">
			The problem is not visibility. The problem is delayed action.
		</p>
		<p class="landing-problem-v">
			When ownership is unclear and approvals happen late, controllable waste compounds every week.
		</p>
	</div>

	<h1 class="landing-title fade-in-up" style="animation-delay: 110ms;">
		{heroTitle}
	</h1>

	<p class="landing-subtitle fade-in-up" style="animation-delay: 220ms;">
		{heroSubtitle}
	</p>
	<div class="landing-quant-promise fade-in-up" style="animation-delay: 250ms;">
		<p class="landing-quant-k">What outcomes-focused teams target</p>
		<p class="landing-quant-v">{heroQuantPromise}</p>
	</div>
	<div class="landing-outcome-chips fade-in-up" style="animation-delay: 285ms;">
		{#each HERO_OUTCOME_CHIPS as chip (chip.label)}
			<div class="landing-outcome-chip">
				<p class="landing-outcome-chip-k">{chip.label}</p>
				<p class="landing-outcome-chip-v">{chip.value}</p>
			</div>
		{/each}
	</div>

	<div class="landing-cta fade-in-up" style="animation-delay: 320ms;">
		<a href={primaryCtaHref} class="btn btn-primary text-base px-8 py-3 pulse-glow" onclick={onPrimaryCta}>
			{primaryCtaLabel}
		</a>
		<a href={secondaryCtaHref} class="btn btn-secondary text-base px-8 py-3" onclick={onSecondaryCta}>
			{secondaryCtaLabel}
		</a>
	</div>
	<p class="landing-cta-free-note fade-in-up" style="animation-delay: 338ms;">
		Start free. Upgrade only when ready.
	</p>
	<div class="landing-free-strip fade-in-up" style="animation-delay: 345ms;">
		<span class="landing-free-pill">Permanent Free Tier</span>
		<span>Start at $0, prove value in your own data, then scale when your team is ready.</span>
	</div>
	<p class="landing-cta-note fade-in-up" style="animation-delay: 360ms;">
		One sign-up path. One workspace. Control cloud and software spend from day one.
	</p>
	<a
		href="#simulator"
		class="landing-cta-link fade-in-up"
		style="animation-delay: 390ms;"
		onclick={onSimulatorCta}
	>
		Run the spend scenario simulator
	</a>

	<div class="landing-proof fade-in-up" style="animation-delay: 420ms;">
		{#each HERO_PROOF_POINTS as point (point.title)}
			<div class="landing-proof-item">
				<p class="landing-proof-k">{point.title}</p>
				<p class="landing-proof-v">{point.detail}</p>
			</div>
		{/each}
	</div>
</div>
