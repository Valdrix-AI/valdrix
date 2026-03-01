<script lang="ts">
	let {
		href,
		onTrackCta
	}: {
		href: string;
		onTrackCta: () => void;
	} = $props();
</script>

<section id="roi" class="container mx-auto px-6 pb-20 landing-section-lazy" data-landing-section="roi">
	<div class="glass-panel landing-validation-cta">
		<p class="landing-proof-k">Advanced ROI Planning</p>
		<h2 class="landing-h2">Need the full 12-month ROI planner?</h2>
		<p class="landing-p">
			Start free and run deeper ROI scenarios in your workspace with team-specific assumptions.
		</p>
		<a href={href} class="btn btn-primary" onclick={onTrackCta}>Open Full ROI Planner</a>
	</div>
</section>
