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
	import { tick } from 'svelte';
	import { uiState } from '$lib/stores/ui.svelte';
	import ToastComponent from '$lib/components/Toast.svelte';
	import CloudLogo from '$lib/components/CloudLogo.svelte';
	import { base } from '$app/paths';
	import { fly } from 'svelte/transition';
	import { browser } from '$app/environment';
	import CommandPalette from '$lib/components/CommandPalette.svelte';
	import { jobStore } from '$lib/stores/jobs.svelte';
	import { allowedNavHrefs, isAdminRole, normalizePersona } from '$lib/persona';
	import ErrorBoundary from '$lib/components/ErrorBoundary.svelte';
	import {
		PUBLIC_CONTACT_CHANNELS,
		PUBLIC_FOOTER_BADGES,
		PUBLIC_FOOTER_CAPTION,
		PUBLIC_FOOTER_LINKS,
		PUBLIC_FOOTER_SUBTITLE,
		PUBLIC_MOBILE_LINKS,
		PUBLIC_PRIMARY_LINKS,
		PUBLIC_RESOURCES_DROPDOWN_LINKS,
		PUBLIC_SIGNAL_STRIP
	} from '$lib/landing/publicNav';
	import {
		getFocusableElements,
		lockBodyScroll,
		resolveNextFocusTarget
	} from '$lib/landing/publicMenuA11y';

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

	const currentYear = new Date().getFullYear();

	type NavItem = { href: string; label: string; icon: string };

	// Full navigation catalogue (filtered by persona + role below)
	const allNavItems: NavItem[] = [
		{ href: '/', label: 'Dashboard', icon: '📊' },
		{ href: '/ops', label: 'Ops Center', icon: '🛠️' },
		{ href: '/onboarding', label: 'Onboarding', icon: '🧭' },
		{ href: '/roi-planner', label: 'ROI Planner', icon: '📈' },
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

	const NAV_SHOW_ALL_KEY = 'valdrics.nav.show_all.v1';
	let showAllNav = $state(false);
	let navPreferenceLoaded = $state(false);
	let prefersReducedMotion = $state(false);
	let publicMenuOpen = $state(false);
	let publicMenuPanel = $state<HTMLDivElement | null>(null);
	let publicMenuButton = $state<HTMLButtonElement | null>(null);
	let publicMenuRestoreFocus = $state<HTMLElement | null>(null);
	let publicResourcesMenuOpen = $state(false);
	let publicResourcesPanel = $state<HTMLDivElement | null>(null);
	let publicResourcesButton = $state<HTMLButtonElement | null>(null);

	$effect(() => {
		if (!browser) return;
		if (typeof window.matchMedia !== 'function') {
			prefersReducedMotion = false;
			return;
		}
		const media = window.matchMedia('(prefers-reduced-motion: reduce)');
		const update = () => {
			prefersReducedMotion = media.matches;
		};
		update();
		if (typeof media.addEventListener === 'function') {
			media.addEventListener('change', update);
			return () => media.removeEventListener('change', update);
		}
		media.addListener(update);
		return () => media.removeListener(update);
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
	let activeSecondaryNavItems = $derived(secondaryNavItems.filter((item) => isActive(item.href)));

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
		if (!browser || !data.user) return;
		const supabase = createSupabaseBrowserClient();
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

	$effect(() => {
		$page.url.pathname;
		publicMenuOpen = false;
		publicResourcesMenuOpen = false;
	});

	$effect(() => {
		if (!browser || !publicMenuOpen) return;

		publicMenuRestoreFocus =
			document.activeElement instanceof HTMLElement ? document.activeElement : null;
		const unlockBodyScroll = lockBodyScroll(document);

		void tick().then(() => {
			const firstFocusable = getFocusableElements(publicMenuPanel)[0];
			firstFocusable?.focus();
		});

		const handleKeydown = (event: KeyboardEvent) => {
			if (event.key === 'Escape') {
				event.preventDefault();
				publicMenuOpen = false;
				return;
			}
			if (event.key !== 'Tab') return;
			const direction = event.shiftKey ? 'backward' : 'forward';
			const activeElement =
				document.activeElement instanceof HTMLElement ? document.activeElement : null;
			const nextTarget = resolveNextFocusTarget(publicMenuPanel, activeElement, direction);
			if (!nextTarget) return;
			event.preventDefault();
			nextTarget.focus();
		};
		const initialScrollY = window.scrollY;
		const handleScroll = () => {
			if (Math.abs(window.scrollY - initialScrollY) > 48) {
				publicMenuOpen = false;
			}
		};
		window.addEventListener('keydown', handleKeydown);
		window.addEventListener('scroll', handleScroll, { passive: true });

		return () => {
			window.removeEventListener('keydown', handleKeydown);
			window.removeEventListener('scroll', handleScroll);
			unlockBodyScroll();
			if (publicMenuRestoreFocus) {
				publicMenuRestoreFocus.focus();
			} else {
				publicMenuButton?.focus();
			}
			publicMenuRestoreFocus = null;
		};
	});

	$effect(() => {
		if (!browser || !publicResourcesMenuOpen) return;

		const handlePointerDown = (event: PointerEvent) => {
			const target = event.target;
			if (!(target instanceof Node)) return;
			if (publicResourcesPanel?.contains(target)) return;
			if (publicResourcesButton?.contains(target)) return;
			publicResourcesMenuOpen = false;
		};

		const handleKeydown = (event: KeyboardEvent) => {
			if (event.key !== 'Escape') return;
			event.preventDefault();
			publicResourcesMenuOpen = false;
			publicResourcesButton?.focus();
		};

		document.addEventListener('pointerdown', handlePointerDown);
		window.addEventListener('keydown', handleKeydown);
		return () => {
			document.removeEventListener('pointerdown', handlePointerDown);
			window.removeEventListener('keydown', handleKeydown);
		};
	});

	function togglePublicMenu(): void {
		publicMenuOpen = !publicMenuOpen;
	}

	function closePublicMenu(): void {
		publicMenuOpen = false;
	}

	function togglePublicResourcesMenu(): void {
		publicResourcesMenuOpen = !publicResourcesMenuOpen;
	}

	function closePublicResourcesMenu(): void {
		publicResourcesMenuOpen = false;
	}
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
				<CloudLogo provider="valdrics" size={32} />
				<span class="text-lg font-semibold text-gradient">Valdrics</span>
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
								<span class="text-xs font-bold uppercase tracking-wider text-accent-400">
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
				<ErrorBoundary>
					{@render children()}
				</ErrorBoundary>
			</div>
		</main>

		<!-- Global Overlays -->
		<CommandPalette bind:isOpen={uiState.isCommandPaletteOpen} />
	{:else}
		<!-- Public Layout (Login/Landing) -->
		<header class="border-b border-ink-800 bg-ink-900/50 backdrop-blur sticky top-0 z-50">
			<nav
				class="container public-top-nav mx-auto flex items-center justify-between gap-4 px-6 py-4"
			>
				<a href={toAppPath('/')} class="flex items-center gap-2">
					<CloudLogo provider="valdrics" size={32} />
					<span class="text-xl font-bold text-gradient hidden sm:inline">Valdrics</span>
				</a>

				<div class="public-nav-primary items-center gap-5 text-sm text-ink-300">
					{#each PUBLIC_PRIMARY_LINKS as link (link.href)}
						{#if link.href === '/resources'}
							<div class="public-nav-dropdown">
								<button
									type="button"
									class="public-nav-dropdown-trigger"
									bind:this={publicResourcesButton}
									aria-haspopup="menu"
									aria-expanded={publicResourcesMenuOpen}
									aria-controls="public-resources-menu"
									onclick={togglePublicResourcesMenu}
								>
									<span>{link.label}</span>
									<svg
										xmlns="http://www.w3.org/2000/svg"
										width="14"
										height="14"
										viewBox="0 0 24 24"
										fill="none"
										stroke="currentColor"
										stroke-width="2"
										stroke-linecap="round"
										stroke-linejoin="round"
										class:rotate-180={publicResourcesMenuOpen}
									>
										<polyline points="6 9 12 15 18 9"></polyline>
									</svg>
								</button>
								{#if publicResourcesMenuOpen}
									<div
										id="public-resources-menu"
										class="public-nav-dropdown-panel"
										role="menu"
										aria-label="Resources"
										bind:this={publicResourcesPanel}
									>
										{#each PUBLIC_RESOURCES_DROPDOWN_LINKS as resourceLink (resourceLink.href)}
											<a
												href={toAppPath(resourceLink.href)}
												role="menuitem"
												class="public-nav-dropdown-item"
												onclick={closePublicResourcesMenu}
											>
												{resourceLink.label}
											</a>
										{/each}
									</div>
								{/if}
							</div>
						{:else}
							<a href={toAppPath(link.href)} class="hover:text-ink-100">{link.label}</a>
						{/if}
					{/each}
				</div>

				<div class="public-nav-secondary items-center gap-2">
					<a href={toAppPath('/talk-to-sales')} class="btn btn-secondary text-sm px-4 py-2">
						Talk to Sales
					</a>
					<a href={toAppPath('/auth/login')} class="btn btn-primary text-sm px-4 py-2">
						Start Free
					</a>
				</div>

				<div class="public-nav-mobile flex items-center gap-2">
					<a href={toAppPath('/auth/login')} class="btn btn-primary public-nav-mobile-cta">
						Start Free
					</a>
					<button
						type="button"
						class="btn btn-ghost p-2 public-nav-menu-toggle"
						bind:this={publicMenuButton}
						aria-label="Toggle menu"
						aria-expanded={publicMenuOpen}
						aria-controls="public-mobile-menu"
						aria-haspopup="dialog"
						onclick={togglePublicMenu}
					>
						{#if publicMenuOpen}
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
								<line x1="18" y1="6" x2="6" y2="18"></line>
								<line x1="6" y1="6" x2="18" y2="18"></line>
							</svg>
						{:else}
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
						{/if}
					</button>
				</div>
			</nav>
			{#if publicMenuOpen}
				<button
					type="button"
					class="fixed inset-0 z-40 bg-ink-950/50 backdrop-blur-[2px] lg:hidden"
					aria-label="Close navigation menu"
					onclick={closePublicMenu}
				></button>
				<div
					id="public-mobile-menu"
					bind:this={publicMenuPanel}
					class="relative z-50 lg:hidden border-t border-ink-800/70 bg-ink-900/95"
					role="dialog"
					aria-modal="true"
					aria-labelledby="public-mobile-menu-title"
				>
					<div class="container mx-auto px-6 py-4">
						<h2 id="public-mobile-menu-title" class="sr-only">Public navigation menu</h2>
						<div class="grid gap-2 text-sm text-ink-200">
							<a
								href={toAppPath('/talk-to-sales')}
								class="btn btn-secondary justify-center mb-1 w-full"
								onclick={closePublicMenu}
							>
								Talk to Sales
							</a>
							<a
								href={toAppPath('/auth/login')}
								class="btn btn-primary justify-center mb-2 w-full"
								onclick={closePublicMenu}
							>
								Start Free
							</a>
							{#each PUBLIC_MOBILE_LINKS as link (link.href)}
								<a
									href={toAppPath(link.href)}
									class="py-3 min-h-11 flex items-center hover:text-ink-100"
									onclick={closePublicMenu}
								>
									{link.label}
								</a>
							{/each}
						</div>
					</div>
				</div>
			{/if}
			<div class="border-t border-ink-800/60 bg-ink-900/65">
				<div
					class="container mx-auto flex flex-wrap items-center gap-x-3 gap-y-1 px-6 py-2 text-xs text-ink-400"
				>
					{#each PUBLIC_SIGNAL_STRIP as message, index (message)}
						<span>{message}</span>
						{#if index < PUBLIC_SIGNAL_STRIP.length - 1}
							<span aria-hidden="true">•</span>
						{/if}
					{/each}
				</div>
			</div>
		</header>

		<main id="main" tabindex="-1" class="page-enter">
			{@render children()}
		</main>

		<footer class="border-t border-ink-800 bg-ink-900/40">
			<div class="container mx-auto px-6 py-10">
				<div class="flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
					<div class="space-y-2">
						<p class="text-sm font-semibold text-ink-100">Valdrics</p>
						<p class="max-w-xl text-sm text-ink-400">{PUBLIC_FOOTER_SUBTITLE}</p>
					</div>

					<nav class="grid grid-cols-2 gap-x-6 gap-y-2 text-sm md:grid-cols-4" aria-label="Footer">
						{#each PUBLIC_FOOTER_LINKS as link (link.href)}
							{#if link.external}
								<a
									href={link.href}
									target="_blank"
									rel="noopener noreferrer"
									class="text-ink-300 hover:text-ink-100"
								>
									{link.label}
								</a>
							{:else}
								<a href={toAppPath(link.href)} class="text-ink-300 hover:text-ink-100"
									>{link.label}</a
								>
							{/if}
						{/each}
					</nav>
				</div>

				<div class="mt-6 flex flex-wrap items-center gap-2" aria-label="Technology badges">
					{#each PUBLIC_FOOTER_BADGES as badge (badge)}
						<span
							class={`badge ${badge === 'Policy-Governed Actions' ? 'badge-success' : 'badge-default'}`}
						>
							{badge}
						</span>
					{/each}
				</div>

					<p class="mt-4 text-sm text-ink-500">{PUBLIC_FOOTER_CAPTION}</p>

					<div class="mt-5 space-y-2" aria-label="Public contact channels">
						<p class="text-xs font-semibold uppercase tracking-[0.12em] text-ink-500">
							Contact Channels
						</p>
						<div class="flex flex-wrap gap-2">
							{#each PUBLIC_CONTACT_CHANNELS as channel (channel.email)}
								<a
									href={channel.href}
									class="badge badge-default text-ink-200 hover:text-ink-100 transition-colors"
									aria-label={`${channel.label} contact ${channel.email}`}
								>
									{channel.label}: {channel.email}
								</a>
							{/each}
						</div>
					</div>

					<p class="mt-6 text-sm text-ink-500">© {currentYear} Valdrics. All rights reserved.</p>
				</div>
		</footer>
	{/if}
</div>

<!-- Global Toasts -->
{#if uiState.toasts.length > 0}
	<div
		class="fixed inset-x-0 bottom-4 z-[100] px-4 sm:inset-x-auto sm:bottom-6 sm:right-6 sm:px-0 sm:max-w-md"
	>
		<div class="flex flex-col gap-3 sm:min-w-[320px]">
			{#each uiState.toasts as toast (toast.id)}
				<ToastComponent {toast} />
			{/each}
		</div>
	</div>
{/if}

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
	.public-top-nav {
		min-width: 0;
	}
	.public-top-nav > a {
		flex-shrink: 0;
	}
	.public-nav-primary,
	.public-nav-secondary {
		display: none;
	}
	.public-nav-dropdown {
		position: relative;
	}
	.public-nav-dropdown-trigger {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		color: var(--color-ink-300);
		transition: color var(--duration-fast) var(--ease-out);
	}
	.public-nav-dropdown-trigger:hover {
		color: var(--color-ink-100);
	}
	.public-nav-dropdown-trigger svg {
		transition: transform var(--duration-fast) var(--ease-out);
	}
	.public-nav-dropdown-panel {
		position: absolute;
		top: calc(100% + 0.65rem);
		left: 0;
		z-index: 80;
		min-width: 12rem;
		padding: 0.45rem;
		border-radius: 0.75rem;
		border: 1px solid rgb(255 255 255 / 0.12);
		background: rgb(7 12 20 / 0.96);
		box-shadow: 0 12px 30px rgb(0 0 0 / 0.45);
		backdrop-filter: blur(10px);
		-webkit-backdrop-filter: blur(10px);
	}
	.public-nav-dropdown-item {
		display: block;
		padding: 0.5rem 0.6rem;
		border-radius: 0.45rem;
		color: var(--color-ink-200);
		transition:
			background-color var(--duration-fast) var(--ease-out),
			color var(--duration-fast) var(--ease-out);
	}
	.public-nav-dropdown-item:hover {
		background: rgb(255 255 255 / 0.08);
		color: var(--color-ink-100);
	}
	.public-nav-dropdown-item:focus-visible,
	.public-nav-dropdown-trigger:focus-visible {
		outline: 2px solid var(--color-accent-500);
		outline-offset: 2px;
		border-radius: 0.45rem;
	}
	.public-nav-mobile {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-left: auto;
		min-width: 0;
	}
	.public-nav-mobile-cta {
		display: none;
		flex-shrink: 0;
	}
	.public-nav-menu-toggle {
		flex-shrink: 0;
	}
	@media (min-width: 640px) {
		.public-nav-mobile-cta {
			display: inline-flex;
		}
	}
	@media (min-width: 1024px) {
		.public-nav-primary,
		.public-nav-secondary {
			display: flex;
		}
		.public-nav-mobile {
			display: none;
		}
	}
</style>
