<script lang="ts">
	import { base } from '$app/paths';
	import { onMount } from 'svelte';
	import AuthGate from '$lib/components/AuthGate.svelte';

	type CustomerCommentStage = 'design_partner' | 'customer';

	type CustomerComment = {
		quote: string;
		attribution: string;
		stage: CustomerCommentStage;
	};

	type CustomerCommentsResponse = {
		ok: boolean;
		items?: CustomerComment[];
		error?: string;
		meta?: {
			total: number;
			hasLiveCustomerEvidence: boolean;
		};
	};

	let { data } = $props();
	const apiPath = `${base}/api/admin/customer-comments`;

	let comments = $state<CustomerComment[]>([]);
	let totalComments = $state(0);
	let hasLiveCustomerEvidence = $state(false);
	let loading = $state(false);
	let saving = $state(false);
	let error = $state('');
	let success = $state('');
	let quote = $state('');
	let attribution = $state('');
	let stage = $state<CustomerCommentStage>('customer');

	async function loadComments(): Promise<void> {
		loading = true;
		error = '';
		try {
			const response = await fetch(apiPath, {
				method: 'GET',
				headers: { accept: 'application/json' }
			});
			const payload = (await response.json().catch(() => ({}))) as CustomerCommentsResponse;
			if (!response.ok || !payload.ok || !payload.items) {
				error = payload.error || `Failed to load customer comments (HTTP ${response.status}).`;
				return;
			}
			comments = payload.items;
			totalComments = payload.meta?.total ?? payload.items.length;
			hasLiveCustomerEvidence = !!payload.meta?.hasLiveCustomerEvidence;
		} catch (exc) {
			error = exc instanceof Error ? exc.message : 'Failed to load customer comments.';
		} finally {
			loading = false;
		}
	}

	async function submit(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		if (!quote.trim() || !attribution.trim()) {
			error = 'Quote and attribution are required.';
			return;
		}

		saving = true;
		error = '';
		success = '';
		try {
			const response = await fetch(apiPath, {
				method: 'POST',
				headers: {
					'content-type': 'application/json',
					accept: 'application/json'
				},
				body: JSON.stringify({
					quote: quote.trim(),
					attribution: attribution.trim(),
					stage
				})
			});
			const payload = (await response.json().catch(() => ({}))) as CustomerCommentsResponse;
			if (!response.ok || !payload.ok || !payload.items) {
				error = payload.error || `Failed to save customer comment (HTTP ${response.status}).`;
				return;
			}
			comments = payload.items;
			totalComments = payload.meta?.total ?? payload.items.length;
			hasLiveCustomerEvidence = !!payload.meta?.hasLiveCustomerEvidence;
			quote = '';
			attribution = '';
			stage = 'customer';
			success = 'Customer comment saved.';
		} catch (exc) {
			error = exc instanceof Error ? exc.message : 'Failed to save customer comment.';
		} finally {
			saving = false;
		}
	}

	onMount(() => {
		if (data.user) {
			void loadComments();
		}
	});
</script>

<AuthGate authenticated={!!data.user} action="manage customer comments">
	<section class="space-y-6">
		<header class="card border border-ink-800">
			<h1 class="text-2xl font-semibold text-ink-100">Customer Comments Feed Admin</h1>
			<p class="mt-2 text-sm text-ink-400">
				Add customer and design-partner quotes used by the public landing page rotator.
			</p>
			<p class="mt-3 text-xs text-ink-500">
				Feed URL: <code>{base}/api/marketing/customer-comments</code>
			</p>
		</header>

		<div class="grid gap-6 lg:grid-cols-2">
			<section class="card border border-ink-800 space-y-4">
				<h2 class="text-lg font-semibold text-ink-100">Add Comment</h2>
				<form class="space-y-4" onsubmit={submit}>
					<div class="space-y-2">
						<label for="comment-quote" class="text-sm font-medium text-ink-300">Quote</label>
						<textarea
							id="comment-quote"
							class="w-full rounded-lg border border-ink-700 bg-ink-900/60 px-3 py-2 text-sm text-ink-100"
							rows="4"
							maxlength="360"
							bind:value={quote}
							placeholder="Example: The control loop removed late-cycle spend surprises."
							required
						></textarea>
					</div>
					<div class="space-y-2">
						<label for="comment-attribution" class="text-sm font-medium text-ink-300"
							>Attribution</label
						>
						<input
							id="comment-attribution"
							type="text"
							class="w-full rounded-lg border border-ink-700 bg-ink-900/60 px-3 py-2 text-sm text-ink-100"
							maxlength="120"
							bind:value={attribution}
							placeholder="Example: CFO, Enterprise SaaS"
							required
						/>
					</div>
					<div class="space-y-2">
						<label for="comment-stage" class="text-sm font-medium text-ink-300"
							>Evidence Stage</label
						>
						<select
							id="comment-stage"
							class="w-full rounded-lg border border-ink-700 bg-ink-900/60 px-3 py-2 text-sm text-ink-100"
							bind:value={stage}
						>
							<option value="customer">Customer</option>
							<option value="design_partner">Design Partner</option>
						</select>
					</div>
					<button type="submit" class="btn btn-primary" disabled={saving}>
						{saving ? 'Saving...' : 'Save Comment'}
					</button>
				</form>
				{#if success}
					<p class="text-sm text-success-400" role="status">{success}</p>
				{/if}
				{#if error}
					<p class="text-sm text-danger-400" role="alert">{error}</p>
				{/if}
			</section>

			<section class="card border border-ink-800 space-y-4">
				<div class="flex items-center justify-between">
					<h2 class="text-lg font-semibold text-ink-100">Current Feed</h2>
					<button
						type="button"
						class="btn btn-secondary"
						onclick={() => void loadComments()}
						disabled={loading}
					>
						{loading ? 'Refreshing...' : 'Refresh'}
					</button>
				</div>
				<p class="text-sm text-ink-400">
					{totalComments} comments in feed
					{#if hasLiveCustomerEvidence}
						· Live customer evidence present
					{:else}
						· Design-partner evidence only
					{/if}
				</p>
				<div class="space-y-3">
					{#each comments as item, index (`${item.quote}-${index}`)}
						<article class="rounded-lg border border-ink-800 bg-ink-950/50 p-3">
							<div class="mb-2 flex items-center justify-between gap-2">
								<span
									class={`inline-flex rounded-full px-2 py-1 text-xs font-semibold ${
										item.stage === 'customer'
											? 'bg-success-500/15 text-success-300 border border-success-500/30'
											: 'bg-accent-500/15 text-accent-300 border border-accent-500/30'
									}`}
								>
									{item.stage === 'customer' ? 'Customer' : 'Design Partner'}
								</span>
							</div>
							<p class="text-sm text-ink-100">"{item.quote}"</p>
							<p class="mt-2 text-xs text-ink-400">{item.attribution}</p>
						</article>
					{/each}
					{#if !loading && comments.length === 0}
						<p class="text-sm text-ink-500">No comments available yet.</p>
					{/if}
				</div>
			</section>
		</div>
	</section>
</AuthGate>
