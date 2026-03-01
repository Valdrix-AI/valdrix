<script lang="ts">
	import { base } from '$app/paths';
	import { FREE_TIER_HIGHLIGHTS, PLAN_COMPARE_CARDS } from '$lib/landing/heroContent';

	let {
		buildFreeTierCtaHref,
		buildPlanCtaHref,
		onTrackCta
	}: {
		buildFreeTierCtaHref: () => string;
		buildPlanCtaHref: (planId: string) => string;
		onTrackCta: (action: string, section: string, value: string) => void;
	} = $props();
</script>

<section id="plans" class="container mx-auto px-6 pb-20 landing-section-lazy" data-landing-section="plans">
	<div class="landing-section-head">
		<h2 class="landing-h2">Choose a plan and launch in one sprint</h2>
		<p class="landing-section-sub">
			Shorten the path from sign-up to first savings decision with a plan built for your stage.
		</p>
	</div>

	<div class="landing-free-tier-card glass-panel">
		<div class="landing-free-tier-head">
			<div>
				<p class="landing-proof-k">Start Free</p>
				<h3 class="landing-h3">Permanent free tier for your first savings workflow</h3>
				<p class="landing-p">
					You can start at $0 with bounded usage, prove economic impact, and upgrade only when you
					need expanded scale and automation.
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
		<div class="landing-free-tier-cta">
			<a
				href={buildFreeTierCtaHref()}
				class="btn btn-primary"
				onclick={() => onTrackCta('cta_click', 'plans', 'start_plan_free')}
			>
				Start on Free Tier
			</a>
			<span class="landing-free-tier-note">Upgrade later to Starter, Growth, or Pro.</span>
		</div>
	</div>

	<div class="landing-plans-grid">
		{#each PLAN_COMPARE_CARDS as plan (plan.id)}
			<article class="glass-panel landing-plan-card">
				<p class="landing-proof-k">{plan.kicker}</p>
				<h3 class="landing-h3">{plan.name}</h3>
				<p class="landing-plan-price">{plan.price}</p>
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
	<div class="landing-onboard-flow glass-panel">
		<p class="landing-proof-k">Fast onboarding flow</p>
		<ol class="landing-onboard-steps">
			<li>Connect cloud and software sources.</li>
			<li>Assign owners and approval responsibilities.</li>
			<li>Run your first owner-led remediation cycle.</li>
		</ol>
		<a
			href={`${base}/pricing`}
			class="landing-cta-link"
			onclick={() => onTrackCta('cta_click', 'plans', 'view_full_pricing')}
		>
			View full pricing and feature details
		</a>
	</div>
</section>
