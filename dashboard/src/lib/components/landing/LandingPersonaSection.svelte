<script lang="ts">
	import { BUYER_ROLE_VIEWS } from '$lib/landing/heroContent';

	type BuyerRoleView = {
		id: string;
		label: string;
		headline: string;
		detail: string;
		signals: readonly string[];
		thirtyDayOutcomes: readonly string[];
	};

	let {
		activeBuyerRole,
		buyerRoleIndex,
		onSelectBuyerRole
	}: {
		activeBuyerRole: BuyerRoleView;
		buyerRoleIndex: number;
		onSelectBuyerRole: (index: number) => void;
	} = $props();
</script>

<section
	id="personas"
	class="container mx-auto px-6 pb-16 landing-section-lazy"
	data-landing-section="personas"
>
	<div class="landing-section-head">
		<h2 class="landing-h2">What each team gets in the first 30 days</h2>
		<p class="landing-section-sub">
			Engineering, FinOps, security, and leadership use one system, but each role sees tailored
			outcomes.
		</p>
	</div>

	<div class="landing-buyer-switch" role="tablist" aria-label="Buyer role views">
		{#each BUYER_ROLE_VIEWS as role, index (role.id)}
			<button
				type="button"
				role="tab"
				id={`buyer-tab-${role.id}`}
				class="landing-buyer-btn"
				class:is-active={buyerRoleIndex === index}
				aria-selected={buyerRoleIndex === index}
				aria-controls={`buyer-panel-${role.id}`}
				tabindex={buyerRoleIndex === index ? 0 : -1}
				onclick={() => onSelectBuyerRole(index)}
			>
				{role.label}
			</button>
		{/each}
	</div>

	<div
		class="glass-panel landing-buyer-panel"
		role="tabpanel"
		id={`buyer-panel-${activeBuyerRole.id}`}
		aria-labelledby={`buyer-tab-${activeBuyerRole.id}`}
	>
		<p class="landing-proof-k">{activeBuyerRole.label} Priority</p>
		<h3 class="landing-h3">{activeBuyerRole.headline}</h3>
		<p class="landing-p">{activeBuyerRole.detail}</p>
		<div class="landing-buyer-signals">
			{#each activeBuyerRole.signals as signal (signal)}
				<span class="landing-buyer-signal">{signal}</span>
			{/each}
		</div>
		<div class="landing-buyer-outcomes">
			<p class="landing-proof-k">In 30 days</p>
			<ul>
				{#each activeBuyerRole.thirtyDayOutcomes as outcome (outcome)}
					<li>{outcome}</li>
				{/each}
			</ul>
		</div>
	</div>
	<div class="landing-persona-proof">
		Outcome: one system that improves weekly operating decisions across technical and financial teams.
	</div>
</section>
