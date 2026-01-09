<!--
  Settings Page - Notification Preferences
  
  Features:
  - Slack notification toggle
  - Digest schedule (daily/weekly/disabled)
  - Alert preferences
  - Test notification button
-->

<script lang="ts">
  import { onMount } from 'svelte';
  import { PUBLIC_API_URL } from '$env/static/public';
  import { createSupabaseBrowserClient } from '$lib/supabase';
  
  export let data;
  
  const supabase = createSupabaseBrowserClient();
  
  let loading = true;
  let saving = false;
  let testing = false;
  let error = '';
  let success = '';
  
  // Settings state
  let settings = {
    slack_enabled: true,
    slack_channel_override: '',
    digest_schedule: 'daily',
    digest_hour: 9,
    digest_minute: 0,
    alert_on_budget_warning: true,
    alert_on_budget_exceeded: true,
    alert_on_zombie_detected: true,
  };
  
  async function getHeaders() {
    const { data: { session } } = await supabase.auth.getSession();
    return {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${session?.access_token}`,
    };
  }
  
  async function loadSettings() {
    try {
      const headers = await getHeaders();
      const res = await fetch(`${PUBLIC_API_URL}/settings/notifications`, { headers });
      
      if (res.ok) {
        settings = await res.json();
      }
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  }
  
  async function saveSettings() {
    saving = true;
    error = '';
    success = '';
    
    try {
      const headers = await getHeaders();
      const res = await fetch(`${PUBLIC_API_URL}/settings/notifications`, {
        method: 'PUT',
        headers,
        body: JSON.stringify(settings),
      });
      
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to save settings');
      }
      
      success = 'Settings saved successfully!';
      setTimeout(() => success = '', 3000);
    } catch (e: any) {
      error = e.message;
    } finally {
      saving = false;
    }
  }
  
  async function testSlack() {
    testing = true;
    error = '';
    
    try {
      const headers = await getHeaders();
      const res = await fetch(`${PUBLIC_API_URL}/settings/notifications/test-slack`, {
        method: 'POST',
        headers,
      });
      
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to send test notification');
      }
      
      success = 'Test notification sent to Slack!';
      setTimeout(() => success = '', 3000);
    } catch (e: any) {
      error = e.message;
    } finally {
      testing = false;
    }
  }
  
  onMount(() => {
    if (data.user) {
      loadSettings();
    } else {
      loading = false;
    }
  });
</script>

<svelte:head>
  <title>Settings | CloudSentinel</title>
</svelte:head>

<div class="space-y-8">
  <!-- Page Header -->
  <div>
    <h1 class="text-2xl font-bold mb-1">Settings</h1>
    <p class="text-ink-400 text-sm">Configure your notification preferences</p>
  </div>
  
  {#if !data.user}
    <div class="card text-center py-12">
      <p class="text-ink-400">Please <a href="/auth/login" class="text-accent-400 hover:underline">sign in</a> to manage settings.</p>
    </div>
  {:else if loading}
    <div class="card">
      <div class="skeleton h-8 w-48 mb-4"></div>
      <div class="skeleton h-4 w-full mb-2"></div>
      <div class="skeleton h-4 w-3/4"></div>
    </div>
  {:else}
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
    
    <!-- Slack Settings -->
    <div class="card stagger-enter">
      <h2 class="text-lg font-semibold mb-5 flex items-center gap-2">
        <span>💬</span> Slack Notifications
      </h2>
      
      <div class="space-y-4">
        <label class="flex items-center gap-3 cursor-pointer">
          <input type="checkbox" bind:checked={settings.slack_enabled} class="toggle" />
          <span>Enable Slack notifications</span>
        </label>
        
        <div class="form-group">
          <label for="channel">Channel Override (optional)</label>
          <input 
            type="text" 
            id="channel"
            bind:value={settings.slack_channel_override}
            placeholder="C01234ABCDE"
            disabled={!settings.slack_enabled}
          />
          <p class="text-xs text-ink-500 mt-1">Leave empty to use the default channel</p>
        </div>
        
        <button 
          class="btn btn-secondary" 
          on:click={testSlack}
          disabled={!settings.slack_enabled || testing}
        >
          {testing ? '⏳ Sending...' : '🧪 Send Test Notification'}
        </button>
      </div>
    </div>
    
    <!-- Digest Schedule -->
    <div class="card stagger-enter" style="animation-delay: 50ms;">
      <h2 class="text-lg font-semibold mb-5 flex items-center gap-2">
        <span>📅</span> Daily Digest
      </h2>
      
      <div class="space-y-4">
        <div class="form-group">
          <label for="schedule">Frequency</label>
          <select id="schedule" bind:value={settings.digest_schedule} class="select">
            <option value="daily">Daily</option>
            <option value="weekly">Weekly (Mondays)</option>
            <option value="disabled">Disabled</option>
          </select>
        </div>
        
        {#if settings.digest_schedule !== 'disabled'}
          <div class="grid grid-cols-2 gap-4">
            <div class="form-group">
              <label for="hour">Hour (UTC)</label>
              <select id="hour" bind:value={settings.digest_hour} class="select">
                {#each Array(24).fill(0).map((_, i) => i) as h}
                  <option value={h}>{h.toString().padStart(2, '0')}:00</option>
                {/each}
              </select>
            </div>
            <div class="form-group">
              <label for="minute">Minute</label>
              <select id="minute" bind:value={settings.digest_minute} class="select">
                {#each [0, 15, 30, 45] as m}
                  <option value={m}>:{m.toString().padStart(2, '0')}</option>
                {/each}
              </select>
            </div>
          </div>
        {/if}
      </div>
    </div>
    
    <!-- Alert Preferences -->
    <div class="card stagger-enter" style="animation-delay: 100ms;">
      <h2 class="text-lg font-semibold mb-5 flex items-center gap-2">
        <span>🚨</span> Alert Preferences
      </h2>
      
      <div class="space-y-3">
        <label class="flex items-center gap-3 cursor-pointer">
          <input type="checkbox" bind:checked={settings.alert_on_budget_warning} class="toggle" />
          <span>Alert when approaching budget limit</span>
        </label>
        
        <label class="flex items-center gap-3 cursor-pointer">
          <input type="checkbox" bind:checked={settings.alert_on_budget_exceeded} class="toggle" />
          <span>Alert when budget is exceeded</span>
        </label>
        
        <label class="flex items-center gap-3 cursor-pointer">
          <input type="checkbox" bind:checked={settings.alert_on_zombie_detected} class="toggle" />
          <span>Alert when zombie resources detected</span>
        </label>
      </div>
    </div>
    
    <!-- Save Button -->
    <div class="flex justify-end">
      <button class="btn btn-primary" on:click={saveSettings} disabled={saving}>
        {saving ? '⏳ Saving...' : '💾 Save Settings'}
      </button>
    </div>
  {/if}
</div>

<style>
  .text-ink-400 { color: var(--color-ink-400); }
  .text-ink-500 { color: var(--color-ink-500); }
  .text-accent-400 { color: var(--color-accent-400); }
  .text-danger-400 { color: var(--color-danger-400); }
  .text-success-400 { color: var(--color-success-400); }
  .bg-danger-500\/10 { background-color: rgb(244 63 94 / 0.1); }
  .bg-success-500\/10 { background-color: rgb(16 185 129 / 0.1); }
  .border-danger-500\/50 { border-color: rgb(244 63 94 / 0.5); }
  .border-success-500\/50 { border-color: rgb(16 185 129 / 0.5); }
  
  .form-group {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .form-group label {
    font-weight: 500;
    font-size: 0.875rem;
  }
  
  input[type="text"], .select {
    width: 100%;
    padding: 0.75rem;
    border: 1px solid var(--color-ink-700);
    border-radius: 0.5rem;
    background: var(--color-ink-900);
    color: white;
  }
  
  input:disabled, .select:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .toggle {
    width: 3rem;
    height: 1.5rem;
    appearance: none;
    background: var(--color-ink-700);
    border-radius: 999px;
    position: relative;
    cursor: pointer;
    transition: background 0.2s;
  }
  
  .toggle:checked {
    background: var(--color-accent-500);
  }
  
  .toggle::after {
    content: '';
    position: absolute;
    top: 2px;
    left: 2px;
    width: 1.25rem;
    height: 1.25rem;
    background: white;
    border-radius: 50%;
    transition: transform 0.2s;
  }
  
  .toggle:checked::after {
    transform: translateX(1.5rem);
  }
  
  .btn {
    padding: 0.75rem 1.5rem;
    border-radius: 0.5rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .btn-primary {
    background: var(--color-accent-500);
    color: white;
    border: none;
  }
  
  .btn-primary:hover:not(:disabled) {
    opacity: 0.9;
  }
  
  .btn-secondary {
    background: transparent;
    border: 1px solid var(--color-ink-600);
    color: var(--color-ink-300);
  }
  
  .btn-secondary:hover:not(:disabled) {
    background: var(--color-ink-800);
  }
  
  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>
