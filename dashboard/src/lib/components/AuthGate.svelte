<script lang="ts">
	/* eslint-disable svelte/no-navigation-without-resolve */
	import { base } from '$app/paths';
	import type { Snippet } from 'svelte';

	let {
		authenticated,
		action = 'continue',
		className = 'card text-center py-12',
		children
	}: {
		authenticated: boolean;
		action?: string;
		className?: string;
		children?: Snippet;
	} = $props();
</script>

{#if authenticated}
	{@render children?.()}
{:else}
	<div class={className}>
		<p class="text-ink-400">
			Please <a href={`${base}/auth/login`} class="text-accent-400 hover:underline">sign in</a> to {action}.
		</p>
	</div>
{/if}
