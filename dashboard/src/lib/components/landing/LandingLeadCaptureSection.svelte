<script lang="ts">
	let {
		subscribeApiPath,
		startFreeHref,
		resourcesHref,
		onTrackCta
	}: {
		subscribeApiPath: string;
		startFreeHref: string;
		resourcesHref: string;
		onTrackCta: (action: string, section: string, value: string) => void;
	} = $props();

	let email = $state('');
	let company = $state('');
	let role = $state('');
	let honey = $state('');
	let submitting = $state(false);
	let status = $state<'idle' | 'success' | 'error'>('idle');

	async function submitSubscription(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		if (submitting) return;
		submitting = true;
		status = 'idle';
		try {
			const response = await fetch(subscribeApiPath, {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({
					email,
					company,
					role,
					referrer: 'landing_lead_capture',
					honey
				})
			});
			if (!response.ok) {
				throw new Error(`subscribe_${response.status}`);
			}
			status = 'success';
			onTrackCta('cta_click', 'lead_capture', 'newsletter_subscribe_success');
			email = '';
			company = '';
			role = '';
			honey = '';
		} catch {
			status = 'error';
			onTrackCta('cta_click', 'lead_capture', 'newsletter_subscribe_error');
		} finally {
			submitting = false;
		}
	}
</script>

<section
	id="resources"
	class="container mx-auto px-6 pb-16 landing-section-lazy"
	data-landing-section="resources"
>
	<div class="landing-section-head">
		<h2 class="landing-h2">Not ready to sign up today? Stay in the loop.</h2>
		<p class="landing-section-sub">
			Get one concise weekly brief with practical cloud, SaaS, and license optimization guidance.
		</p>
	</div>

	<div class="landing-lead-grid">
		<article class="glass-panel landing-lead-card">
			<p class="landing-proof-k">Weekly Brief</p>
			<h3 class="landing-h3">Get practical playbooks by email</h3>
			<p class="landing-p">
				No spam. Just operating guidance, rollout patterns, and templates you can apply quickly.
			</p>
			<form class="landing-lead-form" onsubmit={submitSubscription}>
				<label class="landing-roi-label" for="lead-email">Work email</label>
				<input
					id="lead-email"
					class="input"
					type="email"
					required
					maxlength="254"
					placeholder="you@company.com"
					bind:value={email}
				/>
				<div class="landing-lead-form-grid">
					<div>
						<label class="landing-roi-label" for="lead-company">Company (optional)</label>
						<input
							id="lead-company"
							class="input"
							type="text"
							maxlength="120"
							placeholder="Acme Inc."
							bind:value={company}
						/>
					</div>
					<div>
						<label class="landing-roi-label" for="lead-role">Role (optional)</label>
						<input
							id="lead-role"
							class="input"
							type="text"
							maxlength="120"
							placeholder="FinOps"
							bind:value={role}
						/>
					</div>
				</div>
				<div class="landing-lead-honey" aria-hidden="true">
					<label for="lead-honey">Leave this field empty</label>
					<input
						id="lead-honey"
						type="text"
						tabindex="-1"
						autocomplete="off"
						bind:value={honey}
					/>
				</div>
				<button class="btn btn-primary" type="submit" disabled={submitting}>
					{submitting ? 'Submitting...' : 'Send Me Weekly Insights'}
				</button>
				{#if status === 'success'}
					<p class="landing-lead-status is-success" role="status">
						Subscribed. Check your inbox for your first brief.
					</p>
				{:else if status === 'error'}
					<p class="landing-lead-status is-error" role="alert">
						Subscription failed. Please retry in a moment.
					</p>
				{/if}
			</form>
		</article>

		<article class="glass-panel landing-lead-card">
			<p class="landing-proof-k">Resource Hub</p>
			<h3 class="landing-h3">Prefer self-serve learning first?</h3>
			<p class="landing-p">
				Explore tactical guides, then start free when you are ready to run your own workflows.
			</p>
			<div class="landing-lead-actions">
				<a
					class="btn btn-secondary"
					href={resourcesHref}
					onclick={() => onTrackCta('cta_click', 'lead_capture', 'open_resources')}
				>
					Open Resources
				</a>
				<a
					class="btn btn-primary"
					href={startFreeHref}
					onclick={() => onTrackCta('cta_click', 'lead_capture', 'start_free_from_resources')}
				>
					Start Free
				</a>
			</div>
		</article>
	</div>
</section>
