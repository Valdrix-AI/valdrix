<script lang="ts">
	let {
		href,
		onTrackCta
	}: {
		href: string;
		onTrackCta: () => void;
	} = $props();
</script>

<section id="roi" class="container mx-auto px-6 pb-16 landing-section-lazy" data-landing-section="roi">
	<div class="glass-panel landing-validation-cta">
		<p class="landing-proof-k">Advanced ROI Planning</p>
		<h2 class="landing-h2">Need the full 12-month ROI planner?</h2>
		<p class="landing-p">
			Start free for deeper team-specific scenarios. Preview the model snapshot below before you open
			the full planner.
		</p>

		<div class="landing-roi-snapshot" aria-label="Example ROI model snapshot">
			<p class="landing-roi-snapshot-k">Example 12-month model snapshot</p>
			<div class="landing-roi-snapshot-metrics">
				<div class="landing-roi-snapshot-metric">
					<p>Projected annual spend</p>
					<strong>$1.44M</strong>
				</div>
				<div class="landing-roi-snapshot-metric">
					<p>Controllable waste opportunity</p>
					<strong class="is-positive">$172K</strong>
				</div>
				<div class="landing-roi-snapshot-metric">
					<p>Modeled payback window</p>
					<strong>6-9 weeks</strong>
				</div>
			</div>
			<div class="landing-roi-snapshot-bars" aria-hidden="true">
				<div class="landing-roi-snapshot-row">
					<span>Reactive path</span>
					<div><i style="width: 100%;"></i></div>
				</div>
				<div class="landing-roi-snapshot-row">
					<span>Governed path</span>
					<div><i style="width: 62%;"></i></div>
				</div>
			</div>
		</div>

		<a href={href} class="btn btn-primary w-fit" onclick={onTrackCta}>Open Full ROI Planner</a>
	</div>
</section>
