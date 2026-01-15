<!--
  Settings Page - Notification Preferences
  
  Features:
  - Slack notification toggle
  - Digest schedule (daily/weekly/disabled)
  - Alert preferences
  - Test notification button
-->

<script lang="ts">
  import { PUBLIC_API_URL } from '$env/static/public';
  import { createSupabaseBrowserClient } from '$lib/supabase';
  console.log('PUBLIC_API_URL:', PUBLIC_API_URL);

  
  let { data } = $props();
  
  const supabase = createSupabaseBrowserClient();
  
  let loading = $state(true);
  let saving = $state(false);
  let testing = $state(false);
  let error = $state('');
  let success = $state('');
  
  async function getHeaders() {
    const { data: { session } } = await supabase.auth.getSession();
    return {
      'Authorization': `Bearer ${session?.access_token}`,
      'Content-Type': 'application/json',
    };
  }

  async function loadSettings() {
    try {
      const headers = await getHeaders();
      const res = await fetch(`${PUBLIC_API_URL}/api/v1/settings/notifications`, { headers });
      if (res.ok) {
        settings = await res.json();
      }
    } catch (e) {
      console.error('Failed to load settings:', e);
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
      const res = await fetch(`${PUBLIC_API_URL}/api/v1/settings/notifications`, {
        method: 'PUT',
        headers,
        body: JSON.stringify(settings),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to save settings');
      }
      success = 'General settings saved!';
      setTimeout(() => success = '', 3000);
    } catch (e: any) {
      error = e.message;
    } finally {
      saving = false;
    }
  }
  
  // Settings state
  let settings = $state({
    slack_enabled: true,
    slack_channel_override: '',
    digest_schedule: 'daily',
    digest_hour: 9,
    digest_minute: 0,
    alert_on_budget_warning: true,
    alert_on_budget_exceeded: true,
    alert_on_zombie_detected: true,
  });
  
  // LLM Settings state
  let llmSettings = $state({
    monthly_limit_usd: 10.0,
    alert_threshold_percent: 80,
    hard_limit: false,
    preferred_provider: 'groq',
    preferred_model: 'llama-3.3-70b-versatile',
    openai_api_key: '',
    claude_api_key: '',
    google_api_key: '',
    groq_api_key: '',
    has_openai_key: false,
    has_claude_key: false,
    has_google_key: false,
    has_groq_key: false,
  });
  let loadingLLM = $state(true);
  let savingLLM = $state(false);
  
  // ActiveOps (Remediation) settings
  let activeOpsSettings = $state({
    auto_pilot_enabled: false,
    min_confidence_threshold: 0.95,
  });
  let loadingActiveOps = $state(true);
  let savingActiveOps = $state(false);
  
  let providerModels = $state({
    groq: [],
    openai: [],
    anthropic: [],
    google: [],
  });
  
  
  async function testSlack() {
    testing = true;
    error = '';
    
    try {
      const headers = await getHeaders();
      const res = await fetch(`${PUBLIC_API_URL}/api/v1/settings/notifications/test-slack`, {
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
  
  
  // Carbon settings state
  let carbonSettings = $state({
    carbon_budget_kg: 100,
    alert_threshold_percent: 80,
    default_region: 'us-east-1',
    email_enabled: false,
    email_recipients: '',
  });
  let loadingCarbon = $state(true);
  let savingCarbon = $state(false);
  
  async function loadCarbonSettings() {
    try {
      const headers = await getHeaders();
      const res = await fetch(`${PUBLIC_API_URL}/api/v1/settings/carbon`, { headers });
      
      if (res.ok) {
        carbonSettings = await res.json();
      }
    } catch (e: any) {
      console.error('Failed to load carbon settings:', e);
    } finally {
      loadingCarbon = false;
    }
  }
  
  async function saveCarbonSettings() {
    savingCarbon = true;
    error = '';
    success = '';
    
    try {
      const headers = await getHeaders();
      const res = await fetch(`${PUBLIC_API_URL}/api/v1/settings/carbon`, {
        method: 'PUT',
        headers,
        body: JSON.stringify(carbonSettings),
      });
      
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to save carbon settings');
      }
      
      success = 'Carbon settings saved successfully!';
      setTimeout(() => success = '', 3000);
    } catch (e: any) {
      error = e.message;
    } finally {
      savingCarbon = false;
    }
  }

  async function loadModels() {
    try {
      const res = await fetch(`${PUBLIC_API_URL}/api/v1/settings/llm/models`);
      if (res.ok) {
        providerModels = await res.json();
      }
    } catch (e) {
      console.error('Failed to load LLM models:', e);
    }
  }

  async function loadLLMSettings() {
    try {
      const headers = await getHeaders();
      const res = await fetch(`${PUBLIC_API_URL}/api/v1/settings/llm`, { headers });
      
      if (res.ok) {
        llmSettings = await res.json();
      }
    } catch (e: any) {
      console.error('Failed to load LLM settings:', e);
    } finally {
      loadingLLM = false;
    }
  }

  async function saveLLMSettings() {
    savingLLM = true;
    error = '';
    success = '';
    
    try {
      const headers = await getHeaders();
      const res = await fetch(`${PUBLIC_API_URL}/api/v1/settings/llm`, {
        method: 'PUT',
        headers,
        body: JSON.stringify(llmSettings),
      });
      
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to save LLM settings');
      }
      
      success = 'AI strategy settings saved!';
      setTimeout(() => success = '', 3000);
    } catch (e: any) {
      error = e.message;
    } finally {
      savingLLM = false;
    }
  }

  async function loadActiveOpsSettings() {
    try {
      const headers = await getHeaders();
      const res = await fetch(`${PUBLIC_API_URL}/api/v1/settings/activeops`, { headers });
      
      if (res.ok) {
        activeOpsSettings = await res.json();
      }
    } catch (e: any) {
      console.error('Failed to load ActiveOps settings:', e);
    } finally {
      loadingActiveOps = false;
    }
  }

  async function saveActiveOpsSettings() {
    savingActiveOps = true;
    error = '';
    success = '';
    
    try {
      const headers = await getHeaders();
      const res = await fetch(`${PUBLIC_API_URL}/api/v1/settings/activeops`, {
        method: 'PUT',
        headers,
        body: JSON.stringify(activeOpsSettings),
      });
      
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to save ActiveOps settings');
      }
      
      success = 'ActiveOps / Auto-Pilot settings saved!';
      setTimeout(() => success = '', 3000);
    } catch (e: any) {
      error = e.message;
    } finally {
      savingActiveOps = false;
    }
  }
  
  $effect(() => {
    if (data.user) {
      loadSettings();
      loadCarbonSettings();
      loadModels();
      loadLLMSettings();
      loadActiveOpsSettings();
    } else {
      loading = false;
      loadingCarbon = false;
      loadingLLM = false;
      loadingActiveOps = false;
    }
  });
</script>

<svelte:head>
  <title>Settings | Valdrix</title>
</svelte:head>

<div class="space-y-8">
  <!-- Page Header -->
  <div>
    <h1 class="text-2xl font-bold mb-1">Preferences</h1>
    <p class="text-ink-400 text-sm">Configure your notifications, AI strategy, and GreenOps thresholds.</p>
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
      <div role="alert" class="card border-danger-500/50 bg-danger-500/10">
        <p class="text-danger-400">{error}</p>
      </div>
    {/if}
    
    {#if success}
      <div role="status" class="card border-success-500/50 bg-success-500/10">
        <p class="text-success-400">{success}</p>
      </div>
    {/if}
    
    
    <!-- Carbon Budget Settings -->
    <div class="card stagger-enter relative" class:opacity-60={!['growth', 'pro', 'enterprise', 'trial'].includes(data.subscription?.tier)} class:pointer-events-none={!['growth', 'pro', 'enterprise', 'trial'].includes(data.subscription?.tier)}>
      <div class="flex items-center justify-between mb-5">
        <h2 class="text-lg font-semibold flex items-center gap-2">
          <span>🌱</span> Carbon Budget
        </h2>
        
        {#if !['growth', 'pro', 'enterprise', 'trial'].includes(data.subscription?.tier)}
           <span class="badge badge-warning text-xs">Growth Plan Required</span>
        {/if}
      </div>
      
      {#if !['growth', 'pro', 'enterprise', 'trial'].includes(data.subscription?.tier)}
        <div class="absolute inset-0 z-10 flex items-center justify-center bg-transparent">
             <a href="/billing" class="btn btn-primary shadow-lg pointer-events-auto">Upgrade to Unlock GreenOps</a>
        </div>
      {/if}

      {#if loadingCarbon}
        <div class="skeleton h-4 w-48"></div>
      {:else}
        <div class="space-y-4">
          <div class="form-group">
            <label for="carbon_budget">Monthly Carbon Budget (kg CO₂)</label>
            <input 
              type="number" 
              id="carbon_budget"
              bind:value={carbonSettings.carbon_budget_kg}
              min="0"
              step="10"
              disabled={!['growth', 'pro', 'enterprise', 'trial'].includes(data.subscription?.tier)}
              aria-label="Monthly carbon budget in kilograms"
            />
            <p class="text-xs text-ink-500 mt-1">Set your monthly carbon footprint limit</p>
          </div>
          
          <div class="form-group">
            <label for="alert_threshold">Alert Threshold (%)</label>
            <input 
              type="number" 
              id="alert_threshold"
              bind:value={carbonSettings.alert_threshold_percent}
              min="0"
              max="100"
              disabled={!['growth', 'pro', 'enterprise', 'trial'].includes(data.subscription?.tier)}
              aria-label="Carbon alert threshold percentage"
            />
            <p class="text-xs text-ink-500 mt-1">Warn when usage reaches this percentage of budget</p>
          </div>
          
          <div class="form-group">
            <label for="default_region">Default AWS Region</label>
            <select id="default_region" bind:value={carbonSettings.default_region} class="select" 
              disabled={!['growth', 'pro', 'enterprise', 'trial'].includes(data.subscription?.tier)}
              aria-label="Default AWS region for carbon analysis"
            >
              <option value="us-west-2">US West (Oregon) - 21 gCO₂/kWh ⭐</option>
              <option value="eu-north-1">EU (Stockholm) - 28 gCO₂/kWh ⭐</option>
              <option value="ca-central-1">Canada (Central) - 35 gCO₂/kWh ⭐</option>
              <option value="eu-west-1">EU (Ireland) - 316 gCO₂/kWh</option>
              <option value="us-east-1">US East (N. Virginia) - 379 gCO₂/kWh</option>
              <option value="ap-northeast-1">Asia Pacific (Tokyo) - 506 gCO₂/kWh</option>
            </select>
            <p class="text-xs text-ink-500 mt-1">Regions marked with ⭐ have lowest carbon intensity</p>
          </div>
          
          <!-- Email Notifications -->
          <div class="form-group">
            <label class="flex items-center gap-3 cursor-pointer">
              <input type="checkbox" bind:checked={carbonSettings.email_enabled} class="toggle" 
                disabled={!['growth', 'pro', 'enterprise', 'trial'].includes(data.subscription?.tier)} 
                aria-label="Enable email notifications for carbon alerts"
              />
              <span>Enable email notifications for carbon alerts</span>
            </label>
          </div>
          
          {#if carbonSettings.email_enabled}
            <div class="form-group">
              <label for="email_recipients">Email Recipients</label>
              <input 
                type="text" 
                id="email_recipients"
                bind:value={carbonSettings.email_recipients}
                placeholder="email1@example.com, email2@example.com"
                disabled={!['growth', 'pro', 'enterprise', 'trial'].includes(data.subscription?.tier)}
                aria-label="Carbon alert email recipients"
              />
              <p class="text-xs text-ink-500 mt-1">Comma-separated email addresses for carbon budget alerts</p>
            </div>
          {/if}
          
          <button class="btn btn-primary" onclick={saveCarbonSettings} 
            disabled={savingCarbon || !['growth', 'pro', 'enterprise', 'trial'].includes(data.subscription?.tier)}
            aria-label="Save carbon budget settings"
          >
            {savingCarbon ? '⏳ Saving...' : '💾 Save Carbon Settings'}
          </button>
        </div>
      {/if}
    </div>
    
    <!-- AI Strategy Settings -->
    <div class="card stagger-enter">
      <h2 class="text-lg font-semibold mb-5 flex items-center gap-2">
        <span>🤖</span> AI Strategy
      </h2>
      
      {#if loadingLLM}
        <div class="skeleton h-4 w-48"></div>
      {:else}
        <div class="space-y-4">
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div class="form-group">
              <label for="provider">Preferred Provider</label>
              <select id="provider" bind:value={llmSettings.preferred_provider} class="select" 
                onchange={() => llmSettings.preferred_model = providerModels[llmSettings.preferred_provider as keyof typeof providerModels][0]}
                aria-label="Preferred AI provider"
              >
                <option value="groq">Groq (Ultra-Fast)</option>
                <option value="openai">OpenAI (Gold Standard)</option>
                <option value="anthropic">Anthropic (Claude)</option>
                <option value="google">Google (Gemini)</option>
              </select>
            </div>
            
            <div class="form-group">
              <label for="model">AI Model</label>
              <select id="model" bind:value={llmSettings.preferred_model} class="select" aria-label="Preferred AI model">
                {#each providerModels[llmSettings.preferred_provider as keyof typeof providerModels] as model}
                  <option value={model}>{model}</option>
                {/each}
              </select>
            </div>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div class="form-group">
              <label for="llm_budget">Monthly AI Budget (USD)</label>
              <input 
                type="number" 
                id="llm_budget"
                bind:value={llmSettings.monthly_limit_usd}
                min="0"
                step="1"
                aria-label="Monthly AI budget in USD"
              />
            </div>
            
            <div class="form-group">
              <label for="llm_alert_threshold">Alert Threshold (%)</label>
              <input 
                type="number" 
                id="llm_alert_threshold"
                bind:value={llmSettings.alert_threshold_percent}
                min="0"
                max="100"
                aria-label="AI alert threshold percentage"
              />
            </div>
          </div>


          <div class="space-y-4 pt-4 border-t border-ink-700">
            <h3 class="text-sm font-semibold text-accent-400 uppercase tracking-wider">Bring Your Own Key (Optional)</h3>
            <p class="text-xs text-ink-400">Provide your own API key to pay the provider directly. The platform will still track usage for your awareness.</p>
            
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div class="form-group">
                <label for="openai_key">OpenAI API Key {llmSettings.has_openai_key ? '✅' : ''}</label>
                <input 
                  type="password" 
                  id="openai_key"
                  bind:value={llmSettings.openai_api_key}
                  placeholder={llmSettings.has_openai_key ? '••••••••••••••••' : 'sk-...'}
                  aria-label="OpenAI API Key"
                />
              </div>
              <div class="form-group">
                <label for="claude_key">Claude API Key {llmSettings.has_claude_key ? '✅' : ''}</label>
                <input 
                  type="password" 
                  id="claude_key"
                  bind:value={llmSettings.claude_api_key}
                  placeholder={llmSettings.has_claude_key ? '••••••••••••••••' : 'sk-ant-...'}
                  aria-label="Claude API Key"
                />
              </div>
              <div class="form-group">
                <label for="google_key">Google AI (Gemini) Key {llmSettings.has_google_key ? '✅' : ''}</label>
                <input 
                  type="password" 
                  id="google_key"
                  bind:value={llmSettings.google_api_key}
                  placeholder={llmSettings.has_google_key ? '••••••••••••••••' : 'AIza...'}
                  aria-label="Google AI (Gemini) API Key"
                />
              </div>
              <div class="form-group">
                <label for="groq_key">Groq API Key {llmSettings.has_groq_key ? '✅' : ''}</label>
                <input 
                  type="password" 
                  id="groq_key"
                  bind:value={llmSettings.groq_api_key}
                  placeholder={llmSettings.has_groq_key ? '••••••••••••••••' : 'gsk_...'}
                  aria-label="Groq API Key"
                />
              </div>
            </div>
          </div>

          <div class="form-group">
            <label class="flex items-center gap-3 cursor-pointer">
              <input type="checkbox" bind:checked={llmSettings.hard_limit} class="toggle" aria-label="Enable hard limit for AI budget" />
              <span>Enable Hard Limit (Block AI analysis if budget exceeded)</span>
            </label>
          </div>
          
          <button class="btn btn-primary" onclick={saveLLMSettings} disabled={savingLLM} aria-label="Save AI strategy settings">
            {savingLLM ? '⏳ Saving...' : '💾 Save AI Strategy'}
          </button>
        </div>
      {/if}
    </div>

    <!-- ActiveOps (Remediation) Settings -->
    <div class="card stagger-enter relative" class:opacity-60={!['pro', 'enterprise'].includes(data.subscription?.tier)} class:pointer-events-none={!['pro', 'enterprise'].includes(data.subscription?.tier)}>
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-lg font-semibold flex items-center gap-2">
          <span>⚡</span> ActiveOps (Autonomous Remediation)
        </h2>
        
        {#if !['pro', 'enterprise'].includes(data.subscription?.tier)}
           <span class="badge badge-warning text-xs">Pro Plan Required</span>
        {/if}
      </div>

      {#if !['pro', 'enterprise'].includes(data.subscription?.tier)}
        <div class="absolute inset-0 z-10 flex items-center justify-center bg-transparent">
             <a href="/billing" class="btn btn-primary shadow-lg pointer-events-auto">Upgrade to Unlock Auto-Pilot</a>
        </div>
      {/if}

      <p class="text-xs text-ink-400 mb-5">Enable AI to automatically remediate high-confidence zombie resources during weekly sweeps.</p>
      
      {#if loadingActiveOps}
        <div class="skeleton h-4 w-48"></div>
      {:else}
        <div class="space-y-6">
          <div class="p-4 rounded-lg bg-warning-900/10 border border-warning-900/30">
            <h4 class="text-sm font-bold text-warning-400 mb-1">⚠️ Safety Disclaimer</h4>
            <p class="text-xs text-warning-500 leading-relaxed">
              Auto-Pilot mode allows Valdrix to perform destructive actions (deletion) on identified resources. 
              Always ensure you have regular backups. Actions are only taken if the AI confidence exceeds the specified threshold.
            </p>
          </div>

          <label class="flex items-center gap-3 cursor-pointer">
            <input type="checkbox" bind:checked={activeOpsSettings.auto_pilot_enabled} class="toggle toggle-warning" 
              disabled={!['pro', 'enterprise'].includes(data.subscription?.tier)} 
              aria-label="Enable Auto-Pilot for autonomous deletion"
            />
            <span class="font-medium {activeOpsSettings.auto_pilot_enabled ? 'text-white' : 'text-ink-400'}">
              Enable Auto-Pilot (Weekly Autonomous Deletion)
            </span>
          </label>
          
          <div class="form-group">
            <label for="confidence_threshold">Min Confidence Threshold: {Math.round(activeOpsSettings.min_confidence_threshold * 100)}%</label>
            <input 
              type="range" 
              id="confidence_threshold"
              bind:value={activeOpsSettings.min_confidence_threshold}
              min="0.5"
              max="1.0"
              step="0.01"
              class="range"
              disabled={!activeOpsSettings.auto_pilot_enabled || !['pro', 'enterprise'].includes(data.subscription?.tier)}
              aria-label="Minimum AI confidence threshold for autonomous actions"
            />
            <div class="flex justify-between text-[10px] text-ink-500 mt-1">
              <span>Riskier (50%)</span>
              <span>Ultra-Safe (100%)</span>
            </div>
          </div>
          
          <button class="btn btn-primary" onclick={saveActiveOpsSettings} 
            disabled={savingActiveOps || !['pro', 'enterprise'].includes(data.subscription?.tier)}
            aria-label="Save ActiveOps settings"
          >
            {savingActiveOps ? '⏳ Saving...' : '💾 Save ActiveOps Settings'}
          </button>
        </div>
      {/if}
    </div>

    <!-- Slack Settings -->
    <div class="card stagger-enter">
      <h2 class="text-lg font-semibold mb-5 flex items-center gap-2">
        <span>💬</span> Slack Notifications
      </h2>
      
      <div class="space-y-4">
        <label class="flex items-center gap-3 cursor-pointer">
          <input type="checkbox" bind:checked={settings.slack_enabled} class="toggle" aria-label="Enable Slack notifications" />
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
            aria-label="Slack channel ID override"
          />
          <p class="text-xs text-ink-500 mt-1">Leave empty to use the default channel</p>
        </div>
        
        <button 
          class="btn btn-secondary" 
          onclick={testSlack}
          disabled={!settings.slack_enabled || testing}
          aria-label="Send test Slack notification"
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
          <select id="schedule" bind:value={settings.digest_schedule} class="select" aria-label="Daily digest frequency">
            <option value="daily">Daily</option>
            <option value="weekly">Weekly (Mondays)</option>
            <option value="disabled">Disabled</option>
          </select>
        </div>
        
        {#if settings.digest_schedule !== 'disabled'}
          <div class="grid grid-cols-2 gap-4">
            <div class="form-group">
              <label for="hour">Hour (UTC)</label>
              <select id="hour" bind:value={settings.digest_hour} class="select" aria-label="Digest delivery hour (UTC)">
                {#each Array(24).fill(0).map((_, i) => i) as h}
                  <option value={h}>{h.toString().padStart(2, '0')}:00</option>
                {/each}
              </select>
            </div>
            <div class="form-group">
              <label for="minute">Minute</label>
              <select id="minute" bind:value={settings.digest_minute} class="select" aria-label="Digest delivery minute">
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
      <button class="btn btn-primary" onclick={saveSettings} disabled={saving}>
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

  .toggle-warning:checked {
    background: var(--color-warning-500);
  }
  
  .range {
    width: 100%;
    height: 0.5rem;
    background: var(--color-ink-700);
    border-radius: 999px;
    appearance: none;
    outline: none;
  }

  .range::-webkit-slider-thumb {
    appearance: none;
    width: 1.25rem;
    height: 1.25rem;
    background: var(--color-accent-400);
    border-radius: 50%;
    cursor: pointer;
    transition: transform 0.1s;
  }

  .range::-webkit-slider-thumb:hover {
    transform: scale(1.1);
  }

  .range:disabled::-webkit-slider-thumb {
    background: var(--color-ink-500);
    cursor: not-allowed;
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
  
  .btn-danger {
    background: rgb(220, 38, 38);
    color: white;
    border: none;
  }
  
  .btn-danger:hover:not(:disabled) {
    background: rgb(185, 28, 28);
  }
  
  .connection-status {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: var(--color-ink-500);
  }
  
  .connection-status.connected {
    background: rgb(16, 185, 129);
    box-shadow: 0 0 8px rgb(16, 185, 129 / 0.5);
  }
  
  .border-ink-700 {
    border-color: var(--color-ink-700);
  }

  /* Provider Status Cards */
  .provider-status-card {
    background: var(--color-ink-800);
    border: 1px solid var(--color-ink-700);
    border-radius: 12px;
    padding: 1.5rem;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    transition: all 0.2s ease;
  }

  .provider-status-card:hover {
    border-color: var(--color-accent-500);
    transform: translateY(-2px);
  }

  .logo-sm {
    width: 32px;
    height: 32px;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: bold;
    font-size: 0.8rem;
  }

  .logo-sm.aws { background: rgba(255, 153, 0, 0.1); color: #FF9900; }
  .logo-sm.azure { background: rgba(0, 120, 212, 0.1); color: #0078D4; }
  .logo-sm.gcp { background: rgba(66, 133, 244, 0.1); color: #4284F4; }

  .badge-accent {
    background: rgba(99, 102, 241, 0.2);
    color: var(--color-accent-400);
    border: 1px solid rgba(99, 102, 241, 0.3);
  }
</style>
