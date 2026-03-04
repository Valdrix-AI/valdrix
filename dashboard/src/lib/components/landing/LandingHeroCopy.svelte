<script lang="ts">
	let {
		heroTitle,
		heroSubtitle,
		primaryCtaLabel,
		secondaryCtaLabel,
		secondaryCtaHref,
		primaryCtaHref,
		onPrimaryCta,
		onSecondaryCta
	}: {
		heroTitle: string;
		heroSubtitle: string;
		primaryCtaLabel: string;
		secondaryCtaLabel: string;
		secondaryCtaHref: string;
		primaryCtaHref: string;
		onPrimaryCta: () => void;
		onSecondaryCta: () => void;
	} = $props();
</script>

<div class="landing-copy">
	<div class="landing-kicker fade-in-up" style="animation-delay: 0ms;">
		<span class="badge badge-accent">Cloud, Software, and Carbon Spend Control</span>
		<span class="landing-sep" aria-hidden="true">•</span>
		<span class="landing-kicker-text"
			>See waste and intensity early. Act faster. Protect margin.</span
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

	<div class="landing-cta fade-in-up" style="animation-delay: 280ms;">
		<a
			href={primaryCtaHref}
			class="btn btn-primary text-base px-8 py-3 pulse-glow"
			onclick={onPrimaryCta}
		>
			{primaryCtaLabel}
		</a>
		<a
			href={secondaryCtaHref}
			class="btn btn-secondary text-base px-8 py-3"
			onclick={onSecondaryCta}
		>
			{secondaryCtaLabel}
		</a>
	</div>
	<p class="landing-cta-free-note fade-in-up" style="animation-delay: 300ms;">
		Start free. Upgrade only when ready.
	</p>

	<div class="landing-hero-mini-visual glass-panel fade-in-up" style="animation-delay: 340ms;">
		<p class="landing-proof-k">One Control Loop</p>
		<div class="landing-hero-flow" role="list" aria-label="Valdrics control loop overview">
			<div class="landing-hero-flow-step" role="listitem">
				<p class="landing-hero-flow-step-k">Detect</p>
				<p class="landing-hero-flow-step-v">Live spend movement</p>
			</div>
			<div class="landing-hero-flow-step" role="listitem">
				<p class="landing-hero-flow-step-k">Assign</p>
				<p class="landing-hero-flow-step-v">Owner + approval path</p>
			</div>
			<div class="landing-hero-flow-step" role="listitem">
				<p class="landing-hero-flow-step-k">Act</p>
				<p class="landing-hero-flow-step-v">Safe, measurable remediation</p>
			</div>
		</div>
	</div>
</div>
