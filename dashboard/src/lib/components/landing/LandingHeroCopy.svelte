<script lang="ts">
	let {
		heroTitle,
		heroSubtitle,
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

	<p class="landing-cta-note fade-in-up" style="animation-delay: 320ms;">
		Start free for immediate rollout.
		Want a live proof walkthrough first?
		<a href={demoCtaHref} class="landing-cta-link" onclick={onDemoCta}>See live signal map</a>
	</p>

	<div class="landing-hero-proof-card glass-panel fade-in-up" style="animation-delay: 340ms;">
		<p class="landing-proof-k">Evidence Snapshot · February 28, 2026 (UTC)</p>
		<p class="landing-p">
			<strong>285 validation packs passed</strong> with <strong>0 failed</strong> across Cloud+, SaaS,
			ITAM/license, and connection reporting control paths.
		</p>
		<p class="landing-hero-proof-meta">
			Method note: targeted backend packs plus optimization governance packs in a controlled
			validation run. Capture window: February 28, 2026 (UTC).
		</p>
		<a href="/docs/technical-validation" class="landing-cta-link">View technical validation brief</a>
	</div>

	<div class="landing-hero-mini-visual glass-panel fade-in-up" style="animation-delay: 360ms;">
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
