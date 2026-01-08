<!--
  Dashboard Home Page
  
  Shows overview of:
  - Total costs
  - Carbon footprint
  - Zombie resources
  - Recent LLM usage
-->

<script lang="ts">
  import { onMount } from 'svelte';
  import { PUBLIC_API_URL } from '$env/static/public';
  import { createSupabaseBrowserClient } from '$lib/supabase';
  
  export let data;
  
  const supabase = createSupabaseBrowserClient();
  
  let loading = true;
  let costs: any = null;
  let carbon: any = null;
  let zombies: any = null;
  let error = '';
  
  // Get date range (last 30 days)
  const endDate = new Date().toISOString().split('T')[0];
  const startDate = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
  
  onMount(async () => {
    if (!data.user) {
      loading = false;
      return;
    }
    
    try {
      // Get session for auth header
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) return;
      
      const headers = {
        'Authorization': `Bearer ${session.access_token}`,
      };
      
      // Fetch all data in parallel
      const [costsRes, carbonRes, zombiesRes] = await Promise.all([
        fetch(`${PUBLIC_API_URL}/costs?start_date=${startDate}&end_date=${endDate}`, { headers }),
        fetch(`${PUBLIC_API_URL}/carbon?start_date=${startDate}&end_date=${endDate}`, { headers }),
        fetch(`${PUBLIC_API_URL}/zombies`, { headers }),
      ]);
      
      costs = await costsRes.json();
      carbon = await carbonRes.json();
      zombies = await zombiesRes.json();
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  });
</script>

<svelte:head>
  <title>Dashboard | CloudSentinel</title>
</svelte:head>

{#if !data.user}
  <div class="text-center py-20">
    <h1 class="text-3xl font-bold mb-4">Welcome to CloudSentinel</h1>
    <p class="text-slate-400 mb-8">AI-powered cloud cost optimization</p>
    <a href="/auth/login" class="rounded bg-emerald-600 px-6 py-3 font-medium hover:bg-emerald-500">
      Get Started
    </a>
  </div>
{:else}
  <div class="space-y-6">
    <h1 class="text-2xl font-bold">Dashboard</h1>
    
    {#if loading}
      <div class="text-center py-10 text-slate-400">Loading data...</div>
    {:else if error}
      <div class="rounded bg-red-900/50 p-4 text-red-200">{error}</div>
    {:else}
      <!-- Stats Grid -->
      <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <!-- Total Cost -->
        <div class="rounded-lg border border-slate-800 bg-slate-900 p-6">
          <p class="text-sm text-slate-400">30-Day Cost</p>
          <p class="text-3xl font-bold text-emerald-400">
            ${costs?.total_cost?.toFixed(2) ?? '—'}
          </p>
        </div>
        
        <!-- Carbon Footprint -->
        <div class="rounded-lg border border-slate-800 bg-slate-900 p-6">
          <p class="text-sm text-slate-400">Carbon Footprint</p>
          <p class="text-3xl font-bold text-blue-400">
            {carbon?.total_co2_kg?.toFixed(2) ?? '—'} kg
          </p>
        </div>
        
        <!-- Zombie Resources -->
        <div class="rounded-lg border border-slate-800 bg-slate-900 p-6">
          <p class="text-sm text-slate-400">Zombie Resources</p>
          <p class="text-3xl font-bold text-orange-400">
            {(zombies?.unattached_volumes?.length ?? 0) + 
             (zombies?.old_snapshots?.length ?? 0) + 
             (zombies?.unused_elastic_ips?.length ?? 0)}
          </p>
        </div>
        
        <!-- Monthly Waste -->
        <div class="rounded-lg border border-slate-800 bg-slate-900 p-6">
          <p class="text-sm text-slate-400">Monthly Waste</p>
          <p class="text-3xl font-bold text-red-400">
            ${zombies?.total_monthly_waste?.toFixed(2) ?? '—'}
          </p>
        </div>
      </div>
      
      <!-- Carbon Equivalencies -->
      {#if carbon?.equivalencies}
        <div class="rounded-lg border border-slate-800 bg-slate-900 p-6">
          <h2 class="text-lg font-semibold mb-4">Carbon Impact</h2>
          <div class="grid gap-4 md:grid-cols-4 text-center">
            <div>
              <p class="text-2xl font-bold">{carbon.equivalencies.miles_driven}</p>
              <p class="text-sm text-slate-400">Miles Driven</p>
            </div>
            <div>
              <p class="text-2xl font-bold">{carbon.equivalencies.trees_needed_for_year}</p>
              <p class="text-sm text-slate-400">Trees Needed</p>
            </div>
            <div>
              <p class="text-2xl font-bold">{carbon.equivalencies.smartphone_charges}</p>
              <p class="text-sm text-slate-400">Phone Charges</p>
            </div>
            <div>
              <p class="text-2xl font-bold">{carbon.equivalencies.percent_of_home_month}%</p>
              <p class="text-sm text-slate-400">Of Home/Month</p>
            </div>
          </div>
        </div>
      {/if}
    {/if}
  </div>
{/if}
