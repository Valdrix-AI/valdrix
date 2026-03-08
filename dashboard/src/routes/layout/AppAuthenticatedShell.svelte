<script lang="ts">
	import type { Snippet } from 'svelte';
	import { uiState } from '$lib/stores/ui.svelte';
	import CloudLogo from '$lib/components/CloudLogo.svelte';
	import CommandPalette from '$lib/components/CommandPalette.svelte';
	import { jobStore } from '$lib/stores/jobs.svelte';
	import ErrorBoundary from '$lib/components/ErrorBoundary.svelte';

	type NavItem = { href: string; label: string; icon: string };

	interface Props {
		user: {
			email?: string | null;
		};
		subscription?: {
			tier?: string | null;
		} | null;
		primaryNavItems: NavItem[];
		secondaryNavItems: NavItem[];
		activeSecondaryNavItems: NavItem[];
		showAllNav: boolean;
		persona: string;
		prefersReducedMotion: boolean;
		toAppPath: (path: string) => string;
		isActive: (href: string) => boolean;
		children: Snippet;
	}

	let {
		user,
		subscription,
		primaryNavItems,
		secondaryNavItems,
		activeSecondaryNavItems,
		showAllNav = $bindable(),
		persona,
		prefersReducedMotion,
		toAppPath,
		isActive,
		children
	}: Props = $props();
</script>

<aside id="sidebar" class="sidebar" class:sidebar-collapsed={!uiState.isSidebarOpen}>
	<div class="flex items-center gap-3 px-5 py-5 border-b border-ink-800">
		<CloudLogo provider="valdrics" size={32} />
		<span class="text-lg font-semibold text-gradient">Valdrics</span>
	</div>

	<nav class="flex-1 py-4 min-h-0 overflow-y-auto">
		{#each primaryNavItems as item (item.href)}
			<a
				href={toAppPath(item.href)}
				class="nav-item"
				class:active={isActive(item.href)}
				aria-current={isActive(item.href) ? 'page' : undefined}
				data-sveltekit-preload-data="hover"
				data-sveltekit-preload-code="hover"
			>
				<span class="text-lg">{item.icon}</span>
				<span>{item.label}</span>
			</a>
		{/each}

		{#if secondaryNavItems.length > 0}
			<div class="px-5 pt-3 pb-2">
				<button
					type="button"
					class="btn btn-ghost w-full justify-start text-xs text-ink-400"
					onclick={() => (showAllNav = !showAllNav)}
					aria-expanded={showAllNav}
					aria-controls="sidebar-more-nav"
					title="Your sidebar is filtered by persona. Toggle to show or hide additional pages."
				>
					<span class="capitalize">
						{showAllNav
							? `Hide extras (back to ${persona} view)`
							: `Show all (${secondaryNavItems.length})`}
					</span>
				</button>
			</div>
			{#if !showAllNav && activeSecondaryNavItems.length > 0}
				<div class="px-5 pb-2">
					<p class="text-xs text-ink-500 mb-2">
						You are viewing a page outside your persona navigation.
					</p>
					{#each activeSecondaryNavItems as item (item.href)}
						<a
							href={toAppPath(item.href)}
							class="nav-item"
							class:active={isActive(item.href)}
							aria-current={isActive(item.href) ? 'page' : undefined}
							data-sveltekit-preload-data="hover"
							data-sveltekit-preload-code="hover"
						>
							<span class="text-lg">{item.icon}</span>
							<span>{item.label}</span>
						</a>
					{/each}
				</div>
			{/if}
			{#if showAllNav}
				<div id="sidebar-more-nav" class="pb-3">
					{#each secondaryNavItems as item (item.href)}
						<a
							href={toAppPath(item.href)}
							class="nav-item"
							class:active={isActive(item.href)}
							aria-current={isActive(item.href) ? 'page' : undefined}
							data-sveltekit-preload-data="hover"
							data-sveltekit-preload-code="hover"
						>
							<span class="text-lg">{item.icon}</span>
							<span>{item.label}</span>
						</a>
					{/each}
				</div>
			{/if}
		{/if}
	</nav>

	<div class="border-t border-ink-800 p-4">
		<div class="flex items-center gap-3 mb-3">
			<div
				class="w-8 h-8 rounded-full bg-accent-500/20 flex items-center justify-center text-accent-400 text-sm font-medium"
			>
				{user.email?.charAt(0).toUpperCase()}
			</div>
			<div class="flex-1 min-w-0">
				<p class="text-sm font-medium truncate">{user.email}</p>
				<p class="text-xs text-ink-500 capitalize">{subscription?.tier || 'Free'} Plan</p>
			</div>
		</div>
		<form method="POST" action={toAppPath('/auth/logout')}>
			<button type="submit" class="btn btn-ghost w-full text-left justify-start">
				<span>↩️</span>
				<span>Sign Out</span>
			</button>
		</form>
	</div>
</aside>

<main id="main" tabindex="-1" class="main-content" class:!ml-0={!uiState.isSidebarOpen}>
	<header class="sticky top-0 z-40 bg-ink-900/80 backdrop-blur border-b border-ink-800">
		<div class="flex items-center justify-between px-6 py-3">
			<button
				type="button"
				class="btn btn-ghost p-2"
				onclick={() => uiState.toggleSidebar()}
				aria-label="Toggle sidebar"
				aria-controls="sidebar"
				aria-expanded={uiState.isSidebarOpen}
			>
				<svg
					xmlns="http://www.w3.org/2000/svg"
					width="20"
					height="20"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="2"
					stroke-linecap="round"
					stroke-linejoin="round"
				>
					<line x1="3" y1="12" x2="21" y2="12"></line>
					<line x1="3" y1="6" x2="21" y2="6"></line>
					<line x1="3" y1="18" x2="21" y2="18"></line>
				</svg>
			</button>

			<div class="flex items-center gap-3">
				<button
					type="button"
					class="hidden md:flex items-center gap-2 text-xs text-ink-500 mr-4 hover:text-ink-300 transition-colors"
					onclick={() => (uiState.isCommandPaletteOpen = true)}
					aria-label="Open command palette"
				>
					<kbd class="px-1.5 py-0.5 rounded border border-ink-700 bg-ink-800">⌘</kbd>
					<kbd class="px-1.5 py-0.5 rounded border border-ink-700 bg-ink-800">K</kbd>
				</button>
				{#if jobStore.activeJobsCount > 0}
					<div
						class="flex items-center gap-2 px-3 py-1 rounded-full bg-accent-500/10 border border-accent-500/20 mr-2"
					>
						<span class="relative flex h-2 w-2">
							<span
								class="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent-400 opacity-75"
							></span>
							<span class="relative inline-flex rounded-full h-2 w-2 bg-accent-500"></span>
						</span>
						<span class="text-xs font-bold uppercase tracking-wider text-accent-400">
							{jobStore.activeJobsCount} Active {jobStore.activeJobsCount === 1 ? 'Job' : 'Jobs'}
						</span>
					</div>
				{/if}
				<span class="badge badge-accent">Beta</span>
			</div>
		</div>
	</header>

	<div class="p-6" class:authenticated-shell-enter={!prefersReducedMotion}>
		<ErrorBoundary>
			{@render children()}
		</ErrorBoundary>
	</div>
</main>

<CommandPalette bind:isOpen={uiState.isCommandPaletteOpen} />

<style>
	.authenticated-shell-enter {
		animation: authenticatedShellEnter 400ms var(--ease-out) 200ms both;
	}

	@keyframes authenticatedShellEnter {
		from {
			opacity: 0;
			transform: translateY(8px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}
</style>
