<script lang="ts">
	import { base } from '$app/paths';
	import { BACKEND_CAPABILITY_PILLARS } from '$lib/landing/heroContent';

	let {
		onTrackCta
	}: {
		onTrackCta: (action: string, section: string, value: string) => void;
	} = $props();

	const featuredCapabilities = BACKEND_CAPABILITY_PILLARS.slice(0, 4);
</script>

<section
	id="capabilities"
	class="container mx-auto px-6 pb-20 landing-section-lazy"
	data-landing-section="capabilities"
>
	<div class="landing-section-head">
		<h2 class="landing-h2">One platform for cloud, SaaS, and license spend control</h2>
		<p class="landing-section-sub">
			Valdrics combines cloud economics, GreenOps, SaaS/license management, remediation, and
			executive proof in one operating layer.
		</p>
	</div>

	<div class="landing-coverage-grid">
		{#each featuredCapabilities as capability (capability.title)}
			<article class="glass-panel landing-coverage-card">
				<p class="landing-proof-k">{capability.title}</p>
				<p class="landing-p">{capability.detail}</p>
			</article>
		{/each}
	</div>
	<div class="landing-validation-cta glass-panel">
		<p class="landing-proof-k">Technical Validation</p>
		<p class="landing-p">
			See the public capability-to-API validation summary used for buyer diligence and security
			reviews.
		</p>
		<a
			href={`${base}/docs/technical-validation`}
			class="landing-cta-link"
			onclick={() => onTrackCta('cta_click', 'capabilities', 'open_technical_validation')}
		>
			Open Technical Validation
		</a>
	</div>
</section>
