<script lang="ts">
	import { base } from '$app/paths';

	let {
		visible,
		onAccept,
		onReject,
		onClose
	}: {
		visible: boolean;
		onAccept: () => void;
		onReject: () => void;
		onClose: () => void;
	} = $props();
</script>

{#if visible}
	<div class="landing-cookie-banner" role="dialog" aria-modal="false" aria-labelledby="cookie-consent-title">
		<button
			type="button"
			class="landing-cookie-banner__close"
			aria-label="Close cookie notice"
			onclick={onClose}
		>
			×
		</button>
		<p id="cookie-consent-title" class="landing-proof-k">Cookie preferences</p>
		<p class="landing-p">
			Valdrics uses local storage for analytics and experiment telemetry on this public page.
			You can accept or decline analytics tracking.
		</p>
		<div class="landing-cookie-banner__actions">
			<button type="button" class="btn btn-secondary" onclick={onReject}>Decline analytics</button>
			<button type="button" class="btn btn-primary" onclick={onAccept}>Accept analytics</button>
		</div>
		<p class="landing-cookie-banner__legal">
			Review <a href={`${base}/privacy`}>Privacy</a> and <a href={`${base}/terms`}>Terms</a>.
		</p>
	</div>
{/if}
