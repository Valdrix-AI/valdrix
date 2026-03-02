<!--
  Pricing Page - Public Landing Page for Plans
  
  Features:
  - USD pricing with NGN payment note
  - BYOK available in current plans with no additional platform surcharge
  - Highlight Growth as "Most Popular"
  - Permanent free tier CTA
  - Feature comparison table
-->

<script lang="ts">
	/* eslint-disable svelte/no-navigation-without-resolve */
	import { assets, base } from '$app/paths';
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import { edgeApiPath } from '$lib/edgeProxy';
	import { normalizeCheckoutUrl } from '$lib/utils';
	import { page } from '$app/stores';
	import type { PageData } from './$types';
	import type { PricingPlan } from './plans';
	import { DEFAULT_PRICING_PLANS } from './plans';

	let { data }: { data: PageData } = $props();

	let billingCycle = $state('monthly'); // 'monthly' or 'annual'
	let upgrading = $state(''); // plan ID being upgraded to
	let error = $state(''); // error message for display
	let plans = $derived<PricingPlan[]>(
		Array.isArray(data.plans) && data.plans.length > 0 ? data.plans : DEFAULT_PRICING_PLANS
	);

	async function selectPlan(planId: string) {
		if (upgrading) return;

		// If not logged in, redirect to signup
		if (!data.user) {
			goto(`${base}/auth/login?mode=signup&plan=${planId}&cycle=${billingCycle}`);
			return;
		}

		upgrading = planId;

		try {
			const session = data.session;
			if (!session) throw new Error('Not authenticated');

			const res = await api.post(
				edgeApiPath('/billing/checkout'),
				{
					tier: planId,
					billing_cycle: billingCycle
				},
				{
					headers: {
						Authorization: `Bearer ${session.access_token}`
					}
				}
			);

			if (!res.ok) {
				const err = await res.json();
				throw new Error(err.detail || 'Checkout failed');
			}

			const { checkout_url } = await res.json();
			window.location.assign(normalizeCheckoutUrl(checkout_url, window.location.origin));
		} catch (e) {
			const err = e as Error;
			error = err.message;
			upgrading = '';
		}
	}
</script>

<svelte:head>
	<title>Pricing | Valdrics</title>
	<meta
		name="description"
		content="Simple, transparent pricing for cloud cost optimization. Start on a permanent free tier, with BYOK available in current plans."
	/>
	<meta property="og:title" content="Pricing | Valdrics" />
	<meta
		property="og:description"
		content="Simple, transparent pricing for cloud cost optimization. Start on a permanent free tier, with BYOK available in current plans."
	/>
	<meta property="og:type" content="website" />
	<meta property="og:url" content={new URL($page.url.pathname, $page.url.origin).toString()} />
	<meta
		property="og:image"
		content={new URL(`${assets}/og-image.png`, $page.url.origin).toString()}
	/>
	<meta name="twitter:card" content="summary_large_image" />
	<meta name="twitter:title" content="Pricing | Valdrics" />
	<meta
		name="twitter:description"
		content="Simple, transparent pricing for cloud cost optimization. Start on a permanent free tier, with BYOK available in current plans."
	/>
	<meta
		name="twitter:image"
		content={new URL(`${assets}/og-image.png`, $page.url.origin).toString()}
	/>
</svelte:head>

