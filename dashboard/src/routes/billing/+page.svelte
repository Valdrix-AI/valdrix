<!--
  Billing Page - Paystack Integration
  
  Features:
  - Current plan display with glassmorphism
  - Pricing tier cards
  - Upgrade flow integration
-->

<script lang="ts">
  import { PUBLIC_API_URL } from '$env/static/public';
  import { createSupabaseBrowserClient } from '$lib/supabase';
  
  let { data } = $props();
  
  const supabase = createSupabaseBrowserClient();
  
  let loading = $state(true);
  let subscription = $state<any>(null);
  let error = $state('');
  let upgrading = $state('');
  let billingCycle = $state('monthly');
  
  let plans = $state<any[]>([]);

  $effect(() => {
    if (!data.user) {
      loading = false;
      return;
    }
    loadSubscription();
    loadPlans();
  });
  
  async function loadSubscription() {
    try {
      const session = data.session;
      if (!session) return;
      
      const res = await fetch(`${PUBLIC_API_URL}/billing/subscription`, {
        headers: { 'Authorization': `Bearer ${session.access_token}` }
      });
      
      if (res.ok) {
        subscription = await res.json();
      } else {
        subscription = { tier: 'free', status: 'active' };
      }
    } catch (e: any) {
      error = e.message;
      subscription = { tier: 'free', status: 'active' };
    } finally {
      loading = false;
    }
  }

  async function loadPlans() {
    try {
      const res = await fetch(`${PUBLIC_API_URL}/billing/plans`);
      if (res.ok) {
        plans = await res.json();
      }
    } catch (e) {
      console.error('Failed to load plans', e);
    }
  }
  
  async function upgrade(tier: string) {
    if (upgrading) return;
    upgrading = tier;
    
    try {
      const session = data.session;
      if (!session) throw new Error('Not authenticated');
      
      const res = await fetch(`${PUBLIC_API_URL}/billing/checkout`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${session.access_token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ 
          tier,
          billing_cycle: billingCycle
        })
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
  
  function tierIsCurrent(tier: string): boolean {
    return subscription?.tier?.toLowerCase() === tier.toLowerCase();
  }
</script>

<svelte:head>
  <title>Billing | Valdrix</title>
</svelte:head>

<div class="space-y-8">
  <!-- Page Header -->
  <div>
    <h1 class="text-2xl font-bold mb-1">Billing & Plans</h1>
    <p class="text-ink-400 text-sm">Manage your subscription and payment methods</p>
  </div>
  
  {#if !data.user}
    <div class="card text-center py-12">
      <p class="text-ink-400">Please <a href="/auth/login" class="text-accent-400 hover:underline">sign in</a> to manage billing.</p>
    </div>
  {:else if loading}
    <div class="grid gap-5 md:grid-cols-3">
      {#each [1, 2, 3] as i}
        <div class="card">
          <div class="skeleton h-6 w-24 mb-4"></div>
          <div class="skeleton h-10 w-32 mb-6"></div>
          <div class="skeleton h-8 w-full"></div>
        </div>
      {/each}
    </div>
  {:else if error}
    <div class="card border-danger-500/50 bg-danger-500/10">
      <p class="text-danger-400">{error}</p>
    </div>
  {:else}
    <!-- Current Plan -->
    <div class="glass-panel pulse-glow stagger-enter" style="animation-delay: 0ms;">
      <div class="flex items-center justify-between">
        <div>
          <p class="text-sm text-ink-400 mb-1">Current Plan</p>
          <p class="text-4xl font-bold text-gradient capitalize">{subscription?.tier || 'Free'}</p>
          <div class="flex items-center gap-2 mt-2">
            <span class="badge {subscription?.status === 'active' ? 'badge-success' : 'badge-warning'}">
              {subscription?.status || 'Active'}
            </span>
            {#if subscription?.next_payment_date}
              <span class="text-xs text-ink-500">
                Next billing: {new Date(subscription.next_payment_date).toLocaleDateString()}
              </span>
            {/if}
          </div>
        </div>
        <div class="hero-icon text-6xl">💳</div>
      </div>
    </div>
    
    <!-- Plan Selector -->
    <div class="space-y-6">
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <h2 class="text-lg font-semibold">Upgrade Your Plan</h2>
        
        <!-- Cycle Toggle (Styled for Dashboard) -->
        <div class="flex items-center gap-3 bg-surface-200/50 p-1 rounded-full border border-surface-300 w-fit">
          <button 
            class="px-4 py-1.5 rounded-full text-xs font-medium transition-all {billingCycle === 'monthly' ? 'bg-accent-500 text-white shadow-sm' : 'text-ink-400 hover:text-ink-200'}"
            onclick={() => billingCycle = 'monthly'}
          >
            Monthly
          </button>
          <button 
            class="px-4 py-1.5 rounded-full text-xs font-medium transition-all flex items-center gap-2 {billingCycle === 'annual' ? 'bg-accent-500 text-white shadow-sm' : 'text-ink-400 hover:text-ink-200'}"
            onclick={() => billingCycle = 'annual'}
          >
            Yearly
            {#if billingCycle !== 'annual'}
              <span class="bg-success-500/20 text-success-400 px-1.5 py-0.5 rounded text-[10px] font-bold">Save 17%</span>
            {/if}
          </button>
        </div>
      </div>

      <div class="grid gap-5 md:grid-cols-4">
        {#each plans as plan, i}
          <div 
            class="card stagger-enter {tierIsCurrent(plan.id) ? 'border-accent-500 border-2 bg-accent-500/5' : ''}" 
            style="animation-delay: {50 + i * 50}ms;"
          >
            <!-- Tier Header -->
            <div class="mb-4">
              <div class="flex items-center justify-between">
                <h3 class="text-lg font-semibold capitalize">{plan.name}</h3>
                {#if plan.popular}
                  <span class="text-[10px] bg-accent-500/20 text-accent-400 px-2 py-0.5 rounded-full font-bold uppercase tracking-wider">Popular</span>
                {/if}
              </div>
              <p class="text-3xl font-bold mt-2">
                ${billingCycle === 'monthly' ? plan.price_monthly : Math.round(plan.price_annual / 12)}
                <span class="text-sm text-ink-400 font-normal">/mo</span>
              </p>
              {#if billingCycle === 'annual'}
                <p class="text-[10px] text-success-400 mt-1">Billed annually (${plan.price_annual}/yr)</p>
              {/if}
            </div>
            
            <!-- Features -->
            <ul class="space-y-2 mb-6 flex-grow">
              {#each plan.features as feature}
                <li class="flex items-start gap-2 text-xs text-ink-300">
                  <span class="text-success-400 mt-0.5">✓</span>
                  {feature}
                </li>
              {/each}
            </ul>
            
            <!-- Action Button -->
            {#if tierIsCurrent(plan.id)}
              <button class="btn btn-secondary w-full cursor-default" disabled>
                Current Plan
              </button>
            {:else}
              <button 
                class="btn {plan.popular ? 'btn-primary' : 'btn-secondary'} w-full"
                onclick={() => upgrade(plan.id)}
                disabled={!!upgrading}
              >
                {#if upgrading === plan.id}
                  <span class="spinner"></span>
                  Processing...
                {:else}
                  Upgrade to {plan.name}
                {/if}
              </button>
            {/if}
          </div>
        {/each}

        <!-- Enterprise Card -->
        <div class="card stagger-enter border-dashed border-surface-300 bg-surface-100/30" style="animation-delay: 250ms;">
          <h3 class="text-lg font-semibold">Enterprise</h3>
          <p class="text-ink-400 text-xs mt-2 mb-6">For large organizations with custom security & scale requirements.</p>
          <ul class="space-y-2 mb-6 flex-grow">
            <li class="flex items-start gap-2 text-xs text-ink-300"><span class="text-success-400">✓</span> Unlimited Cloud Accounts</li>
            <li class="flex items-start gap-2 text-xs text-ink-300"><span class="text-success-400">✓</span> SSO (SAML/OIDC)</li>
            <li class="flex items-start gap-2 text-xs text-ink-300"><span class="text-success-400">✓</span> Custom SLAs & Support</li>
          </ul>
          <a href="mailto:enterprise@valdrix.io" class="btn btn-secondary w-full text-center">Contact Sales</a>
        </div>
      </div>
    </div>
    
    <!-- Payment Info -->
    <div class="card stagger-enter text-center" style="animation-delay: 250ms;">
      <h3 class="text-lg font-semibold mb-3">Payment Information</h3>
      <div class="flex items-center justify-center gap-4 text-sm text-ink-400">
        <span>Powered by</span>
        <span class="font-bold text-ink-200">Paystack</span>
        <span>•</span>
        <span>Secure payment processing</span>
      </div>
      <p class="text-xs text-ink-500 mt-2">
        All payments are processed securely. You can cancel your subscription at any time.
      </p>
    </div>
  {/if}
</div>

<style>
  .border-accent-500 { border-color: var(--color-accent-500); }
</style>
