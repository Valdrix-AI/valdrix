<script lang="ts">
	import { ChevronDown, Check, Globe } from '@lucide/svelte';
	import CloudLogo from './CloudLogo.svelte';
	import { fly } from 'svelte/transition';
	import { onMount } from 'svelte';

	let { selectedProvider = '', onSelect } = $props<{
		selectedProvider?: string;
		onSelect: (provider: string) => void;
	}>();

	let isOpen = $state(false);

	const providers = [
		{ id: '', name: 'All Providers' },
		{ id: 'aws', name: 'AWS' },
		{ id: 'azure', name: 'Azure' },
		{ id: 'gcp', name: 'GCP' }
	];

	let selected = $derived(providers.find((p) => p.id === selectedProvider) || providers[0]);

	function handleSelect(id: string) {
		onSelect(id);
		isOpen = false;
	}

	// Click outside logic
	let componentRef = $state<HTMLElement | null>(null);

	function handleClickOutside(event: MouseEvent) {
		if (componentRef && !componentRef.contains(event.target as Node)) {
			isOpen = false;
		}
	}

	onMount(() => {
		document.addEventListener('click', handleClickOutside);
		return () => document.removeEventListener('click', handleClickOutside);
	});
</script>

<div class="relative inline-block" bind:this={componentRef}>
	<button
		type="button"
		class="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-ink-900 border border-ink-700 hover:border-accent-500/50 hover:bg-ink-800 transition-all active:scale-95 group shadow-sm min-w-[140px] justify-between"
		onclick={() => (isOpen = !isOpen)}
		aria-haspopup="listbox"
		aria-expanded={isOpen}
	>
		<div class="flex items-center gap-2">
			{#if selected.id === ''}
				<Globe size={14} class="text-ink-400 group-hover:text-accent-400 transition-colors" />
			{:else}
				<CloudLogo provider={selected.id} size={14} />
			{/if}
			<span class="text-xs font-semibold text-ink-100 tracking-tight">{selected.name}</span>
		</div>
		<ChevronDown
			size={14}
			class="text-ink-500 transition-transform duration-200 {isOpen ? 'rotate-180' : ''}"
		/>
	</button>

	{#if isOpen}
		<div
			transition:fly={{ y: 8, duration: 200 }}
			class="absolute right-0 mt-2 w-48 py-1.5 z-[100] rounded-xl bg-ink-900/95 backdrop-blur-xl border border-ink-700 shadow-2xl overflow-hidden ring-1 ring-white/5"
			role="listbox"
		>
			{#each providers as p (p.id)}
				<button
					type="button"
					class="w-full flex items-center justify-between px-3 py-2 text-xs transition-all hover:bg-accent-500/10 group"
					onclick={() => handleSelect(p.id)}
					role="option"
					aria-selected={selectedProvider === p.id}
				>
					<div class="flex items-center gap-2.5">
						<div class="w-4 h-4 flex items-center justify-center">
							{#if p.id === ''}
								<Globe
									size={14}
									class={selectedProvider === '' ? 'text-accent-400' : 'text-ink-400'}
								/>
							{:else}
								<CloudLogo provider={p.id} size={14} />
							{/if}
						</div>
						<span
							class={selectedProvider === p.id
								? 'text-accent-400 font-bold'
								: 'text-ink-300 group-hover:text-ink-100'}
						>
							{p.name}
						</span>
					</div>

					{#if selectedProvider === p.id}
						<div transition:fly={{ x: 4, duration: 150 }}>
							<Check size={14} class="text-accent-400" />
						</div>
					{/if}
				</button>
			{/each}
		</div>
	{/if}
</div>

<style>
	/* Premium backdrop shadow */
	.shadow-2xl {
		box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
	}
</style>
