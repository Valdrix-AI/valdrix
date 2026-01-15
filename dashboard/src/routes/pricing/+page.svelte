<!--
  Pricing Page - Public Landing Page for Plans
  
  Features:
  - USD pricing with NGN payment note
  - Highlight Growth as "Most Popular"
  - 14-day trial CTA
  - Feature comparison table
-->

<script lang="ts">
  import { PUBLIC_API_URL } from '$env/static/public';
  import { createSupabaseBrowserClient } from '$lib/supabase';
  import { goto } from '$app/navigation';
  
  let { data } = $props();
  
  const supabase = createSupabaseBrowserClient();
  
  let upgrading = $state('');
  let error = $state('');
  
  const plans = [
    {
      id: 'starter',
      name: 'Starter',
      price: 29,
      period: '/mo',
      description: 'For small teams getting started with cloud cost visibility.',
      features: [
        'Single cloud provider (AWS)',
        'Cost dashboards & trends',
        'Budget alerts',
        'Basic zombie detection',
        'Email notifications',
        'Up to $10K monthly cloud spend'
      ],
      cta: 'Start with Starter',
      popular: false
    },
    {
      id: 'growth',
      name: 'Growth',
      price: 79,
      period: '/mo',
      description: 'For growing teams who need AI-powered cost intelligence.',
      features: [
        'Everything in Starter, plus:',
        'Multi-cloud support (AWS, Azure, GCP)',
        'AI-driven cost analysis',
        'Full zombie detection suite',
        'GreenOps (Carbon tracking)',
        'Slack integration',
        'Cost forecasting (30-90 days)',
        'Up to $50K monthly cloud spend'
      ],
      cta: 'Start Free Trial',
      popular: true
    },
    {
      id: 'pro',
      name: 'Pro',
      price: 199,
      period: '/mo',
      description: 'For teams who want automated optimization and full API access.',
      features: [
        'Everything in Growth, plus:',
        'Automated remediation (opt-in)',
        'Reserved Instance intelligence',
        'Full API access (read + write)',
        'Advanced forecasting',
        'Priority support',
        'Up to $200K monthly cloud spend'
      ],
      cta: 'Start Free Trial',
      popular: false
    }
  ];
  
  async function selectPlan(planId: string) {
    if (upgrading) return;
    
    // If not logged in, redirect to signup
    if (!data.user) {
      goto(`/auth/signup?plan=${planId}`);
      return;
    }
    
    upgrading = planId;
    
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) throw new Error('Not authenticated');
      
      const res = await fetch(`${PUBLIC_API_URL}/billing/checkout`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${session.access_token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ tier: planId })
      });
      
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Checkout failed');
      }
      
      const { checkout_url } = await res.json();
      window.location.href = checkout_url;
      
    } catch (e: any) {
      error = e.message;
      upgrading = '';
    }
  }
  
  function startTrial() {
    if (!data.user) {
      goto('/auth/signup?trial=true');
    } else {
      goto('/');
    }
  }
</script>

<svelte:head>
  <title>Pricing | Valdrix</title>
  <meta name="description" content="Simple, transparent pricing for cloud cost optimization. Start with a 14-day free trial." />
</svelte:head>

<div class="pricing-page">
  <!-- Hero Section -->
  <div class="hero-section">
    <h1 class="hero-title">Simple, Transparent Pricing</h1>
    <p class="hero-subtitle">
      Start with a <strong>14-day free trial</strong>. No credit card required.
    </p>
  </div>
  
  {#if error}
    <div class="error-banner">
      <p>{error}</p>
      <button onclick={() => error = ''}>Dismiss</button>
    </div>
  {/if}
  
  <!-- Pricing Cards -->
  <div class="pricing-grid">
    {#each plans as plan, i}
      <div class="pricing-card {plan.popular ? 'popular' : ''}" style="animation-delay: {i * 100}ms;">
        {#if plan.popular}
          <div class="popular-badge">Most Popular</div>
        {/if}
        
        <div class="card-header">
          <h2 class="plan-name">{plan.name}</h2>
          <p class="plan-description">{plan.description}</p>
        </div>
        
        <div class="plan-price">
          <span class="currency">$</span>
          <span class="amount">{plan.price}</span>
          <span class="period">{plan.period}</span>
        </div>
        
        <ul class="feature-list">
          {#each plan.features as feature}
            <li>
              <span class="check-icon">✓</span>
              {feature}
            </li>
          {/each}
        </ul>
        
        <button 
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
        <li>Unlimited cloud spend</li>
        <li>SSO (SAML/OIDC)</li>
        <li>Dedicated support & SLA</li>
        <li>Custom integrations</li>
      </ul>
    </div>
    <a href="mailto:enterprise@valdrix.io" class="enterprise-cta">Contact Sales</a>
  </div>
  
  <!-- Payment Note -->
  <div class="payment-note">
    <p>
      <strong>💳 Secure payments via Paystack.</strong> 
      Prices shown in USD. Payment processed in NGN at current exchange rate.
    </p>
  </div>
  
  <!-- FAQ Section -->
  <div class="faq-section">
    <h2>Frequently Asked Questions</h2>
    
    <div class="faq-grid">
      <div class="faq-item">
        <h3>What happens after my trial ends?</h3>
        <p>After 14 days, you'll be prompted to choose a paid plan. No automatic charges—ever.</p>
      </div>
      
      <div class="faq-item">
        <h3>Can I upgrade or downgrade anytime?</h3>
        <p>Yes! You can change plans at any time. Changes take effect on your next billing cycle.</p>
      </div>
      
      <div class="faq-item">
        <h3>What cloud providers do you support?</h3>
        <p>Starter supports AWS. Growth and Pro support AWS, Azure, and GCP.</p>
      </div>
      
      <div class="faq-item">
        <h3>Is my data secure?</h3>
        <p>Yes. We use read-only IAM roles and never store your cloud credentials.</p>
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
  .hero-section {
    text-align: center;
    margin-bottom: 3rem;
  }
  
  .hero-title {
    font-size: 2.5rem;
    font-weight: 700;
    background: linear-gradient(135deg, var(--color-accent-400), var(--color-primary-400));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 0.75rem;
  }
  
  .hero-subtitle {
    color: var(--color-ink-400);
    font-size: 1.125rem;
  }
  
  .hero-subtitle strong {
    color: var(--color-accent-400);
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
    transition: transform 0.2s, box-shadow 0.2s;
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
    font-size: 0.75rem;
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
    to { transform: rotate(360deg); }
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
