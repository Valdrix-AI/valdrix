<script lang="ts">
	import { base } from '$app/paths';
	import {
		FREE_TIER_HIGHLIGHTS,
		FREE_TIER_LIMIT_NOTE,
		IMPLEMENTATION_COST_FACTS,
		PLAN_COMPARE_CARDS,
		PLANS_PRICING_EXPLANATION
	} from '$lib/landing/heroContent';

	let {
		buildFreeTierCtaHref,
		buildPlanCtaHref,
		talkToSalesHref,
		onTrackCta
	}: {
		buildFreeTierCtaHref: () => string;
		buildPlanCtaHref: (planId: string) => string;
		talkToSalesHref: string;
		onTrackCta: (action: string, section: string, value: string) => void;
	} = $props();
</script>

<section
	id="plans"
	class="container mx-auto px-6 pb-16 landing-section-lazy"
	data-landing-section="plans"
>
	<div class="landing-section-head">
		<h2 class="landing-h2">Choose a plan and launch fast</h2>
		<p class="landing-section-sub">
			Pick the tier that fits your provider coverage, workflow automation depth, and support needs.
		</p>
	</div>

	<div class="landing-plans-pricing-note glass-panel">
		<p class="landing-proof-k">Pricing clarity</p>
		<p class="landing-p">{PLANS_PRICING_EXPLANATION}</p>
	</div>

	<div class="landing-free-tier-card glass-panel">
		<div class="landing-free-tier-head">
			<div>
				<p class="landing-proof-k">Start Free</p>
				<h3 class="landing-h3">Free tier for your first savings workflow</h3>
				<p class="landing-p">
					Start at $0, prove one workflow, and upgrade only when you need more coverage, automation,
					or governance depth.
				</p>
			</div>
			<div class="landing-free-tier-price">
				<p class="landing-free-tier-price-k">Entry Price</p>
				<p class="landing-free-tier-price-v">$0</p>
			</div>
		</div>
		<ul class="landing-plan-features">
			{#each FREE_TIER_HIGHLIGHTS as feature (feature)}
				<li>{feature}</li>
			{/each}
		</ul>
		<p class="landing-free-tier-limit">{FREE_TIER_LIMIT_NOTE}</p>
		<div class="landing-free-tier-cta">
			<a
				href={buildFreeTierCtaHref()}
				class="btn btn-primary"
				onclick={() => onTrackCta('cta_click', 'plans', 'start_plan_free')}
			>
				Start on Free Tier
			</a>
			<span class="landing-free-tier-note">Upgrade later if you need more automation.</span>
		</div>
	</div>

	<div class="landing-plans-grid">
		{#each PLAN_COMPARE_CARDS as plan (plan.id)}
			<article class="glass-panel landing-plan-card">
				<p class="landing-proof-k">{plan.kicker}</p>
				<h3 class="landing-h3">{plan.name}</h3>
				<p class="landing-plan-price">{plan.price}</p>
				<p class="landing-plan-price-note">{plan.priceNote}</p>
				<p class="landing-p">{plan.detail}</p>
				<ul class="landing-plan-features">
					{#each plan.features as feature (feature)}
						<li>{feature}</li>
					{/each}
				</ul>
				<a
					href={buildPlanCtaHref(plan.id)}
					class="btn btn-primary"
					onclick={() => onTrackCta('cta_click', 'plans', `start_plan_${plan.id}`)}
				>
					Start with {plan.name}
				</a>
			</article>
		{/each}
	</div>
	<section class="landing-rollout-section glass-panel" aria-labelledby="rollout-tco-title">
		<p class="landing-proof-k">Rollout clarity</p>
		<h3 id="rollout-tco-title" class="landing-h3">
			Know setup effort before you buy
		</h3>
		<p class="landing-p">
			Estimate software cost and setup effort up front so approval is based on the full picture.
		</p>

		<div class="landing-rollout-grid">
			<article class="landing-rollout-block">
				<p class="landing-proof-k">Setup path</p>
				<ol class="landing-onboard-steps">
					<li>Connect cloud and software sources.</li>
					<li>Assign owners and approval responsibilities.</li>
					<li>Run your first owner-led remediation cycle.</li>
				</ol>
			</article>

			<article class="landing-rollout-block">
				<p class="landing-proof-k">Implementation facts</p>
				<ul class="landing-plan-features">
					{#each IMPLEMENTATION_COST_FACTS as detail (detail)}
						<li>{detail}</li>
					{/each}
				</ul>
			</article>
		</div>

		<div class="landing-rollout-actions">
			<a
				href={`${base}/pricing`}
				class="landing-cta-link"
				onclick={() => onTrackCta('cta_click', 'plans', 'view_full_pricing')}
			>
				View full pricing
			</a>
			<a
				href={talkToSalesHref}
				class="btn btn-secondary"
				onclick={() => onTrackCta('cta_click', 'plans', 'talk_to_sales')}
			>
				Talk to Sales
			</a>
		</div>
	</section>
</section>
