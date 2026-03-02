<script lang="ts">
	import { onMount } from 'svelte';

	let {
		startFreeHref,
		resourcesHref,
		subscribeApiPath,
		onTrackCta
	}: {
		startFreeHref: string;
		resourcesHref: string;
		subscribeApiPath: string;
		onTrackCta: (action: string, section: string, value: string) => void;
	} = $props();

	const DISMISS_KEY = 'valdrics.landing.exit_prompt.dismissed.v1';

	let open = $state(false);
	let email = $state('');
	let submitting = $state(false);
	let status = $state<'idle' | 'success' | 'error'>('idle');

	function dismiss(): void {
		open = false;
		if (typeof window !== 'undefined') {
			window.localStorage.setItem(DISMISS_KEY, '1');
		}
	}

	async function submit(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		if (submitting || !email.trim()) return;
		submitting = true;
		status = 'idle';
		try {
			const response = await fetch(subscribeApiPath, {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({
					email,
					referrer: 'landing_exit_prompt',
					honey: ''
				})
			});
			if (!response.ok) {
				throw new Error(`subscribe_${response.status}`);
			}
			status = 'success';
			onTrackCta('cta_click', 'exit_prompt', 'newsletter_subscribe_success');
		} catch {
			status = 'error';
		} finally {
			submitting = false;
		}
	}

	onMount(() => {
		if (typeof window === 'undefined') return;
		if (typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 1023px)').matches)
			return;
		if (window.localStorage.getItem(DISMISS_KEY) === '1') return;

		const handleMouseOut = (event: MouseEvent) => {
			if (open) return;
			if (event.relatedTarget !== null) return;
			if (event.clientY > 10) return;
			open = true;
			onTrackCta('cta_view', 'exit_prompt', 'desktop_exit_intent');
		};

		window.addEventListener('mouseout', handleMouseOut);
		return () => window.removeEventListener('mouseout', handleMouseOut);
	});
</script>

{#if open}
	<div class="landing-exit-prompt" role="dialog" aria-modal="true" aria-labelledby="exit-prompt-title">
		<button
			type="button"
			class="landing-exit-backdrop"
			aria-label="Dismiss backdrop"
			onclick={dismiss}
		></button>
		<div class="landing-exit-panel">
			<button type="button" class="landing-exit-close" onclick={dismiss} aria-label="Close prompt">
				×
			</button>
			<p class="landing-proof-k">Before you go</p>
			<h2 id="exit-prompt-title" class="landing-h3">Want a weekly spend-control brief instead?</h2>
			<p class="landing-p">
				Get concise cloud and software optimization insights, then start free when your team is ready.
			</p>
			<form class="landing-exit-form" onsubmit={submit}>
				<label class="landing-roi-label" for="exit-email">Work email</label>
				<input
					id="exit-email"
					type="email"
					class="input"
					placeholder="you@company.com"
					required
					maxlength="254"
					bind:value={email}
				/>
				<button type="submit" class="btn btn-primary" disabled={submitting}>
					{submitting ? 'Submitting...' : 'Send Insights'}
				</button>
			</form>
			{#if status === 'success'}
				<p class="landing-lead-status is-success" role="status">Subscribed. Check your inbox.</p>
			{:else if status === 'error'}
				<p class="landing-lead-status is-error" role="alert">
					Subscription failed. You can still use the links below.
				</p>
			{/if}
			<div class="landing-exit-actions">
				<a
					href={resourcesHref}
					class="btn btn-secondary"
					onclick={() => onTrackCta('cta_click', 'exit_prompt', 'open_resources')}
				>
					Open Resources
				</a>
				<a
					href={startFreeHref}
					class="btn btn-primary"
					onclick={() => onTrackCta('cta_click', 'exit_prompt', 'start_free')}
				>
					Start Free
				</a>
			</div>
		</div>
	</div>
{/if}
