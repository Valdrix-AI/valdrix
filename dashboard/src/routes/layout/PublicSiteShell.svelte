<script lang="ts">
	import type { Snippet } from 'svelte';
	import { base } from '$app/paths';
	import CloudLogo from '$lib/components/CloudLogo.svelte';
	import {
		PUBLIC_CONTACT_CHANNELS,
		PUBLIC_FOOTER_BADGES,
		PUBLIC_FOOTER_CAPTION,
		PUBLIC_FOOTER_LINKS,
		PUBLIC_FOOTER_SUBTITLE,
		PUBLIC_MOBILE_LINKS,
		PUBLIC_PRIMARY_LINKS,
		PUBLIC_RESOURCES_DROPDOWN_LINKS
	} from '$lib/landing/publicNav';
	import './layoutPublicNav.css';

	interface Props {
		currentYear: number;
		toAppPath: (path: string) => string;
		publicMenuOpen: boolean;
		publicMenuPanel: HTMLDivElement | null;
		publicMenuButton: HTMLButtonElement | null;
		publicResourcesMenuOpen: boolean;
		publicResourcesPanel: HTMLDivElement | null;
		publicResourcesButton: HTMLButtonElement | null;
		togglePublicMenu: () => void;
		closePublicMenu: () => void;
		togglePublicResourcesMenu: () => void;
		closePublicResourcesMenu: () => void;
		children: Snippet;
	}

	let {
		currentYear,
		toAppPath,
		publicMenuOpen = $bindable(),
		publicMenuPanel = $bindable(),
		publicMenuButton = $bindable(),
		publicResourcesMenuOpen = $bindable(),
		publicResourcesPanel = $bindable(),
		publicResourcesButton = $bindable(),
		togglePublicMenu,
		closePublicMenu,
		togglePublicResourcesMenu,
		closePublicResourcesMenu,
		children
	}: Props = $props();
</script>

<div class="public-site-shell">
	<header class="public-site-header">
	<nav class="container public-top-nav mx-auto flex items-center justify-between gap-4 px-6 py-4">
		<a href={toAppPath('/')} class="public-brand flex items-center gap-2" aria-label="Valdrics home">
			<CloudLogo provider="valdrics" size={40} emphasizeMark={true} />
			<img
				src={`${base}/valdrics_wordmark.svg`}
				alt=""
				class="public-brand-wordmark hidden sm:block"
				width="155"
				height="45"
			/>
		</a>

		<div class="public-nav-primary items-center gap-5 text-sm">
			{#each PUBLIC_PRIMARY_LINKS as link (link.href)}
				{#if link.href === '/resources'}
					<div class="public-nav-dropdown">
						<button
							type="button"
							class="public-nav-dropdown-trigger public-nav-link"
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
					<a href={toAppPath(link.href)} class="public-nav-link">{link.label}</a>
				{/if}
			{/each}
		</div>

		<div class="public-nav-secondary items-center gap-2">
			<a href={toAppPath('/talk-to-sales')} class="btn btn-secondary text-sm px-4 py-2">
				Talk to Sales
			</a>
			<a href={toAppPath('/auth/login')} class="btn btn-primary text-sm px-4 py-2">Start Free</a>
		</div>

		<div class="public-nav-mobile flex items-center gap-2">
			<a href={toAppPath('/auth/login')} class="btn btn-primary public-nav-mobile-cta">Start Free</a>
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
	</header>

	<main id="main" tabindex="-1" class="page-enter public-site-main">
		{@render children()}
	</main>

	<footer class="public-site-footer">
		<div class="container mx-auto px-6 py-10">
			<div class="flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
				<div class="space-y-2">
					<p class="public-footer-brand text-sm font-semibold">Valdrics</p>
					<p class="public-footer-subtitle max-w-xl">{PUBLIC_FOOTER_SUBTITLE}</p>
				</div>

				<nav class="public-footer-nav grid grid-cols-2 gap-x-6 gap-y-2 md:grid-cols-4" aria-label="Footer">
					{#each PUBLIC_FOOTER_LINKS as link (link.href)}
						{#if link.external}
							<a
								href={link.href}
								target="_blank"
								rel="noopener noreferrer"
								class="public-footer-link"
							>
								{link.label}
							</a>
						{:else}
							<a href={toAppPath(link.href)} class="public-footer-link"
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

			<p class="public-footer-caption mt-4">{PUBLIC_FOOTER_CAPTION}</p>

			<div class="mt-5 space-y-2" aria-label="Public contact channels">
				<p class="public-footer-contact-label">
					Contact Channels
				</p>
				<div class="flex flex-wrap gap-2">
					{#each PUBLIC_CONTACT_CHANNELS as channel (channel.email)}
						<a
							href={channel.href}
							class="badge badge-default public-footer-contact"
							aria-label={`${channel.label} contact ${channel.email}`}
						>
							{channel.label}: {channel.email}
						</a>
					{/each}
				</div>
			</div>
			<p class="public-footer-copyright mt-6">© {currentYear} Valdrics. All rights reserved.</p>
		</div>
	</footer>
</div>
