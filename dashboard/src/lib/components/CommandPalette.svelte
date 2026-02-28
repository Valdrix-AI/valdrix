<script lang="ts">
	/* eslint-disable svelte/no-navigation-without-resolve */
	import { fade, fly } from 'svelte/transition';
	import { base } from '$app/paths';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';

	let { isOpen = $bindable(false) } = $props();
	let query = $state('');
	let selectedIndex = $state(0);
	let searchInput = $state<HTMLInputElement | undefined>(undefined);
	let prefersReducedMotion = $state(false);

	const actions = [
		{ id: 'dash', label: 'Go to Dashboard', icon: '📊', path: '/' },
		{ id: 'ops', label: 'Open Ops Center', icon: '🛠️', path: '/ops' },
		{ id: 'onb', label: 'Open Onboarding', icon: '🧭', path: '/onboarding' },
		{ id: 'audit', label: 'Open Audit Logs', icon: '🧾', path: '/audit' },
		{ id: 'conn', label: 'Manage Cloud Connections', icon: '☁️', path: '/connections' },
		{ id: 'green', label: 'View GreenOps Metrics', icon: '🌱', path: '/greenops' },
		{ id: 'llm', label: 'LLM Usage Tracking', icon: '🤖', path: '/llm' },
		{ id: 'bill', label: 'Billing & Subscriptions', icon: '💳', path: '/billing' },
		{ id: 'trop', label: 'Leaderboards', icon: '🏆', path: '/leaderboards' },
		{ id: 'sett', label: 'Account Settings', icon: '⚙️', path: '/settings' },
		{ id: 'admh', label: 'Admin Health Dashboard', icon: '🩺', path: '/admin/health' }
	];

	function toAppPath(path: string): string {
		const normalizedPath = path.startsWith('/') ? path : `/${path}`;
		const normalizedBase = base === '/' ? '' : base;
		return `${normalizedBase}${normalizedPath}`;
	}

	let filteredActions = $derived(
		actions.filter((a) => a.label.toLowerCase().includes(query.toLowerCase()))
	);

	$effect(() => {
		if (isOpen && searchInput) {
			searchInput.focus();
		}
	});

	$effect(() => {
		if (!isOpen) {
			selectedIndex = 0;
			return;
		}
		if (selectedIndex >= filteredActions.length) {
			selectedIndex = 0;
		}
	});

	$effect(() => {
		query;
		selectedIndex = 0;
	});

	onMount(() => {
		const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
		const syncReducedMotion = () => {
			prefersReducedMotion = mediaQuery.matches;
		};
		syncReducedMotion();
		mediaQuery.addEventListener('change', syncReducedMotion);
		return () => mediaQuery.removeEventListener('change', syncReducedMotion);
	});

	function close() {
		isOpen = false;
		query = '';
	}

	function handleAction(path: string) {
		goto(toAppPath(path));
		close();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') close();
		if (filteredActions.length === 0) return;
		if (e.key === 'ArrowDown') {
			e.preventDefault();
			selectedIndex = (selectedIndex + 1) % filteredActions.length;
		}
		if (e.key === 'ArrowUp') {
			e.preventDefault();
			selectedIndex = (selectedIndex - 1 + filteredActions.length) % filteredActions.length;
		}
		if (e.key === 'Enter') {
			e.preventDefault();
			if (filteredActions[selectedIndex]) {
				handleAction(filteredActions[selectedIndex].path);
			}
		}
	}
</script>

{#if isOpen}
	<div
		class="fixed inset-0 z-[200] flex items-start justify-center pt-[15vh] px-4"
		transition:fade={{ duration: prefersReducedMotion ? 0 : 150 }}
	>
		<!-- Backdrop -->
		<button
			type="button"
			class="absolute inset-0 bg-ink-950/60 backdrop-blur-sm border-0 cursor-default"
			aria-label="Close command palette"
			onclick={close}
		></button>

		<!-- Palette -->
		<div
			class="relative w-full max-w-xl glass-card rounded-xl overflow-hidden shadow-2xl border-white/10"
			transition:fly={{ y: -10, duration: prefersReducedMotion ? 0 : 300 }}
			onkeydown={handleKeydown}
			role="dialog"
			aria-modal="true"
			aria-label="Command palette"
			tabindex="0"
		>
			<div class="flex items-center px-4 py-3 border-b border-white/5">
				<span class="text-xl mr-3">🔍</span>
				<input
					type="text"
					bind:value={query}
					bind:this={searchInput}
					placeholder="Search actions, routes, or documentation..."
					class="w-full bg-transparent border-none outline-none text-ink-50 text-lg placeholder-ink-500"
				/>
				<kbd
					class="ml-3 px-1.5 py-0.5 rounded border border-ink-700 bg-ink-800 text-xs text-ink-400"
					>ESC</kbd
				>
			</div>

			<div class="max-h-[350px] overflow-y-auto p-2">
				{#each filteredActions as action, i (action.path)}
					<button
						type="button"
						class="w-full flex items-center gap-3 px-4 py-3 rounded-lg text-left transition-colors
                        {i === selectedIndex
							? 'bg-accent-500/20 text-accent-400'
							: 'text-ink-300 hover:bg-white/5'}"
						onclick={() => handleAction(action.path)}
						onmouseenter={() => (selectedIndex = i)}
					>
						<span class="text-xl">{action.icon}</span>
						<span class="flex-1 font-medium">{action.label}</span>
						{#if i === selectedIndex}
							<span class="text-xs opacity-60">Enter ↩</span>
						{/if}
					</button>
				{:else}
					<div class="px-4 py-10 text-center text-ink-500">
						<p>No matches found for "{query}"</p>
					</div>
				{/each}
			</div>

			<div
				class="px-4 py-2 bg-ink-950/50 border-t border-white/5 flex items-center justify-between"
			>
				<div
					class="flex items-center gap-4 text-xs text-ink-500 uppercase tracking-widest font-bold"
				>
					<div class="flex items-center gap-1.5">
						<kbd class="px-1 rounded bg-ink-800 border border-ink-700">↑↓</kbd>
						Navigate
					</div>
					<div class="flex items-center gap-1.5">
						<kbd class="px-1 rounded bg-ink-800 border border-ink-700">↵</kbd>
						Select
					</div>
				</div>
				<div class="text-xs text-accent-400/60 font-mono">Valdrics Command Palette</div>
			</div>
		</div>
	</div>
{/if}

<style>
	/* Integration with the global theme tokens */
	input::placeholder {
		color: var(--color-ink-500);
	}
</style>
