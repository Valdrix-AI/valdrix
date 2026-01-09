<script lang="ts">
  import { onMount } from 'svelte';
  import { createSupabaseBrowserClient } from '$lib/supabase';
  
  // State management
  let currentStep = 1;
  let selectedTab: 'cloudformation' | 'terraform' = 'cloudformation';
  let externalId = '';
  let cloudformationYaml = '';
  let terraformHcl = '';
  let permissionsSummary: string[] = [];
  let roleArn = '';
  let awsAccountId = '';
  let isLoading = false;
  let isVerifying = false;
  let error = '';
  let success = false;
  let copied = false;
  
  const API_URL = 'http://localhost:8002';
  const supabase = createSupabaseBrowserClient();
  
  // Get access token from Supabase session
  async function getAccessToken(): Promise<string | null> {
    const { data: { session } } = await supabase.auth.getSession();
    return session?.access_token ?? null;
  }
  
  // Step 1: Get templates from backend
  async function getTemplates() {
    isLoading = true;
    error = '';
    
    try {
      const res = await fetch(`${API_URL}/connections/aws/setup`, {
        method: 'POST',
      });
      
      if (!res.ok) throw new Error('Failed to get templates');
      
      const data = await res.json();
      externalId = data.external_id;
      cloudformationYaml = data.cloudformation_yaml;
      terraformHcl = data.terraform_hcl;
      permissionsSummary = data.permissions_summary || [];
    } catch (e) {
      error = e instanceof Error ? e.message : 'Unknown error';
    } finally {
      isLoading = false;
    }
  }
  
  // Copy template to clipboard
  function copyTemplate() {
    const template = selectedTab === 'cloudformation' ? cloudformationYaml : terraformHcl;
    navigator.clipboard.writeText(template);
    copied = true;
    setTimeout(() => copied = false, 2000);
  }
  
  // Download template as file
  function downloadTemplate() {
    const template = selectedTab === 'cloudformation' ? cloudformationYaml : terraformHcl;
    const filename = selectedTab === 'cloudformation' 
      ? 'cloudsentinel-role.yaml' 
      : 'cloudsentinel-role.tf';
    
    const blob = new Blob([template], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }
  
  // Move to step 2
  function proceedToVerify() {
    currentStep = 2;
  }
  
  // Verify connection
  async function verifyConnection() {
    if (!roleArn || !awsAccountId) {
      error = 'Please enter both AWS Account ID and Role ARN';
      return;
    }
    
    isVerifying = true;
    error = '';
    
    try {
      // Get the access token from Supabase session
      const token = await getAccessToken();
      
      if (!token) {
        error = 'Please log in first to verify your AWS connection';
        isVerifying = false;
        return;
      }
      
      const createRes = await fetch(`${API_URL}/connections/aws`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          aws_account_id: awsAccountId,
          role_arn: roleArn,
          external_id: externalId,  // Pass the SAME external_id from step 1!
          region: 'us-east-1',
        }),
      });
      
      if (!createRes.ok) {
        const errData = await createRes.json();
        throw new Error(errData.detail || 'Failed to create connection');
      }
      
      const connection = await createRes.json();
      
      const verifyRes = await fetch(`${API_URL}/connections/aws/${connection.id}/verify`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      });
      
      if (!verifyRes.ok) {
        const errData = await verifyRes.json();
        throw new Error(errData.detail || 'Verification failed');
      }
      
      success = true;
      currentStep = 3;
      
    } catch (e) {
      error = e instanceof Error ? e.message : 'Unknown error';
    } finally {
      isVerifying = false;
    }
  }
  
  onMount(() => {
    getTemplates();
  });
</script>

