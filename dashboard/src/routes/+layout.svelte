<!--
  Root Layout Component
  
  Wraps all pages. Sets up:
  - Global CSS (Tailwind + shadcn)
  - Supabase client for client-side auth
  - Navigation header
-->

<script lang="ts">
  import '../app.css';
  import { createSupabaseBrowserClient } from '$lib/supabase';
  import { onMount } from 'svelte';
  import { invalidate } from '$app/navigation';
  
  export let data;
  
  // Create browser Supabase client
  const supabase = createSupabaseBrowserClient();
  
  // Listen for auth state changes
  onMount(() => {
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      // Refresh data when auth state changes
      if (event === 'SIGNED_IN' || event === 'SIGNED_OUT') {
        invalidate('supabase:auth');
      }
    });
    
    return () => subscription.unsubscribe();
  });
</script>

<div class="min-h-screen bg-slate-950 text-slate-50">
  <!-- Navigation Header -->
  <header class="border-b border-slate-800 bg-slate-900/50 backdrop-blur">
    <nav class="container mx-auto flex items-center justify-between px-4 py-3">
      <a href="/" class="text-xl font-bold text-emerald-400">
        ☁️ CloudSentinel
      </a>
      
      <div class="flex items-center gap-4">
        {#if data.user}
          <span class="text-sm text-slate-400">{data.user.email}</span>
          <form method="POST" action="/auth/logout">
            <button type="submit" class="rounded bg-slate-800 px-3 py-1.5 text-sm hover:bg-slate-700">
              Logout
            </button>
          </form>
        {:else}
          <a href="/auth/login" class="rounded bg-emerald-600 px-3 py-1.5 text-sm hover:bg-emerald-500">
            Login
          </a>
        {/if}
      </div>
    </nav>
  </header>
  
  <!-- Main Content -->
  <main class="container mx-auto px-4 py-8">
    <slot />
  </main>
</div>