<div class="pricing-page">
	<!-- Hero Section -->
	<div class="hero-section">
		<h1 class="hero-title">Simple, Transparent Pricing</h1>
		<p class="hero-subtitle">
			Start with a <strong>permanent free tier</strong>. BYOK is available across current plans with
			no additional platform surcharge.
		</p>

		<!-- Cycle Toggle -->
		<div class="cycle-toggle-container">
			<span class={billingCycle === 'monthly' ? 'active' : ''}>Monthly</span>
			<button
				type="button"
				class="cycle-toggle-switch {billingCycle === 'annual' ? 'annual' : ''}"
				onclick={() => (billingCycle = billingCycle === 'monthly' ? 'annual' : 'monthly')}
				aria-label="Toggle billing cycle"
				role="switch"
				aria-checked={billingCycle === 'annual'}
			>
				<span class="toggle-knob"></span>
			</button>
			<span class={billingCycle === 'annual' ? 'active' : ''}>
				Yearly
				<span class="savings-badge">Save 17%</span>
			</span>
		</div>
	</div>

	{#if error}
		<div class="error-banner">
			<p>{error}</p>
			<button type="button" onclick={() => (error = '')}>Dismiss</button>
		</div>
	{/if}

	<!-- Pricing Grid -->
	<div class="pricing-grid">
		{#each plans as plan, i (plan.id)}
			<div
				class="pricing-card {plan.popular ? 'popular' : ''}"
				style="animation-delay: {i * 100}ms;"
			>
				{#if plan.popular}
					<div class="popular-badge">Most Popular</div>
				{/if}

				<div class="card-header">
					<h2 class="plan-name">{plan.name}</h2>
					<p class="plan-description">{plan.description}</p>
				</div>

				<div class="plan-price">
					<span class="currency">$</span>
					<span class="amount">
						{billingCycle === 'monthly' ? plan.price_monthly : Math.round(plan.price_annual / 12)}
					</span>
					<span class="period">
						{billingCycle === 'monthly' ? '/mo' : '/mo, billed yearly'}
					</span>
				</div>

				<ul class="feature-list">
					{#each plan.features as feature (feature)}
						<li>
							<span class="check-icon">✓</span>
							{feature}
						</li>
					{/each}
				</ul>

				<button
					type="button"
					class="cta-button {plan.popular ? 'primary' : 'secondary'}"
					onclick={() => selectPlan(plan.id)}
					disabled={!!upgrading}
					aria-label="{plan.cta} for {plan.name} plan"
				>
					{#if upgrading === plan.id}
						<span class="spinner" aria-hidden="true"></span>
						Processing...
					{:else}
						{plan.cta}
					{/if}
				</button>
			</div>
		{/each}
	</div>

	<!-- Enterprise Section -->
	<div class="enterprise-section">
		<div class="enterprise-content">
			<h2>Enterprise</h2>
			<p>For organizations with complex requirements and high cloud spend.</p>
			<ul>
				<li>Designed for high cloud spend</li>
				<li>SSO (SAML/OIDC)</li>
				<li>Dedicated support & SLA</li>
				<li>Custom integrations</li>
			</ul>
		</div>
		<a href="mailto:enterprise@valdrics.io" class="enterprise-cta">Contact Sales</a>
	</div>

	<!-- Payment Note -->
	<div class="payment-note">
		<p>
			<strong>Secure payments via Paystack.</strong>
			Prices are listed in USD. Checkout is currently processed in NGN at the live exchange rate. BYOK
			does not add a separate platform surcharge.
		</p>
	</div>

	<!-- FAQ Section -->
	<div class="faq-section">
		<h2>Frequently Asked Questions</h2>

		<div class="faq-grid">
			<div class="faq-item">
				<h3>How does the free tier work?</h3>
				<p>
					The free tier is permanent with usage limits. Upgrade anytime when you need more scale.
				</p>
			</div>

			<div class="faq-item">
				<h3>Is BYOK available on every tier?</h3>
				<p>
					In the current lineup, Free, Starter, Growth, and Pro can use BYOK. Daily AI usage limits
					still apply by tier.
				</p>
			</div>

			<div class="faq-item">
				<h3>Can I upgrade or downgrade anytime?</h3>
				<p>
					You can request plan changes at any time. Most changes take effect on your next billing
					cycle.
				</p>
			</div>

			<div class="faq-item">
				<h3>What cloud providers do you support?</h3>
				<p>Starter supports AWS. Growth and Pro support AWS, Azure, and GCP.</p>
			</div>

			<div class="faq-item">
				<h3>Is my data secure?</h3>
				<p>
					We use read-only cloud roles where supported, and connector secrets are stored encrypted
					at rest.
				</p>
			</div>
		</div>
	</div>
</div>

<style>
	.pricing-page {
		max-width: 1200px;
		margin: 0 auto;
		padding: 2rem;
	}

	/* Hero */
	.hero-subtitle {
		color: var(--color-ink-400);
		font-size: 1.125rem;
		margin-bottom: 2rem;
	}

	.hero-subtitle strong {
		color: var(--color-accent-400);
	}

	/* Cycle Toggle */
	.cycle-toggle-container {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 1rem;
		margin-bottom: 2rem;
		font-weight: 500;
	}

	.cycle-toggle-container span {
		color: var(--color-ink-400);
		transition: color 0.2s;
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.cycle-toggle-container span.active {
		color: var(--color-ink-100);
	}

	.cycle-toggle-switch {
		width: 64px;
		height: 32px;
		background: var(--color-surface-200);
		border: 1px solid var(--color-surface-300);
		border-radius: 999px;
		position: relative;
		cursor: pointer;
		transition: background 0.2s;
		padding: 2px;
	}

	.cycle-toggle-switch.annual {
		background: var(--color-accent-500);
		border-color: var(--color-accent-600);
	}

	.toggle-knob {
		width: 26px;
		height: 26px;
		background: white;
		border-radius: 50%;
		position: absolute;
		top: 2px;
		left: 2px;
		transition: transform 0.2s;
		box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
	}

	.cycle-toggle-switch.annual .toggle-knob {
		transform: translateX(32px);
	}

	.savings-badge {
		background: rgba(var(--color-success-500-rgb), 0.15);
		color: var(--color-success-400);
		font-size: var(--text-xs);
		padding: 0.125rem 0.5rem;
		border-radius: 999px;
		border: 1px solid rgba(var(--color-success-500-rgb), 0.3);
	}

	/* Error Banner */
	.error-banner {
		background: rgba(239, 68, 68, 0.15);
		border: 1px solid rgba(239, 68, 68, 0.3);
		border-radius: 0.5rem;
		padding: 1rem;
		margin-bottom: 2rem;
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.error-banner p {
		color: #f87171;
	}

	.error-banner button {
		background: transparent;
		border: none;
		color: #f87171;
		cursor: pointer;
	}

	/* Pricing Grid */
	.pricing-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
		gap: 1.5rem;
		margin-bottom: 3rem;
	}

	.pricing-card {
		background: var(--color-surface-100);
		border: 1px solid var(--color-surface-200);
		border-radius: 1rem;
		padding: 2rem;
		position: relative;
		transition:
			transform 0.2s,
			box-shadow 0.2s;
		animation: slideUp 0.5s ease-out both;
	}

	.pricing-card:hover {
		transform: translateY(-4px);
		box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
	}

	.pricing-card.popular {
		border-color: var(--color-accent-500);
		background: linear-gradient(135deg, rgba(var(--color-accent-500-rgb), 0.1), transparent);
	}

	.popular-badge {
		position: absolute;
		top: -12px;
		left: 50%;
		transform: translateX(-50%);
		background: linear-gradient(135deg, var(--color-accent-500), var(--color-primary-500));
		color: white;
		padding: 0.375rem 1rem;
		border-radius: 999px;
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.card-header {
		margin-bottom: 1.5rem;
	}

	.plan-name {
		font-size: 1.5rem;
		font-weight: 600;
		margin-bottom: 0.5rem;
	}

	.plan-description {
		color: var(--color-ink-400);
		font-size: 0.875rem;
		line-height: 1.5;
	}

	.plan-price {
		margin-bottom: 1.5rem;
	}

	.currency {
		font-size: 1.5rem;
		font-weight: 500;
		vertical-align: top;
	}

	.amount {
		font-size: 3.5rem;
		font-weight: 700;
		line-height: 1;
	}

	.period {
		color: var(--color-ink-400);
		font-size: 1rem;
	}

	.feature-list {
		list-style: none;
		padding: 0;
		margin: 0 0 2rem 0;
	}

	.feature-list li {
		display: flex;
		align-items: flex-start;
		gap: 0.75rem;
		padding: 0.5rem 0;
		font-size: 0.9rem;
		color: var(--color-ink-300);
	}

	.check-icon {
		color: var(--color-success-400);
		font-weight: bold;
		flex-shrink: 0;
	}

	.cta-button {
		width: 100%;
		padding: 0.875rem 1.5rem;
		border-radius: 0.5rem;
		font-weight: 600;
		cursor: pointer;
		transition: all 0.2s;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
	}

	.cta-button.primary {
		background: linear-gradient(135deg, var(--color-accent-500), var(--color-primary-500));
		border: none;
		color: white;
	}

	.cta-button.primary:hover {
		transform: scale(1.02);
		box-shadow: 0 4px 12px rgba(var(--color-accent-500-rgb), 0.4);
	}

	.cta-button.secondary {
		background: transparent;
		border: 1px solid var(--color-surface-300);
		color: var(--color-ink-200);
	}

	.cta-button.secondary:hover {
		border-color: var(--color-accent-500);
		color: var(--color-accent-400);
	}

	.cta-button:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	/* Enterprise Section */
	.enterprise-section {
		background: var(--color-surface-100);
		border: 1px solid var(--color-surface-200);
		border-radius: 1rem;
		padding: 2rem;
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 2rem;
		margin-bottom: 2rem;
	}

	.enterprise-content h2 {
		font-size: 1.5rem;
		margin-bottom: 0.5rem;
	}

	.enterprise-content p {
		color: var(--color-ink-400);
		margin-bottom: 1rem;
	}

	.enterprise-content ul {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem 1.5rem;
		list-style: none;
		padding: 0;
	}

	.enterprise-content li {
		color: var(--color-ink-300);
		font-size: 0.875rem;
	}

	.enterprise-content li::before {
		content: '✓ ';
		color: var(--color-success-400);
	}

	.enterprise-cta {
		background: var(--color-surface-200);
		color: var(--color-ink-200);
		padding: 0.875rem 2rem;
		border-radius: 0.5rem;
		text-decoration: none;
		font-weight: 600;
		white-space: nowrap;
		transition: all 0.2s;
	}

	.enterprise-cta:hover {
		background: var(--color-surface-300);
	}

	/* Payment Note */
	.payment-note {
		text-align: center;
		padding: 1rem;
		background: rgba(var(--color-accent-500-rgb), 0.1);
		border-radius: 0.5rem;
		margin-bottom: 3rem;
	}

	.payment-note p {
		color: var(--color-ink-300);
		font-size: 0.875rem;
	}

	/* FAQ */
	.faq-section {
		margin-top: 3rem;
	}

	.faq-section h2 {
		text-align: center;
		font-size: 1.5rem;
		margin-bottom: 2rem;
	}

	.faq-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
		gap: 1.5rem;
	}

	.faq-item {
		background: var(--color-surface-100);
		border-radius: 0.75rem;
		padding: 1.5rem;
	}

	.faq-item h3 {
		font-size: 1rem;
		font-weight: 600;
		margin-bottom: 0.5rem;
	}

	.faq-item p {
		color: var(--color-ink-400);
		font-size: 0.875rem;
		line-height: 1.6;
	}

	/* Spinner */
	.spinner {
		width: 16px;
		height: 16px;
		border: 2px solid transparent;
		border-top-color: currentColor;
		border-radius: 50%;
		animation: spin 0.6s linear infinite;
	}

	@keyframes slideUp {
		from {
			opacity: 0;
			transform: translateY(20px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	/* Responsive */
	@media (max-width: 768px) {
		.hero-title {
			font-size: 1.75rem;
		}

		.enterprise-section {
			flex-direction: column;
			text-align: center;
		}

		.enterprise-content ul {
			justify-content: center;
		}
	}
</style>