<div class="onboarding-container">
  <h1>🔗 Connect Your AWS Account</h1>
  
  <!-- Progress indicator -->
  <div class="progress-steps">
    <div class="step" class:active={currentStep >= 1} class:complete={currentStep > 1}>1. Get Template</div>
    <div class="step" class:active={currentStep >= 2} class:complete={currentStep > 2}>2. Deploy & Verify</div>
    <div class="step" class:active={currentStep >= 3}>3. Done!</div>
  </div>
  
  {#if error}
    <div class="error-banner">{error}</div>
  {/if}
  
  <!-- Step 1: Get Template -->
  {#if currentStep === 1}
    <div class="step-content">
      <h2>Step 1: Copy the IAM Role Template</h2>
      <p>Choose your preferred Infrastructure-as-Code format:</p>
      
      {#if isLoading}
        <div class="loading">Generating secure credentials...</div>
      {:else}
        <!-- Tab selector -->
        <div class="tab-selector">
          <button 
            class="tab" 
            class:active={selectedTab === 'cloudformation'}
            on:click={() => selectedTab = 'cloudformation'}
          >
            ☁️ CloudFormation
          </button>
          <button 
            class="tab" 
            class:active={selectedTab === 'terraform'}
            on:click={() => selectedTab = 'terraform'}
          >
            🏗️ Terraform
          </button>
        </div>
        
        <!-- External ID display -->
        <div class="info-box">
          <label>🔐 Your External ID (embedded in template)</label>
          <code class="external-id">{externalId}</code>
        </div>
        
        <!-- Template code -->
        <div class="code-container">
          <div class="code-header">
            <span>{selectedTab === 'cloudformation' ? 'cloudsentinel-role.yaml' : 'cloudsentinel-role.tf'}</span>
            <div class="code-actions">
              <button class="icon-btn" on:click={copyTemplate}>
                {copied ? '✅ Copied!' : '📋 Copy'}
              </button>
              <button class="icon-btn" on:click={downloadTemplate}>
                📥 Download
              </button>
            </div>
          </div>
          <pre class="code-block">{selectedTab === 'cloudformation' ? cloudformationYaml : terraformHcl}</pre>
        </div>
        
        <!-- Permissions transparency -->
        <details class="permissions-accordion">
          <summary>🔍 What permissions are we requesting?</summary>
          <ul>
            {#each permissionsSummary as perm}
              <li>{perm}</li>
            {/each}
          </ul>
        </details>
        
        <div class="instructions">
          <h3>📋 Next Steps</h3>
          <ol>
            <li>Copy or download the template above</li>
            <li>Go to <a href="https://console.aws.amazon.com/cloudformation" target="_blank">AWS CloudFormation Console</a></li>
            <li>Create Stack → Upload the template</li>
            <li>Wait for stack creation to complete</li>
            <li>Copy the <strong>RoleArn</strong> from Outputs</li>
          </ol>
        </div>
        
        <button class="primary-btn" on:click={proceedToVerify}>
          I've deployed the stack → Verify Connection
        </button>
      {/if}
    </div>
  {/if}
  
  <!-- Step 2: Verify -->
  {#if currentStep === 2}
    <div class="step-content">
      <h2>Step 2: Verify Your Connection</h2>
      <p>Enter the details from your AWS CloudFormation stack outputs.</p>
      
      <div class="form-group">
        <label for="accountId">AWS Account ID (12 digits)</label>
        <input 
          type="text" 
          id="accountId"
          bind:value={awsAccountId} 
          placeholder="123456789012"
          maxlength="12"
        />
      </div>
      
      <div class="form-group">
        <label for="roleArn">Role ARN (from CloudFormation Outputs)</label>
        <input 
          type="text" 
          id="roleArn"
          bind:value={roleArn} 
          placeholder="arn:aws:iam::123456789012:role/CloudSentinelReadOnly"
        />
      </div>
      
      <button 
        class="primary-btn" 
        on:click={verifyConnection}
        disabled={isVerifying}
      >
        {isVerifying ? '⏳ Verifying...' : '✅ Verify Connection'}
      </button>
      
      <button class="secondary-btn" on:click={() => currentStep = 1}>
        ← Back to Template
      </button>
    </div>
  {/if}
  
  <!-- Step 3: Success -->
  {#if currentStep === 3 && success}
    <div class="step-content success">
      <div class="success-icon">🎉</div>
      <h2>Connection Successful!</h2>
      <p>CloudSentinel can now analyze your AWS costs and help you save money.</p>
      
      <a href="/" class="primary-btn">
        Go to Dashboard →
      </a>
    </div>
  {/if}
</div>

<style>
  .onboarding-container {
    max-width: 800px;
    margin: 2rem auto;
    padding: 2rem;
  }
  
  h1 {
    text-align: center;
    margin-bottom: 2rem;
  }
  
  .progress-steps {
    display: flex;
    justify-content: space-between;
    margin-bottom: 2rem;
  }
  
  .step {
    flex: 1;
    text-align: center;
    padding: 0.75rem;
    background: var(--card-bg, #1a1a2e);
    border-radius: 8px;
    margin: 0 0.25rem;
    color: var(--text-muted, #888);
    font-size: 0.9rem;
  }
  
  .step.active {
    background: var(--primary, #6366f1);
    color: white;
  }
  
  .step.complete {
    background: var(--success, #10b981);
    color: white;
  }
  
  .step-content {
    background: var(--card-bg, #1a1a2e);
    padding: 2rem;
    border-radius: 12px;
  }
  
  .tab-selector {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1.5rem;
  }
  
  .tab {
    flex: 1;
    padding: 0.75rem;
    border: 1px solid var(--border, #333);
    background: transparent;
    color: var(--text-muted, #888);
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .tab.active {
    background: var(--primary, #6366f1);
    border-color: var(--primary, #6366f1);
    color: white;
  }
  
  .info-box {
    background: var(--bg-secondary, #0f0f1a);
    padding: 1rem;
    border-radius: 8px;
    margin: 1rem 0;
  }
  
  .external-id {
    display: block;
    font-size: 0.9rem;
    padding: 0.5rem;
    background: #000;
    border-radius: 4px;
    word-break: break-all;
    margin-top: 0.5rem;
    font-family: monospace;
  }
  
  .code-container {
    border: 1px solid var(--border, #333);
    border-radius: 8px;
    overflow: hidden;
    margin: 1rem 0;
  }
  
  .code-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 1rem;
    background: var(--bg-secondary, #0f0f1a);
    border-bottom: 1px solid var(--border, #333);
  }
  
  .code-actions {
    display: flex;
    gap: 0.5rem;
  }
  
  .icon-btn {
    padding: 0.25rem 0.5rem;
    background: transparent;
    border: 1px solid var(--border, #333);
    border-radius: 4px;
    color: var(--text-muted, #888);
    cursor: pointer;
    font-size: 0.8rem;
  }
  
  .icon-btn:hover {
    background: var(--primary, #6366f1);
    color: white;
  }
  
  .code-block {
    padding: 1rem;
    margin: 0;
    background: #000;
    color: #0f0;
    font-size: 0.75rem;
    line-height: 1.4;
    overflow-x: auto;
    max-height: 300px;
    white-space: pre-wrap;
  }
  
  .permissions-accordion {
    margin: 1rem 0;
    padding: 1rem;
    background: var(--bg-secondary, #0f0f1a);
    border-radius: 8px;
  }
  
  .permissions-accordion summary {
    cursor: pointer;
    font-weight: 500;
  }
  
  .permissions-accordion ul {
    margin-top: 1rem;
    padding-left: 1.5rem;
  }
  
  .permissions-accordion li {
    margin: 0.5rem 0;
    font-size: 0.9rem;
    color: var(--text-muted, #888);
  }
  
  .instructions {
    margin: 1.5rem 0;
    padding: 1rem;
    background: var(--bg-secondary, #0f0f1a);
    border-radius: 8px;
  }
  
  .instructions h3 {
    margin-bottom: 0.5rem;
  }
  
  .instructions ol {
    padding-left: 1.5rem;
  }
  
  .instructions li {
    margin: 0.5rem 0;
  }
  
  .instructions a {
    color: var(--primary, #6366f1);
  }
  
  .form-group {
    margin: 1rem 0;
  }
  
  label {
    display: block;
    margin-bottom: 0.5rem;
    font-weight: 500;
  }
  
  input {
    width: 100%;
    padding: 0.75rem;
    border: 1px solid var(--border, #333);
    border-radius: 8px;
    background: var(--bg-secondary, #0f0f1a);
    color: white;
    font-size: 1rem;
  }
  
  .primary-btn {
    display: inline-block;
    width: 100%;
    padding: 1rem;
    background: var(--primary, #6366f1);
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 1rem;
    cursor: pointer;
    text-align: center;
    text-decoration: none;
    margin-top: 1rem;
  }
  
  .primary-btn:hover {
    opacity: 0.9;
  }
  
  .primary-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .secondary-btn {
    display: block;
    width: 100%;
    padding: 0.75rem;
    background: transparent;
    color: var(--text-muted, #888);
    border: 1px solid var(--border, #333);
    border-radius: 8px;
    margin-top: 0.5rem;
    cursor: pointer;
  }
  
  .error-banner {
    background: #f43f5e22;
    border: 1px solid #f43f5e;
    color: #f43f5e;
    padding: 1rem;
    border-radius: 8px;
    margin-bottom: 1rem;
  }
  
  .success {
    text-align: center;
    padding: 3rem 2rem;
  }
  
  .success-icon {
    font-size: 4rem;
    margin-bottom: 1rem;
  }
  
  .loading {
    text-align: center;
    padding: 2rem;
    color: var(--text-muted, #888);
  }
</style>