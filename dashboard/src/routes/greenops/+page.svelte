<!--
  GreenOps Dashboard - Carbon Footprint & Sustainability
  
  Features:
  - Carbon footprint tracking (Scope 2 + Scope 3)
  - Carbon efficiency score
  - Green region recommendations
  - Graviton migration opportunities
  - Carbon budget monitoring
-->

<script lang="ts">
  import { PUBLIC_API_URL } from '$env/static/public';
  import { goto } from '$app/navigation';
  
  let { data } = $props();
  
  let carbonData = $derived(data.carbonData);
  let gravitonData = $derived(data.gravitonData);
  let budgetData = $derived(data.budgetData);
  let selectedRegion = $derived(data.selectedRegion);
  let error = $derived(data.error || '');
  let loading = $derived(false);
  
  function handleRegionChange(e: Event) {
    const target = e.target as HTMLSelectElement;
    goto(`?region=${target.value}`, { keepFocus: true, noScroll: true });
  }
  
  // Format CO2 value
  function formatCO2(kg: number): string {
    if (kg < 1) return `${(kg * 1000).toFixed(1)} g`;
    if (kg < 1000) return `${kg.toFixed(2)} kg`;
    return `${(kg / 1000).toFixed(2)} t`;
  }

</script>

<svelte:head>
  <title>GreenOps - Valdrix</title>
</svelte:head>

