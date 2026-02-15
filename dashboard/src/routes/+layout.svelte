<!--
  Root Layout - Premium SaaS Design (2026)
  
  Features:
  - Collapsible sidebar navigation
  - Clean header with user menu
  - Motion-enhanced page transitions
  - Responsive design
-->

<script lang="ts">
	/* eslint-disable svelte/no-navigation-without-resolve */
	import '../app.css';
	import { createSupabaseBrowserClient } from '$lib/supabase';
	import { invalidate } from '$app/navigation';
	import { page } from '$app/stores';
	import { uiState } from '$lib/stores/ui.svelte';
	import ToastComponent from '$lib/components/Toast.svelte';
	import CloudLogo from '$lib/components/CloudLogo.svelte';
	import { base } from '$app/paths';
	import { fly } from 'svelte/transition';
	import { browser } from '$app/environment';
	import CommandPalette from '$lib/components/CommandPalette.svelte';
	import { jobStore } from '$lib/stores/jobs.svelte';
	import { allowedNavHrefs, isAdminRole, normalizePersona } from '$lib/persona';

	let { data, children } = $props();

	// FE-M9: Command Palette (Cmd+K) Placeholder
	$effect(() => {
		if (!browser) return;
		const handleKeydown = (e: KeyboardEvent) => {
			if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
				e.preventDefault();
				uiState.isCommandPaletteOpen = !uiState.isCommandPaletteOpen;
			}
		};
		window.addEventListener('keydown', handleKeydown);
		return () => window.removeEventListener('keydown', handleKeydown);
	});

	const supabase = createSupabaseBrowserClient();

	type NavItem = { href: string; label: string; icon: string };

	// Full navigation catalogue (filtered by persona + role below)
	const allNavItems: NavItem[] = [
		{ href: '/', label: 'Dashboard', icon: '📊' },
		{ href: '/ops', label: 'Ops Center', icon: '🛠️' },
		{ href: '/onboarding', label: 'Onboarding', icon: '🧭' },
		{ href: '/audit', label: 'Audit Logs', icon: '🧾' },
		{ href: '/connections', label: 'Connections', icon: '☁️' },
		{ href: '/greenops', label: 'GreenOps', icon: '🌱' },
		{ href: '/llm', label: 'LLM Usage', icon: '🤖' },
		{ href: '/billing', label: 'Billing', icon: '💳' },
		{ href: '/leaderboards', label: 'Leaderboards', icon: '🏆' },
		{ href: '/savings', label: 'Savings Proof', icon: '💰' },
		{ href: '/settings', label: 'Settings', icon: '⚙️' },
		{ href: '/admin/health', label: 'Admin Health', icon: '🩺' }
	];

	const NAV_SHOW_ALL_KEY = 'valdrix.nav.show_all.v1';
	let showAllNav = $state(false);
	let navPreferenceLoaded = $state(false);
	let prefersReducedMotion = $state(false);

	$effect(() => {
		if (!browser) return;
		const media = window.matchMedia('(prefers-reduced-motion: reduce)');
		const update = () => {
			prefersReducedMotion = media.matches;
		};
		update();
		media.addEventListener('change', update);
		return () => media.removeEventListener('change', update);
	});

	let persona = $derived(normalizePersona(data.profile?.persona));
	let role = $derived(String(data.profile?.role ?? 'member'));

	$effect(() => {
		if (!browser) return;
		if (navPreferenceLoaded) return;
		const raw = window.localStorage.getItem(NAV_SHOW_ALL_KEY);
		if (raw === null) {
			// Persona-first default: show only role/persona primary nav items.
			showAllNav = false;
		} else {
			showAllNav = raw === '1' || raw.toLowerCase() === 'true';
		}
		navPreferenceLoaded = true;
	});

	$effect(() => {
		if (!browser) return;
		if (!navPreferenceLoaded) return;
		window.localStorage.setItem(NAV_SHOW_ALL_KEY, showAllNav ? '1' : '0');
	});

	let visibleNavItems = $derived(
		(() => {
			if (isAdminRole(role)) return allNavItems;
			return allNavItems.filter((item) => item.href !== '/admin/health');
		})()
	);
	let allowlist = $derived(allowedNavHrefs(persona, role));
	let primaryNavItems = $derived(visibleNavItems.filter((item) => allowlist.has(item.href)));
	let secondaryNavItems = $derived(visibleNavItems.filter((item) => !allowlist.has(item.href)));
	let activeSecondaryNavItems = $derived(
		secondaryNavItems.filter((item) => isActive(item.href))
	);

	function toAppPath(path: string): string {
		const normalizedPath = path.startsWith('/') ? path : `/${path}`;
		const normalizedBase = base === '/' ? '' : base;
		return `${normalizedBase}${normalizedPath}`;
	}

	let canonicalHref = $derived(new URL($page.url.pathname, $page.url.origin).toString());
	let shouldNoIndex = $derived(
		!!data.user ||
			$page.url.pathname === toAppPath('/auth') ||
			$page.url.pathname.startsWith(`${toAppPath('/auth')}/`)
	);

	// Check if route is active
	function isActive(href: string): boolean {
		const resolvedHref = toAppPath(href);
		if (resolvedHref === toAppPath('/')) {
			return $page.url.pathname === (base || '/');
		}
		return $page.url.pathname.startsWith(resolvedHref);
	}

	$effect(() => {
		const {
			data: { subscription }
		} = supabase.auth.onAuthStateChange((event) => {
			if (event === 'SIGNED_IN' || event === 'SIGNED_OUT') {
				invalidate('supabase:auth');
			}
		});

		return () => subscription.unsubscribe();
	});

	$effect(() => {
		if (browser && data.user) {
			jobStore.init();
		} else if (browser && !data.user) {
			jobStore.disconnect();
		}
	});
