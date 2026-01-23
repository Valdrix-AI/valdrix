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
	import { invalidate } from '$app/navigation';
	import { page } from '$app/stores';
	import { uiState } from '$lib/stores/ui.svelte';
	import ToastComponent from '$lib/components/Toast.svelte';
	import CloudLogo from '$lib/components/CloudLogo.svelte';
	import { base } from '$app/paths';

	let { data, children } = $props();

	const supabase = createSupabaseBrowserClient();

	// Navigation items
	const navItems = [
		{ href: '/', label: 'Dashboard', icon: '📊' },
		{ href: '/connections', label: 'Cloud Accounts', icon: '☁️' },
		{ href: '/greenops', label: 'GreenOps', icon: '🌱' },
		{ href: '/llm', label: 'LLM Usage', icon: '🤖' },
		{ href: '/billing', label: 'Billing', icon: '💳' },
		{ href: '/leaderboards', label: 'Leaderboards', icon: '🏆' },
		{ href: '/settings', label: 'Settings', icon: '⚙️' }
	];

	// Check if route is active
	function isActive(href: string): boolean {
		const resolvedHref = `${base}${href}`;
		if (resolvedHref === `${base}/` || resolvedHref === '') {
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
</script>

<div class="min-h-screen bg-ink-950 text-ink-100">
	{#if data.user}
		<!-- Sidebar Navigation -->
		<aside class="sidebar" class:sidebar-collapsed={!uiState.isSidebarOpen}>
			<!-- Logo -->
			<div class="flex items-center gap-3 px-5 py-5 border-b border-ink-800">
				<CloudLogo provider="valdrix" size={32} />
				<span class="text-lg font-semibold text-gradient">Valdrix</span>
			</div>

			<!-- Navigation -->
			<nav class="flex-1 py-4">
				{#each navItems as item (item.href)}
					<a href="{base}{item.href}" class="nav-item" class:active={isActive(item.href)}>
						<span class="text-lg">{item.icon}</span>
						<span>{item.label}</span>
					</a>
				{/each}
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
				<form method="POST" action="/auth/logout">
					<button type="submit" class="btn btn-ghost w-full text-left justify-start">
						<span>↩️</span>
						<span>Sign Out</span>
					</button>
				</form>
			</div>
		</aside>

		<!-- Main Content -->
		<main class="main-content" class:!ml-0={!uiState.isSidebarOpen}>
			<!-- Top Bar -->
			<header class="sticky top-0 z-40 bg-ink-900/80 backdrop-blur border-b border-ink-800">
				<div class="flex items-center justify-between px-6 py-3">
					<button
						type="button"
						class="btn btn-ghost p-2"
						onclick={() => uiState.toggleSidebar()}
						aria-label="Toggle sidebar"
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
						<span class="badge badge-accent">Beta</span>
					</div>
				</div>
			</header>

			<!-- Page Content -->
			<div class="p-6 page-enter">
				{@render children()}
			</div>
		</main>
	{:else}
		<!-- Public Layout (Login/Landing) -->
		<header class="border-b border-ink-800 bg-ink-900/50 backdrop-blur sticky top-0 z-50">
			<nav class="container mx-auto flex items-center justify-between px-6 py-4">
				<a href="{base}/" class="flex items-center gap-2">
					<CloudLogo provider="valdrix" size={32} />
					<span class="text-xl font-bold text-gradient">Valdrix</span>
				</a>

				<a href="{base}/auth/login" class="btn btn-primary"> Sign In </a>
			</nav>
		</header>

		<main class="page-enter">
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