<div class="space-y-6">
  <!-- Header -->
  <div class="flex items-center justify-between">
    <div>
      <h1 class="text-2xl font-bold text-white">🌱 GreenOps Dashboard</h1>
      <p class="text-ink-400 mt-1">Monitor your cloud carbon footprint and sustainability</p>
    </div>
    
    <select 
      bind:value={selectedRegion}
      onchange={() => loadAllData()}
      class="bg-ink-800 border border-ink-700 rounded-lg px-3 py-2 text-sm"
      aria-label="Select AWS region for carbon analysis"
    >
      <option value="us-east-1">US East (N. Virginia)</option>
      <option value="us-west-2">US West (Oregon)</option>
      <option value="eu-west-1">EU (Ireland)</option>
      <option value="eu-north-1">EU (Stockholm)</option>
      <option value="ap-northeast-1">Asia Pacific (Tokyo)</option>
    </select>
  </div>
  {#if loading}
    <div class="flex items-center justify-center py-20">
      <div class="animate-spin rounded-full h-8 w-8 border-t-2 border-accent-500"></div>
    </div>
  {:else if !['growth', 'pro', 'enterprise', 'trial'].includes(data.subscription?.tier)}
    <!-- Tier Gating: Show blurred preview with upgrade overlay -->
    <div class="relative">
      <!-- Upgrade Overlay -->
      <div class="absolute inset-0 z-20 flex flex-col items-center justify-center text-center bg-ink-950/60 backdrop-blur-[1px] rounded-xl">
        <div class="text-6xl mb-4">🌱</div>
        <h2 class="text-2xl font-bold text-white mb-2">Upgrade to Unlock GreenOps</h2>
        <p class="text-ink-300 max-w-md mb-6">
          Track your cloud carbon footprint, get green region recommendations, and monitor sustainability metrics.
        </p>
        <div class="flex items-center gap-2 mb-6">
          <span class="badge badge-warning">Growth Plan Required</span>
        </div>
        <a href="/billing" class="btn btn-primary">
          Upgrade to Growth
        </a>
      </div>
      
      <!-- Blurred Preview Content (sample data) -->
      <div class="opacity-50 pointer-events-none select-none">
        <div class="bento-grid">
          <!-- Sample Total CO2 -->
          <div class="glass-panel col-span-2">
            <h2 class="text-ink-400 text-sm font-medium uppercase tracking-wider mb-1">Total Carbon Footprint</h2>
            <span class="text-5xl font-bold text-white">42.7 kg</span>
            <p class="text-ink-400 text-sm mt-2">Combined Scope 2 + Scope 3</p>
          </div>
          <!-- Sample Efficiency -->
          <div class="glass-panel text-center">
            <div class="text-4xl mb-2">📈</div>
            <h3 class="text-ink-400 text-xs uppercase">Efficiency Score</h3>
            <p class="text-3xl font-bold text-white mt-1">89</p>
          </div>
          <!-- Sample Energy -->
          <div class="glass-panel text-center">
            <div class="text-4xl mb-2">⚡</div>
            <h3 class="text-ink-400 text-xs uppercase">Est. Energy</h3>
            <p class="text-3xl font-bold text-white mt-1">156 kWh</p>
          </div>
          <!-- Sample Budget -->
          <div class="glass-panel col-span-2">
            <h3 class="text-lg font-semibold text-white mb-4">📊 Monthly Carbon Budget</h3>
            <div class="w-full bg-ink-800 rounded-full h-3">
              <div class="h-full bg-green-500 rounded-full" style="width: 65%"></div>
            </div>
            <p class="text-right text-xs text-ink-500 mt-1">65% consumed</p>
          </div>
        </div>
      </div>
    </div>
  {:else if error}
    <div class="card bg-red-900/20 border-red-800 p-6">
      <p class="text-red-400">{error}</p>
    </div>
  {:else}
    <!-- Bento Box Grid -->
    <div class="bento-grid">
      
      <!-- 1. Total CO2 (Hero - Large) -->
      <div class="glass-panel col-span-2 relative overflow-hidden group">
        <div class="absolute top-0 right-0 p-4 opacity-10 text-9xl leading-none select-none pointer-events-none">🌍</div>
        <div class="relative z-10 flex flex-col justify-between h-full">
          <div>
            <h2 class="text-ink-400 text-sm font-medium uppercase tracking-wider mb-1">Total Carbon Footprint</h2>
            <div class="flex items-baseline gap-2">
              <span class="text-5xl font-bold text-white tracking-tight">
                {carbonData ? formatCO2(carbonData.total_co2_kg) : '—'}
              </span>
              {#if carbonData?.forecast_30d}
                <span class="text-xs text-ink-400 bg-ink-800/50 px-2 py-1 rounded-full border border-ink-700">
                  Forecast: {formatCO2(carbonData.forecast_30d.projected_co2_kg)} / 30d
                </span>
              {/if}
            </div>
            <p class="text-ink-400 text-sm mt-2">Combined Scope 2 (Operational) & Scope 3 (Embodied)</p>
          </div>
          
          {#if carbonData}
            <div class="grid grid-cols-2 gap-4 mt-6">
               <div>
                  <div class="text-xs text-ink-400 mb-1">Scope 2</div>
                  <div class="h-1.5 w-full bg-ink-800 rounded-full overflow-hidden">
                     <div class="h-full bg-accent-500" style="width: {carbonData.total_co2_kg > 0 ? (carbonData.scope2_co2_kg / carbonData.total_co2_kg * 100) : 0}%"></div>
                  </div>
                  <div class="text-white text-sm mt-1">{formatCO2(carbonData.scope2_co2_kg)}</div>
               </div>
               <div>
                  <div class="text-xs text-ink-400 mb-1">Scope 3</div>
                  <div class="h-1.5 w-full bg-ink-800 rounded-full overflow-hidden">
                     <div class="h-full bg-purple-500" style="width: {carbonData.total_co2_kg > 0 ? (carbonData.scope3_co2_kg / carbonData.total_co2_kg * 100) : 0}%"></div>
                  </div>
                  <div class="text-white text-sm mt-1">{formatCO2(carbonData.scope3_co2_kg)}</div>
               </div>
            </div>
          {/if}
        </div>
      </div>

      <!-- 2. Efficiency Score (Compact) -->
      <div class="glass-panel text-center flex flex-col items-center justify-center">
        <div class="text-4xl mb-2">📈</div>
        <h3 class="text-ink-400 text-xs uppercase font-medium">Efficiency Score</h3>
        <p class="text-3xl font-bold text-white mt-1">
          {carbonData ? carbonData.carbon_efficiency_score : '—'}
        </p>
        <p class="text-ink-500 text-xs">gCO₂e per $1 spent</p>
      </div>

      <!-- 3. Energy Usage (Compact) -->
      <div class="glass-panel text-center flex flex-col items-center justify-center">
        <div class="text-4xl mb-2">⚡</div>
        <h3 class="text-ink-400 text-xs uppercase font-medium">Est. Energy</h3>
        <p class="text-3xl font-bold text-white mt-1">
          {carbonData ? Math.round(carbonData.estimated_energy_kwh) : '—'}
        </p>
        <p class="text-ink-500 text-xs">kWh (incl. PUE)</p>
      </div>

      <!-- 4. Carbon Budget (Wide) -->
      <div class="glass-panel col-span-2">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-semibold text-white flex items-center gap-2">
            📊 Monthly Carbon Budget
          </h3>
          {#if budgetData}
             <span class="badge" class:badge-success={budgetData.alert_status === 'ok'}
                   class:badge-warning={budgetData.alert_status === 'warning'}
                   class:badge-error={budgetData.alert_status === 'exceeded'}>
               {budgetData.alert_status === 'ok' ? 'ON TRACK' : 
                budgetData.alert_status === 'warning' ? 'WARNING' : 'EXCEEDED'}
             </span>
          {/if}
        </div>
        
        {#if budgetData}
          <div class="relative pt-4">
             <div class="flex justify-between text-xs text-ink-400 mb-1">
                <span>{formatCO2(budgetData.current_usage_kg)} used</span>
                <span>Limit: {formatCO2(budgetData.budget_kg)}</span>
             </div>
             <div class="w-full bg-ink-950 rounded-full h-3 border border-ink-800 overflow-hidden">
               <div class="h-full rounded-full transition-all duration-1000 ease-out relative"
                    class:bg-green-500={budgetData.alert_status === 'ok'}
                    class:bg-yellow-500={budgetData.alert_status === 'warning'}
                    class:bg-red-500={budgetData.alert_status === 'exceeded'}
                    style="width: {Math.min(budgetData.usage_percent, 100)}%">
                    <div class="absolute inset-0 bg-white/20 animate-pulse"></div>
               </div>
             </div>
             <p class="text-right text-xs text-ink-500 mt-1">{budgetData.usage_percent}% consumed</p>
          </div>
        {:else}
          <div class="animate-pulse h-12 bg-ink-800/50 rounded"></div>
        {/if}
      </div>

      <!-- 5. Graviton Migration (Row Span) -->
      <div class="glass-panel row-span-2 col-span-2">
         <div class="flex items-center justify-between mb-4">
            <h3 class="text-lg font-semibold text-white flex items-center gap-2">
               🚀 Graviton Candidates
               {#if gravitonData && gravitonData.candidates?.length}
                  <span class="bg-accent-500/20 text-accent-400 text-xs px-2 py-0.5 rounded-full">{gravitonData.candidates.length}</span>
               {/if}
            </h3>
         </div>
         
         <div class="space-y-3 overflow-y-auto max-h-[300px] pr-2 custom-scrollbar">
            {#if gravitonData && gravitonData.candidates?.length > 0}
               {#each gravitonData.candidates.slice(0, 5) as candidate}
                  <div class="bg-ink-900/40 border border-ink-800 rounded-lg p-3 hover:border-accent-500/30 transition-colors">
                     <div class="flex justify-between items-start mb-1">
                        <span class="font-mono text-sm text-white">{candidate.instance_id}</span>
                        <span class="text-green-400 text-xs font-bold">-{candidate.energy_savings_percent}% CO₂</span>
                     </div>
                     <div class="flex items-center gap-2 text-xs text-ink-400">
                        <span>{candidate.current_type}</span>
                        <span>→</span>
                        <span class="text-accent-400">{candidate.recommended_type}</span>
                     </div>
                  </div>
               {/each}
            {:else if gravitonData}
              <div class="text-center py-8 text-ink-500">
                 <p>All workloads optimized! 🎉</p>
              </div>
            {:else}
               <div class="space-y-3">
                  {#each Array(3) as _}
                    <div class="h-16 bg-ink-800/30 rounded-lg animate-pulse"></div>
                  {/each}
               </div>
            {/if}
         </div>
      </div>

      <!-- 6. Real-world Impact -->
      <div class="glass-panel col-span-2">
         <h3 class="text-sm font-semibold text-ink-300 mb-3 uppercase tracking-wider">Environmental Equivalencies</h3>
         
         {#if carbonData?.equivalencies}
           <div class="grid grid-cols-4 gap-2">
             <div class="text-center p-2 bg-ink-900/30 rounded border border-ink-800/50">
               <div class="text-xl mb-1">🚗</div>
               <div class="text-sm font-bold text-white">{carbonData.equivalencies.miles_driven}</div>
               <div class="text-[10px] text-ink-500">miles</div>
             </div>
             <div class="text-center p-2 bg-ink-900/30 rounded border border-ink-800/50">
               <div class="text-xl mb-1">🌳</div>
               <div class="text-sm font-bold text-white">{carbonData.equivalencies.trees_needed_for_year}</div>
               <div class="text-[10px] text-ink-500">trees</div>
             </div>
             <div class="text-center p-2 bg-ink-900/30 rounded border border-ink-800/50">
               <div class="text-xl mb-1">📱</div>
               <div class="text-sm font-bold text-white">{carbonData.equivalencies.smartphone_charges}</div>
               <div class="text-[10px] text-ink-500">charges</div>
             </div>
             <div class="text-center p-2 bg-ink-900/30 rounded border border-ink-800/50">
               <div class="text-xl mb-1">🏠</div>
               <div class="text-sm font-bold text-white">{carbonData.equivalencies.percent_of_home_month}%</div>
               <div class="text-[10px] text-ink-500">home/mo</div>
             </div>
           </div>
         {/if}
      </div>

    </div>

    <!-- Green Regions Section (Separate Flow) -->
    {#if carbonData}
      <div class="glass-panel mt-6">
         <h3 class="text-lg font-semibold mb-3 flex items-center gap-2">
            🌿 Recommended Regions
            <span class="text-xs font-normal text-ink-400 bg-ink-800 px-2 py-0.5 rounded">Lower Carbon Intensity</span>
         </h3>
         {#if carbonData.green_region_recommendations?.length > 0}
           <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
             {#each carbonData.green_region_recommendations.slice(0, 3) as rec}
            <div class="group p-4 rounded-lg bg-gradient-to-br from-green-900/10 to-green-900/5 border border-green-900/30 hover:border-green-500/50 transition-all">
              <div class="flex justify-between items-start">
                 <span class="font-bold text-white group-hover:text-green-400 transition-colors">{rec.region}</span>
                 <span class="text-xs bg-green-900/40 text-green-300 px-1.5 py-0.5 rounded">{rec.carbon_intensity} g/kWh</span>
              </div>
              <div class="mt-2 text-sm text-ink-400">
                 Save <span class="text-green-400 font-bold">{rec.savings_percent}%</span> emissions
              </div>
            </div>
          {/each}
           </div>
         {:else}
           <div class="p-4 rounded-lg bg-gradient-to-br from-green-900/10 to-green-900/5 border border-green-900/30 text-ink-400">
             You’re already in one of the greenest regions 🌿
           </div>
         {/if}
      </div>
    {/if}
  {/if}
</div>

<style>
  .card {
    background-color: var(--color-ink-900);
    border: 1px solid var(--color-ink-800);
    border-radius: 0.75rem;
  }
  
  .badge-success {
    background-color: rgb(34 197 94 / 0.2);
    color: rgb(74 222 128);
  }
  
  .badge-warning {
    background-color: rgb(234 179 8 / 0.2);
    color: rgb(250 204 21);
  }
  
  .badge-error {
    background-color: rgb(239 68 68 / 0.2);
    color: rgb(248 113 113);
  }
  
</style>
