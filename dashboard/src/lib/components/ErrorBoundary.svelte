<script lang="ts">
	import { onMount } from 'svelte';

	let { children } = $props();
	let error = $state<Error | null>(null);

	function asError(value: unknown): Error {
		if (value instanceof Error) return value;
		if (typeof value === 'string') return new Error(value);
		return new Error('Unknown error');
	}

	function captureError(value: unknown) {
		error = asError(value);
	}

	function reset() {
		error = null;
		window.location.reload();
	}

	onMount(() => {
		const handleWindowError = (event: ErrorEvent) => {
			captureError(event.error ?? event.message);
		};
		const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
			captureError(event.reason);
		};

		window.addEventListener('error', handleWindowError);
		window.addEventListener('unhandledrejection', handleUnhandledRejection);
		return () => {
			window.removeEventListener('error', handleWindowError);
			window.removeEventListener('unhandledrejection', handleUnhandledRejection);
		};
	});
</script>

{#if error}
	<div
		class="p-8 m-4 rounded-lg border text-ink-100 shadow-sm flex flex-col items-center justify-center text-center"
		style="border-color: rgb(244 63 94 / 0.3); background-color: rgb(244 63 94 / 0.1);"
	>
		<div class="w-12 h-12 mb-4 text-danger-400">
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
			class="px-4 py-2 text-white rounded-md transition-colors uppercase text-xs font-semibold tracking-wider shadow-sm"
			style="background-color: var(--color-danger-500);"
		>
			Restart Dashboard
		</button>
	</div>
{:else}
	{@render children()}
{/if}
