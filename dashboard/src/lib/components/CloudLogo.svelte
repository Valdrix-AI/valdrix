<script lang="ts">
	import { base } from '$app/paths';

	export let provider: string = 'aws'; // aws, azure, gcp, valdrics
	export let size: number = 16;
	export let className: string = '';
	export let emphasizeMark: boolean = false;

	$: lowProvider = provider?.toLowerCase() || 'aws';

	const logos: Record<string, string> = {
		aws: `${base}/aws-logo.svg`,
		azure: `${base}/azure-logo.png`,
		gcp: `${base}/gcp.svg`,
		valdrics: `${base}/valdrics_icon.png`
	};
</script>

<div class="inline-flex items-center justify-center {className}">
	{#if logos[lowProvider]}
		<img
			src={logos[lowProvider]}
			alt={lowProvider === 'valdrics' ? 'Valdrics logo' : provider}
			class="object-contain cloud-logo-image"
			class:cloud-logo-image-emphasized={emphasizeMark && lowProvider === 'valdrics'}
			width={size}
			height={size}
		/>
	{:else}
		<!-- Fallback Cloud Icon -->
		<svg
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			stroke-width="2"
			stroke-linecap="round"
			stroke-linejoin="round"
			width={size}
			height={size}
		>
			<path
				d="M17.5 19c2.5 0 4.5-2 4.5-4.5 0-2.3-1.7-4.2-3.9-4.5-.6-3.1-3.3-5.5-6.6-5.5-2.8 0-5.3 1.7-6.2 4.2C3.1 9.4 1 11.5 1 14.3c0 2.6 2.1 4.7 4.7 4.7h11.8z"
			/>
		</svg>
	{/if}
</div>

<style>
	.cloud-logo-image {
		display: block;
	}

	.cloud-logo-image-emphasized {
		transform: scale(1.36);
		transform-origin: center;
	}
</style>
