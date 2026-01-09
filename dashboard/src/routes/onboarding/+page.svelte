<script lang="ts">
  import { onMount } from 'svelte';
  
  // State management
  let currentStep = 1;
  let externalId = '';
  let cloudformationUrl = '';
  let instructions = '';
  let roleArn = '';
  let awsAccountId = '';
  let isLoading = false;
  let isVerifying = false;
  let error = '';
  let success = false;
  
  const API_URL = 'http://localhost:8002';
  
  // Step 1: Get setup info from backend
  async function getSetupInfo() {
    isLoading = true;
    error = '';
    
    try {
      const res = await fetch(`${API_URL}/connections/aws/setup`, {
        method: 'POST',
      });
      
      if (!res.ok) throw new Error('Failed to get setup info');
      
      const data = await res.json();
      externalId = data.external_id;
      cloudformationUrl = data.cloudformation_url;
      instructions = data.instructions;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Unknown error';
    } finally {
      isLoading = false;
    }
  }
  
  // Step 2: Open CloudFormation in new tab
  function openCloudFormation() {
    window.open(cloudformationUrl, '_blank');
    currentStep = 2;
  }
  
  // Step 3: Verify connection
  async function verifyConnection() {
    if (!roleArn || !awsAccountId) {
      error = 'Please enter both AWS Account ID and Role ARN';
      return;
    }
    
    isVerifying = true;
    error = '';
    
    try {
      // First, create the connection
      const token = localStorage.getItem('sb-access-token'); // Supabase token
      
      const createRes = await fetch(`${API_URL}/connections/aws`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          aws_account_id: awsAccountId,
          role_arn: roleArn,
          region: 'us-east-1',
        }),
      });
      
      if (!createRes.ok) {
        const errData = await createRes.json();
        throw new Error(errData.detail || 'Failed to create connection');
      }
      
      const connection = await createRes.json();
      
      // Then verify it
      const verifyRes = await fetch(`${API_URL}/connections/aws/${connection.id}/verify`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
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
    getSetupInfo();
  });
</script>

<div class="onboarding-container">
  <h1>🔗 Connect Your AWS Account</h1>
  
  <!-- Progress indicator -->
  <div class="progress-steps">
    <div class="step" class:active={currentStep >= 1} class:complete={currentStep > 1}>1. Generate</div>
    <div class="step" class:active={currentStep >= 2} class:complete={currentStep > 2}>2. Deploy</div>
    <div class="step" class:active={currentStep >= 3}>3. Verify</div>
  </div>
  
  {#if error}
    <div class="error-banner">{error}</div>
  {/if}
  
  <!-- Step 1: Generate External ID -->
  {#if currentStep === 1}
    <div class="step-content">
      <h2>Step 1: Deploy IAM Role</h2>
      <p>We'll create a read-only IAM role in your AWS account. This allows CloudSentinel to fetch your cost data.</p>
      
      {#if isLoading}
        <div class="loading">Generating secure credentials...</div>
      {:else}
        <div class="info-box">
          <label>Your External ID (required for security)</label>
          <code class="external-id">{externalId}</code>
        </div>
        
        <button class="primary-btn" on:click={openCloudFormation}>
          🚀 Open AWS CloudFormation
        </button>
        
        <p class="hint">This opens AWS Console to deploy the IAM role. Takes ~2 minutes.</p>
      {/if}
    </div>
  {/if}
  
  <!-- Step 2: Enter Role ARN -->
  {#if currentStep === 2}
    <div class="step-content">
      <h2>Step 2: Enter Your Role ARN</h2>
      <p>After the CloudFormation stack completes, copy the <strong>RoleArn</strong> from the Outputs tab.</p>
      
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
        <label for="roleArn">Role ARN</label>
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
        ← Back
      </button>
    </div>
  {/if}
  
  <!-- Step 3: Success -->
  {#if currentStep === 3 && success}
    <div class="step-content success">
      <h2>🎉 Connection Successful!</h2>
      <p>CloudSentinel can now analyze your AWS costs.</p>
      
      <a href="/" class="primary-btn">
        Go to Dashboard →
      </a>
    </div>
  {/if}
</div>

<style>
  .onboarding-container {
    max-width: 600px;
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
    padding: 0.5rem;
    background: var(--card-bg, #1a1a2e);
    border-radius: 8px;
    margin: 0 0.25rem;
    color: var(--text-muted, #888);
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
  
  .info-box {
    background: var(--bg-secondary, #0f0f1a);
    padding: 1rem;
    border-radius: 8px;
    margin: 1rem 0;
  }
  
  .external-id {
    display: block;
    font-size: 1rem;
    padding: 0.5rem;
    background: #000;
    border-radius: 4px;
    word-break: break-all;
    margin-top: 0.5rem;
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
  
  .hint {
    color: var(--text-muted, #888);
    font-size: 0.9rem;
    margin-top: 0.5rem;
  }
  
  .success {
    text-align: center;
  }
  
  .loading {
    text-align: center;
    padding: 2rem;
    color: var(--text-muted, #888);
  }
</style>