</script>

<svelte:head>
	<link rel="canonical" href={canonicalHref} />
	<meta name="robots" content={shouldNoIndex ? 'noindex,nofollow' : 'index,follow'} />
</svelte:head>

<div class="min-h-screen bg-ink-950 text-ink-100">
	<a href="#main" class="skip-link">Skip to content</a>
	{#if data.user}
		<!-- Sidebar Navigation -->
		<aside id="sidebar" class="sidebar" class:sidebar-collapsed={!uiState.isSidebarOpen}>
			<!-- Logo -->
			<div class="flex items-center gap-3 px-5 py-5 border-b border-ink-800">
				<CloudLogo provider="valdrix" size={32} />
				<span class="text-lg font-semibold text-gradient">Valdrix</span>
			</div>

			<!-- Navigation -->
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
							<p class="text-[10px] text-ink-500 mb-2">
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

			<!-- User Section -->
			<div class="border-t border-ink-800 p-4">
				<div class="flex items-center gap-3 mb-3">
					<div
						class="w-8 h-8 rounded-full bg-accent-500/20 flex items-center justify-center text-accent-400 text-sm font-medium"
					>
						{data.user.email?.charAt(0).toUpperCase()}
					</div>
					<div class="flex-1 min-w-0">
						<p class="text-sm font-medium truncate">{data.user.email}</p>
						<p class="text-xs text-ink-500 capitalize">{data.subscription?.tier || 'Free'} Plan</p>
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

		<!-- Main Content -->
		<main id="main" tabindex="-1" class="main-content" class:!ml-0={!uiState.isSidebarOpen}>
			<!-- Top Bar -->
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
								<span class="text-[10px] font-bold uppercase tracking-wider text-accent-400">
									{jobStore.activeJobsCount} Active {jobStore.activeJobsCount === 1
										? 'Job'
										: 'Jobs'}
								</span>
							</div>
						{/if}
						<span class="badge badge-accent">Beta</span>
					</div>
				</div>
			</header>

			<!-- Page Content -->
			<div
				class="p-6"
				in:fly={{
					y: 8,
					duration: prefersReducedMotion ? 0 : 400,
					delay: prefersReducedMotion ? 0 : 200
				}}
			>
				{@render children()}
			</div>
		</main>

		<!-- Global Overlays -->
		<CommandPalette bind:isOpen={uiState.isCommandPaletteOpen} />
	{:else}
		<!-- Public Layout (Login/Landing) -->
		<header class="border-b border-ink-800 bg-ink-900/50 backdrop-blur sticky top-0 z-50">
			<nav class="container mx-auto flex items-center justify-between px-6 py-4">
				<a href={toAppPath('/')} class="flex items-center gap-2">
					<CloudLogo provider="valdrix" size={32} />
					<span class="text-xl font-bold text-gradient">Valdrix</span>
				</a>

				<a href={toAppPath('/auth/login')} class="btn btn-primary"> Sign In </a>
			</nav>
		</header>

		<main id="main" tabindex="-1" class="page-enter">
			{@render children()}
		</main>
	{/if}
</div>

<!-- Global Toasts -->
<div class="fixed bottom-6 right-6 z-[100] flex flex-col gap-3 min-w-[320px] max-w-md">
	{#each uiState.toasts as toast (toast.id)}
		<ToastComponent {toast} />
	{/each}
</div>

<style>
	/* Custom Tailwind classes for this component */
	.bg-ink-950 {
		background-color: var(--color-ink-950);
	}
	.border-ink-800 {
		border-color: var(--color-ink-800);
	}
	.text-ink-100 {
		color: var(--color-ink-100);
	}
	.text-ink-500 {
		color: var(--color-ink-500);
	}
	.text-accent-400 {
		color: var(--color-accent-400);
	}
	.bg-accent-500\/20 {
		background-color: rgb(6 182 212 / 0.2);
	}
</style>
