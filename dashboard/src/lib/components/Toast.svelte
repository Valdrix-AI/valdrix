<script lang="ts">
  import { fade, fly } from 'svelte/transition';
  import { backOut } from 'svelte/easing';
  import { uiState, type Toast } from '$lib/stores/ui.svelte';

  let { toast } = $props<{ toast: Toast }>();

  function getIcon(type: Toast['type']) {
    switch (type) {
      case 'success': return '✅';
      case 'warning': return '⚠️';
      case 'error': return '❌';
      case 'rate-limit': return '⏳';
      default: return 'ℹ️';
    }
  }

  function getColors(type: Toast['type']) {
    switch (type) {
      case 'success': return 'border-emerald-500/50 bg-emerald-500/10 text-emerald-400';
      case 'warning': return 'border-amber-500/50 bg-amber-500/10 text-amber-400';
      case 'error': return 'border-rose-500/50 bg-rose-500/10 text-rose-400';
      case 'rate-limit': return 'border-cyan-500/50 bg-cyan-500/10 text-cyan-400 font-medium';
      default: return 'border-ink-700 bg-ink-800 text-ink-100';
    }
  }
</script>

<div 
  class="flex items-center gap-3 px-4 py-3 rounded-xl border backdrop-blur-md shadow-2xl {getColors(toast.type)}"
  in:fly={{ y: 20, duration: 400, easing: backOut }}
  out:fade={{ duration: 200 }}
>
  <span class="text-lg">{getIcon(toast.type)}</span>
  <p class="text-sm leading-tight flex-1">{toast.message}</p>
  <button 
    class="ml-2 p-1 hover:bg-white/10 rounded-full transition-colors"
    onclick={() => uiState.removeToast(toast.id)}
    aria-label="Dismiss"
  >
    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M18 6 6 18"/><path d="m6 6 12 12"/>
    </svg>
  </button>
</div>
