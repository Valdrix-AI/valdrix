<script lang="ts">
	let {
		href,
		worksheetHref,
		onTrackCta,
		onTrackWorksheetCta
	}: {
		href: string;
		worksheetHref: string;
		onTrackCta: () => void;
		onTrackWorksheetCta: () => void;
	} = $props();
</script>

<section id="roi" class="container mx-auto px-6 pb-16 landing-section-lazy" data-landing-section="roi">
	<div class="glass-panel landing-validation-cta">
		<p class="landing-proof-k">Advanced ROI Planning</p>
		<h2 class="landing-h2">Need the full 12-month ROI planner?</h2>
		<p class="landing-p">
			Start free for deeper team-specific scenarios, or download a worksheet first for internal
			review.
		</p>
		<div class="landing-lead-actions">
			<a href={href} class="btn btn-primary" onclick={onTrackCta}>Open Full ROI Planner</a>
			<a href={worksheetHref} class="btn btn-secondary" onclick={onTrackWorksheetCta}>
				Download ROI Assumptions Worksheet
			</a>
		</div>
	</div>
</section>
