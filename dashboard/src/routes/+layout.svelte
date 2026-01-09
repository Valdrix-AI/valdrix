<!--
  Root Layout - Premium SaaS Design (2026)
  
  Features:
  - Collapsible sidebar navigation
  - Clean header with user menu
  - Motion-enhanced page transitions
  - Responsive design
-->

<script lang="ts">
  import '../app.css';
  import { createSupabaseBrowserClient } from '$lib/supabase';
  import { onMount } from 'svelte';
  import { invalidate } from '$app/navigation';
  import { page } from '$app/stores';
  
  export let data;
  
  const supabase = createSupabaseBrowserClient();
  let sidebarOpen = true;
  
  // Navigation items
  const navItems = [
    { href: '/', label: 'Dashboard', icon: '📊' },
    { href: '/llm', label: 'LLM Usage', icon: '🤖' },
    { href: '/onboarding', label: 'AWS Setup', icon: '☁️' },
    { href: '/leaderboards', label: 'Leaderboards', icon: '🏆' },
    { href: '/settings', label: 'Settings', icon: '⚙️' },
  ];
  
  // Check if route is active
  function isActive(href: string): boolean {
    if (href === '/') return $page.url.pathname === '/';
    return $page.url.pathname.startsWith(href);
  }
  
  onMount(() => {
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event) => {
      if (event === 'SIGNED_IN' || event === 'SIGNED_OUT') {
        invalidate('supabase:auth');
      }
    });
    
    return () => subscription.unsubscribe();
  });
</script>

<div class="min-h-screen bg-ink-950 text-ink-100">
  {#if data.user}
    <!-- Sidebar Navigation -->
    <aside class="sidebar" class:sidebar-collapsed={!sidebarOpen}>
      <!-- Logo -->
      <div class="flex items-center gap-3 px-5 py-5 border-b border-ink-800">
        <span class="text-2xl">☁️</span>
        <span class="text-lg font-semibold text-gradient">CloudSentinel</span>
      </div>
      
      <!-- Navigation -->
      <nav class="flex-1 py-4">
        {#each navItems as item}
          <a 
            href={item.href} 
            class="nav-item"
            class:active={isActive(item.href)}
          >
            <span class="text-lg">{item.icon}</span>
            <span>{item.label}</span>
          </a>
        {/each}
      </nav>
      
      <!-- User Section -->
      <div class="border-t border-ink-800 p-4">
        <div class="flex items-center gap-3 mb-3">
          <div class="w-8 h-8 rounded-full bg-accent-500/20 flex items-center justify-center text-accent-400 text-sm font-medium">
            {data.user.email?.charAt(0).toUpperCase()}
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-sm font-medium truncate">{data.user.email}</p>
            <p class="text-xs text-ink-500">Free Plan</p>
          </div>
        </div>
        <form method="POST" action="/auth/logout">
          <button type="submit" class="btn btn-ghost w-full text-left justify-start">
            <span>↩️</span>
            <span>Sign Out</span>
          </button>
        </form>
      </div>
    </aside>
    
    <!-- Main Content -->
    <main class="main-content" class:!ml-0={!sidebarOpen}>
      <!-- Top Bar -->
      <header class="sticky top-0 z-40 bg-ink-900/80 backdrop-blur border-b border-ink-800">
        <div class="flex items-center justify-between px-6 py-3">
          <button 
            type="button"
            class="btn btn-ghost p-2"
            on:click={() => sidebarOpen = !sidebarOpen}
            aria-label="Toggle sidebar"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="3" y1="12" x2="21" y2="12"></line>
              <line x1="3" y1="6" x2="21" y2="6"></line>
              <line x1="3" y1="18" x2="21" y2="18"></line>
            </svg>
          </button>
          
          <div class="flex items-center gap-3">
            <span class="badge badge-accent">Beta</span>
          </div>
        </div>
      </header>
      
      <!-- Page Content -->
      <div class="p-6 page-enter">
        <slot />
      </div>
    </main>
  {:else}
    <!-- Public Layout (Login/Landing) -->
    <header class="border-b border-ink-800 bg-ink-900/50 backdrop-blur sticky top-0 z-50">
      <nav class="container mx-auto flex items-center justify-between px-6 py-4">
        <a href="/" class="flex items-center gap-2">
          <span class="text-2xl">☁️</span>
          <span class="text-xl font-bold text-gradient">CloudSentinel</span>
        </a>
        
        <a href="/auth/login" class="btn btn-primary">
          Sign In
        </a>
      </nav>
    </header>
    
    <main class="page-enter">
      <slot />
    </main>
  {/if}
</div>

<style>
  /* Custom Tailwind classes for this component */
  .bg-ink-950 { background-color: var(--color-ink-950); }
  .bg-ink-900 { background-color: var(--color-ink-900); }
  .border-ink-800 { border-color: var(--color-ink-800); }
  .text-ink-100 { color: var(--color-ink-100); }
  .text-ink-500 { color: var(--color-ink-500); }
  .text-accent-400 { color: var(--color-accent-400); }
  .bg-accent-500\/20 { background-color: rgb(6 182 212 / 0.2); }
</style>
