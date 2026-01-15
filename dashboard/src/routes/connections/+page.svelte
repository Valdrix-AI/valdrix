<script lang="ts">
  import { PUBLIC_API_URL } from '$env/static/public';
  import { createSupabaseBrowserClient } from '$lib/supabase';
  import CloudLogo from '$lib/components/CloudLogo.svelte';
  import { onMount } from 'svelte';
  
  let { data } = $props();
  const supabase = createSupabaseBrowserClient();
  
  let loadingAWS = $state(true);
  let loadingAzure = $state(true);
  let loadingGCP = $state(true);
  
  let awsConnection: any = $state(null);
  let azureConnection: any = $state(null);
  let gcpConnection: any = $state(null);
  
  let gcpProjectId = $state('');
  let azureSubscriptionId = $state('');
  
  let discoveredAccounts: any[] = $state([]);
  let loadingDiscovered = $state(false);
  let syncingOrg = $state(false);
  let linkingAccount: string | null = $state(null);
  
  let error = $state('');
  let success = $state('');

  async function getHeaders() {
    const { data: { session } } = await supabase.auth.getSession();
    return {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${session?.access_token}`,
    };
  }

  async function loadConnections() {
    try {
      const headers = await getHeaders();
      
      // AWS
      const awsRes = await fetch(`${PUBLIC_API_URL}/api/v1/connections/aws`, { headers });
      if (awsRes.ok) {
        const awsData = await awsRes.json();
        awsConnection = awsData.length > 0 ? awsData[0] : null;
      }
      loadingAWS = false;

      // Azure
      const azureRes = await fetch(`${PUBLIC_API_URL}/api/v1/connections/azure`, { headers });
      if (azureRes.ok) {
        const azureData = await azureRes.json();
        azureConnection = azureData.length > 0 ? azureData[0] : null;
      }
      loadingAzure = false;

      // GCP
      const gcpRes = await fetch(`${PUBLIC_API_URL}/api/v1/connections/gcp`, { headers });
      if (gcpRes.ok) {
        const gcpData = await gcpRes.json();
        gcpConnection = gcpData.length > 0 ? gcpData[0] : null;
      }
      loadingGCP = false;

      if (awsConnection?.is_management_account) {
        loadDiscoveredAccounts();
      }
    } catch (e: any) {
      error = "Failed to load cloud accounts. Check backend connection.";
      loadingAWS = loadingAzure = loadingGCP = false;
    }
  }

  async function loadDiscoveredAccounts() {
    loadingDiscovered = true;
    try {
      const headers = await getHeaders();
      const res = await fetch(`${PUBLIC_API_URL}/api/v1/connections/aws/discovered`, { headers });
      if (res.ok) {
        discoveredAccounts = await res.json();
      }
    } catch (e) {
      console.error('Failed to load discovered accounts', e);
    } finally {
      loadingDiscovered = false;
    }
  }

  async function syncAWSOrg() {
    if (!awsConnection) return;
    syncingOrg = true;
    success = '';
    error = '';
    try {
      const headers = await getHeaders();
      const res = await fetch(`${PUBLIC_API_URL}/api/v1/connections/aws/${awsConnection.id}/sync-org`, {
        method: 'POST',
        headers
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Sync failed');
      
      success = data.message;
      await loadDiscoveredAccounts();
      setTimeout(() => success = '', 3000);
    } catch (e: any) {
      error = e.message;
    } finally {
      syncingOrg = false;
    }
  }

  async function linkDiscoveredAccount(discoveredId: string) {
    linkingAccount = discoveredId;
    success = '';
    error = '';
    try {
      const headers = await getHeaders();
      const res = await fetch(`${PUBLIC_API_URL}/api/v1/connections/aws/discovered/${discoveredId}/link`, {
        method: 'POST',
        headers
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Linking failed');
      
      success = data.message;
      await loadDiscoveredAccounts();
      await loadConnections();
      setTimeout(() => success = '', 3000);
    } catch (e: any) {
      error = e.message;
    } finally {
      linkingAccount = null;
    }
  }

  onMount(() => {
    loadConnections();
  });
</script>

<svelte:head>
  <title>Cloud Accounts | Valdrix</title>
</svelte:head>

<div class="space-y-8">
  <div class="flex items-center justify-between">
    <div>
      <h1 class="text-3xl font-bold mb-2">Cloud Accounts</h1>
      <p class="text-ink-400">Manage your multi-cloud connectivity and enterprise organization discovery.</p>
    </div>
    <a href="/onboarding" class="btn btn-primary !w-auto">
      <span>➕</span> Connect New Provider
    </a>
  </div>

  {#if error}
    <div class="card border-danger-500/50 bg-danger-500/10">
      <p class="text-danger-400">{error}</p>
    </div>
  {/if}

  {#if success}
    <div class="card border-success-500/50 bg-success-500/10">
      <p class="text-success-400">{success}</p>
    </div>
  {/if}

  <!-- Integration Status Cards -->
  <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
    <!-- AWS -->
    <div class="glass-panel stagger-enter" style="animation-delay: 0ms;">
      <div class="flex items-center justify-between mb-4">
        <div class="flex items-center gap-3">
          <CloudLogo provider="aws" size={40} />
          <div>
            <h3 class="font-bold text-lg">AWS</h3>
            <p class="text-xs text-ink-500">Public Cloud Provider</p>
          </div>
        </div>
        {#if loadingAWS}
          <div class="skeleton w-4 h-4 rounded-full"></div>
        {:else if awsConnection}
          <span class="badge badge-success">Active</span>
        {:else}
          <span class="badge badge-default">Disconnected</span>
        {/if}
      </div>
      
      {#if awsConnection}
        <div class="space-y-2 mb-6">
          <div class="flex justify-between text-xs">
            <span class="text-ink-400">Account ID:</span>
            <span class="font-mono">{awsConnection.aws_account_id}</span>
          </div>
          <div class="flex justify-between text-xs">
            <span class="text-ink-400">Type:</span>
            <span class="capitalize">{awsConnection.is_management_account ? 'Management Account' : 'Member Account'}</span>
          </div>
        </div>
        <a href="/onboarding" class="btn btn-ghost text-xs w-full">Update Settings</a>
      {:else if !loadingAWS}
        <p class="text-xs text-ink-400 mb-6">Establish a secure connection using our 1-click CloudFormation template.</p>
        <a href="/onboarding" class="btn btn-primary text-xs w-full">Connect AWS</a>
      {/if}
    </div>

    <!-- Azure -->
    <div class="glass-panel stagger-enter" style="animation-delay: 100ms;">
      <div class="flex items-center justify-between mb-4">
        <div class="flex items-center gap-3">
          <CloudLogo provider="azure" size={40} />
          <div>
            <h3 class="font-bold text-lg">Azure</h3>
            <p class="text-xs text-ink-500">Public Cloud Provider</p>
          </div>
        </div>
        {#if loadingAzure}
          <div class="skeleton w-4 h-4 rounded-full"></div>
        {:else if azureConnection}
          <span class="badge badge-accent">Secure</span>
        {:else}
          <span class="badge badge-default">Disconnected</span>
        {/if}
      </div>
      
      {#if azureConnection}
        <div class="space-y-2 mb-6">
          <div class="flex justify-between text-xs">
            <span class="text-ink-400">Subscription:</span>
            <span class="font-mono truncate max-w-[120px]">{azureConnection.subscription_id}</span>
          </div>
          <div class="flex justify-between text-xs">
            <span class="text-ink-400">Auth:</span>
            <span>Zero-Secret</span>
          </div>
        </div>
        <a href="/onboarding" class="btn btn-ghost text-xs w-full">Update Settings</a>
      {:else if !loadingAzure}
        <p class="text-xs text-ink-400 mb-6">Connect via Workload Identity Federation for secret-less security.</p>
        <div class="flex flex-col gap-2">
           <a href="/onboarding" class="btn btn-secondary text-xs w-full">Connect Azure</a>
           <span class="badge badge-warning text-[10px] w-full justify-center">Growth Tier Required</span>
        </div>
      {/if}
    </div>

    <!-- GCP -->
    <div class="glass-panel stagger-enter" style="animation-delay: 200ms;">
      <div class="flex items-center justify-between mb-4">
        <div class="flex items-center gap-3">
          <CloudLogo provider="gcp" size={40} />
          <div>
            <h3 class="font-bold text-lg">GCP</h3>
            <p class="text-xs text-ink-500">Public Cloud Provider</p>
          </div>
        </div>
        {#if loadingGCP}
          <div class="skeleton w-4 h-4 rounded-full"></div>
        {:else if gcpConnection}
          <span class="badge badge-accent">Secure</span>
        {:else}
          <span class="badge badge-default">Disconnected</span>
        {/if}
      </div>
      
      {#if gcpProjectId && gcpConnection}
        <div class="space-y-2 mb-6">
          <div class="flex justify-between text-xs">
            <span class="text-ink-400">Project ID:</span>
            <span class="font-mono">{gcpConnection.project_id}</span>
          </div>
          <div class="flex justify-between text-xs">
            <span class="text-ink-400">Auth:</span>
            <span>Identity Federation</span>
          </div>
        </div>
        <a href="/onboarding" class="btn btn-ghost text-xs w-full">Update Settings</a>
      {:else if !loadingGCP}
        <p class="text-xs text-ink-400 mb-6">Seamless integration using GCP Workload Identity pools.</p>
        <div class="flex flex-col gap-2">
           <a href="/onboarding" class="btn btn-secondary text-xs w-full">Connect GCP</a>
           <span class="badge badge-warning text-[10px] w-full justify-center">Growth Tier Required</span>
        </div>
      {/if}
    </div>
  </div>

  <!-- AWS Organizations Hub (RELOCATED & POLISHED) -->
  {#if awsConnection?.is_management_account}
    <div class="card stagger-enter mt-12 border-accent-500/30 bg-accent-500/5 relative overflow-hidden" 
         class:opacity-60={!['growth', 'pro', 'enterprise', 'trial'].includes(data.subscription?.tier)}>
      
      <!-- Background pattern -->
      <div class="absolute top-0 right-0 p-8 opacity-10 pointer-events-none">
        <span class="text-9xl">🏢</span>
      </div>

      <div class="relative z-10">
        <div class="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
          <div>
            <h2 class="text-2xl font-bold flex items-center gap-2 mb-1">
              <span>🏢</span> AWS Organizations Hub
            </h2>
            <p class="text-sm text-ink-400">
              Managing Organization: <span class="text-accent-400 font-mono">{awsConnection.organization_id || 'Global'}</span>
            </p>
          </div>
          
          <div class="flex items-center gap-3">
            {#if !['growth', 'pro', 'enterprise', 'trial'].includes(data.subscription?.tier)}
               <span class="badge badge-warning">Growth Tier Required</span>
            {:else}
              <button 
                class="btn btn-primary !w-auto flex items-center gap-2" 
                onclick={syncAWSOrg} 
                disabled={syncingOrg}
              >
                {#if syncingOrg}
                  <div class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                  <span>Syncing...</span>
                {:else}
                  <span>🔄</span>
                  <span>Sync Accounts</span>
                {/if}
              </button>
            {/if}
          </div>
        </div>

        {#if !['growth', 'pro', 'enterprise', 'trial'].includes(data.subscription?.tier)}
          <div class="py-20 text-center glass-panel bg-black/20 border-white/5">
            <div class="mb-6 text-5xl">🔒</div>
            <h3 class="text-xl font-bold mb-2">Enterprise Organization Discovery</h3>
            <p class="text-ink-400 max-w-md mx-auto mb-8">
              Unlock the ability to automatically discover, monitor, and optimize hundreds of member accounts across your entire AWS Organization.
            </p>
            <a href="/billing" class="btn btn-primary !w-auto px-8 py-3">Upgrade to Growth Tier</a>
          </div>
        {:else}
          <div class="grid grid-cols-1 lg:grid-cols-4 gap-6 mb-8">
            <div class="card bg-ink-900/50 p-4 border-ink-800">
              <p class="text-xs text-ink-500 mb-1">Total Discovered</p>
              <p class="text-2xl font-bold">{discoveredAccounts.length}</p>
            </div>
            <div class="card bg-ink-900/50 p-4 border-ink-800">
              <p class="text-xs text-ink-500 mb-1">Linked Accounts</p>
              <p class="text-2xl font-bold text-success-400">{discoveredAccounts.filter(a => a.status === 'linked').length}</p>
            </div>
            <div class="card bg-ink-900/50 p-4 border-ink-800">
              <p class="text-xs text-ink-500 mb-1">Pending Link</p>
              <p class="text-2xl font-bold text-warning-400">{discoveredAccounts.filter(a => a.status === 'discovered').length}</p>
            </div>
            <div class="card bg-ink-900/50 p-4 border-ink-800">
              <p class="text-xs text-ink-500 mb-1">Org Status</p>
              <p class="text-2xl font-bold text-accent-400">Synced</p>
            </div>
          </div>

          {#if loadingDiscovered}
            <div class="space-y-4">
              <div class="skeleton h-12 w-full"></div>
              <div class="skeleton h-12 w-full"></div>
              <div class="skeleton h-12 w-full"></div>
            </div>
          {:else if discoveredAccounts.length > 0}
            <div class="overflow-x-auto rounded-xl border border-ink-800">
              <table class="w-full text-sm text-left">
                <thead class="bg-ink-900/80 text-ink-400 uppercase text-[10px] tracking-wider">
                  <tr>
                    <th class="px-6 py-4 font-semibold uppercase">Account Details</th>
                    <th class="px-6 py-4 font-semibold uppercase">Email</th>
                    <th class="px-6 py-4 font-semibold uppercase">Status</th>
                    <th class="px-6 py-4 font-semibold uppercase text-right">Action</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-ink-800">
                  {#each discoveredAccounts as acc}
                    <tr class="hover:bg-accent-500/5 transition-colors">
                      <td class="px-6 py-4">
                        <div class="font-bold mb-0.5">{acc.name || 'Unnamed Account'}</div>
                        <div class="text-xs font-mono text-ink-500">{acc.account_id}</div>
                      </td>
                      <td class="px-6 py-4 text-ink-400">{acc.email || '-'}</td>
                      <td class="px-6 py-4">
                        <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium
                          {acc.status === 'linked' ? 'bg-success-500/10 text-success-400 border border-success-500/20' : 
                          'bg-ink-800 text-ink-400 border border-ink-700'}">
                          <span class="w-1.5 h-1.5 rounded-full {acc.status === 'linked' ? 'bg-success-400' : 'bg-ink-500'}"></span>
                          {acc.status}
                        </div>
                      </td>
                      <td class="px-6 py-4 text-right">
                        {#if acc.status === 'discovered'}
                          <button 
                            class="btn btn-ghost btn-sm text-accent-400 hover:text-accent-300 hover:bg-accent-400/10"
                            onclick={() => linkDiscoveredAccount(acc.id)}
                            disabled={linkingAccount === acc.id}
                          >
                            {linkingAccount === acc.id ? 'Connecting...' : 'Link Account →'}
                          </button>
                        {:else}
                          <span class="text-success-400 font-medium">✓ Linked</span>
                        {/if}
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {:else}
            <div class="py-16 text-center border-2 border-dashed border-ink-800 rounded-3xl bg-ink-900/20">
              <div class="text-5xl mb-4">🔍</div>
              <h3 class="text-xl font-bold mb-2">No Member Accounts Found</h3>
              <p class="text-ink-500 max-w-sm mx-auto mb-6">We couldn't find any member accounts. Run a sync to scan your Organization.</p>
              <button class="btn btn-primary !w-auto px-8" onclick={syncAWSOrg}>
                Start Organizational Scan
              </button>
            </div>
          {/if}
        {/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .glass-panel {
    background: rgba(15, 23, 42, 0.4);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 24px;
    padding: 1.5rem;
    transition: all 0.3s ease;
  }
  
  .glass-panel:hover {
    border-color: rgba(6, 182, 212, 0.3);
    box-shadow: 0 10px 30px -15px rgba(6, 182, 212, 0.2);
    transform: translateY(-2px);
  }
</style>
