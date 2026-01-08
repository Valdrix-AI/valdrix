<!--
  Login Page
  
  Supabase Auth UI with email/password login.
  Styled with shadcn-svelte design system.
-->

<script lang="ts">
  import { createSupabaseBrowserClient } from '$lib/supabase';
  import { goto } from '$app/navigation';
  
  let email = '';
  let password = '';
  let loading = false;
  let error = '';
  let mode: 'login' | 'signup' = 'login';
  
  const supabase = createSupabaseBrowserClient();
  
  async function handleSubmit() {
    loading = true;
    error = '';
    
    try {
      if (mode === 'login') {
        const { error: authError } = await supabase.auth.signInWithPassword({
          email,
          password,
        });
        
        if (authError) throw authError;
        goto('/');
      } else {
        const { error: authError } = await supabase.auth.signUp({
          email,
          password,
        });
        
        if (authError) throw authError;
        error = '✅ Check your email for confirmation link!';
      }
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  }
</script>

<svelte:head>
  <title>{mode === 'login' ? 'Login' : 'Sign Up'} | CloudSentinel</title>
</svelte:head>

<div class="flex min-h-[80vh] items-center justify-center">
  <div class="w-full max-w-md rounded-lg border border-slate-800 bg-slate-900 p-8">
    <h1 class="mb-6 text-2xl font-bold text-center">
      {mode === 'login' ? 'Welcome Back' : 'Create Account'}
    </h1>
    
    {#if error}
      <div class="mb-4 rounded bg-red-900/50 p-3 text-sm text-red-200">
        {error}
      </div>
    {/if}
    
    <form on:submit|preventDefault={handleSubmit} class="space-y-4">
      <div>
        <label for="email" class="mb-1 block text-sm text-slate-400">Email</label>
        <input
          id="email"
          type="email"
          bind:value={email}
          required
          class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-white focus:border-emerald-500 focus:outline-none"
          placeholder="you@example.com"
        />
      </div>
      
      <div>
        <label for="password" class="mb-1 block text-sm text-slate-400">Password</label>
        <input
          id="password"
          type="password"
          bind:value={password}
          required
          minlength="6"
          class="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-white focus:border-emerald-500 focus:outline-none"
          placeholder="••••••••"
        />
      </div>
      
      <button
        type="submit"
        disabled={loading}
        class="w-full rounded bg-emerald-600 py-2.5 font-medium hover:bg-emerald-500 disabled:opacity-50"
      >
        {#if loading}
          Loading...
        {:else}
          {mode === 'login' ? 'Sign In' : 'Sign Up'}
        {/if}
      </button>
    </form>
    
    <p class="mt-6 text-center text-sm text-slate-400">
      {#if mode === 'login'}
        Don't have an account?
        <button on:click={() => mode = 'signup'} class="text-emerald-400 hover:underline">
          Sign up
        </button>
      {:else}
        Already have an account?
        <button on:click={() => mode = 'login'} class="text-emerald-400 hover:underline">
          Sign in
        </button>
      {/if}
    </p>
  </div>
</div>
