<!--
  Dashboard Home Page - Premium SaaS Design
  
  Features:
  - Stats cards with motion animations
  - Staggered entrance effects
  - Clean data visualization
  - Loading skeletons
-->

<script lang="ts">
  import { PUBLIC_API_URL } from '$env/static/public';
  import { createSupabaseBrowserClient } from '$lib/supabase';
  import DateRangePicker from '$lib/components/DateRangePicker.svelte';
  
  let { data } = $props();
  
  const supabase = createSupabaseBrowserClient();
  
  let loading = $state(true);
  let costs: any = $state(null);
  let carbon: any = $state(null);
  let zombies: any = $state(null);
  let analysis: any = $state(null);
  let error = $state('');
  let startDate = $state('');
  let endDate = $state('');
  
  // Table pagination state
  let currentPage = $state(0);
  let remediating = $state<string | null>(null);
  
  /**
   * Handle remediation action for a zombie resource.
   * Creates a remediation request and navigates to approval workflow.
   */
  async function handleRemediate(finding: any) {
    if (remediating) return;
    
    remediating = finding.resource_id;
    
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) throw new Error('Not authenticated');
      
      const response = await fetch(`${PUBLIC_API_URL}/zombies/request`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${session.access_token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          resource_id: finding.resource_id,
          resource_type: finding.resource_type || 'unknown',
          action: finding.recommended_action?.toLowerCase().includes('delete') ? 'delete_volume' : 'stop_instance',
          estimated_savings: parseFloat(finding.monthly_cost?.replace('$', '') || '0'),
          create_backup: true,
        }),
      });
      
      if (!response.ok) {
        const data = await response.json();
        if (response.status === 403) {
          alert('⚡ Upgrade Required: Auto-remediation requires Pro tier or higher.');
        } else {
          alert(`Error: ${data.detail || 'Failed to create remediation request'}`);
        }
        return;
      }
      
      const result = await response.json();
      alert(`✅ Remediation request created! ID: ${result.request_id}\n\nAn admin must approve before execution.`);
      
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    } finally {
      remediating = null;
    }
  }

  async function loadData() {
    if (!data.user || !startDate || !endDate) {
      loading = false;
      return;
    }
    
    loading = true;
    error = '';
    
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) return;
      
      const headers = {
        'Authorization': `Bearer ${session.access_token}`,
      };
      
      const [costsRes, carbonRes, zombiesRes, analyzeRes] = await Promise.all([
        fetch(`${PUBLIC_API_URL}/costs?start_date=${startDate}&end_date=${endDate}`, { headers }),
        fetch(`${PUBLIC_API_URL}/carbon?start_date=${startDate}&end_date=${endDate}`, { headers }),
        fetch(`${PUBLIC_API_URL}/zombies?analyze=true`, { headers }),
        fetch(`${PUBLIC_API_URL}/analyze?start_date=${startDate}&end_date=${endDate}`, { headers }),
      ]);
      
      costs = await costsRes.json();
      carbon = await carbonRes.json();
      zombies = await zombiesRes.json();
      analysis = analyzeRes.ok ? await analyzeRes.json() : { analysis: 'Analysis unavailable.' };
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  }
  
  function handleDateChange(dates: { startDate: string; endDate: string }) {
    startDate = dates.startDate;
    endDate = dates.endDate;
    if (data.user) {
      loadData();
    }
  }
  
  let zombieCount = $derived(zombies ? Object.values(zombies).reduce((acc: number, val: any) => {
    return Array.isArray(val) ? acc + val.length : acc;
  }, 0) : 0);
  
  let analysisText = $derived(analysis?.analysis ?? '');
  
  // Calculate period label from dates
  let periodLabel = $derived((() => {
    if (!startDate || !endDate) return 'Period';
    const start = new Date(startDate);
    const end = new Date(endDate);
    const days = Math.round((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24));
    if (days <= 7) return '7-Day';
    if (days <= 30) return '30-Day';
    if (days <= 90) return '90-Day';
    return `${days}-Day`;
  })());
</script>

<svelte:head>
  <title>Dashboard | Valdrix</title>
</svelte:head>

