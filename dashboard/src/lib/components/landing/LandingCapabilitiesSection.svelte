<script lang="ts">
	import {
		DECISION_LEDGER_STEPS,
		DECISION_LEDGER_SUMMARY,
		TRUST_ECOSYSTEM_BADGES
	} from '$lib/landing/heroContent';

	const decisionLedger = DECISION_LEDGER_STEPS;
	const coverageSummary = DECISION_LEDGER_SUMMARY;
</script>

<section
	id="capabilities"
	class="container mx-auto px-6 pb-16 landing-section-lazy"
	data-landing-section="capabilities"
>
	<div class="landing-section-head">
		<h2 class="landing-h2">What happens between alert and action</h2>
		<p class="landing-section-sub">
			Most platforms stop at detection. Valdrics keeps the owner, guardrails, approval, and
			outcome visible until the action is complete.
		</p>
	</div>

	<div class="glass-panel landing-coverage-surface landing-ledger-surface">
		<div class="landing-coverage-surface-copy">
			<p class="landing-proof-k">Decision operating layer</p>
			<h3 class="landing-h3">This is not another dashboard layer.</h3>
			<p class="landing-p">
				Valdrics is built around the missing motion after detection: who owns the issue, what
				checks apply, who approves it, and how the outcome gets recorded.
			</p>
			<div class="landing-coverage-summary" aria-label="Coverage summary">
				{#each coverageSummary as item (item.label)}
					<div class="landing-coverage-summary-item">
						<p class="landing-coverage-summary-k">{item.label}</p>
						<p class="landing-coverage-summary-v">{item.value}</p>
					</div>
				{/each}
			</div>
		</div>
		<div class="landing-coverage-surface-side">
			<p class="landing-proof-k">Connected inputs</p>
			<div class="landing-coverage-badges" aria-label="Platform coverage">
				{#each TRUST_ECOSYSTEM_BADGES as badge (badge)}
					<span class="landing-coverage-badge">{badge}</span>
				{/each}
			</div>
		</div>
	</div>

	<div class="landing-coverage-grid-head">
		<p class="landing-proof-k">Decision ledger</p>
		<p class="landing-p">This is the path most competitor pages skip.</p>
	</div>

	<div class="landing-decision-ledger">
		{#each decisionLedger as entry (entry.title)}
			<article class="glass-panel landing-decision-card">
				<div class="landing-decision-card-head">
					<p class="landing-decision-step">{entry.step}</p>
					<p class="landing-proof-k">{entry.kicker}</p>
				</div>
				<h3 class="landing-h3">{entry.title}</h3>
				<p class="landing-p">{entry.detail}</p>
				<p class="landing-decision-meta">{entry.meta}</p>
			</article>
		{/each}
	</div>
</section>
