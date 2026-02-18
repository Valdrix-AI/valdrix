<script lang="ts">
	import { onMount } from 'svelte';

	let { children } = $props();
	let error = $state(null);

	function reset() {
		error = null;
		window.location.reload();
	}

	onMount(() => {
		const handleError = (e: ErrorEvent) => {
			error = e.error || new Error('Unknown error');
			return true; // prevent default browser logging if desired
		};

		window.addEventListener('error', handleError);
		return () => window.removeEventListener('error', handleError);
	});
</script>

{#if error}
	<div
		class="p-8 m-4 bg-red-50 border border-red-200 rounded-lg text-red-900 shadow-sm flex flex-col items-center justify-center text-center"
	>
		<div class="w-12 h-12 mb-4 text-red-500">
			<svg
				xmlns="http://www.w3.org/2000/svg"
				fill="none"
				viewBox="0 0 24 24"
				stroke-width="1.5"
				stroke="currentColor"
			>
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"
				/>
			</svg>
		</div>
		<h2 class="text-xl font-bold mb-2">Something went wrong</h2>
		<p class="text-sm opacity-80 mb-6 max-w-md">
			The dashboard encountered an unexpected error. This has been logged for our engineering team.
		</p>
		<button
			onclick={reset}
			class="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 transition-colors uppercase text-xs font-semibold tracking-wider shadow-sm"
		>
			Restart Dashboard
		</button>
	</div>
{:else}
	{@render children()}
{/if}