{#if !data.user}
  <!-- Public Landing -->
  <div class="min-h-[85vh] flex flex-col items-center justify-center text-center px-4">
    <!-- Floating Cloud Icon -->
    <div class="hero-icon mb-6">
      <span class="text-7xl drop-shadow-lg">☁️</span>
    </div>
    
    <!-- Main Heading -->
    <h1 class="fade-in-up text-4xl md:text-6xl font-bold mb-5 max-w-3xl leading-tight" style="animation-delay: 100ms;">
      <span class="text-gradient">Cloud Cost</span> Intelligence
    </h1>
    
    <!-- Subheading -->
    <p class="fade-in-up text-lg md:text-xl mb-10 max-w-xl leading-relaxed" style="animation-delay: 200ms; color: var(--color-ink-400);">
      AI-powered FinOps platform that tracks costs, carbon footprint, and zombie resources in real-time.
    </p>
    
    <!-- CTA Buttons -->
    <div class="fade-in-up flex flex-col sm:flex-row gap-4" style="animation-delay: 300ms;">
      <a href="/auth/login" class="btn btn-primary text-base px-8 py-3 pulse-glow">
        Get Started Free →
      </a>
      <a href="#features" class="btn btn-secondary text-base px-8 py-3">
        Learn More
      </a>
    </div>
    
    <!-- Feature Pills -->
    <div class="fade-in-up flex flex-wrap justify-center gap-3 mt-16" style="animation-delay: 500ms;">
      <span class="badge badge-accent">💰 Cost Tracking</span>
      <span class="badge badge-success">🌱 Carbon Footprint</span>
      <span class="badge badge-warning">👻 Zombie Detection</span>
      <span class="badge badge-default">🤖 AI Analysis</span>
    </div>
  </div>
{:else}
  <div class="space-y-8">
    <!-- Page Header with Date Range Picker -->
    <div class="flex flex-col gap-4">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-2xl font-bold mb-1">Dashboard</h1>
          <p class="text-ink-400 text-sm">Overview of your cloud infrastructure</p>
        </div>
      </div>
      
      <DateRangePicker onDateChange={handleDateChange} />
    </div>
    
    {#if loading}
      <!-- Loading Skeletons -->
      <div class="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
        {#each [1, 2, 3, 4] as i}
          <div class="card" style="animation-delay: {i * 50}ms;">
            <div class="skeleton h-4 w-20 mb-3"></div>
            <div class="skeleton h-8 w-32"></div>
          </div>
        {/each}
      </div>
    {:else if error}
      <div class="card border-danger-500/50 bg-danger-500/10">
        <p class="text-danger-400">{error}</p>
      </div>
    {:else}
      <!-- Stats Grid -->
      <div class="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
        <!-- Period Cost -->
        <div class="card card-stat stagger-enter" style="animation-delay: 0ms;">
          <p class="text-sm text-ink-400 mb-1">{periodLabel} Cost</p>
          <p class="text-3xl font-bold" style="color: var(--color-accent-400);">
            ${costs?.total_cost?.toFixed(2) ?? '0.00'}
          </p>
          <p class="text-xs text-ink-500 mt-2">
            vs last period
          </p>
        </div>
        
        <!-- Carbon Footprint -->
        <div class="card card-stat stagger-enter" style="animation-delay: 50ms;">
          <p class="text-sm text-ink-400 mb-1">Carbon Footprint</p>
          <p class="text-3xl font-bold" style="color: var(--color-success-400);">
            {carbon?.total_co2_kg?.toFixed(2) ?? '0.00'} kg
          </p>
          <p class="text-xs text-ink-500 mt-2">
            CO₂ emissions
          </p>
        </div>
        
        <!-- Zombie Resources -->
        <div class="card card-stat stagger-enter" style="animation-delay: 100ms;">
          <p class="text-sm text-ink-400 mb-1">Zombie Resources</p>
          <p class="text-3xl font-bold" style="color: var(--color-warning-400);">
            {zombieCount}
          </p>
          <p class="text-xs text-ink-500 mt-2">
            Unused resources found
          </p>
        </div>
        
        <!-- Monthly Waste -->
        <div class="card card-stat stagger-enter" style="animation-delay: 150ms;">
          <p class="text-sm text-ink-400 mb-1">Monthly Waste</p>
          <p class="text-3xl font-bold" style="color: var(--color-danger-400);">
            ${zombies?.total_monthly_waste?.toFixed(2) ?? '0.00'}
          </p>
          <p class="text-xs text-ink-500 mt-2">
            Potential savings
          </p>
        </div>
      </div>
      
      <!-- AI Insights - Interactive Cards -->
      {#if zombies?.ai_analysis}
        {@const aiData = zombies.ai_analysis}
        
        <!-- Hero Savings Card -->
        <div class="glass-panel stagger-enter col-span-full" style="animation-delay: 200ms;">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-sm text-ink-400 mb-1">Potential Monthly Savings</p>
              <p class="text-5xl font-bold text-gradient">
                {aiData.total_monthly_savings || '$0.00'}
              </p>
              <p class="text-sm text-ink-400 mt-2">{aiData.summary || 'Analysis complete.'}</p>
            </div>
            <div class="hero-icon text-6xl">💰</div>
          </div>
        </div>
        
        <!-- AI Findings Table - Scalable Design -->
        {#if aiData.resources && aiData.resources.length > 0}
          {@const pageSize = 10}
          {@const totalPages = Math.ceil(aiData.resources.length / pageSize)}
          
          <div class="card stagger-enter" style="animation-delay: 250ms;">
            <!-- Table Header -->
            <div class="flex items-center justify-between mb-4">
              <h3 class="text-lg font-semibold">
                🧟 Zombie Resources ({aiData.resources.length})
              </h3>
              <div class="flex items-center gap-2 text-xs text-ink-400">
                <span>Page {currentPage + 1} of {totalPages}</span>
              </div>
            </div>
            
            <!-- Responsive Table -->
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="border-b border-ink-700 text-left text-xs text-ink-400 uppercase tracking-wider">
                    <th class="pb-3 pr-4">Resource</th>
                    <th class="pb-3 pr-4">Type</th>
                    <th class="pb-3 pr-4">Cost</th>
                    <th class="pb-3 pr-4">Confidence</th>
                    <th class="pb-3 pr-4">Risk</th>
                    <th class="pb-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {#each aiData.resources.slice(currentPage * pageSize, (currentPage + 1) * pageSize) as finding, i}
                    <tr class="border-b border-ink-800 hover:bg-ink-800/50 transition-colors">
                      <!-- Resource ID -->
                      <td class="py-3 pr-4">
                        <div class="font-mono text-xs truncate max-w-[150px]" title={finding.resource_id}>
                          {finding.resource_id}
                        </div>
                        <!-- Expandable explanation -->
                        <details class="mt-1">
                          <summary class="text-xs text-ink-500 cursor-pointer hover:text-accent-400">
                            View details
                          </summary>
                          <p class="text-xs text-ink-400 mt-1 max-w-xs">
                            {finding.explanation}
                          </p>
                          {#if finding.confidence_reason}
                            <p class="text-xs text-ink-500 mt-1 italic">
                              {finding.confidence_reason}
                            </p>
                          {/if}
                        </details>
                      </td>
                      
                      <!-- Type Badge -->
                      <td class="py-3 pr-4">
                        <span class="badge badge-default text-xs">
                          {finding.resource_type || 'Resource'}
                        </span>
                      </td>
                      
                      <!-- Monthly Cost -->
                      <td class="py-3 pr-4 font-semibold text-success-400">
                        {finding.monthly_cost || '$0'}
                      </td>
                      
                      <!-- Confidence -->
                      <td class="py-3 pr-4">
                        <span class="inline-flex items-center gap-1">
                          <span class="w-2 h-2 rounded-full {finding.confidence === 'high' ? 'bg-danger-400' : finding.confidence === 'medium' ? 'bg-warning-400' : 'bg-success-400'}"></span>
                          <span class="text-xs capitalize">{finding.confidence}</span>
                        </span>
                      </td>
                      
                      <!-- Risk -->
                      <td class="py-3 pr-4">
                        <span class="text-xs {finding.risk_if_deleted === 'high' ? 'text-danger-400' : finding.risk_if_deleted === 'medium' ? 'text-warning-400' : 'text-ink-400'}">
                          {finding.risk_if_deleted || 'low'}
                        </span>
                      </td>
                      
                      <!-- Action Button -->
                      <td class="py-3 text-right">
                        <button 
                          class="btn btn-ghost text-xs hover:bg-accent-500/20 hover:text-accent-400"
                          onclick={() => handleRemediate(finding)}
                          disabled={remediating === finding.resource_id}
                        >
                          {#if remediating === finding.resource_id}
                            <span class="animate-pulse">...</span>
                          {:else}
                            {finding.recommended_action || 'Review'}
                          {/if}
                        </button>
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
            
            <!-- Pagination -->
            {#if totalPages > 1}
              <div class="flex items-center justify-between mt-4 pt-4 border-t border-ink-800">
                <button 
                  class="btn btn-ghost text-xs"
                  disabled={currentPage === 0}
                  onclick={() => currentPage = Math.max(0, currentPage - 1)}
                >
                  ← Previous
                </button>
                
                <div class="flex items-center gap-1">
                  {#each Array(Math.min(totalPages, 5)) as _, p}
                    {@const pageNum = totalPages <= 5 ? p : 
                      currentPage < 3 ? p :
                      currentPage > totalPages - 3 ? totalPages - 5 + p :
                      currentPage - 2 + p}
                    <button 
                      class="w-8 h-8 rounded text-xs {currentPage === pageNum ? 'bg-accent-500 text-white' : 'hover:bg-ink-700'}"
                      onclick={() => currentPage = pageNum}
                    >
                      {pageNum + 1}
                    </button>
                  {/each}
                </div>
                
                <button 
                  class="btn btn-ghost text-xs"
                  disabled={currentPage >= totalPages - 1}
                  onclick={() => currentPage = Math.min(totalPages - 1, currentPage + 1)}
                >
                  Next →
                </button>
              </div>
            {/if}
          </div>
        {/if}
        
        <!-- General Recommendations -->
        {#if aiData.general_recommendations && aiData.general_recommendations.length > 0}
          <div class="card stagger-enter" style="animation-delay: 400ms;">
            <h3 class="text-lg font-semibold mb-3">💡 Recommendations</h3>
            <ul class="space-y-2">
              {#each aiData.general_recommendations as rec}
                <li class="flex items-start gap-2 text-sm text-ink-300">
                  <span class="text-accent-400">•</span>
                  {rec}
                </li>
              {/each}
            </ul>
          </div>
        {/if}
      {:else if analysisText}
        <!-- Fallback: Plain text analysis -->
        <div class="card stagger-enter" style="animation-delay: 200ms;">
          <div class="flex items-center justify-between mb-3">
            <h2 class="text-lg font-semibold">AI Insights</h2>
            <span class="badge badge-default">LLM</span>
          </div>
          <div class="text-sm text-ink-300 whitespace-pre-wrap leading-relaxed">
            {analysisText}
          </div>
        </div>
      {/if}
      
      <!-- Carbon Impact Section -->
      {#if carbon?.equivalencies}
        <div class="card stagger-enter" style="animation-delay: 200ms;">
          <h2 class="text-lg font-semibold mb-5">Carbon Impact</h2>
          <div class="grid gap-6 md:grid-cols-4 text-center">
            <div class="p-4 rounded-lg bg-ink-800/50">
              <p class="text-2xl font-bold text-ink-100">{carbon.equivalencies.miles_driven}</p>
              <p class="text-sm text-ink-400 mt-1">Miles Driven</p>
            </div>
            <div class="p-4 rounded-lg bg-ink-800/50">
              <p class="text-2xl font-bold text-ink-100">{carbon.equivalencies.trees_needed_for_year}</p>
              <p class="text-sm text-ink-400 mt-1">Trees Needed</p>
            </div>
            <div class="p-4 rounded-lg bg-ink-800/50">
              <p class="text-2xl font-bold text-ink-100">{carbon.equivalencies.smartphone_charges}</p>
              <p class="text-sm text-ink-400 mt-1">Phone Charges</p>
            </div>
            <div class="p-4 rounded-lg bg-ink-800/50">
              <p class="text-2xl font-bold text-ink-100">{carbon.equivalencies.percent_of_home_month}%</p>
              <p class="text-sm text-ink-400 mt-1">Of Home/Month</p>
            </div>
          </div>
        </div>
      {/if}
      
      <!-- Zombie Resources Table -->
      {#if zombieCount > 0}
        <div class="card stagger-enter" style="animation-delay: 250ms;">
          <div class="flex items-center justify-between mb-5">
            <h2 class="text-lg font-semibold">Zombie Resources</h2>
            <span class="badge badge-warning">{zombieCount} found</span>
          </div>
          
          <div class="overflow-x-auto">
            <table class="table">
              <thead>
                <tr>
                  <th>Resource</th>
                  <th>Type</th>
                  <th>Monthly Cost</th>
                  <th>AI Reasoning & Confidence</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {#each zombies?.unattached_volumes ?? [] as vol}
                  <tr>
                    <td class="font-mono text-xs">{vol.resource_id}</td>
                    <td><span class="badge badge-default">EBS Volume</span></td>
                    <td class="text-danger-400">${vol.monthly_cost}</td>
                    <td>
                      <div class="flex flex-col gap-1 max-w-xs">
                        <p class="text-[10px] leading-tight text-ink-300">{vol.explainability_notes || 'Resource detached and accruing idle costs.'}</p>
                        <div class="flex items-center gap-2">
                          <div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
                            <div class="h-full bg-accent-500" style="width: {(vol.confidence_score || 0.85) * 100}%"></div>
                          </div>
                          <span class="text-[10px] font-bold text-accent-400">{Math.round((vol.confidence_score || 0.85) * 100)}% Match</span>
                        </div>
                      </div>
                    </td>
                    <td>
                      <button class="btn btn-ghost text-xs">Review</button>
                    </td>
                  </tr>
                {/each}
                {#each zombies?.old_snapshots ?? [] as snap}
                  <tr>
                    <td class="font-mono text-xs">{snap.resource_id}</td>
                    <td><span class="badge badge-default">Snapshot</span></td>
                    <td class="text-danger-400">${snap.monthly_cost}</td>
                    <td>
                      <div class="flex flex-col gap-1 max-w-xs">
                        <p class="text-[10px] leading-tight text-ink-300">{snap.explainability_notes || 'Snapshot age exceeds standard retention policy.'}</p>
                        <div class="flex items-center gap-2">
                          <div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
                            <div class="h-full bg-accent-500" style="width: {(snap.confidence_score || 0.99) * 100}%"></div>
                          </div>
                          <span class="text-[10px] font-bold text-accent-400">{Math.round((snap.confidence_score || 0.99) * 100)}% Match</span>
                        </div>
                      </div>
                    </td>
                    <td>
                      <button class="btn btn-ghost text-xs">Review</button>
                    </td>
                  </tr>
                {/each}
                {#each zombies?.unused_elastic_ips ?? [] as eip}
                  <tr>
                    <td class="font-mono text-xs">{eip.resource_id}</td>
                    <td><span class="badge badge-default">Elastic IP</span></td>
                    <td class="text-danger-400">${eip.monthly_cost}</td>
                    <td>
                      <div class="flex flex-col gap-1 max-w-xs">
                        <p class="text-[10px] leading-tight text-ink-300">{eip.explainability_notes || 'Unassociated EIP address found.'}</p>
                        <div class="flex items-center gap-2">
                          <div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
                            <div class="h-full bg-accent-500" style="width: {(eip.confidence_score || 0.98) * 100}%"></div>
                          </div>
                          <span class="text-[10px] font-bold text-accent-400">{Math.round((eip.confidence_score || 0.98) * 100)}% Match</span>
                        </div>
                      </div>
                    </td>
                    <td><button class="btn btn-ghost text-xs">Review</button></td>
                  </tr>
                {/each}
                {#each zombies?.idle_instances ?? [] as ec2}
                  <tr>
                    <td class="font-mono text-xs">{ec2.resource_id}</td>
                    <td><span class="badge badge-default">Idle EC2 ({ec2.instance_type})</span></td>
                    <td class="text-danger-400">${ec2.monthly_cost}</td>
                    <td>
                      <div class="flex flex-col gap-1 max-w-xs">
                        <p class="text-[10px] leading-tight text-ink-300">{ec2.explainability_notes || 'Low CPU and network utilization detected over 7 days.'}</p>
                        <div class="flex items-center gap-2">
                          <div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
                            <div class="h-full bg-accent-500" style="width: {(ec2.confidence_score || 0.92) * 100}%"></div>
                          </div>
                          <span class="text-[10px] font-bold text-accent-400">{Math.round((ec2.confidence_score || 0.92) * 100)}% Match</span>
                        </div>
                      </div>
                    </td>
                    <td><button class="btn btn-ghost text-xs">Review</button></td>
                  </tr>
                {/each}
                {#each zombies?.orphan_load_balancers ?? [] as lb}
                  <tr>
                    <td class="font-mono text-xs">{lb.resource_id}</td>
                    <td><span class="badge badge-default">Orphan {lb.lb_type.toUpperCase()}</span></td>
                    <td class="text-danger-400">${lb.monthly_cost}</td>
                    <td>
                      <div class="flex flex-col gap-1 max-w-xs">
                        <p class="text-[10px] leading-tight text-ink-300">{lb.explainability_notes || 'Load balancer has no healthy targets associated.'}</p>
                        <div class="flex items-center gap-2">
                          <div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
                            <div class="h-full bg-accent-500" style="width: {(lb.confidence_score || 0.95) * 100}%"></div>
                          </div>
                          <span class="text-[10px] font-bold text-accent-400">{Math.round((lb.confidence_score || 0.95) * 100)}% Match</span>
                        </div>
                      </div>
                    </td>
                    <td><button class="btn btn-ghost text-xs">Review</button></td>
                  </tr>
                {/each}
                {#each zombies?.idle_rds_databases ?? [] as rds}
                  <tr>
                    <td class="font-mono text-xs">{rds.resource_id}</td>
                    <td><span class="badge badge-default">Idle RDS ({rds.db_class})</span></td>
                    <td class="text-danger-400">${rds.monthly_cost}</td>
                    <td>
                      <div class="flex flex-col gap-1 max-w-xs">
                        <p class="text-[10px] leading-tight text-ink-300">{rds.explainability_notes || 'No connections detected in the last billing cycle.'}</p>
                        <div class="flex items-center gap-2">
                          <div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
                            <div class="h-full bg-accent-500" style="width: {(rds.confidence_score || 0.88) * 100}%"></div>
                          </div>
                          <span class="text-[10px] font-bold text-accent-400">{Math.round((rds.confidence_score || 0.88) * 100)}% Match</span>
                        </div>
                      </div>
                    </td>
                    <td><button class="btn btn-ghost text-xs">Review</button></td>
                  </tr>
                {/each}
                {#each zombies?.underused_nat_gateways ?? [] as nat}
                  <tr>
                    <td class="font-mono text-xs">{nat.resource_id}</td>
                    <td><span class="badge badge-default">Idle NAT Gateway</span></td>
                    <td class="text-danger-400">${nat.monthly_cost}</td>
                    <td>
                      <div class="flex flex-col gap-1 max-w-xs">
                        <p class="text-[10px] leading-tight text-ink-300">{nat.explainability_notes || 'Minimal data processing detected compared to runtime cost.'}</p>
                        <div class="flex items-center gap-2">
                          <div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
                            <div class="h-full bg-accent-500" style="width: {(nat.confidence_score || 0.80) * 100}%"></div>
                          </div>
                          <span class="text-[10px] font-bold text-accent-400">{Math.round((nat.confidence_score || 0.80) * 100)}% Match</span>
                        </div>
                      </div>
                    </td>
                    <td><button class="btn btn-ghost text-xs">Review</button></td>
                  </tr>
                {/each}
                {#each zombies?.idle_s3_buckets ?? [] as s3}
                  <tr>
                    <td class="font-mono text-xs">{s3.resource_id}</td>
                    <td><span class="badge badge-default">Idle S3 Bucket</span></td>
                    <td class="text-danger-400">${s3.monthly_cost}</td>
                    <td>
                      <div class="flex flex-col gap-1 max-w-xs">
                        <p class="text-[10px] leading-tight text-ink-300">{s3.explainability_notes || 'No GET/PUT requests recorded in the last 30 days.'}</p>
                        <div class="flex items-center gap-2">
                          <div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
                            <div class="h-full bg-accent-500" style="width: {(s3.confidence_score || 0.90) * 100}%"></div>
                          </div>
                          <span class="text-[10px] font-bold text-accent-400">{Math.round((s3.confidence_score || 0.90) * 100)}% Match</span>
                        </div>
                      </div>
                    </td>
                    <td><button class="btn btn-ghost text-xs">Review</button></td>
                  </tr>
                {/each}
                {#each zombies?.legacy_ecr_images ?? [] as ecr}
                  <tr>
                    <td class="font-mono text-xs truncate max-w-[150px]">{ecr.resource_id}</td>
                    <td><span class="badge badge-default">ECR Image</span></td>
                    <td class="text-danger-400">${ecr.monthly_cost}</td>
                    <td>
                      <div class="flex flex-col gap-1 max-w-xs">
                        <p class="text-[10px] leading-tight text-ink-300">{ecr.explainability_notes || 'Untagged or superseded by multiple newer versions.'}</p>
                        <div class="flex items-center gap-2">
                          <div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
                            <div class="h-full bg-accent-500" style="width: {(ecr.confidence_score || 0.99) * 100}%"></div>
                          </div>
                          <span class="text-[10px] font-bold text-accent-400">{Math.round((ecr.confidence_score || 0.99) * 100)}% Match</span>
                        </div>
                      </div>
                    </td>
                    <td><button class="btn btn-ghost text-xs">Review</button></td>
                  </tr>
                {/each}
                {#each zombies?.idle_sagemaker_endpoints ?? [] as sm}
                  <tr>
                    <td class="font-mono text-xs">{sm.resource_id}</td>
                    <td><span class="badge badge-default">SageMaker Endpoint</span></td>
                    <td class="text-danger-400">${sm.monthly_cost}</td>
                    <td>
                      <div class="flex flex-col gap-1 max-w-xs">
                        <p class="text-[10px] leading-tight text-ink-300">{sm.explainability_notes || 'Endpoint has not processed any inference requests recently.'}</p>
                        <div class="flex items-center gap-2">
                          <div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
                            <div class="h-full bg-accent-500" style="width: {(sm.confidence_score || 0.95) * 100}%"></div>
                          </div>
                          <span class="text-[10px] font-bold text-accent-400">{Math.round((sm.confidence_score || 0.95) * 100)}% Match</span>
                        </div>
                      </div>
                    </td>
                    <td><button class="btn btn-ghost text-xs">Review</button></td>
                  </tr>
                {/each}
                {#each zombies?.cold_redshift_clusters ?? [] as rs}
                  <tr>
                    <td class="font-mono text-xs">{rs.resource_id}</td>
                    <td><span class="badge badge-default">Redshift Cluster</span></td>
                    <td class="text-danger-400">${rs.monthly_cost}</td>
                    <td>
                      <div class="flex flex-col gap-1 max-w-xs">
                        <p class="text-[10px] leading-tight text-ink-300">{rs.explainability_notes || 'Cluster has been in idle state for over 14 days.'}</p>
                        <div class="flex items-center gap-2">
                          <div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
                            <div class="h-full bg-accent-500" style="width: {(rs.confidence_score || 0.85) * 100}%"></div>
                          </div>
                          <span class="text-[10px] font-bold text-accent-400">{Math.round((rs.confidence_score || 0.85) * 100)}% Match</span>
                        </div>
                      </div>
                    </td>
                    <td><button class="btn btn-ghost text-xs">Review</button></td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        </div>
      {/if}
    {/if}
  </div>
{/if}

<style>
  .border-danger-500\/50 { border-color: rgb(244 63 94 / 0.5); }
</style>
